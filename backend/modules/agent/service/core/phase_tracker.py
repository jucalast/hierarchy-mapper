"""
modules.agent.service.core.phase_tracker
=========================================
Construção do system prompt dinâmico por fase da investigação do agente.

_build_phase_status analisa o histórico de mensagens para determinar em qual
fase do workflow o agente está (Mapeamento Pipedrive → Comunicação → Dossiê → Final)
e gera o system prompt com apenas as instruções necessárias para aquela fase —
economizando tokens e reduzindo confusão do modelo.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from core.observability.logging_config import get_logger
from modules.agent.service.prompts import SYSTEM_PROMPT_POWERFUL
from modules.agent.service.helpers import _get_tools_called

log = get_logger(__name__)


def _build_phase_status(messages: list, query_type: str = "agent_workflow", org_id: int | None = None, ctx: dict | None = None) -> str:
    """
    Constrói o system prompt completo para a fase atual da investigação.
    """
    import re as _re
    from modules.agent.service.prompts import render_prompt

    if not ctx:
        # Fallback se não for passado context (não deve ocorrer se chamado pelo loop correto)
        ctx = {}

    today = datetime.now().strftime('%Y-%m-%d')

    # ── Extrai estado da investigação de forma robusta ──────────────────────
    # Inclui TODAS as ferramentas fundamentais para evitar loops
    _CORE_TRACKED = {
        "pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals",
        "pipedrive_get_activities", "pipedrive_get_all_activities",
        "whatsapp_get_messages", "email_get_contact_history",
        "prepare_live_coaching_session", "open_hierarchy_drawer", "pipedrive_create_task",
        "generate_dossier", "deep_company_investigation", "evaluate_prospects",
        "generate_sales_message", "email_send", "whatsapp_send_message"
    }
    tools_called = _get_tools_called(messages, target_tools=_CORE_TRACKED)
    
    # Detecta rascunho pronto
    draft_done = "generate_sales_message" in tools_called
    
    contacts_found: list[str] = []   # contatos encontrados no pipedrive_get_persons
    contact_phones: dict[str, str] = {} # Mapeamento nome -> telefone
    org_name: str = ""
    whatsapp_searched: set[str] = set()
    email_searched: set[str] = set()
    task_contacts: set[str] = set()  # Contatos vinculados a atividades pendentes (Prioridade Máxima)

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Extração de metadados para controle fino (Nomes, WhatsApps, Emails)
        if role == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tn = block.get("name", "")
                args = block.get("input") or {}
                if tn == "pipedrive_get_org" and args.get("org_name"):
                    org_name = args["org_name"].strip()
                if tn == "whatsapp_get_messages":
                    if args.get("contact"):
                        whatsapp_searched.add(args["contact"].lower())
                    if args.get("org_name"):
                        whatsapp_searched.add(args["org_name"].lower())
                if tn == "email_get_contact_history":
                    name = args.get("contact_name") or args.get("org_name") or ""
                    if name:
                        email_searched.add(name.lower())
                if tn == "batch_communication_search":
                    for c in args.get("contacts", []):
                        if isinstance(c, dict) and c.get("name"):
                            whatsapp_searched.add(c["name"].lower())
                            email_searched.add(c["name"].lower())
                    if args.get("org_name"):
                        whatsapp_searched.add(args["org_name"].lower())
                        email_searched.add(args["org_name"].lower())

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "tool_result":
                    continue
                tn = item.get("tool_name", "")
                tc = str(item.get("content", ""))
                
                if tn == "pipedrive_get_org" and not org_name:
                    m_sum = _re.search(r'"summary"\s*:\s*"([^|]+)\|', tc)
                    if m_sum: org_name = m_sum.group(1).strip()

                if tn == "pipedrive_get_persons":
                    try:
                        import json as _json
                        data = _json.loads(tc)
                        persons_list = data.get("persons", []) if isinstance(data, dict) else []
                        for p in persons_list:
                            if isinstance(p, dict) and p.get("name"):
                                name = p["name"].strip()
                                if name not in contacts_found:
                                    contacts_found.append(name)
                                    if p.get("phone"): contact_phones[name] = str(p["phone"]).strip()
                    except Exception: pass

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
        # Padrões para detectar indicações: "fale com X", "cobrar retorno com X", etc.
        # Versão simplificada e agressiva: pega qualquer coisa que venha depois de um verbo de ação comercial
        # até encontrar o primeiro nome Capitalizado, ignorando aspas, espaços ou símbolos intermediários.
        patterns = [
            r'(?:fale|falar|tratar|contato|chame|procure|indico|indicação|recomendo|conversar|follow-up|cobrar|acompanhar|retorno|atender|responder)[^A-ZÁÉÍÓÚÃÕÂÊÎÔÛç]*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)',
            r'(?:contato|com)\s+[^A-ZÁÉÍÓÚÃÕÂÊÎÔÛç]*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)'
        ]
        referrals = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                name = m.strip()
                # Descarta termos comuns de negócio capturados acidentalmente
                if len(name) > 2 and name.lower() not in ['para', 'como', 'esta', 'esse', 'essa', 'quem', 'onde', 'quando', 'porque', 'orçamento', 'financeiro', 'comercial', 'compras', 'vendas', 'diretor', 'gerente', 'negócio', 'parceiro', 'empresa', 'cliente', 'retorno', 'pedido', 'analise', 'execute', 'seguinte', 'atividade']:
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

        # Se for string representando uma lista/dicionário, tenta parsear usando json ou ast
        if isinstance(content, str):
            content_trimmed = content.strip()
            if content_trimmed.startswith("[") or content_trimmed.startswith("{"):
                try:
                    import json as _json
                    content = _json.loads(content_trimmed)
                except Exception:
                    try:
                        import ast as _ast
                        content = _ast.literal_eval(content_trimmed)
                    except Exception:
                        pass

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
                    # Tenta extrair nomes do JSON das atividades (person_name é o canal oficial de prioridade)
                    try:
                        import json as _json
                        data = _json.loads(tc)
                        # O retorno da tool usa a chave 'pending' (veja tools.py:exec_pipedrive_get_activities)
                        activities = data.get("pending", []) or data.get("activities", []) or data.get("data", [])
                        if not isinstance(activities, list): activities = []
                        
                        for act in activities:
                            p_name = act.get("person_name")
                            if p_name:
                                # No pending da tool, done já é False por definição (ou 0)
                                task_contacts.add(p_name)
                                referred_contacts.add(p_name)
                            # Também busca no assunto e nota da atividade
                            for ref in _extract_referrals(act.get("subject", "")):
                                referred_contacts.add(ref)
                            for ref in _extract_referrals(act.get("note", "")):
                                referred_contacts.add(ref)
                    except:
                        # Fallback para regex no texto bruto
                        for ref in _extract_referrals(tc):
                            referred_contacts.add(ref)
                
                elif tn == "pipedrive_get_org":
                    # Tenta pegar o contato principal do deal/org se estiver no JSON
                    try:
                        import json as _json
                        data = _json.loads(tc)
                        if isinstance(data, dict):
                            p_name = data.get("contact_name") or data.get("person_name")
                            if p_name:
                                referred_contacts.add(p_name)
                    except: pass

    # ── Extrai Objetivo Original (para priorizar contatos citados na tarefa)
    goal_contacts = set()
    
    company_name = ctx.get("company_name", "J.Ferres")
    seller_name = ctx.get("seller_name", "João Luccas")

    # Procura o objetivo nos últimos 3 msgs de usuário (mais robusto que apenas messages[0] em histórico longo)
    user_msgs = [m for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
    for um in reversed(user_msgs[-3:]):
        u_content = um["content"]
        
        # 1. Extração por padrões explícitos (ex: "cobrar retorno com X")
        goal_referrals = _extract_referrals(u_content)
        for r in goal_referrals:
            goal_contacts.add(r)
            referred_contacts.add(r)
            
        # 2. Extração de todos os nomes Capitalizados no trecho do objetivo
        # Foca apenas no texto antes de tags de escopo
        clean_goal = u_content.split("\n[OBRIGATÓRIO")[0].split("\n[ESCOPO")[0].strip()
        names_in_goal = _re.findall(r'([A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛç][a-záéíóúãõâêîôûç]+)?)', clean_goal)
        for n in names_in_goal:
            if n.lower() not in [seller_name.lower(), company_name.lower(), "pipedrive", "whatsapp", "email", "linkb2b", "knorr", "bremse", "analise", "execute", "atividade"]:
                goal_contacts.add(n)
                referred_contacts.add(n)
        
        # Se encontrou nomes no objetivo, para de procurar em mensagens anteriores
        if goal_contacts:
            break

    # ── OTIMIZAÇÃO DE FILA: Prioriza (1) Citados no Goal, (2) Indicados em tarefas, (3) Ativos
    optimized_contacts = []
    
    # Passo 0: PRIORIDADE ABSOLUTA - Contatos vinculados a tarefas pendentes no CRM
    for c in contacts_found:
        if _is_referred(c, task_contacts) and c not in optimized_contacts:
            optimized_contacts.append(c)

    # Passo 1: Prioridade Alta - Contatos do objetivo (goal)
    # Primeiro os que foram extraídos via padrões explícitos (com Matheus Muniz)
    for c in contacts_found:
        if _is_referred(c, goal_contacts) and c not in optimized_contacts:
            optimized_contacts.append(c)
            
    # Passo 2: Contatos referenciados em atividades ou conversas
    for c in contacts_found:
        if _is_referred(c, referred_contacts) and c not in optimized_contacts:
            optimized_contacts.append(c)
            
    # Passo 3: Contatos que já sabemos serem ativos (têm mensagens)
    for c in contacts_found:
        if c in active_contacts and c not in optimized_contacts:
            optimized_contacts.append(c)
            
    # Passo 4: O restante (alfabético ou ordem original do Pipedrive)
    remaining_unsorted = [c for c in contacts_found if c not in optimized_contacts]
    optimized_contacts.extend(remaining_unsorted)

    # Garantia de segurança: Matheus Muniz DEVE estar no topo se citado no goal
    # Mesmo que a lista de contatos seja longa, o Passo 1 já deve ter cuidado disso.

    pending_wapp  = [c for c in optimized_contacts if not _searched(c, whatsapp_searched)]
    pending_email = [c for c in optimized_contacts if not _searched(c, email_searched)]
    org_wapp_done  = bool(org_name and _searched(org_name, whatsapp_searched))
    org_email_done = bool(org_name and _searched(org_name, email_searched))

    if draft_done:
        # SE JÁ TEM RASCUNHO, A INVESTIGAÇÃO ESTÁ CONCLUÍDA POR DEFINIÇÃO.
        # Isso impede que o agente entre em loop buscando históricos de outros contatos
        # após já ter decidido o que falar.
        comms_complete = True
    elif active_contacts:
        # Se encontramos um contato ativo com histórico substancial (PARADA ANTECIPADA),
        # a fase de comunicação é considerada concluída, liberando o agente para agir
        # (criar tarefas, sugerir ações, dossiê) sem forçá-lo a esgotar os demais contatos irrelevantes.
        comms_complete = pipedrive_complete
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
        "(5) CONTINUIDADE OBRIGATÓRIA (CRÍTICO): Se uma ferramenta retornar 0 resultados ou dados vazios, VOCÊ NÃO DEVE PARAR. Registre o fato e CHAME IMEDIATAMENTE a próxima ferramenta pendente na mesma resposta. NUNCA encerre seu turno apenas com comentários de texto sem chamar uma ferramenta, e NUNCA declare a tarefa como concluída se ainda houver nomes na lista 'Pendente' abaixo, a menos que todas as fases da investigação estejam 100% concluídas.\n"
        "(6) PROSPECÇÃO ATIVA (CRÍTICO): Se as ferramentas de histórico de comunicação retornarem ZERO resultados (nenhuma conversa no WhatsApp ou E-mail), NÃO bloqueie a execução! Isso significa que o lead é frio e VOCÊ TEM AUTORIZAÇÃO para iniciar o primeiro contato. Nesses casos, use as ferramentas de escrita (`whatsapp_send_message` or `email_send`) para executar as tarefas de prospecção (como 'Apresentar empresa' ou 'Enviar proposta').\n"
        "(7) IDENTIDADE: João Luccas (joao.moura@jferres.com.br ou qualquer e-mail do domínio jferres.com.br) é o vendedor/remetente (você / o usuário do sistema). Ele NUNCA deve ser cadastrado ou sugerido como contato (person/lead) de nenhuma empresa no Pipedrive. Os contatos reais e leads são sempre os destinatários/interlocutores externos (ex: Lgustavo/Luis Gustavo).\n"
        "1. INFORMAÇÃO GERAL E BUSCAS\n"
        "Se o usuário enviou uma ordem direta (ex: 'marque a tarefa', 'crie o contato'), você NÃO PRECISA investigar WhatsApp ou E-mail a menos que a tarefa envolva entender o contexto da conversa. Execute as ferramentas de alteração imediatamente!\n"
        "Se a tarefa for abstrata ou estratégica (ex: 'quais os próximos passos', 'o que falei com fulano'), aí sim você DEVE usar ferramentas como `pipedrive_get_org`, `whatsapp_get_messages`, etc.\n"
        "(7) SENSO DE PROSPECÇÃO (CRÍTICO): Você tem a capacidade de guardar a história de um relacionamento. Quando o usuário mencionar que conheceu um lead em um evento, indicação, feira, etc., você DEVE usar a ferramenta `update_prospecting_context` para salvar essa informação qualitativa e a 'temperature' (ex: 'morno', 'quente'). Nas suas comunicações futuras (e-mail, whatsapp), SEMPRE leia o 'prospecting_context' retornado por `pipedrive_get_org` ou `pipedrive_get_persons` e USE esse contexto para criar empatia e rapport na mensagem, adaptando o tom de acordo com a origem do lead.\n\n"
        "(8) NOME DO AGENTE: Seu nome é 'Agente de Investigação Comercial LinkB2B'. Este é o nome do seu próprio sistema/plataforma de vendas. Você está ABSOLUTAMENTE PROIBIDO de buscar informações, contatos, deals ou atividades sobre a organização 'LinkB2B', pois ela representa o seu próprio sistema, e não o cliente externo sob investigação."
    )

    # ── Tratamento Específico: Tarefas do Dia (atalho eficiente) ─────────────
    # pipedrive_tasks é mantido como fast-path porque a ação é 100% determinística.
    if query_type == "pipedrive_tasks":
        if "pipedrive_get_all_activities" not in tools_called:
            return render_prompt(
                f"Data: {today}. Você é o Agente de Atendimento Comercial LinkB2B.\n"
                "O usuário quer saber o que ele tem para fazer hoje (tarefas/atividades).\n"
                "Sua PRÓXIMA FERRAMENTA deve ser obrigatoriamente: pipedrive_get_all_activities.\n"
                "Execute-a para obter a lista completa de atividades para hoje e atrasadas.\n"
                "NÃO chame nenhuma outra ferramenta antes desta. Apenas chame pipedrive_get_all_activities com um dicionário vazio {}.\n"
                "Não faça perguntas ao usuário, execute diretamente a ferramenta.",
                ctx
            )
        else:
            return render_prompt(
                f"Data: {today}. Você é o Agente de Atendimento Comercial LinkB2B.\n"
                "As tarefas foram buscadas e os cards de ação já foram gerados automaticamente na interface. "
                "Escreva apenas uma mensagem curta e encorajadora informando quantas tarefas há para hoje e quantas estão atrasadas. "
                "NÃO chame mais ferramentas.",
                ctx
            )

    # ── Tratamento Específico: Resumo de Ligação (Pós-Chamada) ──────────────
    _is_call_summary = any("[ALERTA DE CONTEXTO: LIGAÇÃO FINALIZADA]" in str(m.get("content", "")) for m in messages[-2:])
    if _is_call_summary:
        return render_prompt(
            f"Data: {today}. Você é o Agente Comercial LinkB2B — especialista em CRM e fechamento.\n"
            "Uma ligação acabou de ser finalizada e você recebeu a transcrição completa.\n\n"
            "SUA MISSÃO CRÍTICA:\n"
            "1. ANALISE: Leia a transcrição e identifique: dores do cliente, preços citados, compromissos firmados e reuniões agendadas.\n"
            "2. RESUMO EXECUTIVO: Escreva um resumo curto e matador da conversa.\n"
            "3. ATUALIZAÇÃO DO CRM (AÇÃO IMEDIATA):\n"
            "   - Identifique a tarefa de ligação no Pipedrive (use `pipedrive_get_activities`).\n"
            "   - Marque-a como concluída (`done=true`) e adicione o resumo como nota.\n"
            "   - Se uma nova reunião ou follow-up foi acordado, use `pipedrive_create_task` para agendar.\n"
            "4. REGRA DE OURO (NÃO DUPLICAR): Antes de sugerir ou criar QUALQUER nova tarefa, você DEVE obrigatoriamente chamar `pipedrive_get_activities` para ver as tarefas futuras. Se já existir uma tarefa para o mesmo objetivo (ex: 'Enviar proposta'), VOCÊ ESTÁ PROIBIDO de sugerir uma nova. Apenas atualize a nota da tarefa existente se necessário.\n"
            "5. CONTINUIDADE: Sua missão só termina quando o CRM refletir a realidade da ligação. Sugira os botões de ação necessários.\n\n"
            "Seja proativo. Se o cliente pediu uma proposta, sua sugestão de próximo passo DEVE ser rascunhar essa proposta.",
            ctx
        )

    # ── MODO AGENTE UNIVERSAL (Copilot-style) ────────────────────────────────
    # Para QUALQUER query que NÃO seja investigação de empresa (deal_status/agent_workflow),
    # o modelo recebe um prompt universal com TODAS as ferramentas e decide sozinho.
    #
    # VANTAGEM: NÃO depende do classificador de intenções. Mesmo se o classificador
    # errar (ex: retornar "general" para "o que tenho pra fazer"), o modelo principal
    # (Claude/Gemini) é inteligente o suficiente para escolher a ferramenta certa.
    #
    # Isso é equivalente ao "agent mode" do GitHub Copilot.
    # Detecta se o MODO CONTEXTO está ativo no histórico de mensagens
    context_mode_active = False
    command_mode_active = False
    for msg in messages:
        if msg.get("role") == "user":
            msg_content = str(msg.get("content", ""))
            if "[MODO CONTEXTO" in msg_content:
                context_mode_active = True
            
            # Detecta comandos diretos
            content_lower = msg_content.lower().strip()
            import re as _re
            if _re.search(r'\b(execute|realizar|realize|marque|crie|adicione|atualize|altere|mande|envie|agende|ligue)\b', content_lower):
                command_mode_active = True

    # Se estiver dentro de um chat de uma empresa específica (org_id > 0), é sempre sobre um negócio específico,
    # exigindo a investigação completa, a menos que estejamos no MODO CONTEXTO, puxando tarefas globais,
    # ou executando um comando direto.
    _is_investigation = query_type in ("deal_status", "agent_workflow") or (
        org_id is not None
        and org_id > 0
        and query_type != "pipedrive_tasks"
        and not context_mode_active
        and not command_mode_active
    )
    _investigation_active = bool(
        not context_mode_active 
        and not command_mode_active 
        and ({"pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"} & tools_called)
    )

    if not _is_investigation and not _investigation_active:
        # ── Turnos seguintes: Detecção automática por ferramentas chamadas ──
        # Em vez de depender do classificador, detectamos o que apresentar
        # pelo que o modelo JÁ FEZ (quais ferramentas foram chamadas).
        if tools_called:
            _tool_result_map = {
                "pipedrive_get_all_activities": "tarefas e atividades de hoje e atrasadas",
                "email_get_inbox": "e-mails da caixa de entrada",
                "email_get_contact_history": "histórico de e-mails do contato",
                "whatsapp_list_chats": "conversas recentes do WhatsApp",
                "whatsapp_get_messages": "mensagens do WhatsApp",
                "web_search_external": "resultados da pesquisa na web",
                "pipedrive_get_persons": "contatos da empresa",
                "pipedrive_get_deals": "negócios/deals da empresa",
            }
            _found = [desc for tool, desc in _tool_result_map.items() if tool in tools_called]
            _what = ", ".join(_found) if _found else "dados coletados"

            return render_prompt(
                f"Data: {today}. Você é o Agente Comercial LinkB2B.\n"
                f"Você já coletou: {_what}.\n"
                "Apresente os resultados de forma altamente profissional, organizada e detalhada para o usuário.\n"
                "Se o usuário fez uma pergunta específica, responda diretamente usando os dados coletados.\n"
                "Se as tarefas incluem empresas, agrupe por empresa. Se são e-mails, organize por data.\n"
                "AÇÃO E CONTINUIDADE: Se a solicitação do usuário exige uma ação concreta (como criar ou atualizar tarefas no CRM, enviar mensagens de WhatsApp/E-mail, criar notas ou sugerir próximos passos estrategicamente), você DEVE chamar a ferramenta correspondente agora.\n"
                "REGRA CRÍTICA DE COMANDOS DIRETOS: Nunca escreva apenas 'Tarefa concluída' se você não executou as ferramentas solicitadas pelo usuário! Se o usuário pediu para atualizar uma tarefa e criar um contato, você DEVE emitir a chamada para `pipedrive_update_task` primeiro. No próximo turno você criará o contato.\n"
                "IMPORTANTE: Se você precisa fazer MAIS DE UMA ação (ex: atualizar uma tarefa E criar um contato), chame APENAS UMA FERRAMENTA agora (ex: pipedrive_update_task). Assim que ela terminar, você chamará a próxima no turno seguinte. Não tente chamar duas ferramentas de escrita ao mesmo tempo.\n"
                "Se você não encontrou os IDs necessários nos dados coletados, explique isso CLARAMENTE ao usuário em vez de encerrar a conversa.\n"
                "Caso contrário (se for apenas uma pergunta informativa e você já tiver todos os dados para respondê-la), NÃO chame mais ferramentas e escreva apenas a resposta final.",
                ctx
            )

        # ── Primeiro turno: Prompt Universal com TODAS as ferramentas ──
        # O LLM analisa a mensagem e DECIDE SOZINHO qual ferramenta usar.
        return render_prompt(
            f"Data: {today}. Você é o Agente Comercial LinkB2B — o parceiro de negócios inteligente do usuário.\n\n"
            "Você é um AGENTE AUTÔNOMO com acesso a ferramentas poderosas de CRM, WhatsApp e Email.\n"
            "Analise a mensagem do usuário e DECIDA SOZINHO qual ferramenta usar para responder da melhor forma.\n\n"
            "REGRAS ABSOLUTAS:\n"
            "(1) Execute diretamente — NUNCA peça permissão ou faça perguntas de confirmação.\n"
            "(2) Uma ferramenta por turno — nunca duas.\n"
            "(3) Se a pergunta pode ser respondida com dados do sistema, USE a ferramenta certa.\n"
            "(4) Se o usuário fornecer DADOS DE UM CONTATO (nome, email, telefone), PRIORIZE CADASTRAR/ATUALIZAR IMEDIATAMENTE usando `pipedrive_create_person` em vez de investigar.\n"
            "(5) Se é uma saudação ou pergunta sobre o sistema, responda diretamente SEM ferramentas.\n\n"
            "FERRAMENTAS DISPONÍVEIS E QUANDO USAR CADA UMA:\n\n"
            "📋 TAREFAS E AGENDA:\n"
            "• pipedrive_get_all_activities → Para 'o que tenho pra fazer?', 'minhas tarefas', 'agenda de hoje', "
            "'o que tá pendente?', 'atividades atrasadas'. Chame com argumentos: {}\n\n"
            "🏢 CRM / EMPRESAS:\n"
            "• pipedrive_get_org → Para buscar info de uma empresa específica no CRM\n"
            "• pipedrive_get_persons → Para listar contatos/pessoas de uma empresa\n"
            "• pipedrive_get_deals → Para ver negócios/deals de uma empresa\n"
            "• pipedrive_get_activities → Para ver tarefas DE UMA empresa específica\n\n"
            "💬 WHATSAPP:\n"
            "• whatsapp_list_chats → Para 'me mostra minhas conversas', 'quem me mandou mensagem'\n"
            "• whatsapp_get_messages → Para ler mensagens de um contato específico\n\n"
            "📧 EMAIL:\n"
            "• email_get_inbox → Para 'me mostra meus emails', 'tem email novo?', 'caixa de entrada'\n"
            "• email_get_contact_history → Para buscar emails de um contato ou empresa específica\n\n"
            "🔍 PESQUISA:\n"
            "• web_search_external → Para pesquisar informações na web sobre empresas/contatos\n\n"
            "✍️ AÇÕES DE ESCRITA / COMANDOS DIRETOS:\n"
            "• pipedrive_create_person → Para criar um novo contato (ATENÇÃO: use a chave 'name', NUNCA 'contact_name')\n"
            "• pipedrive_update_task → Para marcar uma tarefa como concluída (done=true) ou alterar detalhes\n"
            "• pipedrive_create_task → Para criar uma nova tarefa / follow-up\n"
            "• pipedrive_create_note → Para adicionar uma nota a um deal\n"
            "• email_send / whatsapp_send_message → Para enviar comunicações ativas\n\n"
            "DECISÃO: Leia a mensagem do usuário, escolha a ferramenta mais adequada e execute-a imediatamente.\n"
            "Se nenhuma ferramenta for necessária (saudação, pergunta sobre o sistema), responda diretamente com "
            "uma saudação calorosa, apresente-se e diga brevemente o que pode fazer pelo usuário.",
            ctx
        )

    # ── Fluxo de Investigação de Empresa (deal_status / agent_workflow) ─────
    # A partir daqui, estamos em modo de investigação rígida.
    # Este fluxo NÃO foi alterado — continua funcionando exatamente como antes.
    if not tools_called:
        return render_prompt(base + "\n\nInício. Execute pipedrive_get_org agora.", ctx)

    # ── Fase 2 — Mapeamento Pipedrive ────────────────────────────────────────
    if not pipedrive_complete:
        remaining = [t for t in [
            "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"
        ] if t not in tools_called]
        next_tool_line = f"\nPRÓXIMA FERRAMENTA: {remaining[0]}" if remaining else ""
        return render_prompt(
            base
            + "\n\nFase: Mapeamento Pipedrive."
            + f" Faltam (nesta ordem): {' → '.join(remaining)}."
            + next_tool_line
            + "\nNÃO inicie WhatsApp/Email antes de concluir os 4 passos do Pipedrive.",
            ctx
        )

    # ── Fase 3 — Investigação de comunicação ─────────────────────────────────
    if not comms_complete:
        # Determina exatamente qual é a próxima ferramenta a chamar
        next_action = ""
        
        # REGRA DE ESGOTAMENTO (Priority First): Esgota WhatsApp + Email do contato prioritário
        # antes de passar para o próximo da fila.
        for c in optimized_contacts:
            is_priority = _is_referred(c, goal_contacts) or _is_referred(c, referred_contacts) or c in active_contacts
            if is_priority:
                if not _searched(c, whatsapp_searched):
                    phone = contact_phones.get(c, "")
                    phone_hint = f" com contact='{c}' e phone='{phone}'" if phone else f" com contact='{c}'"
                    next_action = f"PRÓXIMA FERRAMENTA: whatsapp_get_messages{phone_hint}"
                    break
                if not _searched(c, email_searched):
                    next_action = f"PRÓXIMA FERRAMENTA: email_get_contact_history com contact_name='{c}'"
                    break
            
        if not next_action:
            # Se esgotou os prioritários ou não há, segue a ordem pendente normal
            if pending_wapp:
                c = pending_wapp[0]
                phone = contact_phones.get(c, "")
                phone_hint = f" com contact='{c}' e phone='{phone}'" if phone else f" com contact='{c}'"
                next_action = f"PRÓXIMA FERRAMENTA: whatsapp_get_messages{phone_hint}"
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
            wa_list = []
            for c in pending_wapp:
                p = contact_phones.get(c)
                wa_list.append(f"{c} (tel: {p})" if p else c)
            pending_parts.append(f"WhatsApp de: {', '.join(wa_list)}")
        if pending_email:
            pending_parts.append(f"Email de: {', '.join(pending_email)}")
        if not org_wapp_done and org_name:
            pending_parts.append(f"WhatsApp pela empresa '{org_name}'")
        if not org_email_done and org_name:
            pending_parts.append(f"Email pela empresa '{org_name}'")
        pending_str = "; ".join(pending_parts) if pending_parts else "verificar contatos da organização"

        return render_prompt(
            base
            + f"\n\nFase: Investigação de comunicação."
            + f"\nPendente: {pending_str}."
            + f"\n{next_action}."
            + "\n\nREGRA DE OURO (MUITO CRÍTICO): Se houver uma atividade pendente vinculada a uma pessoa específica (ex: Matheus Muniz), você DEVE começar a investigação OBRIGATORIAMENTE por essa pessoa. Não mude a ordem da fila."
            + "\n\nPROSPECÇÃO ATIVA (CRÍTICO): Se as ferramentas de histórico de comunicação retornarem ZERO resultados (nenhuma conversa no WhatsApp ou E-mail), NÃO bloqueie a execução! Isso significa que o lead é frio e VOCÊ TEM AUTORIZAÇÃO para iniciar o primeiro contato. Nesses casos, use as ferramentas de escrita (`whatsapp_send_message` or `email_send`) para executar as tarefas de prospecção (como 'Apresentar empresa' ou 'Enviar proposta').\n"
            + "\n\nPROIBIDO: não chame pipedrive_get_all_activities (busca TODAS as empresas)."
            + " PROIBIDO: não use ferramentas de escrita (email_send, whatsapp_send_message) antes de completar a investigação."
            + " PROIBIDO: não use web_search_external durante investigação de empresa, EXCETO como último recurso para descobrir o domínio do site/e-mail caso não encontre contatos."
            + "\nPROIBIDO: NUNCA passe nomes de negócios (Deals) ou emojis nos campos de contato. Use APENAS o nome exato da empresa ou da pessoa."
            + "\n\nPRIORIDADE: examine as atividades para decidir a ordem. Se uma tarefa menciona 'fale com X' ou 'aguardando Y': essa pessoa vem antes."
            + "\nFOCO EXCLUSIVO NO CONTATO ATIVO E PREVENÇÃO DE LOOP (REGRA DE OURO): Se você encontrar um contato com comunicação recente relevante que já responde à dúvida (ex: proposta enviada, preenchimento, negociação ativa, etc.), VOCÊ DEVE INTERROMPER A INVESTIGAÇÃO DE OUTROS CONTATOS IMEDIATAMENTE. NÃO pesquise outros contatos ou a organização se já encontrou o contexto com a pessoa principal. Se você decidiu parar a investigação antecipadamente por ter encontrado conteúdo relevante, escreva 'REGRA DE OURO' ou 'PARADA ANTECIPADA' no seu raciocínio e você PODE E DEVE chamar 'generate_dossier' ou escrever sua resposta final, ignorando a lista de pendências acima."
            + "\nRADAR: ao ler conversas, se aparecer nome novo, investigue também — mesmo fora do Pipedrive."
            + "\nCROSS-VALIDAÇÃO: compare Pipedrive com comunicações — aponte discrepâncias de datas, status ou pessoas não cadastradas.",
            ctx
        )

    # ── Fase 3b — Aguardando generate_dossier ────────────────────────────────
    if not dossier_done:
        return render_prompt(
            base
            + "\n\nTodas as fontes foram investigadas. Chame generate_dossier agora.",
            ctx
        )

    # ── Fase 4 — Dossiê final ─────────────────────────────────────────────────
    return render_prompt(
        base
        + "\n\nFase final. A investigação terminou. Escreva APENAS o Dossiê Final em texto corrido "
        "(parágrafos, sem bullets, sem emojis), contendo:"
        "\n1. Resumo do negócio: o que diz o Pipedrive (deal, valor, funil)."
        "\n2. Histórico de comunicação: o que foi falado exatamente (assuntos, nomes, datas, quem disse o quê)."
        "\n3. Situação real: status atual cruzando CRM com comunicações."
        "\n\nREGRAS:"
        "\n- NÃO escreva 'Ações Sugeridas:', 'Próximos Passos:' ou qualquer lista de ações — isso vem em seguida automaticamente."
        "\n- NÃO chame nenhuma ferramenta agora. Apenas escreva o dossiê."
        "\n- Finalize no ponto 3.",
        ctx
    )
