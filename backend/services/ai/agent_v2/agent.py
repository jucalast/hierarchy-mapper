"""
Agente V2 — native tool calling via Anthropic API.

Protocolo de eventos emitidos (NDJSON):
  {"type": "thinking", "content": "..."}
  {"type": "tool_call",    "call_id": "...", "tool": "...", "args": {...}, "label": "..."}
  {"type": "tool_result",  "call_id": "...", "tool": "...", "summary": "...", "ok": bool}
  {"type": "confirmation_required", "action_id": "...", "tool": "...", "label": "...", "args": {...}, "preview": "..."}
  {"type": "final",   "response": "..."}
  {"type": "error",   "content": "..."}
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List

from services.ai.agent_v2.tools import TOOLS, execute_write_tool, get_tools_anthropic_schema
from services.ai.agent_v2.email_context_extractor import extract_email_narrative, extract_thread_summary
from core.logging_config import get_logger

log = get_logger(__name__)

# Pending write actions aguardando confirmação { action_id -> {...} }
_PENDING: Dict[str, Dict[str, Any]] = {}

MAX_ITERATIONS = 20

# Prompt para modelos potentes (Claude, Gemini, Llama 70b+)
SYSTEM_PROMPT_POWERFUL = f"""Data de Referência: {datetime.now().strftime('%Y-%m-%d')}
Você é o Agente de Investigação Comercial LinkB2B — um investigador que pensa em voz alta, age passo a passo e adapta o plano conforme o que vai encontrando.

## REGRA ABSOLUTA: UMA FERRAMENTA POR TURNO

Nunca chame mais de uma ferramenta por resposta. Sempre.

---

## COMO AGIR EM CADA TURNO

**ANTES de chamar a ferramenta** — escreva em linguagem natural:
- Qual é o objetivo do usuário (referencie sempre)
- O que você vai buscar agora e por quê é o próximo passo lógico
- O que você espera encontrar

**DEPOIS de receber o resultado** (turno seguinte) — escreva:
- O que você encontrou, com interpretação ("interessante, o último contato foi em X — isso pode indicar Y")
- Como isso confirma, refuta ou muda o que você sabia
- Decisão adaptativa: o que isso te leva a fazer AGORA (pode ser diferente do plano inicial)

**ADAPTAÇÃO DE SEQUÊNCIA:**
- Se um resultado muda significativamente o contexto, adapte a ordem das próximas ferramentas
- Exemplo: "Como encontrei 0 contatos no Pipedrive, vou pular a análise de contatos individuais e ir direto para busca por empresa"
- Exemplo: "Como as tarefas mostram que tudo está atualizado, vou focar em verificar se há comunicações recentes fora do CRM"
- NUNCA pule o Bloco 1 (Pipedrive) completamente — ele é a base, mas pode adaptar a ordem dentro dele se justificado

---

## SEQUÊNCIA DE INVESTIGAÇÃO — uma ferramenta por vez:

### BLOCO 1 — PIPEDRIVE (passos 1-4 são INVIOLÁVEIS, execute todos antes de qualquer WhatsApp/Email):

**PASSO 1:** `pipedrive_get_org` — visão geral
**PASSO 2:** `pipedrive_get_persons` — todos os contatos da empresa
**PASSO 3:** `pipedrive_get_deals` — funil, valor, etapa, e qual contato está atrelado ao deal
**PASSO 4:** `pipedrive_get_activities` — tarefas pendentes e histórico de ações

Só avance para o Bloco 2 após ter executado os 4 passos acima. Sem exceção.

**SE O PASSO 2 RETORNAR 0 CONTATOS:** NÃO finalize. Pule o Bloco 2 e vá DIRETO para o Bloco 3 — a busca por empresa via WhatsApp e email é OBRIGATÓRIA mesmo sem contatos cadastrados. Pode haver histórico de comunicação com o domínio da empresa mesmo que não exista nenhuma pessoa no Pipedrive.

---

### BLOCO 2 — COMUNICAÇÃO (após ter o mapa completo do Pipedrive):

**PASSO CRÍTICO: ANALISE AS TAREFAS ANTES DE MONTAR A FILA**

Antes de decidir quem investigar primeiro, examine `pipedrive_get_activities`:
- Se uma tarefa diz "fale com X" ou "aguardando retorno de X": X tem PRIORIDADE MÁXIMA
- Se uma tarefa indica que o contato A indicou o contato B: investige B antes de A
- Se uma tarefa mostra que o contato já foi abordado: pode ser menos prioritário
- Se não há tarefas específicas: use a regra padrão abaixo

**Monte sua fila de investigação com base no que as tarefas indicam:**
1. Contatos mencionados em tarefas pendentes/ativas (prioridade máxima)
2. O contato diretamente atrelado ao deal (campo "pessoa" do negócio)
3. Os demais contatos da organização no Pipedrive

**Exemplo de raciocínio:**
- "A tarefa diz 'aguardando retorno da Kamila sobre aprovação' → Kamila vem primeiro"
- "A tarefa mostra que Wesley indicou falar com Pedro → vou investigar Pedro antes de Wesley"
- "Não há tarefas específicas → começo pelo contato do deal"

**Para cada pessoa da fila (um por vez):**
- `whatsapp_get_messages` com o NOME DA PESSOA — NUNCA use whatsapp_list_chats
- `email_get_contact_history` com o NOME DA PESSOA — NUNCA use email_get_inbox

**REGRA CRÍTICA SOBRE EMAIL:**
- NUNCA use `email_get_inbox` quando você já tem o nome do contato
- `email_get_inbox` é APENAS para ver os últimos emails da caixa de entrada geral sem filtro
- Sempre use `email_get_contact_history` quando souber o nome da pessoa ou da empresa
- Se `email_get_contact_history` falhar, tente usar o nome da organização (org_name) como parâmetro

**Ao ler cada conversa — ative o RADAR DE NOMES:**
Se aparecer qualquer nome novo ("fale com a Kamila", "o João aprova", "o diretor Pedro decidiu"):
- Adicione esse nome à fila AGORA
- Busque essa pessoa mesmo que não exista no Pipedrive
- Isso se aplica a QUALQUER nome mencionado, inclusive os que parecem ser do operador do sistema

---

### BLOCO 3 — BUSCA POR EMPRESA (OBRIGATÓRIO ANTES DE FINALIZAR):

Após esgotar todos os contatos (cadastrados + encontrados nas conversas), ou se não houver nenhum contato:
- PASSO 5: `whatsapp_get_messages` com o nome da organização
- PASSO 6: `email_get_contact_history` com o nome da organização

REGRA DE OURO: Você ESTÁ PROIBIDO de chamar `generate_dossier` sem antes ter executado a busca por WhatsApp e E-mail com o nome da organização. Isso garante que não perderemos comunicações antigas atreladas apenas ao domínio da empresa.

---

### BLOCO 4 — CONSOLIDAÇÃO:

`generate_dossier` → depois escreva o dossiê final

---

## INTELIGÊNCIA DE INVESTIGAÇÃO

- **Se um contato disse "fale com X"**: X entra na fila antes dos outros contatos restantes
- **Se o Pipedrive tem 1 contato mas emails mencionam 3 nomes**: investigue os 3
- **Se uma conversa tem 0 mensagens**: registre "sem histórico" e passe para o próximo
- **Ao narrar emails**: cite quem disse o quê com datas ("Em 15/02, João disse que precisa aprovar as especificações. Em 18/02, Wesley respondeu enviando as especificações. Em 20/02, você respondeu que vai analisar e retorna até quarta")
- **Ao narrar**: cite fatos reais ("o último email foi em março falando sobre embalagens, o que indica interesse mas sem avanço") — não generalize

---

## CROSS-VALIDAÇÃO DE DADOS (CONEXÃO ENTRE FONTES)

**APÓS cada busca de comunicação (WhatsApp/Email), compare com o Pipedrive:**

- **Data de último contato:** Se o WhatsApp mostra última mensagem em março mas o Pipedrive diz "último contato em janeiro", comente a discrepância
- **Status de tarefas:** Se o Pipedrive tem tarefa "aguardando reunião" mas o histórico mostra que a reunião já foi marcada, o Pipedrive está desatualizado
- **Decisores mencionados:** Se emails mencionam "o diretor Pedro aprovou" mas Pedro não está nos contatos do Pipedrive, registre essa lacuna
- **Consistência de informações:** Se o Pipedrive diz "deal em negociação" mas as conversas mostram que o cliente recusou, aponte a contradição

**Exemplos de conexão entre fontes:**
- "O Pipedrive mostra tarefa pendente de marcar reunião, e pelo WhatsApp vejo que o João já enviou mensagem propondo data — está consistente"
- "Curioso, o Pipedrive diz que o último contato foi em janeiro, mas o email mostra troca em março — o Pipedrive pode estar desatualizado"
- "Pelo histórico, o João enviou email e WhatsApp para o contato e está pendente de marcar reunião exatamente como registrado no Pipedrive"

**Ao narrar o raciocínio, SEMPRE conecte:**
- "O que o Pipedrive mostra" + "O que o WhatsApp/Email mostra" + "Conclusão sobre consistência"

---

## CALIBRAÇÃO DA RESPOSTA FINAL

Antes de responder, identifique o tipo de pergunta do usuário:

- **"como está o andamento?" / "qual o status?"** → resposta factual de status. NÃO sugira ações proativamente. Ao final, mencione discretamente: "Se quiser, posso criar tarefas, rascunhar um email ou mensagem para retomar o contato."
- **"o que eu devo fazer?" / "próximos passos?"** → sugira ações concretas com base nos dados.
- **"me manda um email / mensagem"** → use as ferramentas de escrita.

---

## REGRAS ABSOLUTAS:
- **UMA FERRAMENTA POR TURNO**: nunca emita mais de um tool_use na mesma resposta
- **SEM PERMISSÕES**: nunca diga "Você gostaria de...", "Posso verificar?", "Deseja continuar?" — apenas execute
- **SEMPRE REFERENCIE O OBJETIVO**: cada ação deve ser conectada ao que o usuário pediu
- **FUZZY SEARCH**: se o nome completo falhar, tente parcial, sem sufixo ("do Brasil"), ou domínio do email
- **CITE FONTES**: todo fato deve ter origem (Pipedrive, WhatsApp, Email + data)
- **NÃO FINALIZE CEDO**: só conclua após esgotar todos os contatos e a busca por empresa
- **EVITE CONTAMINAÇÃO DE EXEMPLOS**: Os nomes de pessoas e empresas usados nesta instrução (como "Wesley Pinheiro", "Kamila", "Pedro", "Bottcher do Brasil", "João Moura") são APENAS exemplos ilustrativos. NUNCA use esses nomes ou os dados deles se eles não aparecerem nos dados REAIS fornecidos pelo banco de dados ou pelas ferramentas de busca atuais do negócio sob investigação. Se não houver contatos cadastrados ou identificados no caso real, relate claramente que não há contatos cadastrados ou identificados, em vez de inventar ou copiar nomes fictícios.

---

## FORMATO DO DOSSIÊ FINAL:

REGRA ABSOLUTA: **Escreva em PARÁGRAFOS CORRIDOS, sem usar NENHUM bullet point, NENHUMA lista numerada, NENHUM tópico e NENHUM emoji.** 

Sua resposta final deve ser um texto fluido, como uma redação ou e-mail executivo. O texto deve fluir naturalmente contando a seguinte história:
- Comece narrando o contexto da empresa, do negócio, valor e em que estágio está no Pipedrive.
- Incorpore na narrativa quem são os contatos e com quem estamos falando.
- Descreva detalhadamente o que você encontrou no WhatsApp e no E-mail (mencione os assuntos dos e-mails, as datas e os temas discutidos, não omita esses dados valiosos).
- Narre como estão as tarefas e atividades atuais.
- Termine o texto com uma conclusão e a sugestão do próximo passo lógico.

**Exemplo de narrativa:**
"A Bottcher do Brasil tem um deal aberto no valor de R$0, ainda sem valor definido. O contato principal é Wesley Pinheiro, que está atrelado ao negócio. Pelo histórico de emails, houve 6 trocas de mensagens, sendo a última em 15 de março de 2026 sobre homologação de embalagens. Wesley está aguardando retorno sobre especificações técnicas para prosseguir. Não há histórico de mensagens no WhatsApp. O Pipedrive mostra 2 atividades pendentes: agendar reunião com Wesley e enviar proposta técnica. Curiosamente, o Pipedrive indica último contato em janeiro, mas os emails mostram interação em março, o que sugere que o CRM pode estar desatualizado. A situação atual é que o negócio está parado aguardando retorno de Wesley sobre as especificações para então agendar a reunião de homologação."

**Regras:**
- NÃO use bullets (•)
- NÃO use emojis (📋, 📊, 💬, etc.)
- NÃO use linhas separadoras (━━━)
- Escreva em parágrafos corridos
- Cite datas e fontes (Pipedrive, WhatsApp, Email)
- Ao final, se a pergunta foi sobre status: "Se quiser, posso criar tarefas, email ou mensagem para retomar o contato."
- Se a pergunta foi sobre ação: sugira a próxima ação concreta baseada nos dados
"""

# Prompt para modelos básicos (Llama 8b, etc)
SYSTEM_PROMPT_BASIC = f"""Data de Referência: {datetime.now().strftime('%Y-%m-%d')}
Você é um INVESTIGADOR COMERCIAL. Regras ABSOLUTAS:

## REGRA PRINCIPAL: CHAME APENAS UMA FERRAMENTA POR RESPOSTA.

Nunca chame múltiplas ferramentas ao mesmo tempo. Sempre explique o que está fazendo antes de chamar.

## SEQUÊNCIA (uma ferramenta por vez — BLOCOS INVIOLÁVEIS):

BLOCO 1 — execute todos antes de qualquer WhatsApp/Email:
1. `pipedrive_get_org`
2. `pipedrive_get_persons`
3. `pipedrive_get_deals`
4. `pipedrive_get_activities`

BLOCO 2 — comunicação (comece pelo contato do deal, depois os demais):
5. `whatsapp_get_messages` com NOME DA PESSOA
6. `email_get_contact_history` com NOME DA PESSOA
→ Ao ler: se aparecer nome novo ("fale com X", "aprovação de Y"), adicione à fila e busque também — mesmo fora do Pipedrive
→ SE O PASSO 2 RETORNAR 0 CONTATOS: pule o Bloco 2 e vá DIRETO para o Bloco 3. NÃO finalize sem buscar por empresa.

BLOCO 3 — busca por empresa (OBRIGATÓRIO ANTES DE FINALIZAR):
7. `whatsapp_get_messages` com nome da organização
8. `email_get_contact_history` com nome da organização
→ NUNCA chame generate_dossier sem ter feito os passos 7 e 8.

BLOCO 4:
9. `generate_dossier` → relatório final

REGRAS DO RELATÓRIO FINAL:
- Escreva em texto corrido (parágrafos).
- PROIBIDO usar bullets, números, listas, tópicos ou emojis.
- Descreva TUDO o que achou nas comunicações de forma narrativa fluida.

REGRAS:
- NUNCA use whatsapp_list_chats ou email_get_inbox quando já tem o nome da pessoa
- NUNCA pule os passos 1-4 para ir direto ao WhatsApp/Email
- PROIBIDO mais de 1 ferramenta por resposta
- PROIBIDO pedir permissão
- Pergunta de "status" → só descreva, não sugira ações
"""

SYSTEM_PROMPT_DIRECT = f"""Data de Referência: {datetime.now().strftime('%Y-%m-%d')}
Você está em MODO DE EXECUÇÃO DIRETA. O usuário aprovou uma ação específica gerada pela investigação anterior.

REGRA ABSOLUTA: Execute APENAS a ferramenta indicada na instrução do usuário, com os parâmetros fornecidos.
- Se precisar de um ID não fornecido, use UMA ferramenta de leitura mínima para obtê-lo.
- Após executar, confirme o resultado brevemente.
- PROIBIDO: iniciar investigação completa, chamar pipedrive_get_org sem necessidade, generate_dossier, suggest_next_actions.
"""


# ── Sanitização de Dados ───────────────────────────────────────────────────

def _sanitize_email(data: dict) -> str:
    """Compacta e-mails em formato narrativo denso com extração de decisores.
    Usa sempre o módulo email_context_extractor para narrativa detalhada."""
    if not data or not isinstance(data, dict): return str(data)
    emails = data.get("emails", [])
    if not emails: return "📧 Nenhum e-mail encontrado."

    contact_name = data.get("contact", "")
    
    try:
        narrative = extract_thread_summary(emails, contact_name)
        header = f"📧 E-mails com {contact_name or 'o contato'} ({len(emails)} e-mails):\n"
        narrative = header + narrative
        entry_ids = [e.get("entryId", "") for e in emails[:5] if e.get("entryId")]
        if entry_ids:
            narrative += f"\n[EntryIDs para email_reply: {', '.join(entry_ids[:3])}]"
        return narrative
    except Exception as e:
        # Fallback para formato original apenas em caso de erro real
        lines = [f"📧 HISTÓRICO EMAIL ({data.get('count', 0)} msgs):"]
        for e in emails[:8]:
            body = e.get("preview", "").replace("\n", " ").strip()
            from_addr = e.get("from", "")
            # Extrai nome e domínio para fuzzy search
            name_part = from_addr.split("<")[0].strip() if "<" in from_addr else from_addr
            domain = from_addr.split("@")[-1].split(">")[0] if "@" in from_addr else ""

            subject = e.get("subject", "(sem assunto)")
            date = e.get("date", "")
            body_summary = body[:180] if body else ""

            lines.append(f"  [{date}] {name_part}: '{subject}' | {body_summary}")
            if domain and domain not in ["gmail.com", "hotmail.com", "outlook.com"]:
                lines.append(f"    → Domínio empresarial: {domain}")

        # Detecta pessoas mencionadas para name radar
        all_text = " ".join([e.get("preview", "") for e in emails[:5]])
        mentioned = _extract_names_from_text(all_text)
        if mentioned:
            lines.append(f"  👤 Decisores mencionados: {', '.join(mentioned[:5])}")

        return "\n".join(lines)


def _extract_names_from_text(text: str) -> list:
    """Extrai nomes próprios mencionados no texto (simples heurística)."""
    import re
    if not text: return []

    # Padrões comuns: "O [Nome] vai", "Fale com [Nome]", "[Nome] disse"
    patterns = [
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+',  # Nome próprio (2+ palavras capitalizadas)
        r'(?:o|a|com|para)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',  # "o João", "com a Kamila"
    ]

    found = set()
    for p in patterns:
        matches = re.findall(p, text, re.IGNORECASE)
        for m in matches:
            name = m[0] if isinstance(m, tuple) else m
            name = name.strip()
            # Filtra palavras comuns que não são nomes
            if name and len(name) > 3 and name.lower() not in ['para', 'como', 'esta', 'esse', 'essa', 'quem', 'onde', 'quando', 'porque']:
                found.add(name)

    return list(found)[:10]  # Limita para não poluir

def _sanitize_pipedrive(data: dict) -> str:
    """Converte dados do Pipedrive em dossiê executivo compacto."""
    if not data or not isinstance(data, dict): return str(data)

    # Caso seja lista de organizações
    if "organizations" in data:
        orgs = data["organizations"][:10]
        if not orgs: return "📊 Nenhuma empresa encontrada."
        return "📊 Empresas: " + " | ".join([f"{o['name']} (ID:{o['id']})" for o in orgs])

    # Caso seja detalhe de uma organização/deal
    sections = []

    _org_field = data.get("org")
    org_name = data.get("name", "") or (
        _org_field.get("name", "") if isinstance(_org_field, dict) else str(_org_field or "")
    )
    if org_name:
        sections.append(f"🏢 ORG: {org_name}")

    # Deals estruturados
    if "deals" in data and data["deals"]:
        deals_lines = ["💼 DEALS:"]
        for d in data["deals"][:5]:
            title = d.get('title', 'Sem título')
            status = d.get('status', 'N/A')
            value = d.get('value', 0)
            currency = d.get('currency', 'BRL')
            stage = d.get('stage', 'Desconhecido')
            deals_lines.append(f"   • [ID:{d.get('id','?')}] {title} | {status} | R${value:,.0f} | Funil: {stage}")
        sections.append("\n".join(deals_lines))

    # Contatos estruturados
    if "persons" in data and data["persons"]:
        persons_lines = ["👥 CONTATOS:"]
        for p in data["persons"][:15]:
            name = p.get('name', 'N/A')
            email = p.get('email', '')
            phone = p.get('phone', '')
            contact = email or phone or 'sem contato'
            persons_lines.append(f"   • [ID:{p.get('id','?')}] {name} ({contact})")
        sections.append("\n".join(persons_lines))

    # Atividades pendentes
    if "activities" in data and data["activities"]:
        acts_lines = ["📋 ATIVIDADES:"]
        pending_count = 0
        for a in data["activities"][:8]:
            subject = a.get('subject', 'Sem assunto')
            due = a.get('due_date', 'sem data')
            done = a.get('done', False)
            note = (a.get('note') or '')[:80]
            status = "✓" if done else "◯"
            if not done:
                pending_count += 1
            acts_lines.append(f"   {status} [ID:{a.get('id','?')}] {subject} (venc: {due}){f' | {note}' if note else ''}")
        if pending_count > 0:
            acts_lines.append(f"   ⚠️ {pending_count} pendente(s)")
        sections.append("\n".join(acts_lines))

    # Notas
    if "notes" in data and data["notes"]:
        notes_lines = ["📝 NOTAS RECENTES:"]
        for n in data["notes"][:3]:
            note_text = str(n)[:200]
            notes_lines.append(f"   • {note_text}")
        sections.append("\n".join(notes_lines))

    # Atividades vindas de exec_pipedrive_get_activities (chave "pending")
    if "pending" in data and data["pending"]:
        acts_lines = ["📋 ATIVIDADES PENDENTES:"]
        for a in data["pending"][:8]:
            act_id = a.get('id', '?')
            subject = a.get('subject', 'Sem assunto')
            due = a.get('due_date', 'sem data')
            note = (a.get('note') or '')[:80]
            acts_lines.append(f"   ◯ [ID:{act_id}] {subject} (venc: {due}){f' | {note}' if note else ''}")
        sections.append("\n".join(acts_lines))

    return "\n\n".join(sections) if sections else "📊 Sem dados relevantes no Pipedrive."

def _sanitize_whatsapp(data: dict) -> str:
    """Compacta histórico de WhatsApp em log narrativo denso com tom da conversa."""
    if not data or not isinstance(data, dict): return str(data)
    msgs = data.get("messages", [])
    contact = data.get('contact', 'o contato')
    if not msgs: return f"💬 WhatsApp: Nenhuma mensagem com {contact}."

    lines = [f"💬 WHATSAPP ({contact}) - {len(msgs)} mensagens:"]

    # Últimas mensagens (mais recentes primeiro)
    recent_msgs = msgs[-12:]
    has_response_from_contact = False
    last_msg_time = None

    for m in recent_msgs:
        if isinstance(m, str):
            # Se for string formatada, usa direto
            lines.append(f"  {m}")
            if f"[{contact}]" in m or f"[{contact.lower()}]" in m.lower():
                has_response_from_contact = True
            elif "[Você]" not in m and "[joao.moura" not in m:
                has_response_from_contact = True
            continue

        if not isinstance(m, dict):
            continue

        sender_raw = m.get('sender') or m.get('from') or ''
        is_me = m.get('from_me') or m.get('fromMe') or 'EU' in str(sender_raw)
        sender = 'EU' if is_me else contact
        if not is_me:
            has_response_from_contact = True

        body = (m.get('body') or m.get('text') or '').replace("\n", " ").strip()
        timestamp = m.get('timestamp', '') or m.get('date', '')
        if timestamp and not last_msg_time:
            last_msg_time = str(timestamp)[:10]

        lines.append(f"  [{sender}]: {body[:200]}")

    # Detecta tom da conversa
    all_text = ""
    for m in recent_msgs:
        if isinstance(m, str):
            all_text += " " + m
        elif isinstance(m, dict):
            all_text += " " + (m.get('body') or m.get('text') or '')
    all_text = all_text.lower()

    if "obrigado" in all_text or "perfeito" in all_text or "ok" in all_text:
        sentiment = "✅ positivo"
    elif "urgente" in all_text or "preciso" in all_text or "hoje" in all_text:
        sentiment = "⚠️ urgente"
    elif "aguardo" in all_text or "quando" in all_text or "falta" in all_text:
        sentiment = "⏳ aguardando"
    elif not has_response_from_contact:
        sentiment = "🔇 sem resposta"
    else:
        sentiment = "🔄 em andamento"

    lines.append(f"  📊 Status: {sentiment} | Última: {last_msg_time or 'desconhecida'}")

    return "\n".join(lines)

def _sanitize_result(tool_name: str, result: Any) -> Any:
    """Orquestra a limpeza retornando strings otimizadas para o LLM."""
    try:
        if not result: return "Sem resultados."
        if tool_name == "suggest_next_actions": return "Tarefas sugeridas criadas na interface para o usuário aprovar."
        if "email" in tool_name: return _sanitize_email(result)
        if "pipedrive" in tool_name: return _sanitize_pipedrive(result)
        if "whatsapp" in tool_name: return _sanitize_whatsapp(result)
        return result
    except Exception as e:
        return f"Erro na sanitização: {e} | Dados brutos: {str(result)[:500]}"

# ───────────────────────────────────────────────────────────────────────────



def _emit(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _raw_log(process_id: str, event_type: str, data: Any):
    """Loga dados brutos e estruturados para depuração profunda do Agente V2."""
    try:
        import os
        import json
        from datetime import datetime
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Tenta usar o diretório que o usuário prefere (backend/backend/logs)
        log_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "backend", "logs"))
        if not os.path.exists(log_dir):
            log_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "logs"))
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # 1. Log NDJSON (para processamento e auditoria técnica)
        ndjson_file = os.path.join(log_dir, "agent_v2_raw.log")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "process_id": process_id,
            "event": event_type,
            "data": data
        }
        with open(ndjson_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            
        # 2. Log Markdown (estruturadinho para leitura humana direta)
        md_file = os.path.join(log_dir, "agent_v2_debug.md")
        with open(md_file, "a", encoding="utf-8") as f:
            if event_type == "agent_start":
                f.write(f"\n\n# 🕵️ Investigação: {process_id} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n")
                f.write(f"**Mensagem Original**: `{data.get('message')}`\n")
                f.write(f"**Org ID**: `{data.get('org_id')}` | **Preferência**: `{data.get('preferred')}`\n")
                f.write("\n---\n")
            
            elif event_type == "llm_request":
                f.write(f"\n## 🔄 Turno {data.get('iteration')}\n")
                f.write("### 🤖 Chamada LLM\n")
                f.write("<details><summary><b>System Prompt</b> (clique para expandir)</summary>\n\n")
                f.write(f"```text\n{data.get('system')}\n```\n</details>\n\n")
                
                # Mostra apenas as últimas 2 mensagens para não poluir o MD
                messages = data.get("messages", [])
                if messages:
                    f.write("**Contexto Recente do Histórico**:\n")
                    for m in messages[-2:]:
                        role = m.get("role", "unknown")
                        content = m.get("content", "")
                        # Se content for lista (tool results), formata bonito
                        if isinstance(content, list):
                            content_str = json.dumps(content, indent=2, ensure_ascii=False)
                        else:
                            content_str = str(content)
                        f.write(f"- **{role.upper()}**:\n```json\n{content_str}\n```\n")
            
            elif event_type == "llm_response":
                f.write("### 📥 Resposta Bruta do Modelo\n")
                f.write("```json\n" + json.dumps(data.get("response"), indent=2, ensure_ascii=False) + "\n```\n")
            
            elif event_type == "tool_execute_start":
                f.write(f"#### 🛠️ Executando: `{data.get('tool')}`\n")
                f.write(f"**Argumentos**: `{json.dumps(data.get('args'), ensure_ascii=False)}`\n")
            
            elif event_type == "tool_execute_result":
                f.write(f"#### 📦 Resultado da Ferramenta: `{data.get('tool')}`\n")
                res_raw = data.get("result_raw")
                res_str = json.dumps(res_raw, indent=2, ensure_ascii=False, default=str)
                # Trunca se for gigantesco para não travar o editor do usuário
                if len(res_str) > 10000:
                    res_str = res_str[:10000] + "\n... [TRUNCADO NO PREVIEW]"
                f.write("```json\n" + res_str + "\n```\n")
                f.write("\n---\n")
            
            elif event_type == "agent_final_response":
                f.write("\n## 🏁 Dossiê / Resposta Final\n")
                f.write(f"{data.get('response')}\n")
                f.write(f"\n**Status**: Concluído em {datetime.now().strftime('%H:%M:%S')}\n")
                f.write("\n" + "="*80 + "\n")
                
            elif event_type == "agent_error":
                 f.write(f"\n## ❌ ERRO NO PROCESSO\n")
                 f.write(f"```text\n{data.get('content')}\n```\n")

    except Exception:
        # Silencioso para não quebrar o fluxo principal
        pass


def _get_thinking_fallback(tool_name: str, args: dict) -> str:
    """Thinking mínimo contextual quando o modelo não gera texto e o auxiliar falha.
    Diferente do _get_label — explica o raciocínio, não só o que está sendo feito."""
    if not args:
        args = {}
    org = args.get("org_name", "a empresa")
    contact = args.get("contact") or args.get("contact_name") or "o contato"
    templates = {
        "pipedrive_get_org":
            f"Vou começar mapeando {org} no Pipedrive para ter a visão geral: deals, contatos e status.",
        "pipedrive_get_persons":
            f"Com a visão geral mapeada, agora listo todos os contatos de {org} — preciso dos nomes para investigar as comunicações.",
        "pipedrive_get_deals":
            f"Com os contatos identificados, verifico os detalhes do deal de {org}: funil, valor e etapa atual.",
        "pipedrive_get_activities":
            f"Com o deal mapeado, busco as tarefas e atividades de {org} para entender o histórico e priorizar quem contatar.",
        "whatsapp_get_messages":
            f"Com o Pipedrive mapeado, verifico as mensagens de WhatsApp de {contact} para cruzar com o que o CRM registrou.",
        "email_get_contact_history":
            f"Verifico o histórico de e-mails de {contact} para complementar o que o WhatsApp e o Pipedrive já revelaram.",
        "generate_dossier":
            "Todas as fontes foram investigadas. Vou organizar os dados em um dossiê final para o usuário.",
    }
    return templates.get(tool_name, f"Verificando {tool_name.replace('_', ' ')} para continuar a investigação.")


def _get_label(tool_name: str, args: dict) -> str:
    args = args or {}
    labels = {
        "whatsapp_get_messages": f"Buscando mensagens de {args.get('contact', '...')}",
        "whatsapp_list_chats": "Listando chats do WhatsApp",
        "whatsapp_send_message": f"Enviar mensagem para {args.get('contact', '...')}",
        "pipedrive_get_org": f"Consultando {args.get('org_name', '...')} no Pipedrive",
        "pipedrive_get_persons": f"Buscando contatos de {args.get('org_name', '...')}",
        "pipedrive_get_deals": f"Buscando deals de {args.get('org_name', '...')}",
        "pipedrive_get_activities": f"Buscando atividades de {args.get('org_name', '...')}",
        "pipedrive_get_all_activities": "Buscando todas as atividades de hoje e atrasadas",
        "pipedrive_update_deal": f"Atualizando deal #{args.get('deal_id', '...')}",
        "pipedrive_create_task": f"Criar tarefa: {args.get('subject', '...')}",
        "pipedrive_update_task": f"Atualizando atividade #{args.get('activity_id', '...')}",
        "pipedrive_create_note": f"Adicionando nota ao deal #{args.get('deal_id', '...')}",
        "email_get_inbox": "Acessando caixa de entrada",
        "email_get_contact_history": f"Buscando e-mails de {args.get('contact_name') or args.get('org_name') or args.get('contact_email') or '...'}",
        "email_send": f"Enviar e-mail para {args.get('to', '...')}",
        "email_reply": f"Responder e-mail de {args.get('contact_name', '...')}",
        "web_search_external": f"Pesquisando: {args.get('query', '...')}",
    }
    return labels.get(tool_name, tool_name)


# ── Conversão de formatos entre Anthropic e OpenAI/Groq ──────────────────────

def _tools_to_openai(tools: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _messages_to_ollama_native(system: str, messages: list) -> list:
    """Converte histórico interno para o formato nativo /api/chat do Ollama."""
    result = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "assistant":
            text_parts = []
            tool_calls = []
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "text":
                        text_parts.append(b.get("text", ""))
                    elif b.get("type") == "tool_use":
                        tool_calls.append({
                            "function": {
                                "name": b["name"],
                                "arguments": b["input"] if isinstance(b["input"], dict) else {},
                            }
                        })
            elif isinstance(content, str):
                text_parts.append(content)
            entry: dict = {"role": "assistant", "content": " ".join(text_parts)}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            result.append(entry)
        elif role == "user":
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_result":
                        raw = b["content"]
                        result.append({
                            "role": "tool",
                            "content": json.dumps(raw) if isinstance(raw, (dict, list)) else str(raw),
                        })
                    elif b.get("type") == "text":
                        result.append({"role": "user", "content": b["text"]})
            else:
                result.append({"role": "user", "content": str(content)})
    return result


def _messages_to_openai(messages: list) -> list:
    """Converte o histórico interno para o formato de Chat Completion da OpenAI/Groq."""
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "assistant":
            text_parts = []
            tool_calls = []
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "text":
                        text_parts.append(b.get("text", ""))
                    elif b.get("type") == "tool_use":
                        tool_calls.append({
                            "id": b["id"],
                            "type": "function",
                            "function": {
                                "name": b["name"],
                                "arguments": json.dumps(b["input"])
                            }
                        })
            elif isinstance(content, str):
                text_parts.append(content)
            
            res = {"role": "assistant", "content": " ".join(text_parts) if text_parts else None}
            if tool_calls:
                res["tool_calls"] = tool_calls
            result.append(res)

        elif role == "user":
            if isinstance(content, list):
                # Pode conter tool_result
                for b in content:
                    if b.get("type") == "tool_result":
                        result.append({
                            "role": "tool",
                            "tool_call_id": b["tool_use_id"],
                            "content": json.dumps(b["content"]) if isinstance(b["content"], (dict, list)) else str(b["content"])
                        })
                    elif b.get("type") == "text":
                        result.append({"role": "user", "content": b["text"]})
            else:
                result.append({"role": "user", "content": str(content)})

    return result


def _response_from_openai(resp: dict) -> dict:
    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    finish = choice.get("finish_reason", "stop")

    content = []
    if msg.get("content"):
        content.append({"type": "text", "text": msg["content"]})
    for tc in (msg.get("tool_calls") or []):
        func = tc.get("function", {})
        try:
            inp = json.loads(func.get("arguments", "{}"))
        except Exception:
            inp = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "name": func.get("name", ""),
            "input": inp,
        })

    return {
        "content": content,
        "stop_reason": "tool_use" if finish == "tool_calls" else "end_turn",
    }


def _tools_to_gemini(tools: list) -> list:
    funcs = []
    for t in tools:
        funcs.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        })
    return [{"functionDeclarations": funcs}]


def _messages_to_gemini(messages: list) -> list:
    result = []
    for msg in messages:
        role = msg["role"]
        gemini_role = "model" if role == "assistant" else "user"
        content = msg["content"]
        
        parts = []
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for b in content:
                if b.get("type") == "text":
                    text_val = b.get("text", "").strip()
                    if text_val:
                        parts.append({"text": text_val})
                elif b.get("type") == "tool_use":
                    parts.append({
                        "functionCall": {
                            "name": b.get("name", ""),
                            "args": b.get("input") or {}
                        }
                    })
                elif b.get("type") == "tool_result":
                    tc = b.get("content", "{}")
                    try:
                        tc_dict = json.loads(tc) if isinstance(tc, str) else tc
                    except Exception:
                        tc_dict = {"result": str(tc)}
                    # Gemini exige que functionResponse.response seja um dict (objeto JSON)
                    if not isinstance(tc_dict, dict):
                        tc_dict = {"output": str(tc_dict)}
                    parts.append({
                        "functionResponse": {
                            "name": b.get("tool_name", "unknown_tool"),
                            "response": tc_dict
                        }
                    })
        
        if parts:
            result.append({"role": gemini_role, "parts": parts})
    return result


def _response_from_gemini(resp: dict) -> dict:
    candidates = resp.get("candidates", [])
    if not candidates:
        return {"content": [], "stop_reason": "end_turn"}
    
    parts = candidates[0].get("content", {}).get("parts", [])
    
    content = []
    for part in parts:
        if "text" in part:
            content.append({"type": "text", "text": part["text"]})
        elif "functionCall" in part:
            call = part["functionCall"]
            content.append({
                "type": "tool_use",
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": call.get("name", ""),
                "input": call.get("args", {}),
            })
            
    stop_reason = "tool_use" if any(c["type"] == "tool_use" for c in content) else "end_turn"
    
    return {
        "content": content,
        "stop_reason": stop_reason,
    }


# Modelos Groq que suportam tool calling — testados e confirmados em 2026-05-07
_GROQ_TOOL_MODELS = [
    "llama-3.3-70b-versatile",                    # 70B — melhor qualidade
    "meta-llama/llama-4-scout-17b-16e-instruct",   # Llama 4 Scout — alta performance
    "qwen/qwen3-32b",                              # Qwen 3 — excelente p/ coding/logic
    "llama-3.1-8b-instant",                        # 8B — rápido e estável
]

# Cache de rate limit por modelo (compartilhado entre iterações do mesmo processo)
# Mapeia "provider:model" → timestamp até quando está bloqueado
import time as _time
import json as _json
import os as _os
from collections import deque

_RATE_STATE_FILE = _os.path.join(_os.path.dirname(__file__), ".rate_state.json")
_agent_rate_limited_until: dict[str, float] = {}


def _load_rate_state() -> None:
    """Carrega estado de rate limit persistido — evita bater no limite logo após restart."""
    try:
        if not _os.path.exists(_RATE_STATE_FILE):
            return
        with open(_RATE_STATE_FILE, "r") as f:
            data = _json.load(f)
        now = _time.monotonic()
        wall_now = _time.time()
        saved_wall = data.get("saved_at", wall_now)
        elapsed = wall_now - saved_wall  # segundos desde o último save

        # Restaura RPM tracker: converte wall clock → monotônico corretamente
        rpm = data.get("rpm_tracker", {})
        for model, timestamps in rpm.items():
            # Filtra entradas com menos de 60s e converte para tempo monotônico atual
            adjusted = [now - (wall_now - t) for t in timestamps if wall_now - t < 60]
            if adjusted:
                _rpm_tracker[model] = deque(adjusted)

        # Restaura TPM tracker
        tpm = data.get("tpm_tracker", {})
        for model, entries in tpm.items():
            adjusted = [(now - (wall_now - t), tokens) for t, tokens in entries if wall_now - t < 60]
            if adjusted:
                _tpm_tracker[model] = deque(adjusted)

        # Restaura cooldowns individuais
        cooldowns = data.get("cooldowns", {})
        for key, until_wall in cooldowns.items():
            remaining = until_wall - wall_now
            if remaining > 0:
                _agent_rate_limited_until[key] = now + remaining

        # Restaura RPD (somente se for o mesmo dia UTC)
        from datetime import datetime, timezone
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if data.get("rpd_date") == today_utc:
            _rpd_tracker.update(data.get("rpd_tracker", {}))
    except Exception:
        pass


def _save_rate_state() -> None:
    """Persiste estado de rate limit para sobreviver a restarts."""
    try:
        from datetime import datetime, timezone
        now = _time.monotonic()
        wall_now = _time.time()
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        rpm = {}
        for model, dq in _rpm_tracker.items():
            valid = [t for t in dq if now - t < 60]
            if valid:
                rpm[model] = [wall_now - (now - t) for t in valid]

        tpm = {}
        for model, dq in _tpm_tracker.items():
            valid = [(t, tokens) for t, tokens in dq if now - t < 60]
            if valid:
                tpm[model] = [(wall_now - (now - t), tokens) for t, tokens in valid]

        cooldowns = {}
        for key, until_mono in _agent_rate_limited_until.items():
            remaining = until_mono - now
            if remaining > 0:
                cooldowns[key] = wall_now + remaining

        with open(_RATE_STATE_FILE, "w") as f:
            _json.dump({
                "saved_at": wall_now,
                "rpm_tracker": rpm,
                "tpm_tracker": tpm,
                "cooldowns": cooldowns,
                "rpd_tracker": _rpd_tracker,
                "rpd_date": today_utc,
            }, f)
    except Exception:
        pass

# ── Limites de contexto por modelo (tokens) ──────────────────────────────────
_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # Groq
    "llama-3.3-70b-versatile":                   131_072,
    "llama-3.1-8b-instant":                      131_072,
    "meta-llama/llama-4-scout-17b-16e-instruct": 131_072,
    "qwen/qwen3-32b":                            131_072,
    "llama-3.2-11b-vision-preview":              131_072,
    # Claude
    "claude-3-5-sonnet-latest":                  200_000,
    "claude-3-5-haiku-latest":                   200_000,
    # Cerebras
    "llama3.1-8b":                               8_192,
    "llama-3.3-70b":                             8_192,
    # SambaNova
    "Meta-Llama-3.3-70B-Instruct":               128_000,
    "Llama-4-Scout-17B-16E-Instruct":            128_000,
    # DeepSeek
    "deepseek-chat":                             64_000,
    # Gemini
    "gemini-2.5-pro":                            1_048_576,
    "gemini-2.5-flash":                          1_048_576,
    "gemini-2.5-flash-lite":                     1_048_576,
    # Ollama (local — sem limite real)
    "qwen2.5:14b":                               128_000,
    "llama3.2":                                  128_000,
    "llama3":                                    8_192,
}

# ── RPM, TPM e RPD por modelo (todos os providers) ───────────────────────────
# RPD = Requests Per Day (resets à meia-noite UTC)
# None = sem limite conhecido / ilimitado

_MODEL_LIMITS: dict[str, dict] = {
    # ── Groq free tier ───────────────────────────────────────────────────────
    # Fonte: console.groq.com/docs/rate-limits
    "llama-3.3-70b-versatile": {
        "rpm": 30, "tpm": 12_000, "rpd": 1_000, "tpd": 100_000,
    },
    "llama-3.1-8b-instant": {
        "rpm": 30, "tpm": 6_000, "rpd": 14_400, "tpd": 500_000,
    },
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "rpm": 30, "tpm": 30_000, "rpd": 1_000, "tpd": 500_000,
    },
    "qwen/qwen3-32b": {
        "rpm": 60, "tpm": 6_000, "rpd": 1_000, "tpd": 500_000,
    },
    "llama-3.2-11b-vision-preview": {
        "rpm": 30, "tpm": 7_000, "rpd": 7_000, "tpd": 500_000,
    },
    # ── Claude (Anthropic API — tier 1) ──────────────────────────────────────
    # Fonte: platform.claude.com/docs/en/api/rate-limits
    # ITPM = input tokens/min | OTPM = output tokens/min | sem RPD
    "claude-3-5-sonnet-latest": {
        "rpm": 50, "tpm": 38_000, "rpd": None,   # 30k ITPM + 8k OTPM
    },
    "claude-3-5-haiku-latest": {
        "rpm": 50, "tpm": 60_000, "rpd": None,   # 50k ITPM + 10k OTPM
    },
    # ── Cerebras free tier ────────────────────────────────────────────────────
    # Fonte: inference-docs.cerebras.ai/support/rate-limits
    # ATENÇÃO: llama-3.3-70b foi DEPRECIADO em fev/2026
    "llama3.1-8b": {
        "rpm": 30, "tpm": 60_000, "rpd": 14_400, "tpd": 1_000_000,
    },
    # ── SambaNova free tier ───────────────────────────────────────────────────
    # Fonte: docs.sambanova.ai/docs/en/models/rate-limits
    # ATENÇÃO: RPD free = apenas 20 req/dia — extremamente restrito
    "Meta-Llama-3.3-70B-Instruct": {
        "rpm": 20, "tpm": None, "rpd": 20, "tpd": 200_000,
    },
    "Llama-4-Scout-17B-16E-Instruct": {
        "rpm": 20, "tpm": None, "rpd": 20, "tpd": 200_000,
    },
    # ── DeepSeek ──────────────────────────────────────────────────────────────
    # Fonte: api-docs.deepseek.com/quick_start/rate_limit
    # Sem limites fixos — concorrência dinâmica baseada na carga do servidor
    # Retorna 429 quando servidor está sobrecarregado; sem RPM/TPM/RPD publicados
    "deepseek-chat": {
        "rpm": None, "tpm": None, "rpd": None,
    },
    # ── Gemini free tier ──────────────────────────────────────────────────────
    # Fonte: ai.google.dev/gemini-api/docs/rate-limits (maio 2026)
    "gemini-2.5-flash-lite": {
        "rpm": 15, "tpm": 1_000_000, "rpd": 1_000,
    },
    "gemini-2.5-flash": {
        "rpm": 10, "tpm": 1_000_000, "rpd": 250,
    },
    "gemini-2.5-pro": {
        "rpm": 5, "tpm": 1_000_000, "rpd": 100,
    },
    # ── Ollama (local/Colab — sem limites) ────────────────────────────────────
    # (ausência no dict = sem limite aplicado)
}

# Helpers de acesso rápido (retrocompat)
def _get_rpm(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("rpm")

def _get_tpm(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("tpm")

def _get_rpd(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("rpd")

def _get_tpd(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("tpd")

# Trackers em memória
_rpm_tracker: dict[str, deque] = {}           # model → deque[timestamp]
_tpm_tracker: dict[str, deque] = {}           # model → deque[(timestamp, tokens)]
_rpd_tracker: dict[str, int]   = {}           # model → count (hoje UTC)
_rpd_date:    str               = ""           # data UTC atual — reset ao mudar

# Carrega estado persistido ao iniciar (sobrevive a restarts)
_load_rate_state()


def _count_tokens(messages: list, tools: list | None = None) -> int:
    """Conta tokens reais usando tiktoken (cl100k_base — compatível com Llama 3)."""
    import json
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in messages:
            content = msg.get("content") or ""
            if isinstance(content, list):
                text = " ".join(str(b.get("text") or b.get("content") or "") for b in content)
            else:
                text = str(content)
            total += len(enc.encode(text)) + 4  # +4 overhead por mensagem
        if tools:
            total += len(enc.encode(json.dumps(tools)))
        return total
    except Exception:
        # Fallback se tiktoken falhar
        total = sum(len(str(m.get("content") or "")) for m in messages)
        if tools:
            total += len(json.dumps(tools))
        return total // 4


def _rpd_today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _check_rpd(model: str) -> tuple[bool, str]:
    """
    Verifica cota diária (RPD e TPD).
    Retorna (pode_prosseguir, motivo_bloqueio_ou_vazio).
    """
    global _rpd_date, _rpd_tracker
    today = _rpd_today()
    if _rpd_date != today:
        _rpd_tracker = {}
        _rpd_date = today

    rpd_limit = _get_rpd(model)
    if rpd_limit and _rpd_tracker.get(f"{model}:req", 0) >= rpd_limit:
        used = _rpd_tracker.get(f"{model}:req", 0)
        return False, f"RPD esgotado ({used}/{rpd_limit} req hoje)"

    tpd_limit = _get_tpd(model)
    if tpd_limit and _rpd_tracker.get(f"{model}:tok", 0) >= tpd_limit:
        used = _rpd_tracker.get(f"{model}:tok", 0)
        return False, f"TPD esgotado ({used:,}/{tpd_limit:,} tokens hoje)"

    return True, ""


def _rpd_used(model: str) -> dict:
    """Retorna uso diário: {req, tokens}."""
    return {
        "req": _rpd_tracker.get(f"{model}:req", 0),
        "tokens": _rpd_tracker.get(f"{model}:tok", 0),
    }


def _rpm_wait(model: str) -> float:
    limit = _get_rpm(model)
    if not limit:
        return 0.0
    now = _time.monotonic()
    dq = _rpm_tracker.setdefault(model, deque())
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= limit:
        return max(0.0, 60.0 - (now - dq[0]) + 0.1)
    return 0.0


def _tpm_wait(model: str, tokens_needed: int) -> float:
    limit = _get_tpm(model)
    if not limit:
        return 0.0
    now = _time.monotonic()
    dq = _tpm_tracker.setdefault(model, deque())
    while dq and now - dq[0][0] > 60:
        dq.popleft()
    tokens_used = sum(t for _, t in dq)
    if tokens_used + tokens_needed > limit:
        return max(0.0, 60.0 - (now - dq[0][0]) + 0.1) if dq else 0.0
    return 0.0


def _pre_call_check(
    model: str,
    estimated_tokens: int,
    pending_events: list | None,
    rl_key: str,
    provider: str | None = None,
) -> tuple[bool, float]:
    """
    Bypassed as requested — no longer limits locally or forces wait sleeps.
    """
    return True, 0.0


def _post_call_record(model: str, actual_tokens: int = 0) -> None:
    """Registra uma requisição bem-sucedida nos trackers (RPM, TPM, RPD)."""
    global _rpd_date, _rpd_tracker
    now = _time.monotonic()
    _rpm_tracker.setdefault(model, deque()).append(now)
    if actual_tokens > 0:
        _tpm_tracker.setdefault(model, deque()).append((now, actual_tokens))
    today = _rpd_today()
    if _rpd_date != today:
        _rpd_tracker = {}
        _rpd_date = today
    _rpd_tracker[model] = _rpd_tracker.get(model, 0) + 1
    _save_rate_state()


def _on_429(model: str, rl_key: str, retry_after: int) -> None:
    """Atualiza trackers quando recebe 429 — preenche RPM e persiste."""
    cooldown = retry_after or 60
    _agent_rate_limited_until[rl_key] = _time.monotonic() + cooldown
    rpm_limit = _get_rpm(model) or 15
    dq = _rpm_tracker.setdefault(model, deque())
    while len(dq) < rpm_limit:
        dq.appendleft(_time.monotonic())
    _save_rate_state()


# ── Chamada via router — mesmo fluxo do V1 ───────────────────────────────────

async def _call_with_tools(
    system: str,
    messages: list,
    tools: list,
    preferred: str | None = None,
    strict_mode: bool | None = None,
    pending_events: list | None = None,  # eventos a emitir pro stream (rate_wait, context_overflow)
) -> dict:
    """
    Usa get_router().chain() exatamente como o V1 usa ask_llm:
    - Respeita preferência de modelo via get_preferred_model()
    - Respeita strict_mode via get_strict_mode_preference()
    - Usa a mesma ordem de providers e fallbacks da v1
    - Ordena modelos dentro de cada provider com o preferido primeiro
    Suporta Claude (Anthropic nativo) e Groq (OpenAI-compat) com tools.
    """
    import time
    from core.config import settings
    from core.http_client import get_http_client
    from services.ai.llm.router import get_router, get_preferred_model, get_strict_mode_preference

    router = get_router()
    preferred = preferred or get_preferred_model()
    # Só aplica preferência global quando strict_mode não foi explicitamente passado (None)
    if strict_mode is None:
        strict_mode = get_strict_mode_preference()
    else:
        strict_mode = bool(strict_mode)

    if strict_mode and preferred:
        target_provider = None
        if preferred in router._providers:
            target_provider = preferred
        elif preferred in (settings.ai_gemini_models_list or []):
            target_provider = "gemini"
        elif preferred in (settings.ai_groq_models_list or []):
            target_provider = "groq"
        elif preferred in (settings.ai_claude_models_list or []):
            target_provider = "claude"
        elif preferred in (settings.ai_sambanova_models_list or []):
            target_provider = "sambanova"
        elif preferred in (settings.ai_deepseek_models_list or []):
            target_provider = "deepseek"
        elif preferred in (settings.ai_cerebras_models_list or []):
            target_provider = "cerebras"

        if strict_mode and target_provider and target_provider in router._providers:
            providers = [router._providers[target_provider]]
        else:
            # Se não for strict, usa a cadeia completa começando pelo preferido
            providers = router.chain(preferred=preferred)
    else:
        providers = router.chain(preferred=preferred)

    # Estima tokens gerais para ordenação adaptativa de provedores se não for strict_mode
    if not strict_mode:
        from services.ai.llm.router import _estimate_tokens
        from services.ai.llm.base import LLMMessage
        general_msgs = [LLMMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages if isinstance(m, dict)]
        general_est_tokens = _estimate_tokens(general_msgs)

        base_prov_names = [p.name for p in providers]
        if general_est_tokens < 15_000:
            # Menos tokens -> Prioriza provedores com modelos pequenos, rápidos e leves
            lightweight = ["gemini", "groq", "cerebras"]
            sorted_prov_names = [p for p in lightweight if p in base_prov_names] + [p for p in base_prov_names if p not in lightweight]
            providers = [router._providers[name] for name in sorted_prov_names if name in router._providers]
        elif general_est_tokens > 100_000:
            # Mais de 100k tokens -> Prioriza provedores com contextos massivos
            heavyweight = ["gemini", "claude", "sambanova"]
            sorted_prov_names = [p for p in heavyweight if p in base_prov_names] + [p for p in base_prov_names if p not in heavyweight]
            providers = [router._providers[name] for name in sorted_prov_names if name in router._providers]

    client = get_http_client()
    last_err = "nenhum provider disponível"
    
    log.info("agent.llm.chain", providers=[p.name for p in providers], preferred=preferred, strict_mode=strict_mode)

    for provider in providers:
        if not provider.available:
            continue

        # Skip rápido se o provider foi rate-limitado recentemente no router
        from services.ai.llm.router import _provider_rate_limited_until
        cooldown_until = _provider_rate_limited_until.get(provider.name, 0)
        if time.monotonic() < cooldown_until:
            # Se for o provider preferido ou se estivermos em strict_mode, NÃO pula!
            is_preferred = False
            if preferred:
                if preferred == provider.name:
                    is_preferred = True
                elif provider.name == "gemini" and "gemini" in preferred:
                    is_preferred = True
                elif provider.name == "groq" and preferred in (settings.ai_groq_models_list or []):
                    is_preferred = True
                elif provider.name == "claude" and preferred in (settings.ai_claude_models_list or []):
                    is_preferred = True
                elif provider.name in ("sambanova", "deepseek", "cerebras", "ollama") and preferred in (settings.ai_sambanova_models_list or settings.ai_deepseek_models_list or settings.ai_cerebras_models_list or settings.ai_ollama_models_list or []):
                    is_preferred = True

            if not strict_mode and not is_preferred:
                remaining = round(cooldown_until - time.monotonic())
                log.info("agent.llm.provider.skipped_cooldown", provider=provider.name, remaining_sec=remaining)
                continue

        # ── Claude ────────────────────────────────────────────────────────
        if provider.name == "claude":
            key = settings.ANTHROPIC_API_KEY
            if not key:
                continue
            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            all_models = settings.ai_claude_models_list or ["claude-sonnet-4-5", "claude-3-5-haiku-latest"]
            
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                       "content-type": "application/json"}
            _claude_msgs_for_count = [{"role": "system", "content": system}] + \
                                     [{"role": m.get("role","user"), "content": str(m.get("content",""))}
                                      for m in messages if isinstance(m, dict)]
            estimated_tokens = _count_tokens(_claude_msgs_for_count, tools)

            from services.ai.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in all_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens > ctx_limit:
                    log.warning("agent.claude.context_limit_skipped", model=m, estimated=estimated_tokens, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = all_models

            def _claude_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                if estimated_tokens < 15_000:
                    return sz
                elif estimated_tokens < 100_000:
                    if sz == 2: return 0
                    if sz == 1: return 1
                    return 2
                else:
                    return -sz

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_claude_size_sort_key)
                models = [preferred] + other_models
            else:
                valid_models.sort(key=_claude_size_sort_key)
                models = valid_models

            for model in models:
                _rl_key = f"claude:{model}"

                ctx_limit = _MODEL_CONTEXT_LIMITS.get(model)
                if ctx_limit and estimated_tokens > ctx_limit:
                    last_err = f"{model} contexto muito grande ({estimated_tokens} > {ctx_limit})"
                    if pending_events is not None:
                        pending_events.append({"type": "context_overflow", "provider": "claude", "model": model,
                                               "estimated_tokens": estimated_tokens, "limit": ctx_limit})
                    continue

                can_go, wait = _pre_call_check(model, estimated_tokens, pending_events, _rl_key, provider="claude")
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                max_retries = 3 if strict_mode else 1
                for attempt in range(1, max_retries + 1):
                    try:
                        resp = await client.post(
                            "https://api.anthropic.com/v1/messages",
                            json={"model": model, "max_tokens": 4096, "temperature": 0.1,
                                  "system": system, "messages": messages, "tools": tools},
                            headers=headers, timeout=120.0 if strict_mode else 20.0,
                        )
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key, None)
                        data = resp.json()
                        real_tokens = (data.get("usage") or {}).get("input_tokens", 0) + \
                                      (data.get("usage") or {}).get("output_tokens", 0)
                        _post_call_record(model, real_tokens)
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": "claude", "model": model})
                        data["_successful_provider"] = "claude"
                        data["_successful_model"] = model
                        return data

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key, retry_after)
                        last_err = f"rate_limit {model}"
                        if attempt < max_retries:
                            import asyncio
                            _wait = min(retry_after or 15, 15)
                            log.warning("agent.llm.retry_wait", provider="claude", model=model,
                                        wait_sec=_wait, attempt=attempt)
                            if pending_events is not None:
                                pending_events.append({"type": "rate_wait", "provider": "claude", "model": model, "wait_sec": _wait, "reason": "RPM"})
                            await asyncio.sleep(_wait)
                            continue
                        break

                    if resp.status_code in (401, 402, 403):
                        last_err = f"claude sem crédito/chave (HTTP {resp.status_code})"
                        break

                    last_err = f"claude HTTP {resp.status_code}"
                    break

                if strict_mode and "rate_limit" in last_err:
                    break

            # Se todos os modelos falharam para Claude, coloca o provedor em cooldown
            from services.ai.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until["claude"] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider="claude", reason=f"all_models_failed (last: {last_err})")

        # ── Groq ──────────────────────────────────────────────────────────
        elif provider.name == "groq":
            key = settings.GROQ_API_KEY
            if not key:
                continue
            # _GROQ_TOOL_MODELS define a ordem — modelos testados e confirmados.
            # settings pode adicionar extras, mas os testados ficam primeiro.
            extra = [m for m in (settings.ai_groq_models_list or []) if m not in _GROQ_TOOL_MODELS]
            all_models = list(_GROQ_TOOL_MODELS) + extra
            
            oai_tools = _tools_to_openai(tools)
            oai_msgs = [{"role": "system", "content": system}] + _messages_to_openai(messages)
            headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}

            # Nomes de provider ("groq", "gemini", "claude") não são modelos —
            # quando preferred é um nome de provider, usa todos os modelos desse provider.
            _provider_names = set(router._providers.keys())  # groq, gemini, claude, sambanova, deepseek, cerebras
            preferred_is_provider_name = preferred in _provider_names

            estimated_tokens = _count_tokens(oai_msgs, oai_tools)

            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            from services.ai.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in all_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens > ctx_limit:
                    log.warning("agent.groq.context_limit_skipped", model=m, estimated=estimated_tokens, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = all_models

            def _groq_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                if estimated_tokens < 15_000:
                    return sz
                elif estimated_tokens < 100_000:
                    if sz == 2: return 0
                    if sz == 1: return 1
                    return 2
                else:
                    return -sz

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_groq_size_sort_key)
                all_models = [preferred] + other_models
            else:
                valid_models.sort(key=_groq_size_sort_key)
                all_models = valid_models

            for idx, model in enumerate(all_models):
                # Em strict_mode com modelo ESPECÍFICO, pula os outros modelos.
                if strict_mode and preferred and not preferred_is_provider_name and model != preferred:
                    continue

                # Verifica se o modelo suporta o tamanho do contexto
                ctx_limit = _MODEL_CONTEXT_LIMITS.get(model)
                if ctx_limit and estimated_tokens > ctx_limit:
                    log.warning("agent.llm.context_overflow",
                                model=model, estimated=estimated_tokens, limit=ctx_limit)
                    last_err = f"{model} contexto muito grande ({estimated_tokens} > {ctx_limit} tokens)"
                    if pending_events is not None:
                        pending_events.append({
                            "type": "context_overflow",
                            "provider": "groq",
                            "model": model,
                            "estimated_tokens": estimated_tokens,
                            "limit": ctx_limit,
                        })
                    continue

                _rl_key = f"groq:{model}"
                can_go, wait = _pre_call_check(model, estimated_tokens, pending_events, _rl_key, provider="groq")
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                is_last_model = (idx == len(all_models) - 1)
                max_retries = 3 if strict_mode else 1
                current_msgs = oai_msgs  # pode ser truncado em 413
                for attempt in range(1, max_retries + 1):
                    try:
                        resp = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            json={"model": model, "max_tokens": 4096, "temperature": 0.1,
                                  "messages": current_msgs, "tools": oai_tools, "tool_choice": "auto"},
                            headers=headers, timeout=120.0 if strict_mode else 20.0,
                        )
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(5)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key, None)
                        data = resp.json()
                        real_tokens = (data.get("usage") or {}).get("total_tokens", 0)
                        _post_call_record(model, real_tokens)
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": "groq", "model": model})
                        res = _response_from_openai(data)
                        res["_successful_provider"] = "groq"
                        res["_successful_model"] = model
                        return res

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key, retry_after)
                        last_err = f"rate_limit {model}"
                        if attempt < max_retries:
                            import asyncio
                            _wait = min(retry_after or 15, 15)
                            log.warning("agent.llm.retry_wait", model=model,
                                        wait_sec=_wait, attempt=attempt)
                            if pending_events is not None:
                                pending_events.append({"type": "rate_wait", "provider": "groq", "model": model, "wait_sec": _wait, "reason": "RPM"})
                            await asyncio.sleep(_wait)
                            continue
                        break

                    if resp.status_code == 413:
                        # Contexto muito grande — trunca e retenta uma vez
                        if len(current_msgs) > 4:
                            current_msgs = [current_msgs[0]] + current_msgs[-3:]
                            continue
                        last_err = f"groq 413: contexto muito grande para {model}"
                        break

                    if resp.status_code == 400:
                        body_lower = resp.text.lower()
                        if "decommissioned" in body_lower or "deprecated" in body_lower or "not found" in body_lower:
                            last_err = f"groq model decommissioned: {model}"
                            break
                    if resp.status_code in (500, 502, 503, 504):
                        last_err = f"groq HTTP {resp.status_code} (transitório)"
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(3 * attempt)
                            continue
                        break
                    last_err = f"groq HTTP {resp.status_code}: {resp.text[:100]}"
                    break

            # Se todos os modelos falharam para Groq, coloca o provedor em cooldown
            from services.ai.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until["groq"] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider="groq", reason=f"all_models_failed (last: {last_err})")

        # ── Gemini ────────────────────────────────────────────────────────
        elif provider.name == "gemini":
            key = settings.GEMINI_API_KEY
            if not key:
                continue
            
            _DEPRECATED_GEMINI = {"gemini-flash-latest", "gemini-1.5-flash", "gemini-2.0-flash-exp", "gemini-2.0-pro-exp"}
            _DEFAULT_GEMINI = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
            all_models = [m for m in (settings.ai_gemini_models_list or []) if m not in _DEPRECATED_GEMINI] or _DEFAULT_GEMINI
            gemini_tools = _tools_to_gemini(tools)
            gemini_msgs = _messages_to_gemini(messages)
            
            _gemini_msgs_for_count = [{"role": "system", "content": system}] + \
                                      [{"role": "user", "content": str(m.get("parts", [{}])[0].get("text", "")
                                                                       if isinstance(m, dict) else "")}
                                       for m in gemini_msgs]
            estimated_tokens_gemini = _count_tokens(_gemini_msgs_for_count)

            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            from services.ai.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in all_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens_gemini > ctx_limit:
                    log.warning("agent.gemini.context_limit_skipped", model=m, estimated=estimated_tokens_gemini, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = all_models

            def _gemini_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                if estimated_tokens_gemini < 15_000:
                    return sz
                elif estimated_tokens_gemini < 100_000:
                    if sz == 2: return 0
                    if sz == 1: return 1
                    return 2
                else:
                    return -sz

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_gemini_size_sort_key)
                models = [preferred] + other_models
            else:
                valid_models.sort(key=_gemini_size_sort_key)
                models = valid_models

            payload = {
                "contents": gemini_msgs,
                "systemInstruction": {"parts": [{"text": system}]},
                "tools": gemini_tools,
                "generationConfig": {
                    "temperature": 0.1,
                }
            }

            for model in models:
                _rl_key = f"gemini:{model}"

                can_go, wait = _pre_call_check(model, estimated_tokens_gemini, pending_events, _rl_key, provider="gemini")
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                max_retries = 3 if strict_mode else 1
                for attempt in range(1, max_retries + 1):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    try:
                        resp = await client.post(url, json=payload, timeout=120.0 if strict_mode else 20.0)
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key, None)
                        data = resp.json()
                        usage = data.get("usageMetadata") or {}
                        real_tokens = usage.get("totalTokenCount", 0)
                        _post_call_record(model, real_tokens)
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": "gemini", "model": model})
                        res = _response_from_gemini(data)
                        res["_successful_provider"] = "gemini"
                        res["_successful_model"] = model
                        return res

                    if resp.status_code == 429:
                        last_err = f"rate_limit {model}"
                        body_text = resp.text[:500].lower() if hasattr(resp, "text") else ""
                        is_daily_quota = "daily" in body_text or "daily limit" in body_text
                        if is_daily_quota:
                            log.warning("agent.llm.quota_exhausted", provider="gemini", model=model)
                            _agent_rate_limited_until[_rl_key] = _time.monotonic() + 3600
                            # Marca RPD como esgotado
                            rpd_limit = _get_rpd(model) or 1500
                            global _rpd_date, _rpd_tracker
                            _rpd_tracker[model] = rpd_limit
                            _save_rate_state()
                            break
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key, retry_after)
                        if attempt < max_retries:
                            import asyncio
                            _wait = min(retry_after or 10, 15)
                            log.warning("agent.llm.retry_wait", provider="gemini", model=model,
                                        wait_sec=_wait, attempt=attempt)
                            if pending_events is not None:
                                pending_events.append({"type": "rate_wait", "provider": "gemini", "model": model, "wait_sec": _wait, "reason": "RPM"})
                            await asyncio.sleep(_wait)
                            continue
                        break

                    if resp.status_code in (500, 502, 503, 504):
                        last_err = f"gemini HTTP {resp.status_code} (transitório)"
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break
                    last_err = f"gemini HTTP {resp.status_code}: {resp.text[:100]}"
                    break

                if strict_mode and "rate_limit" in last_err:
                    break

            # Se todos os modelos falharam para Gemini, coloca o provedor em cooldown
            from services.ai.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until["gemini"] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider="gemini", reason=f"all_models_failed (last: {last_err})")

        # ── Providers OpenAI-compat extras (SambaNova, DeepSeek, Cerebras) ──────
        elif provider.name in ("sambanova", "deepseek", "cerebras", "ollama"):
            _prov_cfg = {
                "sambanova": {
                    "key_fn": lambda: settings.SAMBANOVA_API_KEY,
                    "url": "https://api.sambanova.ai/v1/chat/completions",
                    "models_fn": lambda: settings.ai_sambanova_models_list,
                },
                "deepseek": {
                    "key_fn": lambda: settings.DEEPSEEK_API_KEY,
                    "url": "https://api.deepseek.com/v1/chat/completions",
                    "models_fn": lambda: settings.ai_deepseek_models_list,
                },
                "cerebras": {
                    "key_fn": lambda: settings.CEREBRAS_API_KEY,
                    "url": "https://api.cerebras.ai/v1/chat/completions",
                    "models_fn": lambda: settings.ai_cerebras_models_list,
                },
                "ollama": {
                    "key_fn": lambda: "ollama",
                    "url": "http://localhost:11434/api/chat",
                    "models_fn": lambda: settings.ai_ollama_models_list,
                    "timeout": 300.0,
                    "native": True,  # usa API nativa Ollama (não OpenAI-compat)
                },
            }[provider.name]

            prov_key = _prov_cfg["key_fn"]()
            if not prov_key:
                continue

            prov_headers = {"Authorization": f"Bearer {prov_key}", "content-type": "application/json"}
            prov_msgs = [{"role": "system", "content": system}] + _messages_to_openai(messages)
            oai_tools_prov = _tools_to_openai(tools)
            estimated_tokens_prov = _count_tokens(prov_msgs, oai_tools_prov)

            prov_models = _prov_cfg["models_fn"]() or []
            
            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            from services.ai.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in prov_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens_prov > ctx_limit:
                    log.warning(f"agent.{provider.name}.context_limit_skipped", model=m, estimated=estimated_tokens_prov, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = prov_models

            def _prov_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                if estimated_tokens_prov < 15_000:
                    return sz
                elif estimated_tokens_prov < 100_000:
                    if sz == 2: return 0
                    if sz == 1: return 1
                    return 2
                else:
                    return -sz

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_prov_size_sort_key)
                prov_models = [preferred] + other_models
            else:
                valid_models.sort(key=_prov_size_sort_key)
                prov_models = valid_models

            for idx_p, model in enumerate(prov_models):
                _rl_key_p = f"{provider.name}:{model}"

                # Pula modelos que estão atualmente em cooldown de rate-limit (429) para evitar retentativas inúteis, exceto no strict_mode
                if not strict_mode and time.monotonic() < _agent_rate_limited_until.get(_rl_key_p, 0.0):
                    log.info("agent.llm.model_cooldown_skipped", provider=provider.name, model=model)
                    continue

                ctx_limit = _MODEL_CONTEXT_LIMITS.get(model)
                if ctx_limit and estimated_tokens_prov > ctx_limit:
                    last_err = f"{model} contexto muito grande ({estimated_tokens_prov} > {ctx_limit})"
                    if pending_events is not None:
                        pending_events.append({"type": "context_overflow", "provider": provider.name, "model": model,
                                               "estimated_tokens": estimated_tokens_prov, "limit": ctx_limit})
                    continue

                can_go, wait = _pre_call_check(model, estimated_tokens_prov, pending_events, _rl_key_p, provider=provider.name)
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                is_last = (idx_p == len(prov_models) - 1)
                cur_msgs = prov_msgs
                max_retries = 3 if strict_mode else 1
                is_ollama_native = _prov_cfg.get("native", False)
                ollama_msgs = _messages_to_ollama_native(system, messages) if is_ollama_native else None
                for attempt in range(1, max_retries + 1):
                    try:
                        if is_ollama_native:
                            # Ollama native API — usa /api/chat com options.num_gpu=0 (forçar CPU)
                            ollama_tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {})}} for t in tools]
                            req_payload: dict = {"model": model, "messages": ollama_msgs, "stream": False,
                                                 "options": {"num_gpu": 0, "temperature": 0.1}}
                            if ollama_tools:
                                req_payload["tools"] = ollama_tools
                            resp = await client.post(
                                _prov_cfg["url"],
                                json=req_payload,
                                timeout=120.0 if strict_mode else (60.0 if provider.name == "ollama" else 20.0),
                            )
                        else:
                            req_payload = {
                                "model": model,
                                "max_tokens": 4096,
                                "temperature": 0.1,
                                "messages": cur_msgs,
                                "tools": oai_tools_prov,
                                "tool_choice": "auto"
                            }
                            req_headers = dict(prov_headers)
                            if provider.name == "cerebras":
                                if "max_completion_tokens" not in req_payload and "max_tokens" not in req_payload:
                                    req_payload["max_completion_tokens"] = 4096
                                if "gpt-oss-120b" in model:
                                    req_payload["reasoning_effort"] = "high" if strict_mode else "medium"
                                elif "zai-glm-4.7" in model:
                                    req_payload["clear_thinking"] = True
                                if "service_tier" not in req_payload:
                                    req_payload["service_tier"] = "auto"
                                req_headers["queue_threshold"] = "15000"
                                req_headers["Cerebras-Queue-Threshold"] = "15000"

                            resp = await client.post(
                                _prov_cfg["url"],
                                json=req_payload,
                                headers=req_headers,
                                timeout=120.0 if strict_mode else 20.0,
                            )
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key_p, None)
                        data = resp.json()
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": provider.name, "model": model})
                        if is_ollama_native:
                            # Converte resposta nativa Ollama para formato interno
                            msg = data.get("message", {})
                            tcs = msg.get("tool_calls") or []
                            oai_tcs = []
                            for tc in tcs:
                                fn = tc.get("function", {})
                                args = fn.get("arguments", {})
                                oai_tcs.append({"id": f"call_{uuid.uuid4().hex[:8]}", "type": "function",
                                                "function": {"name": fn.get("name", ""),
                                                             "arguments": json.dumps(args) if isinstance(args, dict) else args}})
                            openai_fmt = {"choices": [{"message": {"content": msg.get("content"), "tool_calls": oai_tcs},
                                                       "finish_reason": "tool_calls" if oai_tcs else "stop"}]}
                            real_tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
                            _post_call_record(model, real_tokens)
                            res = _response_from_openai(openai_fmt)
                            res["_successful_provider"] = provider.name
                            res["_successful_model"] = model
                            return res
                        real_tokens = (data.get("usage") or {}).get("total_tokens", 0)
                        _post_call_record(model, real_tokens)
                        res = _response_from_openai(data)
                        res["_successful_provider"] = provider.name
                        res["_successful_model"] = model
                        return res

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key_p, retry_after)
                        last_err = f"rate_limit {model}"
                        if attempt < max_retries:
                            import asyncio
                            wait = min(retry_after or 10, 15)
                            log.warning("agent.llm.retry_wait", provider=provider.name, model=model,
                                        wait_sec=wait, attempt=attempt)
                            if pending_events is not None:
                                pending_events.append({"type": "rate_wait", "provider": provider.name, "model": model, "wait_sec": wait, "reason": "RPM"})
                            await asyncio.sleep(wait)
                            continue
                        break

                    if resp.status_code in (401, 402, 403):
                        last_err = f"{provider.name} sem crédito/chave (HTTP {resp.status_code})"
                        break

                    if resp.status_code == 413:
                        if len(cur_msgs) > 4:
                            cur_msgs = [cur_msgs[0]] + cur_msgs[-3:]
                            continue
                        last_err = f"{provider.name} 413: contexto muito grande para {model}"
                        break

                    if resp.status_code in (500, 502, 503, 504):
                        last_err = f"{provider.name} HTTP {resp.status_code} (transitório)"
                        if attempt < max_retries - 1:
                            import asyncio
                            await asyncio.sleep(3)
                            continue
                        break

                    last_err = f"{provider.name} HTTP {resp.status_code}: {resp.text[:100]}"
                    break

            # Se todos os modelos falharam para este provedor extra, coloca-o em cooldown
            from services.ai.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until[provider.name] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider=provider.name, reason="all_models_failed")

    raise RuntimeError(f"Todos os providers falharam: {last_err}")


# ── Thinking pós-decisão — gerado DEPOIS de saber qual ferramenta será chamada ─

_TOOL_THINKING_SYSTEM = """Você é o Agente de Investigação Comercial LinkB2B narrando sua investigação em voz alta.

Você receberá:
- OBJETIVO: o que o usuário perguntou
- ENCONTRADO ATÉ AGORA: resumo do que cada ferramenta já retornou (esta é a única fonte de dados reais!)
- PRÓXIMA AÇÃO: qual ferramenta vai ser usada agora

Escreva 2-4 frases que demonstrem RACIOCÍNIO INVESTIGATIVO real:

1. Referencie o objetivo do usuário com a empresa específica.
2. Conecte o que foi encontrado: compare dados de fontes diferentes, note inconsistências, destaque o que é relevante para o objetivo.
3. Se cabível, questione discrepâncias entre o Pipedrive e as mensagens.
4. Explique por que a próxima ferramenta é a escolha certa AGORA — baseado nos dados reais, não em ordem genérica.

EXEMPLOS DE RACIOCÍNIO ESPERADO (USE APENAS COMO REFERÊNCIA DE ESTILO, NUNCA COPIE OS NOMES OU DADOS DOS EXEMPLOS):
- "legal, o Pipedrive tem 2 atividades pendentes — uma delas menciona que o cliente enviou proposta em fevereiro. Isso é interessante porque ainda não confirmei se houve resposta, então vou verificar o e-mail do contato principal para cruzar com a tarefa."
- "curioso: o deal está aberto mas sem valor e sem funil definido. Ainda não temos contatos cadastrados no CRM, então vou buscar as mensagens do WhatsApp da empresa para entender se o negócio avançou além do Pipedrive."
- "encontrei 6 e-mails sobre homologação de embalagens com o contato, mas nenhuma mensagem no WhatsApp. Isso confirma que a comunicação foi por e-mail. Vou agora verificar se há outras pessoas envolvidas no histórico."

REGRAS ABSOLUTAS:
- NUNCA use nomes, datas ou dados dos exemplos (como "Wesley Pinheiro", "Pedro", "Bottcher", "15 de março") se eles não estiverem explicitamente listados nos dados REAIS da seção "ENCONTRADO ATÉ AGORA" do caso atual.
- Se não houver contatos ou nomes de pessoas nos dados reais (ENCONTRADO ATÉ AGORA), NUNCA invente nomes de pessoas ou contatos. Refira-se apenas à empresa ou diga que não há contatos cadastrados.
- A instrução de "citar nomes reais" aplica-se APENAS se os nomes reais estiverem presentes nos dados fornecidos na seção "ENCONTRADO ATÉ AGORA". Caso contrário, não use nenhum nome próprio de contato.
- Termine com ponto final.
- Não sugira ações comerciais."""


async def _generate_tool_thinking(
    tool_name: str,
    tool_args: dict,
    messages: list,
    skip_groq: bool = False,
    skip_cerebras: bool = False,
) -> str:
    """
    Gera raciocínio narrativo DEPOIS de saber qual ferramenta será executada.
    Isso garante que o thinking seja sempre consistente com a ação real do agente.

    skip_groq=True quando o modelo principal já é Groq — evita dobrar o consumo
    de quota do Groq free tier usando Groq-8b também para thinking.

    Ordem de qualidade: Gemini Flash → Cerebras → Groq 8b (se skip_groq=False).
    Retorna "" em caso de falha — o loop usa _get_label como fallback.
    """
    from core.config import settings
    from core.http_client import get_http_client

    client = get_http_client()

    # Constrói resumo estruturado: objetivo + o que cada ferramenta encontrou
    # Isso dá ao modelo de thinking um mapa claro para cross-referenciar,
    # em vez de JSON cru que ele não consegue sintetizar.
    tool_label = _get_label(tool_name, tool_args)

    user_objective = ""
    findings_lines: list[str] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Primeira mensagem de texto do usuário = objetivo original
        if role == "user" and isinstance(content, str) and not user_objective and len(content) < 300:
            user_objective = content.strip()

        # Resultados de ferramentas = o que foi encontrado
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                tn = item.get("tool_name", "")
                tc = str(item.get("content", ""))
                if not tn:
                    continue
                # Para ferramentas de comunicação, inclui mais linhas — o modelo
                # de thinking precisa do conteúdo real para raciocinar, não só o cabeçalho
                if tn in ("email_get_contact_history", "whatsapp_get_messages"):
                    relevant = "\n  ".join(
                        l.strip() for l in tc.split("\n")[:6] if l.strip()
                    )[:400]
                else:
                    relevant = tc.split("\n")[0].strip()[:200]
                findings_lines.append(f"• {tn}: {relevant}")

    # Mantém apenas as últimas 8 descobertas para não sobrecarregar o contexto
    findings_summary = "\n".join(findings_lines[-8:]) if findings_lines else "Nenhuma ferramenta executada ainda."

    context_prompt = (
        f"OBJETIVO: {user_objective or 'não identificado'}\n\n"
        f"ENCONTRADO ATÉ AGORA:\n{findings_summary}\n\n"
        f"PRÓXIMA AÇÃO: {tool_label} ({tool_name})"
    )

    thinking_msgs = [
        {"role": "system", "content": _TOOL_THINKING_SYSTEM},
        {"role": "user", "content": context_prompt},
    ]

    # Providers em ordem de qualidade de raciocínio (não apenas velocidade)
    candidates: list[tuple[str, str, str, str]] = []
    if settings.GEMINI_API_KEY and settings.ai_gemini_models_list:
        # Gemini tem melhor raciocínio contextual para thinking
        candidates.append((
            "gemini",
            settings.GEMINI_API_KEY,
            "",  # URL dinâmica para Gemini
            settings.ai_gemini_models_list[0],  # modelo preferencial de alta disponibilidade da lista
        ))
    if settings.CEREBRAS_API_KEY and settings.ai_cerebras_models_list and not skip_cerebras:
        candidates.append((
            "cerebras",
            settings.CEREBRAS_API_KEY,
            "https://api.cerebras.ai/v1/chat/completions",
            settings.ai_cerebras_models_list[0],
        ))
    if settings.GROQ_API_KEY and not skip_groq:
        candidates.append((
            "groq",
            settings.GROQ_API_KEY,
            "https://api.groq.com/openai/v1/chat/completions",
            "llama-3.1-8b-instant",
        ))

    for prov_name, api_key, url, model in candidates:
        _rl_key = f"{prov_name}:{model}"
        if _time.monotonic() < _agent_rate_limited_until.get(_rl_key, 0):
            continue
        try:
            if prov_name == "gemini":
                gemini_url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={api_key}"
                )
                gemini_msgs = [
                    {"role": "user" if m["role"] != "assistant" else "model",
                     "parts": [{"text": m["content"]}]}
                    for m in thinking_msgs
                    if m["role"] != "system"
                ]
                system_text = next(
                    (m["content"] for m in thinking_msgs if m["role"] == "system"), ""
                )
                resp = await client.post(
                    gemini_url,
                    json={
                        "contents": gemini_msgs,
                        "systemInstruction": {"parts": [{"text": system_text}]},
                        "generationConfig": {"maxOutputTokens": 250, "temperature": 0.2},
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    parts = (
                        resp.json()
                        .get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])
                    )
                    text = "".join(p.get("text", "") for p in parts).strip()
                    if text:
                        return text
                if resp.status_code == 429:
                    _agent_rate_limited_until[_rl_key] = _time.monotonic() + 60
            else:
                req_payload = {
                    "model": model,
                    "max_tokens": 250,
                    "temperature": 0.2,
                    "messages": thinking_msgs
                }
                req_headers = {
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json"
                }
                if prov_name == "cerebras":
                    # Imposição de limite de tokens preventiva (Evita erro 429 defensivo por alocação MSL)
                    if "max_completion_tokens" not in req_payload and "max_tokens" not in req_payload:
                        req_payload["max_completion_tokens"] = 250
                    if "gpt-oss-120b" in model:
                        req_payload["reasoning_effort"] = "medium"
                    elif "zai-glm-4.7" in model:
                        req_payload["clear_thinking"] = True
                    if "service_tier" not in req_payload:
                        req_payload["service_tier"] = "auto"
                    req_headers["queue_threshold"] = "15000"
                    req_headers["Cerebras-Queue-Threshold"] = "15000"

                resp = await client.post(
                    url,
                    json=req_payload,
                    headers=req_headers,
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    text = (
                        resp.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if text:
                        return text
                if resp.status_code == 429:
                    _agent_rate_limited_until[_rl_key] = _time.monotonic() + 60
        except Exception as e:
            log.warning("agent.llm.thinking_aux_error", provider=prov_name, model=model, error=str(e))
            pass

    return ""


def _build_phase_status(messages: list) -> str:
    """
    Constrói o system prompt completo para a fase atual da investigação.
    Cada fase inclui todas as instruções comportamentais relevantes para ela —
    sem enviar o que não é necessário naquele momento.
    Fase 1 ~80 tokens, Fase 2 ~120, Fase 3 ~200, Fase 4 ~150.
    Fallback: SYSTEM_PROMPT_POWERFUL completo se qualquer exceção ocorrer.
    """
    import re as _re

    today = datetime.now().strftime('%Y-%m-%d')

    # ── Extrai estado da investigação ────────────────────────────────────────
    tools_called: set[str] = set()   # todas as ferramentas já chamadas
    contacts_found: list[str] = []   # contatos encontrados no pipedrive_get_persons
    org_name: str = ""
    whatsapp_searched: set[str] = set()
    email_searched: set[str] = set()

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # ── Lê ARGS das tool_use blocks (mensagens do assistente)
        # Mais confiável que parsear o resultado — captura o que FOI pedido.
        # Também popula tools_called para rastrear fase mesmo se o tool_result for truncado.
        if role == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tn = block.get("name", "")
                if tn:
                    tools_called.add(tn)
                args = block.get("input") or {}
                if tn == "pipedrive_get_org" and args.get("org_name"):
                    org_name = args["org_name"].strip()
                if tn == "whatsapp_get_messages" and args.get("contact"):
                    whatsapp_searched.add(args["contact"].lower())
                if tn == "email_get_contact_history":
                    name = args.get("contact_name") or args.get("org_name") or ""
                    if name:
                        email_searched.add(name.lower())

        # ── Lê RESULTADOS das tool_result blocks (mensagens do user/tool)
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            tn = item.get("tool_name", "")
            tc = str(item.get("content", ""))
            if not tn:
                continue

            tools_called.add(tn)

            if tn == "pipedrive_get_org" and not org_name:
                m_sum = _re.search(r'"summary"\s*:\s*"([^|]+)\|', tc)
                if m_sum:
                    org_name = m_sum.group(1).strip()
                if not org_name:
                    m_name = _re.search(r'"name"\s*:\s*"([^"]+)"', tc)
                    if m_name:
                        org_name = m_name.group(1).strip()
                if not org_name:
                    m_org = _re.search(r'🏢 ORG:\s*([^\n\\]+)', tc)
                    if m_org:
                        org_name = m_org.group(1).strip()

            # Extrai TODOS os contatos do resultado de pipedrive_get_persons
            if tn == "pipedrive_get_persons" and not contacts_found:
                parsed_ok = False
                try:
                    import json as _json
                    data = _json.loads(tc)
                    persons_list = data.get("persons", []) if isinstance(data, dict) else []
                    for p in persons_list:
                        if isinstance(p, dict) and p.get("name"):
                            name = p["name"].strip()
                            name_lower = name.lower()
                            is_company = any(suffix in name_lower for suffix in [
                                "gmbh", "ltda", "s.a", "sa", "participaco", "participaço", 
                                "holding", "corp", "s/a", "industria", "indústria", 
                                "comercio", "comércio", "servico", "serviço", "eireli", 
                                "me", "epp", "grupo"
                            ])
                            if is_company:
                                continue
                            if name and name not in contacts_found:
                                contacts_found.append(name)
                    parsed_ok = len(contacts_found) > 0
                except Exception:
                    pass

                if not parsed_ok:
                    import unicodedata as _uc
                    def _strip_acc(s: str) -> str:
                        return "".join(c for c in _uc.normalize("NFD", s.lower()) if _uc.category(c) != "Mn")

                    raw = tc
                    names = _re.findall(
                        r'([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][a-záéíóúãõâêîôûç]+)*)',
                        raw,
                    )
                    # Normaliza org_name SEM acento para comparação robusta
                    org_words_norm = set(_strip_acc(org_name or "").split())
                    for n in names:
                        n_lower = n.lower()
                        is_company = any(suffix in n_lower for suffix in [
                            "gmbh", "ltda", "s.a", "sa", "participaco", "participaço", 
                            "holding", "corp", "s/a", "industria", "indústria", 
                            "comercio", "comércio", "servico", "serviço", "eireli", 
                            "me", "epp", "grupo"
                        ])
                        if is_company:
                            continue
                        n_words_norm = set(_strip_acc(n).split())
                        stopwords_ext = {"do", "da", "de", "dos", "das", "ltda", "sa", "s.a", "cia"}
                        # Descarta se for o nome da org (comparação sem acento)
                        if not n_words_norm.issubset(org_words_norm | stopwords_ext):
                            if n not in contacts_found:
                                contacts_found.append(n)
                contacts_found = contacts_found[:15]

            # Rastreia WhatsApp por resultado (fallback quando args não disponíveis)
            if tn == "whatsapp_get_messages" and not any(True for _ in []):
                m = _re.search(
                    r'(?:mensagens\s+com|com)\s+([A-Za-záéíóúãõâêîôûç][^\-·\n]{2,40})',
                    tc, _re.IGNORECASE
                )
                if m:
                    whatsapp_searched.add(m.group(1).strip().lower())

            # Rastreia email por resultado (fallback)
            if tn == "email_get_contact_history" or tn == "email_get_inbox":
                m = _re.search(
                    r'(?:e-mails?\s+(?:\w+\s+)?(?:para|encontrados\s+para)|histórico\s+para)\s+'
                    r'([A-Za-záéíóúãõâêîôûç][^\n·\(]{2,50})',
                    tc, _re.IGNORECASE
                )
                if m:
                    email_searched.add(m.group(1).strip().lower())

    # ── Helpers ──────────────────────────────────────────────────────────────
    import unicodedata as _uc2
    def _norm_acc(s: str) -> str:
        """Remove diacríticos e converte para minúsculas para comparação fuzzy."""
        return "".join(c for c in _uc2.normalize("NFD", s.lower()) if _uc2.category(c) != "Mn")

    def _searched(name: str, done: set[str]) -> bool:
        """Fuzzy match insensível a acentos — 'Ápice' == 'Apice', 'Wesley' == 'wesley'."""
        nl = _norm_acc(name)
        done_norm = {_norm_acc(d) for d in done}
        words = nl.split()
        if not words:
            return False
        return (
            nl in done_norm
            or words[0] in done_norm
            or any(words[0] in d or d in nl for d in done_norm)
        )

    # ── Determina fase ───────────────────────────────────────────────────────
    if "pipedrive_get_all_activities" in tools_called:
        tools_called.add("pipedrive_get_activities")
        
    _pd_required = {"pipedrive_get_org", "pipedrive_get_persons",
                    "pipedrive_get_deals", "pipedrive_get_activities"}
    pipedrive_complete = _pd_required.issubset(tools_called)

    # ── OTIMIZAÇÃO DE TOKENS E ITERAÇÕES (FOCO NO CONTATO ATIVO & RECOMENDAÇÕES) ──
    active_contacts = set()
    referred_contacts = set()

    def _extract_referrals(text: str) -> list[str]:
        import re
        if not text:
            return []
        # Padrões para detectar indicações: "fale com X", "falar com X", "indico o X", etc.
        patterns = [
            r'(?:fale|falar|tratar|contato|chame|procure|indico|indicação|recomendo|conversar)\s+(?:com|o|a|com\s+o|com\s+a|direto\s+com)?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)',
            r'falar\s+direto\s+com\s+([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)'
        ]
        referrals = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                name = m.strip()
                if len(name) > 2 and name.lower() not in ['para', 'como', 'esta', 'esse', 'essa', 'quem', 'onde', 'quando', 'porque', 'orçamento', 'financeiro', 'comercial', 'compras', 'vendas', 'diretor', 'gerente', 'negócio', 'parceiro']:
                    if name not in referrals:
                        referrals.append(name)
        return referrals

    def _is_referred(contact_name: str, referred_names: set[str]) -> bool:
        cn_norm = _norm_acc(contact_name)
        cn_words = set(cn_norm.split())
        for r in referred_names:
            r_norm = _norm_acc(r)
            r_words = set(r_norm.split())
            if r_norm in cn_norm or cn_norm in r_norm or (r_words and r_words.issubset(cn_words)) or (cn_words and cn_words.issubset(r_words)):
                return True
        return False

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                tn = item.get("tool_name", "")
                tc = str(item.get("content", ""))
                if not tn or not tc:
                    continue

                if tn in ("whatsapp_get_messages", "email_get_contact_history"):
                    c_name = None
                    try:
                        import json as _json
                        data = _json.loads(tc)
                        if isinstance(data, dict):
                            c_name = data.get("contact") or data.get("contact_name")
                        elif isinstance(data, str):
                            # Tenta extrair de "💬 WHATSAPP (Contact):"
                            m_wa = _re.search(r'💬 WHATSAPP \(([^)]+)\):', data)
                            if m_wa:
                                c_name = m_wa.group(1).strip()
                            else:
                                # Tenta extrair de "📧 HISTÓRICO EMAIL (Contact):" ou do thread extractor
                                m_em = _re.search(r'📧 HISTÓRICO EMAIL \(([^)]+)\):', data)
                                if m_em:
                                    c_name = m_em.group(1).strip()
                                else:
                                    m_em2 = _re.search(r'📧 E-mails com ([^:\n]+):', data)
                                    if m_em2:
                                        c_name = m_em2.group(1).strip()
                                    else:
                                        # Fallback geral para thread summary que pode começar com "Thread com " ou similar
                                        m_em3 = _re.search(r'(?:Thread|E-mails|Mensagens)\s+(?:com|de|para)\s+([A-Za-záéíóúãõâêîôûç\s]{2,40})', data, _re.IGNORECASE)
                                        if m_em3:
                                            c_name = m_em3.group(1).strip()
                    except Exception:
                        pass

                    if not c_name:
                        # Tenta extrair a chave "contact" ou "contact_name" do JSON (mesmo que truncado)
                        m_json_c = _re.search(r'"(?:contact|contact_name)"\s*:\s*"([^"]+)"', tc)
                        if m_json_c:
                            c_name = m_json_c.group(1).strip()
                    if not c_name:
                        m_c = _re.search(r'(?:mensagens\s+com|com|para)\s+([A-Za-záéíóúãõâêîôûç\s]{2,40})', tc, _re.IGNORECASE)
                        if m_c:
                            c_name = m_c.group(1).strip()

                    if c_name:
                        c_name_lower = c_name.lower().strip()
                        has_active = False
                        msg_count = 0
                        has_reply = False
                        
                        try:
                            import json as _json
                            import ast
                            data = None
                            try:
                                data = _json.loads(tc)
                            except Exception:
                                try:
                                    data = ast.literal_eval(tc)
                                except Exception:
                                    pass
                                    
                            if isinstance(data, dict) and data.get("ok"):
                                msg_count = data.get("count", 0)
                                if tn == "whatsapp_get_messages":
                                    messages_list = data.get("messages", []) or []
                                    has_reply = any(isinstance(m, str) and not m.startswith("[Você]") and not m.startswith("[joao.moura") for m in messages_list)
                                    if msg_count >= 10 and has_reply:
                                        has_active = True
                                elif tn == "email_get_contact_history":
                                    if msg_count >= 3:
                                        has_active = True
                            elif isinstance(data, str):
                                # Se data for a string sanitizada!
                                lines = [l.strip() for l in data.split("\n") if l.strip()]
                                chat_lines = [l for l in lines if l.startswith("[")]
                                if tn == "whatsapp_get_messages":
                                    msg_count = len(chat_lines)
                                    if msg_count == 0:
                                        m_text_count = _re.search(r'(\d+)\s*(?:mensagens|conversas)', data, _re.IGNORECASE)
                                        if m_text_count:
                                            msg_count = int(m_text_count.group(1))
                                    has_reply = any(not any(x in l for x in ["[Você]", "[EU]", "[joao.moura"]) for l in chat_lines)
                                    if (msg_count >= 10 or len(lines) >= 8) and has_reply:
                                        has_active = True
                                elif tn == "email_get_contact_history":
                                    has_reply = "sem resposta" not in data.lower() and "nenhum e-mail" not in data.lower()
                                    if has_reply:
                                        has_active = True
                        except Exception:
                            pass

                        # Fallback robusto via Regex (para JSONs truncados ou formatados incorretamente)
                        if not has_active:
                            # 1. Tenta extrair o count do JSON (mesmo que truncado)
                            m_count = _re.search(r'"count"\s*:\s*(\d+)', tc)
                            if m_count:
                                msg_count = int(m_count.group(1))
                            else:
                                # Tenta buscar padrões como "34 mensagens" ou "12 e-mails" no texto
                                m_text_count = _re.search(r'(\d+)\s*(?:mensagens|e-mails|emails|conversas)', tc, _re.IGNORECASE)
                                if m_text_count:
                                    msg_count = int(m_text_count.group(1))
                                    
                            # 2. Busca se há resposta do contato externo (que não é Você ou joao.moura)
                            has_reply = bool(_re.search(r'\[(?!Você)(?!joao\.moura)[^\]]+\]:', tc))
                            
                            if tn == "whatsapp_get_messages":
                                if msg_count >= 10 and has_reply:
                                    has_active = True
                            elif tn == "email_get_contact_history":
                                if msg_count >= 3:
                                    has_active = True

                        if not has_active:
                            # Heurística textual como fallback final de salvaguarda
                            text_lower = tc.lower()
                            if "nenhum e-mail encontrado" not in text_lower and "0 e-mails" not in text_lower and "0 mensagens" not in text_lower and "não encontrado" not in text_lower and "sem histórico" not in text_lower:
                                # Se o texto for substancial (representando conversa madura ou truncado), aceita
                                if len(tc) > 800 or "truncado" in text_lower or tc.count("\n") > 10:
                                    has_active = True

                        if has_active:
                            for c in contacts_found:
                                if _norm_acc(c) == _norm_acc(c_name) or _searched(c, {c_name_lower}) or _norm_acc(c) in _norm_acc(c_name):
                                    active_contacts.add(c)

                        for ref in _extract_referrals(tc):
                            referred_contacts.add(ref)

                elif tn == "pipedrive_get_activities":
                    for ref in _extract_referrals(tc):
                        referred_contacts.add(ref)

    if active_contacts:
        optimized_contacts = []
        for c in contacts_found:
            if _searched(c, whatsapp_searched) or _searched(c, email_searched):
                optimized_contacts.append(c)
            elif _is_referred(c, referred_contacts):
                optimized_contacts.append(c)
        if not optimized_contacts:
            optimized_contacts = contacts_found
    else:
        optimized_contacts = contacts_found

    pending_wapp  = [c for c in optimized_contacts if not _searched(c, whatsapp_searched)]
    pending_email = [c for c in optimized_contacts if not _searched(c, email_searched)]
    org_wapp_done  = bool(org_name and _searched(org_name, whatsapp_searched))
    org_email_done = bool(org_name and _searched(org_name, email_searched))

    if active_contacts:
        comms_complete = (
            pipedrive_complete
            and not pending_wapp
            and not pending_email
        )
    else:
        comms_complete = (
            pipedrive_complete
            and not pending_wapp
            and not pending_email
            and (org_wapp_done or not org_name)
            and (org_email_done or not org_name)
        )
    dossier_done = "generate_dossier" in tools_called

    base = (
        f"Data: {today}. Agente de Investigação Comercial LinkB2B.\n"
        "REGRAS: (1) Uma ferramenta por turno — nunca duas. "
        "(2) Execute diretamente — nunca pergunte permissão. "
        "(3) whatsapp_get_messages e email_get_contact_history com o NOME DA PESSOA "
        "— NUNCA use whatsapp_list_chats ou email_get_inbox quando já tem o nome. "
        "(4) ANTES de cada ferramenta: escreva em linguagem natural o que o usuário quer, "
        "o que você já encontrou e por que esta ferramenta é o próximo passo. "
        "Cite nomes reais, datas e dados concretos do histórico. "
        "(5) IDENTIDADE: João Moura (joao.moura@jferres.com.br ou qualquer e-mail do domínio jferres.com.br) é o vendedor/remetente (você / o usuário do sistema). Ele NUNCA deve ser cadastrado ou sugerido como contato (person/lead) de nenhuma empresa no Pipedrive. Os contatos reais e leads são sempre os destinatários/interlocutores externos (ex: Lgustavo/Luis Gustavo)."
    )

    # ── Fase 1 — Início ───────────────────────────────────────────────────────
    if not tools_called:
        return base + "\n\nInício. Execute pipedrive_get_org agora."

    # ── Fase 2 — Mapeamento Pipedrive ────────────────────────────────────────
    if not pipedrive_complete:
        remaining = [t for t in [
            "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"
        ] if t not in tools_called]
        next_tool_line = f"\nPRÓXIMA FERRAMENTA: {remaining[0]}" if remaining else ""
        return (
            base
            + "\n\nFase: Mapeamento Pipedrive."
            + f" Faltam (nesta ordem): {' → '.join(remaining)}."
            + next_tool_line
            + "\nNÃO inicie WhatsApp/Email antes de concluir os 4 passos do Pipedrive."
        )

    # ── Fase 3 — Investigação de comunicação ─────────────────────────────────
    if not comms_complete:
        # Determina exatamente qual é a próxima ferramenta a chamar
        if pending_wapp:
            next_action = f"PRÓXIMA FERRAMENTA: whatsapp_get_messages com contact='{pending_wapp[0]}'"
        elif pending_email:
            next_action = f"PRÓXIMA FERRAMENTA: email_get_contact_history com contact_name='{pending_email[0]}'"
        elif not org_wapp_done and org_name:
            next_action = f"PRÓXIMA FERRAMENTA: whatsapp_get_messages com contact='{org_name}'"
        elif not org_email_done and org_name:
            next_action = f"PRÓXIMA FERRAMENTA: email_get_contact_history com org_name='{org_name}'"
        else:
            next_action = "PRÓXIMA FERRAMENTA: whatsapp_get_messages ou email_get_contact_history para contatos restantes"

        # Lista completa de pendências para contexto
        pending_parts = []
        if pending_wapp:
            pending_parts.append(f"WhatsApp de: {', '.join(pending_wapp)}")
        if pending_email:
            pending_parts.append(f"Email de: {', '.join(pending_email)}")
        if not org_wapp_done and org_name:
            pending_parts.append(f"WhatsApp pela empresa '{org_name}'")
        if not org_email_done and org_name:
            pending_parts.append(f"Email pela empresa '{org_name}'")
        pending_str = "; ".join(pending_parts) if pending_parts else "verificar contatos da organização"

        return (
            base
            + f"\n\nFase: Investigação de comunicação."
            + f"\nPendente: {pending_str}."
            + f"\n{next_action}."
            + "\n\nPROIBIDO: não chame pipedrive_get_all_activities (busca TODAS as empresas)."
            + " PROIBIDO: não use ferramentas de escrita (email_send, whatsapp_send_message) antes de completar a investigação."
            + " PROIBIDO: não use web_search_external durante investigação de empresa, EXCETO como último recurso para descobrir o domínio do site/e-mail caso não encontre contatos."
            + "\nPROIBIDO: NUNCA passe nomes de negócios (Deals) ou emojis nos campos de contato. Use APENAS o nome exato da empresa ou da pessoa."
            + "\n\nPRIORIDADE: examine as atividades para decidir a ordem. Se uma tarefa menciona 'fale com X' ou 'aguardando Y': essa pessoa vem antes."
            + "\nFOCO EXCLUSIVO NO CONTATO ATIVO (REGRA DE OURO): Se você identificar que as comunicações ativas da empresa estão sendo centralizadas em um interlocutor específico (ex: Gabriel, com mais de 10 mensagens no WhatsApp ou e-mails maduros), você deve focar EXCLUSIVAMENTE nele. NÃO gaste tokens nem tempo de execução buscando ou investigando contatos inativos/periféricos (como Gustavo, WOLDASCH, Wagner etc.), exceto se o contato ativo o recomendou explicitamente. Se o contato ativo já resolve o histórico, encerre as buscas adicionais e chame 'generate_dossier' imediatamente."
            + "\nRADAR: ao ler conversas, se aparecer nome novo, investigue também — mesmo fora do Pipedrive."
            + "\nCROSS-VALIDAÇÃO: compare Pipedrive com comunicações — aponte discrepâncias de datas, status ou pessoas não cadastradas."
        )

    # ── Fase 3b — Aguardando generate_dossier ────────────────────────────────
    if not dossier_done:
        return (
            base
            + "\n\nTodas as fontes foram investigadas. Chame generate_dossier agora."
        )

    # ── Fase 4 — Dossiê final ─────────────────────────────────────────────────
    return (
        base
        + "\n\nFase final. A investigação terminou. Escreva APENAS o Dossiê Final em texto corrido "
        "(parágrafos, sem bullets, sem emojis), contendo:"
        "\n1. Resumo do negócio: o que diz o Pipedrive (deal, valor, funil)."
        "\n2. Histórico de comunicação: o que foi falado exatamente (assuntos, nomes, datas, quem disse o quê)."
        "\n3. Situação real: status atual cruzando CRM com comunicações."
        "\n\nREGRAS:"
        "\n- NÃO escreva 'Ações Sugeridas:', 'Próximos Passos:' ou qualquer lista de ações — isso vem em seguida automaticamente."
        "\n- NÃO chame nenhuma ferramenta agora. Apenas escreva o dossiê."
        "\n- Finalize no ponto 3."
    )


def _suggest_actions_done(messages: list) -> bool:
    """Retorna True se suggest_next_actions já foi chamado em alguma mensagem do histórico."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_use" and block.get("name") == "suggest_next_actions":
                    return True
    return False


async def _agent_loop(
    messages: list,
    tools: list,
    start_iteration: int = 0,
    org_id: int | None = None,
    preferred: str | None = None,
    strict_mode: bool = False,
    process_id: str | None = None,
    direct_action: bool = False,
    parent_message_id: str | None = None,
    action_index: int | None = None,
) -> AsyncGenerator[str, None]:
    """Loop central do agente. Yields eventos NDJSON."""
    import re as _re
    process_id = process_id or f"proc_{uuid.uuid4().hex[:8]}"

    # Acumula resultados de ferramentas para degradação graciosa
    _collected_tool_summaries: list[str] = []
    # Garante que o evento final seja emitido apenas uma vez (dossiê)
    _final_emitted = False
    _max_iters = 6 if direct_action else MAX_ITERATIONS

    # Ferramentas cujos resultados nunca devem ser descartados do histórico:
    # sem eles o modelo perde a lista de contatos e começa a repetir ou pular buscas.
    _PINNED_TOOLS = {
        "pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities",
        "whatsapp_get_messages", "email_get_contact_history"
    }

    def _is_pinned(msg: dict) -> bool:
        content = msg.get("content", "")
        if not isinstance(content, list):
            return False
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use" and item.get("name") in _PINNED_TOOLS:
                return True
            if item.get("tool_name") in _PINNED_TOOLS:
                return True
        return False

    for iteration in range(start_iteration, _max_iters):
        # Sai imediatamente se o dossiê foi emitido e suggest_actions já foi chamado
        if _final_emitted and _suggest_actions_done(messages):
            return

        # Controle de ritmo (pacing sleep) defensivo para evitar estouro de RPM/TPM no Cerebras/Groq
        if iteration > 0:
            import asyncio as _asyncio
            from core.config import settings as _s
            _is_rate_sensitive = False
            if preferred:
                pref_lower = preferred.lower()
                if "cerebras" in pref_lower or "groq" in pref_lower:
                    _is_rate_sensitive = True
                elif pref_lower in (_s.ai_cerebras_models_list or []) or pref_lower in (_s.ai_groq_models_list or []):
                    _is_rate_sensitive = True
            
            if _is_rate_sensitive:
                pacing_delay = 1.5 if strict_mode else 1.0
                log.info("agent.llm.pacing_delay", provider=preferred, seconds=pacing_delay, iteration=iteration)
                await _asyncio.sleep(pacing_delay)

        # Corte de memória inteligente: preserva resultados críticos (lista de contatos,
        # deals e atividades) independente da posição no histórico, para que o modelo
        # não perca o mapa de quem investigar nas iterações finais do fluxo sequencial.
        if len(messages) > 40:
            pinned = [m for m in messages[1:-20] if _is_pinned(m)]
            recent = messages[-20:]
            pinned_set = set(id(m) for m in pinned)
            messages = [messages[0]] + pinned + [m for m in recent if id(m) not in pinned_set]

        # System prompt por fase: contém todas as instruções necessárias para o
        # momento atual — sem enviar o que já não é relevante.
        if direct_action:
            system = SYSTEM_PROMPT_DIRECT
        else:
            try:
                system = _build_phase_status(messages)
            except Exception:
                system = SYSTEM_PROMPT_POWERFUL

        # ── Tool calling ──────────────────────────────────────────────────────
        try:
            import asyncio as _asyncio
            _raw_log(process_id, "llm_request", {"system": system, "messages": messages, "iteration": iteration})
            _pending_events: list = []
            # Roda _call_with_tools como task em background para poder emitir
            # eventos (rate_wait, model_active) em tempo real enquanto ele aguarda.
            _llm_task = _asyncio.create_task(_call_with_tools(
                system, messages, tools,
                preferred=preferred, strict_mode=strict_mode,
                pending_events=_pending_events,
            ))
            while not _llm_task.done():
                while _pending_events:
                    yield _emit(_pending_events.pop(0))
                await _asyncio.sleep(0.05)
            response = await _llm_task  # propaga exceção se houver

            # Se deu certo, atualiza o preferred de forma "sticky" para manter o modelo que funcionou!
            if response and not strict_mode:
                succ_model = response.get("_successful_model")
                if succ_model:
                    preferred = succ_model
                    log.info("agent.llm.preferred.updated", preferred_model=preferred, iteration=iteration)

            # Esvazia quaisquer eventos restantes após conclusão
            for _ev in _pending_events:
                yield _emit(_ev)
            _pending_events.clear()
            _raw_log(process_id, "llm_response", {"response": response})
        except Exception as e:
            if _collected_tool_summaries:
                partial = "\n".join(f"• {s}" for s in _collected_tool_summaries)
                yield _emit({
                    "type": "final",
                    "response": (
                        f"⚠️ Os serviços de IA estão temporariamente sobrecarregados. "
                        f"Aqui estão os dados coletados até agora:\n\n{partial}\n\n"
                        f"Tente novamente em alguns minutos para a análise completa."
                    ),
                })
            else:
                _raw_log(process_id, "agent_error", {"content": f"Erro ao chamar LLM: {e}"})
                yield _emit({"type": "error", "content": f"Erro ao chamar LLM: {e}"})
            return

        content = response.get("content", [])
        stop_reason = response.get("stop_reason", "end_turn")

        text_blocks = [b for b in content if b.get("type") == "text"]
        tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]

        # ── Fallback: alguns modelos menores (Cerebras/Groq 8B) retornam tool calls
        # como texto JSON — seja como resposta exclusiva (sem tool_use_blocks) ou
        # embutido no texto junto com um tool call estruturado real (resposta dupla).
        # Em ambos os casos: detecta, converte e limpa o JSON do texto da UI.
        if text_blocks:
            def _extract_json_objects(text: str) -> list[str]:
                """Extrai objetos JSON balanceados (suporta aninhamento)."""
                results, depth, start = [], 0, -1
                for i, ch in enumerate(text):
                    if ch == '{':
                        if depth == 0:
                            start = i
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0 and start >= 0:
                            results.append(text[start:i + 1])
                            start = -1
                return results

            _combined_text = " ".join(b.get("text", "") for b in text_blocks)
            for _jc in _extract_json_objects(_combined_text):
                try:
                    _obj = json.loads(_jc)
                    _tool_name = _obj.get("name") or _obj.get("function")
                    _tool_args = _obj.get("arguments") or _obj.get("input") or _obj.get("parameters") or {}
                    if isinstance(_tool_args, str):
                        try:
                            _tool_args = json.loads(_tool_args)
                        except Exception:
                            _tool_args = {}
                    if _tool_name and _tool_name in TOOLS and isinstance(_tool_args, dict):
                        # Sem tool_use estruturado: converte o JSON em tool_use real
                        if not tool_use_blocks:
                            tool_use_blocks.append({
                                "type": "tool_use",
                                "id": f"tc_fallback_{uuid.uuid4().hex[:8]}",
                                "name": _tool_name,
                                "input": _tool_args,
                            })
                            stop_reason = "tool_use"
                        # Com ou sem tool_use: remove o JSON do texto para não poluir a UI
                        text_blocks = [
                            {**b, "text": b.get("text", "").replace(_jc, "").strip()}
                            for b in text_blocks
                        ]
                        text_blocks = [b for b in text_blocks if b.get("text")]
                        # Reconstrói content para que o histórico reflita o tool_use real.
                        # Sem isso, _build_phase_status não rastreia whatsapp_searched/email_searched
                        # a partir dos args do assistente — a fase fica em loop infinito.
                        content = text_blocks + tool_use_blocks
                        break
                except Exception:
                    pass

        # ── Thinking: gerado DEPOIS de saber qual ferramenta será chamada ────
        # Prioridade: texto nativo completo > auxiliar completo > nada (sem fallback seco).
        # O label da ferramenta já é mostrado pelo tool_call event — não duplicar.
        if tool_use_blocks:
            first_tool = tool_use_blocks[0]
            native_text = " ".join(b.get("text", "").strip() for b in text_blocks).strip()
            native_is_complete = bool(native_text and native_text[-1] in ".!?")

            if native_is_complete and len(native_text) > 40:
                # Modelo principal (Claude/Gemini) gerou raciocínio genuíno
                yield _emit({"type": "thinking", "content": native_text})
            else:
                # Modelo não narrou (Groq) — tenta auxiliar de qualidade
                # skip_groq=True evita dobrar quota quando main também é Groq,
                # mas agora sem injection o risco de comportamento errado é zero,
                # então só skipamos quando há alternativa disponível.
                from core.config import settings as _s
                _groq_models = set(_s.ai_groq_models_list or [])
                _cerebras_models = set(_s.ai_cerebras_models_list or [])
                
                _main_is_groq = (
                    not preferred
                    or (preferred or "").lower() == "groq"
                    or preferred in _groq_models
                )
                _main_is_cerebras = (
                    (preferred or "").lower() == "cerebras"
                    or preferred in _cerebras_models
                )
                
                # Só pula Groq se Gemini ou Cerebras estiverem disponíveis
                _has_alt_for_groq = bool(
                    (_s.GEMINI_API_KEY and _s.ai_gemini_models_list)
                    or (_s.CEREBRAS_API_KEY and _s.ai_cerebras_models_list)
                )
                # Só pula Cerebras se Gemini ou Groq estiverem disponíveis
                _has_alt_for_cerebras = bool(
                    (_s.GEMINI_API_KEY and _s.ai_gemini_models_list)
                    or (_s.GROQ_API_KEY and _s.ai_groq_models_list)
                )
                
                _tn = first_tool.get("name", "")
                _ta = first_tool.get("input") or {}

                # Para ferramentas Pipedrive e generate_dossier, o template é suficiente.
                # Não vale chamar o modelo auxiliar — economiza quota para as comunicações.
                _template_only_tools = {
                    "pipedrive_get_org", "pipedrive_get_persons",
                    "pipedrive_get_deals", "pipedrive_get_activities",
                    "generate_dossier", "suggest_next_actions"
                }
                if _tn in _template_only_tools:
                    # suggest_next_actions não precisa de fallback de thinking visível na UI
                    if _tn != "suggest_next_actions":
                        yield _emit({"type": "thinking", "content": _get_thinking_fallback(_tn, _ta)})
                else:
                    # Para WhatsApp/Email (dados de comunicação), o aux tem contexto real para raciocinar
                    aux_thinking = await _generate_tool_thinking(
                        _tn, _ta, messages,
                        skip_groq=(_main_is_groq and _has_alt_for_groq),
                        skip_cerebras=(_main_is_cerebras and _has_alt_for_cerebras),
                    )
                    aux_is_complete = bool(aux_thinking and aux_thinking[-1] in ".!?")
                    thinking_text = (
                        aux_thinking if aux_is_complete
                        else _get_thinking_fallback(_tn, _ta)
                    )
                    if thinking_text:
                        yield _emit({"type": "thinking", "content": thinking_text})

        # Resposta final (sem tool calls)
        if stop_reason == "end_turn" or not tool_use_blocks:
            response_text = " ".join(b.get("text", "") for b in text_blocks).strip()
            if not response_text:
                response_text = "Tarefa concluída."

            # Modo execução direta: emite resultado e sai sem fase detection
            if direct_action:
                if not _final_emitted:
                    _raw_log(process_id, "agent_final_response", {"response": response_text})
                    yield _emit({"type": "final", "response": response_text})
                return

            # Interceptor anti-permissão: se o modelo pediu permissão em vez de agir,
            # injeta uma correção e força mais uma iteração de ferramentas.
            _PERMISSION_PHRASES = [
                "você gostaria", "gostaria de verificar", "gostaria de buscar",
                "deseja continuar", "deseja verificar", "posso verificar",
                "posso buscar", "posso investigar", "quer que eu",
                "para prosseguir", "preciso de mais informações",
                "você prefere", "prefere que eu",
            ]
            _resp_lower = response_text.lower()
            _is_asking_permission = any(p in _resp_lower for p in _PERMISSION_PHRASES)

            if _is_asking_permission and iteration < MAX_ITERATIONS - 2:
                messages.append({"role": "assistant", "content": content})
                
                try:
                    _status = _build_phase_status(messages)
                    m_action = _re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
                    action_str = m_action.group(1) if m_action else "Consulte o plano de fases para decidir o próximo passo."
                except Exception:
                    _status = "Status desconhecido"
                    action_str = "Continue investigando ou chame a ferramenta final."

                messages.append({
                    "role": "user",
                    "content": (
                        "PROIBIDO pedir permissão. "
                        "Não faça perguntas de confirmação ao usuário durante a investigação.\n\n"
                        f"OBRIGATÓRIO AGORA: {action_str}\n\n"
                        f"Contexto atual:\n{_status}"
                    ),
                })
                continue

            # Extrai dados reais do histórico para sugestões e prompts
            found_org = ""
            found_deal_id = None
            found_activities = []
            found_contacts = []
            for _m in messages:
                _m_content = _m.get("content", "")
                if isinstance(_m_content, list):
                    for _item in _m_content:
                        if isinstance(_item, dict) and _item.get("type") == "tool_result":
                            _t_name = _item.get("tool_name", "")
                            _t_content = str(_item.get("content", ""))
                            try:
                                _t_data = json.loads(_t_content) if _t_content.strip().startswith(("{", "[")) else {}
                            except Exception:
                                _t_data = {}
                            if _t_name in ("pipedrive_get_org", "pipedrive_get_persons"):
                                if _t_name == "pipedrive_get_org":
                                    found_org = _t_data.get("org", {}).get("name") or _t_data.get("name") or found_org
                                _p_list = _t_data.get("persons") or []
                                for _p in _p_list:
                                    _p_name = _p.get("name")
                                    if _p_name:
                                        _p_name_clean = _p_name.strip().lower()
                                        if _p_name_clean not in [c.get("name", "").strip().lower() for c in found_contacts]:
                                            found_contacts.append(_p)
                            elif _t_name == "pipedrive_get_deals":
                                _d_list = _t_data.get("deals") or []
                                for _d in _d_list:
                                    if _d.get("status") == "open":
                                        found_deal_id = _d.get("id") or found_deal_id
                            elif _t_name == "pipedrive_get_activities":
                                _p_list = _t_data.get("pending") or []
                                for _a in _p_list:
                                    _act_id = _a.get("id")
                                    if _act_id and _act_id not in [act.get("id") for act in found_activities]:
                                        found_activities.append({
                                            "id": _act_id,
                                            "subject": _a.get("subject", "Sem assunto"),
                                            "due_date": _a.get("due_date", "sem data")
                                        })

            # Interceptor anti-finalização prematura e injeção de suggest_next_actions
            if iteration < MAX_ITERATIONS - 2:
                try:
                    _msgs_with_current = messages + [{"role": "assistant", "content": content}]
                    _status = _build_phase_status(_msgs_with_current)
                    _is_complete = "Fase final" in _status

                    if not _is_complete and stop_reason == "end_turn" and not tool_use_blocks:
                        # Investigação incompleta — força continuar (só para respostas de texto puro)
                        m_action = _re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
                        action_str = m_action.group(1) if m_action else "Consulte o plano de fases."
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"ERRO: INVESTIGAÇÃO INCOMPLETA. Você tentou finalizar a resposta sem usar a ferramenta obrigatória.\n"
                                f"Para a investigação estar completa, você DEVE executar a próxima etapa.\n\n"
                                f"OBRIGATÓRIO AGORA:\n{action_str}\n\n"
                                f"Contexto:\n{_status}"
                            ),
                        })
                        continue

                    # Investigação completa — verifica se suggest_next_actions já foi chamado
                    if not _final_emitted and not _suggest_actions_done(_msgs_with_current) and stop_reason == "end_turn" and not tool_use_blocks:
                        # Emite o dossiê agora e força turno dedicado para suggest_next_actions
                        _raw_log(process_id, "agent_final_response", {"response": response_text})
                        yield _emit({"type": "final", "response": response_text})
                        _final_emitted = True

                        real_data_summary = []
                        if found_org:
                            real_data_summary.append(f"  - Organização/Empresa: '{found_org}'")
                        if found_deal_id:
                            real_data_summary.append(f"  - ID do Negócio Comercial (deal_id): {found_deal_id}")
                        if found_activities:
                            real_data_summary.append("  - Atividades Pendentes no Pipedrive (IDs REAIS):")
                            for _a in found_activities:
                                real_data_summary.append(f"    • ID: {_a['id']} | Assunto: '{_a['subject']}' | Vencimento: {_a['due_date']}")
                        if found_contacts:
                            real_data_summary.append("  - Contatos Atuais no Pipedrive:")
                            for _c in found_contacts:
                                real_data_summary.append(f"    • {_c.get('name')} (E-mail: {_c.get('email') or 'N/A'}, Tel: {_c.get('phone') or 'N/A'})")
                        else:
                            real_data_summary.append("  - Contatos Atuais no Pipedrive: Nenhum contato cadastrado ainda!")

                        real_data_str = "\n".join(real_data_summary) if real_data_summary else "  (Nenhum ID específico encontrado)"

                        messages.append({"role": "assistant", "content": content})
                        context_lines = [s for s in _collected_tool_summaries[-10:] if s]
                        context_str = "\n".join(f"  • {s}" for s in context_lines) if context_lines else "  (sem dados específicos)"
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Dossiê entregue. DADOS REAIS EXTRAÍDOS DO HISTÓRICO (USE APENAS ESTES IDS):\n{real_data_str}\n\n"
                                f"RESUMO DAS FONTES:\n{context_str}\n\n"
                                "Você é um Consultor de Vendas B2B sênior e altamente estratégico. "
                                "Chame OBRIGATORIAMENTE 'suggest_next_actions' com 3-6 ações específicas, contextualizadas e comercialmente brilhantes.\n"
                                "Cada ação DEVE ter:\n"
                                "• 'label': texto curto, persuasivo e atraente para o botão (comercialmente focado)\n"
                                "• 'prompt': instrução autossuficiente com IDs e parâmetros REAIS obtidos nas buscas.\n\n"
                                "REGRAS OBRIGATÓRIAS DE RACIOCÍNIO COMERCIAL:\n"
                                "1. EVITAR CADASTROS DUPLICADOS (CRÍTICO): Se o nome da pessoa identificada na comunicação (ex: Gabriel) "
                                "já está listado nos 'Contatos Atuais no Pipedrive' fornecidos acima (mesmo com pequenas variações), "
                                "você está ABSOLUTAMENTE PROIBIDO de sugerir criar o contato. O usuário considera isso um erro grave. "
                                "Apenas sugira 'pipedrive_create_person' se for um contato 100% novo revelado no histórico que não esteja no CRM. "
                                "(Lembre-se: João Moura é o vendedor, nunca cadastre ele).\n"
                                "   Prompt caso novo: 'Execute pipedrive_create_person: name=[NOME_REAL_DO_CONTATO], email=[EMAIL_REAL], org_name=[NOME_DA_EMPRESA]' (substitua sempre as chaves por valores reais, nunca use palavras genéricas ou colchetes no prompt final)\n\n"
                                "2. CONCLUIR ATIVIDADE: Se há uma atividade pendente de follow-up e o histórico de e-mails ou WhatsApp "
                                "mostra que já houve uma interação/resposta real recente, sugira marcar essa atividade pendente como feita.\n"
                                "   O 'label' da ação DEVE conter obrigatoriamente o assunto da tarefa no formato: 'Concluir atividade pendente · [Assunto da Tarefa]'.\n"
                                "   Exemplo: se a tarefa pendente tem o assunto 'Ligar para Gabriel', o label deve ser exatamente: 'Concluir atividade pendente · Ligar para Gabriel'.\n"
                                "   Prompt: 'Execute pipedrive_update_task com activity_id=[ID_NUMERICO_REAL] e done=true' (substitua sempre pelo ID numérico real da atividade encontrado no CRM, nunca escreva a palavra literal 'ID')\n\n"
                                "3. ANÁLISE DE OBJEÇÃO DE PREÇO (MUITO IMPORTANTE): Verifique atentamente se o contato (ex: Gabriel) indicou "
                                "nas mensagens de WhatsApp ou E-mail que nosso preço/orçamento está alto, caro, fora do orçamento, ou que "
                                "está comparando com a concorrência que é mais barata. Neste cenário de objeção de preço:\n"
                                "   - NÃO sugira sequências genéricas de follow-ups persistentes pedindo reunião. Isso afasta o cliente e é ineficaz.\n"
                                "   - Em vez disso, crie um plano sob medida focado em contornar a objeção de preço, ajustando propostas, "
                                "estudando margens e negociando termos técnicos de valor. A sequência de 5 tarefas no Pipedrive deve ser:\n"
                                "     * Tarefa 1: Estudo interno de custos e viabilidade de desconto de margem (tipo='task', due_date='<HOJE+1d>')\n"
                                "     * Tarefa 2: WhatsApp/Email rápido de alinhamento com o contato, informando que estamos revisando os custos (tipo='task', due_date='<HOJE+1d>')\n"
                                "     * Tarefa 3: Elaborar e Enviar Proposta Comercial Revisada com a melhor margem possível ou especificações alternativas para caber no budget (tipo='task', due_date='<HOJE+3d>')\n"
                                "     * Tarefa 4: Ligação consultiva para entender as propostas dos concorrentes e termos técnicos (tipo='call', due_date='<HOJE+6d>')\n"
                                "     * Tarefa 5: Ligação/Reunião de fechamento comercial definitivo (tipo='call' ou 'meeting', due_date='<HOJE+10d>')\n"
                                "   - Se NÃO houver reclamação de preço alto no histórico: use uma sequência padrão de 5 follow-ups progressivos de qualificação "
                                "visando agendar uma reunião de apresentação.\n"
                                "   Exemplo de prompt para sequência de follow-ups adaptada:\n"
                                "   label: 'Criar plano de 5 tarefas de negociação de preço para <CONTATO>' (ou 'Criar sequência de 5 follow-ups para reunião' se for fluxo padrão)\n"
                                "   prompt: 'Execute pipedrive_create_task 5 vezes em sequência para criar o plano de negociação/follow-up com <EMPRESA> (deal_id=<ID>):\n"
                                "Tarefa 1: subject=\"<ASSUNTO ESTRETEGICO DA TAREFA 1>\", type=\"task\", due_date=\"<HOJE+1d>\", org_name=\"<EMPRESA>\", note=\"<DETALHE COMERCIAL ESTRUTURADO DA TAREFA 1>\"\n"
                                "Tarefa 2: ...'\n\n"
                                "4. ENVIAR PROPOSTA COM DESCONTO / RESPOSTA RÁPIDA: Se o histórico indica que o vendedor (João) prometeu um desconto (ex: 9% de desconto) "
                                "ou que ficou de enviar uma nova proposta e isso ainda não foi formalizado/fechado, sugira uma ação direta de envio por e-mail ou WhatsApp "
                                "com o teor exato da proposta negociada, citando os valores discutidos.\n\n"
                                "5. RESPONDER E-MAIL / WHATSAPP: Se há um e-mail ou thread ativo com entry_id real, ou mensagem do WhatsApp recente sem resposta, "
                                "sugira uma resposta comercialmente impecável, oferecendo resolver a dor do cliente.\n"
                                "   Prompt: 'Execute email_reply com entry_id=[ENTRY_ID_REAL] e body=[TEXTO_DA_RESPOSTA_REAL]' (substitua sempre pelas informações reais coletadas das buscas, nunca use colchetes ou as palavras genéricas no prompt final)\n\n"
                                "NÃO invente IDs. Se não tiver ID real, não use o prompt correspondente.\n"
                                "NÃO escreva nenhum outro texto no seu retorno. Apenas chame suggest_next_actions."
                            ),
                        })
                        continue
                except Exception:
                    pass

            if _final_emitted and not _suggest_actions_done(messages):
                # O dossiê já foi emitido, mas o LLM falhou em gerar o suggest_next_actions.
                # Injetamos ações a partir dos dados reais coletados durante a investigação.
                from datetime import datetime, timedelta
                fallback_actions = []
                today = datetime.now()

                for act in found_activities:
                    fallback_actions.append({
                        "label": f"Concluir atividade pendente · {act['subject']}",
                        "prompt": f"Execute pipedrive_update_task com activity_id={act['id']} e done=true"
                    })

                if found_org:
                    # Detect price objections in messages to customize fallback follow-ups
                    has_price_objection = False
                    objection_keywords = ["caro", "alto", "preço", "preco", "orcamento", "orçamento", "desconto", "concorrencia", "concorrência", "valor"]
                    for _m in messages:
                        _m_content = str(_m.get("content", "")).lower()
                        if any(kw in _m_content for kw in objection_keywords):
                            has_price_objection = True
                            break

                    def _d(delta): return (today + timedelta(days=delta)).strftime("%Y-%m-%d")

                    if has_price_objection:
                        seq_prompt = (
                            f"Execute pipedrive_create_task 5 vezes em sequência para criar o plano de negociação e contorno de objeção de preço com {found_org}"
                            + (f" (deal_id={found_deal_id})" if found_deal_id else "") + ":\n"
                            f"Tarefa 1: subject=\"Estudo interno de margem e engenharia de custos\", type=\"task\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Analisar viabilidade de concessão de descontos adicionais ou alteração de especificações para caber no orçamento.\"\n"
                            f"Tarefa 2: subject=\"Aviso de revisão de proposta comercial\", type=\"task\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Enviar mensagem ao contato informando que estamos revisando internamente os valores para apresentar uma alternativa competitiva.\"\n"
                            f"Tarefa 3: subject=\"Enviar proposta comercial revisada\", type=\"task\", due_date=\"{_d(3)}\", org_name=\"{found_org}\", note=\"Elaborar e enviar por e-mail ou WhatsApp a proposta com novos preços ou especificações.\"\n"
                            f"Tarefa 4: subject=\"Ligação de acompanhamento consultivo\", type=\"call\", due_date=\"{_d(6)}\", org_name=\"{found_org}\", note=\"Ligar para entender o comparativo com a concorrência e o feedback sobre a proposta ajustada.\"\n"
                            f"Tarefa 5: subject=\"Fechamento comercial / alinhamento final\", type=\"meeting\", due_date=\"{_d(10)}\", org_name=\"{found_org}\", note=\"Reunião rápida ou ligação para fechar o pedido ou ajustar termos finais de pagamento.\""
                        )
                        lbl = "Criar plano de 5 tarefas de negociação de preço"
                    else:
                        seq_prompt = (
                            f"Execute pipedrive_create_task 5 vezes em sequência para criar o plano de follow-up para agendar reunião com {found_org}"
                            + (f" (deal_id={found_deal_id})" if found_deal_id else "") + ":\n"
                            f"Tarefa 1: subject=\"Follow-up 1: Ligar para {found_org}\", type=\"call\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Primeira tentativa de contato. Apresentar J.Ferres e propor reunião rápida de 20 min.\"\n"
                            f"Tarefa 2: subject=\"Follow-up 2: Email de apresentação\", type=\"task\", due_date=\"{_d(3)}\", org_name=\"{found_org}\", note=\"Enviar e-mail de apresentação propondo reunião. Referenciar último assunto discutido.\"\n"
                            f"Tarefa 3: subject=\"Follow-up 3: Segunda ligação\", type=\"call\", due_date=\"{_d(7)}\", org_name=\"{found_org}\", note=\"Segunda tentativa. Perguntar se recebeu o e-mail e verificar disponibilidade.\"\n"
                            f"Tarefa 4: subject=\"Follow-up 4: Canal alternativo (LinkedIn)\", type=\"task\", due_date=\"{_d(10)}\", org_name=\"{found_org}\", note=\"Tentar contato via LinkedIn ou outro canal para propor reunião.\"\n"
                            f"Tarefa 5: subject=\"Follow-up 5: Tentativa final\", type=\"call\", due_date=\"{_d(14)}\", org_name=\"{found_org}\", note=\"Última tentativa antes de arquivar. Propor horário específico para reunião de 30 min.\""
                        )
                        lbl = "Criar sequência de 5 follow-ups para reunião"

                    fallback_actions.append({
                        "label": lbl,
                        "prompt": seq_prompt,
                    })

                if fallback_actions:
                    _raw_log(process_id, "agent_fallback_suggested_actions", {"actions": fallback_actions})
                    yield _emit({
                        "type": "suggested_actions",
                        "actions": fallback_actions
                    })

            if not _final_emitted:
                _raw_log(process_id, "agent_final_response", {"response": response_text})
                yield _emit({"type": "final", "response": response_text})
            return

        # Separa ferramentas de leitura e escrita
        tool_results = []
        write_tool_pending = None
        read_blocks = []

        for block in tool_use_blocks:
            tool_name = block.get("name", "")
            tool_args = block.get("input") or {}
            tool_id = block.get("id", "")

            if tool_name not in TOOLS:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": f"Ferramenta '{tool_name}' não encontrada",
                    "is_error": True,
                })
                continue

            tool_meta = TOOLS[tool_name]

            # Ferramenta de ESCRITA — bloqueia se a investigação não estiver completa.
            # Impede que o modelo envie emails/mensagens sem o usuário ter pedido.
            if tool_meta["type"] == "write":
                if direct_action:
                    # No modo de ação direta, executa a ferramenta de escrita imediatamente sem pedir confirmação adicional
                    call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
                    
                    async def make_write_executor(t_name, t_args, o_id):
                        async def write_executor(args):
                            return await execute_write_tool(t_name, args, org_id=o_id)
                        return write_executor
                    
                    read_blocks.append((block, call_id, await make_write_executor(tool_name, tool_args, org_id)))
                    continue

                try:
                    _phase = _build_phase_status(messages)
                    _write_allowed = "Fase final" in _phase
                except Exception:
                    _write_allowed = True  # em caso de erro, não bloqueia

                if not _write_allowed:
                    # Retorna tool_result bloqueado e injeta instrução de continuar investigação
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": (
                            "BLOQUEADO: complete a investigação antes de enviar mensagens ou emails. "
                            + _phase
                        ),
                        "is_error": False,
                    })
                    continue

                if write_tool_pending is None:
                    call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
                    write_tool_pending = {
                        "block": block,
                        "call_id": call_id,
                        "label": _get_label(tool_name, tool_args),
                        "prior_results": [],
                        "org_id": org_id,
                    }
                continue  # leituras primeiro

            # Guard: generate_dossier só pode ser chamado quando todas as
            # comunicações foram investigadas (fase 3b ou posterior).
            if tool_name == "generate_dossier":
                try:
                    _gd_phase = _build_phase_status(messages)
                    _gd_allowed = (
                        "Todas as fontes foram investigadas" in _gd_phase
                        or "Fase final" in _gd_phase
                    )
                except Exception:
                    _gd_allowed = True
                if not _gd_allowed:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": (
                            "BLOQUEADO: complete todas as buscas de comunicação antes de consolidar. "
                            + _gd_phase
                        ),
                        "is_error": False,
                    })
                    continue

            executor = tool_meta.get("executor")
            if not executor:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": "Executor não definido",
                    "is_error": True,
                })
                continue

            call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
            read_blocks.append((block, call_id, executor))

        # Executa ferramentas de leitura SEQUENCIALMENTE — uma por vez.
        # Se o modelo enviou múltiplas (desobedeceu a instrução), executa a primeira
        # e marca as demais como "skip" para que o modelo as chame individualmente nas
        # próximas iterações. Isso garante que a API receba tool_result para todos os
        # tool_use do turno (obrigatoriedade da spec), sem quebrar o fluxo narrativo.
        if read_blocks:
            first_block, first_call_id, first_executor = read_blocks[0]
            skipped_blocks = read_blocks[1:]

            # Executa a primeira ferramenta
            tool_args = first_block.get("input") or {}
            tool_id = first_block.get("id", "")
            tool_name = first_block.get("name", "")

            yield _emit({"type": "tool_call", "call_id": first_call_id, "tool": tool_name,
                         "args": tool_args, "label": _get_label(tool_name, tool_args)})

            _raw_log(process_id, "tool_execute_start", {"tool": tool_name, "args": tool_args, "call_id": first_call_id})
            try:
                import inspect
                sig = inspect.signature(first_executor)
                exec_kwargs = {}
                if "org_id" in sig.parameters:
                    exec_kwargs["org_id"] = org_id
                if "messages" in sig.parameters:
                    exec_kwargs["messages"] = messages
                tool_result = await first_executor(tool_args, **exec_kwargs)
                _raw_log(process_id, "tool_execute_result", {"tool": tool_name, "result_raw": tool_result, "call_id": first_call_id})
            except Exception as e:
                tool_result = {"ok": False, "error": str(e)}

            # Retry automático: se a ferramenta falhou por erro transitório, tenta mais uma vez.
            # Não retenta erros esperados como "não encontrado" ou "0 resultados".
            if not tool_result.get("ok"):
                _err = str(tool_result.get("error", "")).lower()
                _expected = any(x in _err for x in [
                    "não encontrad", "not found", "nenhum", "0 contatos", "0 deal",
                    "0 mensagens", "0 e-mail", "sem histórico",
                ])
                if not _expected:
                    try:
                        import asyncio as _asyncio
                        await _asyncio.sleep(1)
                        import inspect
                        sig = inspect.signature(first_executor)
                        if "org_id" in sig.parameters:
                            tool_result = await first_executor(tool_args, org_id=org_id)
                        else:
                            tool_result = await first_executor(tool_args)
                    except Exception as e:
                        tool_result = {"ok": False, "error": str(e)}

            ok = tool_result.get("ok", False)
            summary = tool_result.get("summary") or tool_result.get("error") or ("OK" if ok else "Erro")
            yield _emit({"type": "tool_result", "call_id": first_call_id, "tool": tool_name, "summary": summary, "ok": ok})
            yield _emit({"type": "context_saved"})

            if ok and summary:
                _collected_tool_summaries.append(f"[{tool_name}] {summary}")

            if ok and tool_name == "suggest_next_actions":
                actions = tool_result.get("actions", [])
                if actions:
                    yield _emit({"type": "suggested_actions", "actions": actions})

            sanitized = _sanitize_result(tool_name, tool_result)
            raw_content = json.dumps(sanitized, ensure_ascii=False)
            if len(raw_content) > 1200:
                raw_content = raw_content[:1200] + "... [TRUNCADO]"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "tool_name": tool_name,
                "content": raw_content,
            })

            # Marca ferramentas extras como skipped (protocolo exige tool_result para todas)
            for skip_block, skip_call_id, _ in skipped_blocks:
                skip_tool_id = skip_block.get("id", "")
                skip_tool_name = skip_block.get("name", "")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": skip_tool_id,
                    "tool_name": skip_tool_name,
                    "content": "SKIPPED: chame apenas uma ferramenta por vez. Chame esta ferramenta individualmente na próxima resposta.",
                    "is_error": False,
                })

        # Pausa para ferramenta de escrita (leituras já foram executadas)
        if write_tool_pending:
            action_id = str(uuid.uuid4())
            block = write_tool_pending["block"]
            tool_name = block["name"]
            tool_args = block["input"]

            messages_with_assistant = messages + [{"role": "assistant", "content": content}]

            _PENDING[action_id] = {
                "tool_use_id": block["id"],
                "tool": tool_name,
                "args": tool_args,
                "call_id": write_tool_pending["call_id"],
                "label": write_tool_pending["label"],
                "messages_snapshot": messages_with_assistant,
                "prior_results": tool_results,  # inclui resultados das leituras paralelas
                "iteration": iteration + 1,
                "org_id": write_tool_pending.get("org_id"),
                "process_id": process_id,
                "parent_message_id": parent_message_id,
                "action_index": action_index,
            }

            label_fn = TOOLS[tool_name].get("confirm_label")
            confirm_label = label_fn(tool_args) if callable(label_fn) else write_tool_pending["label"]
            preview = tool_args.get("message") or tool_args.get("body") or json.dumps(tool_args, ensure_ascii=False)[:120]

            yield _emit({
                "type": "confirmation_required",
                "action_id": action_id,
                "tool": tool_name,
                "label": confirm_label,
                "preview": str(preview),
                "args": tool_args,
            })
            return

        # Todos os tool calls processados — adiciona ao histórico e continua
        # Adiciona a resposta do assistente (chamada de ferramenta)
        messages.append({"role": "assistant", "content": content, "tool_use_id": [b["id"] for b in tool_use_blocks] if tool_use_blocks else None})
        
        # Adiciona os resultados usando o formato de lista de objetos que o _messages_to_openai entende
        messages.append({"role": "user", "content": tool_results})

    # Esgotou iterações
    yield _emit({
        "type": "final",
        "response": "Não consegui concluir a tarefa dentro do número máximo de passos. Tente reformular o pedido.",
    })


async def run_agent(
    message: str,
    history: List[Dict],
    org_id: int | None = None,
    preferred: str | None = None,
    strict_mode: bool = False,
    thread_id: str | None = None,
    direct_action: bool = False,
    parent_message_id: str | None = None,
    action_index: int | None = None,
    is_regeneration: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Gerador assíncrono — yields strings NDJSON.
    Usa native tool calling da API Anthropic.
    """
    tools = get_tools_anthropic_schema()
    if direct_action:
        # Filtra as ferramentas disponíveis para conter apenas a ferramenta explicitada na mensagem/ação direta.
        # Isso impede que o modelo chame pipedrive_get_org ou suggest_next_actions em modo direto.
        from services.ai.agent_v2.tools import TOOLS
        matched_tools = [name for name in TOOLS.keys() if name in message]
        if matched_tools:
            tools = [t for t in tools if t["name"] in matched_tools]
            log.info("agent.direct_action.tools_filtered", matched=matched_tools)

    # Resolve o nome real da org no Pipedrive quando org_id é fornecido
    # Evita que o modelo use nomes errados/variantes (ex: "GmbH" vs "Gmb H")
    org_context = ""
    if org_id:
        try:
            from services.pipedrive.pipedrive_service import pipedrive_service
            orgs = await pipedrive_service.list_organizations()
            org = next((o for o in (orgs or []) if o.get("id") == org_id), None)
            if org:
                org_context = f"\n[Contexto: a empresa selecionada é '{org['name']}' — use este nome exato nas ferramentas]"
        except Exception:
            pass

    # Constrói o histórico de conversa
    messages: list = []
    for m in history[-15:]:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})

    # Mensagem atual com contexto de nome correto
    messages.append({"role": "user", "content": message + org_context})

    process_id = f"proc_{uuid.uuid4().hex[:8]}"
    _raw_log(process_id, "agent_start", {"message": message, "org_id": org_id, "preferred": preferred})

    final_response = ""
    collected_events = []
    async for chunk in _agent_loop(messages, tools, org_id=org_id, preferred=preferred, strict_mode=strict_mode, process_id=process_id, direct_action=direct_action, parent_message_id=parent_message_id, action_index=action_index):
        # Rastreia a resposta final antes de emitir
        try:
            data = _json.loads(chunk)
            collected_events.append(data)
            if data.get("type") == "final":
                final_response = data.get("response", "")
        except Exception:
            pass
        yield chunk

    # Persiste as mensagens no banco após o stream completo
    if thread_id:
        try:
            from core.database import async_session as _async_session
            async with _async_session() as db:
                if parent_message_id and action_index is not None:
                    # ─── Suggested action saving logic ───
                    # Carrega a mensagem do assistente pai e atualiza os eventos dela com os resultados dessa execução
                    from sqlalchemy import select
                    from models.conversation import ConversationMessage
                    result = await db.execute(
                        select(ConversationMessage).where(ConversationMessage.id == parent_message_id)
                    )
                    parent_msg = result.scalar_one_or_none()
                    if parent_msg:
                        has_confirm = any(e.get("type") == "confirmation_required" for e in collected_events)
                        action_status = "awaiting_confirm" if has_confirm else "done"

                        # Vamos salvar os logs desta execução e o status no data da mensagem do assistente pai.
                        msg_data = dict(parent_msg.data or {})
                        runs = msg_data.get("suggested_actions_runs", {})
                        runs[str(action_index)] = {
                            "status": action_status,
                            "logs": collected_events,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        msg_data["suggested_actions_runs"] = runs
                        parent_msg.data = msg_data
                        
                        # Também precisamos atualizar o log/evento "suggested_actions" original em parent_msg.logs para refletir que ela foi executada
                        parent_logs = list(parent_msg.logs or [])
                        for event in parent_logs:
                            if event.get("type") == "suggested_actions" and "actions" in event:
                                # Adiciona o status/logs na ação correspondente
                                if 0 <= action_index < len(event["actions"]):
                                    action_item = event["actions"][action_index]
                                    action_item["status"] = action_status
                                    action_item["logs"] = collected_events
                        parent_msg.logs = parent_logs
                        
                        db.add(parent_msg)
                        await db.commit()
                        log.info("agent.suggested_action.saved_to_parent", parent_message_id=parent_message_id, action_index=action_index)
                else:
                    # Comportamento padrão de salvar como mensagens separadas se não for uma ação sugerida atrelada ao pai
                    from api.v1.endpoints.conversations import save_message as _save_message
                    if not is_regeneration:
                        await _save_message(db, thread_id, "user", message)
                    if final_response:
                        await _save_message(db, thread_id, "assistant", final_response, logs=collected_events)
                    log.info("agent.messages.saved", thread_id=thread_id, is_regeneration=is_regeneration)
        except Exception as e:
            log.warning("agent.messages.save_failed", thread_id=thread_id, error=str(e))


async def resume_after_confirmation(
    action_id: str,
    approved: bool,
    thread_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Retoma o agente após confirmação de uma ação de escrita."""
    pending = _PENDING.pop(action_id, None)
    if not pending:
        yield _emit({"type": "error", "content": "Ação não encontrada ou expirada"})
        return

    tool_name = pending["tool"]
    tool_args = pending["args"]
    tool_use_id = pending["tool_use_id"]
    call_id = pending["call_id"]
    label = pending.get("label", tool_name)
    parent_message_id = pending.get("parent_message_id")
    action_index = pending.get("action_index")

    # Emite o tool call que estava pendente
    yield _emit({"type": "tool_call", "call_id": call_id, "tool": tool_name, "args": tool_args, "label": label})

    pending_org_id = pending.get("org_id")
    pending_process_id = pending.get("process_id", f"proc_res_{uuid.uuid4().hex[:8]}")

    if approved:
        try:
            _raw_log(pending_process_id, "tool_execute_write_start", {"tool": tool_name, "args": tool_args})
            result = await execute_write_tool(tool_name, tool_args, org_id=pending_org_id)
            _raw_log(pending_process_id, "tool_execute_write_result", {"tool": tool_name, "result_raw": result})
        except Exception as e:
            result = {"ok": False, "error": str(e)}
    else:
        result = {"ok": False, "error": "Ação cancelada pelo usuário"}

    ok = result.get("ok", False)
    summary = result.get("result") or result.get("error") or ("OK" if ok else "Erro")

    yield _emit({"type": "tool_result", "call_id": call_id, "tool": tool_name, "summary": summary, "ok": ok})

    # Monta a lista completa de tool results (reads anteriores + write confirmado)
    write_result = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "tool_name": tool_name,
        "content": json.dumps(result, ensure_ascii=False),
    }
    all_results = pending["prior_results"] + [write_result]

    # Restaura conversa e adiciona os resultados
    messages = pending["messages_snapshot"]  # Já inclui a mensagem do assistente com tool_use blocks
    messages.append({"role": "user", "content": all_results})

    tools = get_tools_anthropic_schema()
    start_iter = pending.get("iteration", 1)

    final_response = ""
    collected_events = []
    
    async for chunk in _agent_loop(messages, tools, start_iteration=start_iter, org_id=pending_org_id, process_id=pending_process_id, parent_message_id=parent_message_id, action_index=action_index):
        try:
            data = _json.loads(chunk)
            collected_events.append(data)
            if data.get("type") == "final":
                final_response = data.get("response", "")
        except Exception:
            pass
        yield chunk

    if thread_id:
        try:
            from core.database import async_session as _async_session
            async with _async_session() as db:
                if parent_message_id and action_index is not None:
                    # Carrega a mensagem do assistente pai e atualiza os eventos dela
                    from sqlalchemy import select
                    from models.conversation import ConversationMessage
                    result = await db.execute(
                        select(ConversationMessage).where(ConversationMessage.id == parent_message_id)
                    )
                    parent_msg = result.scalar_one_or_none()
                    if parent_msg:
                        msg_data = dict(parent_msg.data or {})
                        runs = msg_data.get("suggested_actions_runs", {})
                        
                        # Recupera logs anteriores de SuggestedActionTask (que geraram a confirmação)
                        prev_run = runs.get(str(action_index), {})
                        prev_logs = prev_run.get("logs", [])
                        
                        # Combina os logs anteriores com os novos logs desta retomada
                        combined_logs = prev_logs + collected_events
                        
                        has_confirm = any(e.get("type") == "confirmation_required" for e in collected_events)
                        action_status = "awaiting_confirm" if has_confirm else "done"
                        
                        runs[str(action_index)] = {
                            "status": action_status,
                            "logs": combined_logs,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        msg_data["suggested_actions_runs"] = runs
                        parent_msg.data = msg_data
                        
                        # Também atualiza o log/evento "suggested_actions" original em parent_msg.logs
                        parent_logs = list(parent_msg.logs or [])
                        for event in parent_logs:
                            if event.get("type") == "suggested_actions" and "actions" in event:
                                if 0 <= action_index < len(event["actions"]):
                                    action_item = event["actions"][action_index]
                                    action_item["status"] = action_status
                                    action_item["logs"] = combined_logs
                        parent_msg.logs = parent_logs
                        
                        db.add(parent_msg)
                        await db.commit()
                        log.info("agent.suggested_action.confirm.saved_to_parent", parent_message_id=parent_message_id, action_index=action_index)
                else:
                    from api.v1.endpoints.conversations import save_message as _save_message
                    if final_response:
                        await _save_message(db, thread_id, "assistant", final_response, logs=collected_events)
            log.info("agent.messages.resumed_saved", thread_id=thread_id)
        except Exception as e:
            log.warning("agent.messages.resumed_save_failed", thread_id=thread_id, error=str(e))
