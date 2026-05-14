"""
Serviço de Estratégia e Consultoria de Vendas B2B.
Analisa a situação atual do negócio, histórico de comunicações (WhatsApp, E-mail) e dados do CRM
usando as melhores metodologias de vendas (MEDDPICC, SPIN Selling, Challenger Sale) para sugerir
ações comerciais de alta performance de forma dinâmica.
"""
import json
import re
from datetime import datetime
from typing import Any, Dict, List
from core.logging_config import get_logger
from services.ai.llm.router import ask_llm
from services.ai.llm.base import LLMTier
from services.ai.business_context_service import BusinessContextService

log = get_logger(__name__)

class SalesStrategyService:
    """
    Serviço dedicado à inteligência comercial B2B.
    Aplica técnicas consagradas de vendas para diagnosticar negócios e gerar planos de ação impecáveis.
    """

    async def analyze_and_suggest_actions(self, messages: List[Dict[str, Any]], org_id: int | None = None, contact_name: str = "", phone: str = "") -> Dict[str, Any]:
        """
        Analisa o histórico de mensagens e o contexto comercial atual para gerar
        um diagnóstico de vendas rico e ações executáveis.
        """
        log.info("sales_strategy_service.analyze_and_suggest_actions", org_id=org_id)
        
        # 1. Serializa o histórico relevante para fornecer contexto ao LLM
        history_serialized = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Extrai apenas texto e resumos de resultados de ferramentas para não poluir
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_result":
                            tool_name = item.get("tool_name", "")
                            tool_content = str(item.get("content", ""))
                            # Aumentado para 12.000 para suportar conversas longas sem perder o fim do histórico (o mais importante)
                            if len(tool_content) > 12000:
                                tool_content = tool_content[:12000] + "... [conteúdo truncado]"
                            text_parts.append(f"[Resultado da ferramenta '{tool_name}': {tool_content}]")
                content = "\n".join(text_parts)
            
            history_serialized.append({
                "role": role,
                "content": str(content)
            })

        # 1.5 Carrega Contexto de Negócio (Configurado no Sistema)
        business_context = await BusinessContextService.get_tenant_context()
        biz_data_str = json.dumps(business_context, indent=2, ensure_ascii=False) if business_context else "Sem contexto de negócio configurado."

        # 2. Constrói o Prompt Estratégico de Vendas B2B sênior
        system_prompt = (
            "Você é o Diretor Comercial de B2B e Coach de Vendas Sênior da J.Ferres. "
            "Sua missão é analisar o histórico de investigações, dados do CRM Pipedrive e mensagens (WhatsApp/Email) "
            "para diagnosticar o estado real do negócio e sugerir as melhores ações comerciais possíveis, "
            "utilizando técnicas consagradas de vendas:\n\n"
            "## METODOLOGIAS DE VENDAS EXIGIDAS:\n"
            "1. **SPIN Selling**: Identifique a Situação, Problemas latentes do cliente (atrasos de entrega, problemas de qualidade com fornecedor atual, caixas rasgando, etc.), "
            "as Implicações desses problemas (parada de linha de fábrica, reclamações de clientes finais) e a Necessidade de Solução. **Use isso para criar ganchos de curiosidade e urgência.**\n"
            "2. **Venda Consultiva (Autoridade Técnica)**: Você não é apenas um vendedor, você é um consultor técnico da J.Ferres. "
            "Sempre que possível, use ganchos de autoridade como: \n"
            "   - **Cálculo de Mackee**: Mencione que podemos otimizar o peso da caixa mantendo a resistência ideal, reduzindo custos sem perder qualidade.\n"
            "   - **Laboratório Próprio**: Diga que temos testes internos de compressão e resistência para garantir o melhor material.\n"
            "   - **Estratégia de Itens de Menor Volume**: Explique que somos mais competitivos e agressivos em itens de menor volume/lançamentos, onde o mercado costuma ser caro.\n"
            "3. **MEDDPICC**: Identifique a Dor Principal (Pain), os Critérios de Decisão (Decision Criteria), "
            "quem é o Decisor (Economic Buyer), e a Concorrência (Competition).\n"
            "4. **Challenger Sale**: 'Ensine' o cliente sobre valor técnico. Desafie a ideia de que o fornecedor atual é imbatível apenas pelo preço unitário, mostrando o custo do desperdício.\n\n"
            "## CONTEXTO DA J.FERRES (NOSSA EMPRESA):\n"
            f"{biz_data_str}\n\n"
            "## REGRAS DE OURO PARA AS COPYS (MENSAGENS):\n"
            f"- **PRONTO PARA ENVIO (SEM PLACEHOLDERS)**: É terminantemente PROIBIDO o uso de colchetes `[]`. A mensagem deve estar PRONTA. Use data real: Hoje é {datetime.now().strftime('%A, %d/%m/%Y')}.\n"
            "- **RECONHECIMENTO DE ENTIDADE (STRICT CONTEXT)**: Se o nome de um contato no WhatsApp/Email contiver o nome da empresa alvo (ex: 'Gabriel - Compras Walsywa' e a empresa é 'Walsywa'), você DEVE assumir que se trata da mesma empresa. É erro grave de análise dizer que o histórico não é relevante por causa de sufixos de departamento ou cargo.\n"
            "- **SELEÇÃO INTELIGENTE DE CANAL**: Analise o volume e a RECÊNCIA das interações. Priorize o canal (WhatsApp ou Email) onde o cliente demonstra maior engajamento ou onde ocorreu a última conversa relevante. Se o usuário explicitamente pedir um canal para uma tarefa, obedeça, mas em geral, siga onde o cliente 'mora'. Nunca use e-mail por preguiça se o WhatsApp for o canal de maior calor.\n"
            "- **PROIBIDO SER GENÉRICO (ANTI-SPAM)**: NUNCA, em hipótese alguma, comece com 'Prezado', 'Espero que esteja bem', 'Tudo bem?', 'Como vai?'. Isso destrói a autoridade técnica. Comece direto no assunto ou com uma provocação técnica (Challenger Sale).\n"
            "- **ZERO REDUNDÂNCIA (DATA-DRIVEN E LEITURA DE HISTÓRICO)**: É terminantemente PROIBIDO perguntar ao cliente informações que já constam no histórico (ex: 'Os preços incluem IPI?', 'Quem são os fornecedores?', 'É cartonagem?'). Leia TODO o histórico até o fim ATENTAMENTE. Se a resposta para sua dúvida já foi dada pelo contato mais abaixo na conversa, NÃO REPITA A PERGUNTA na sua nova mensagem. Analise friamente: 'O cliente já informou se tem IPI? Sim, então não pergunto. Ele já falou quem é o fornecedor? Sim, então não pergunto'. USE os dados fornecidos para criar argumentos lógicos de fechamento ou criar encerramentos firmes.\n"
            "- **EXEMPLO DE MENSAGEM PROIBIDA (NÃO FAÇA)**: \"Prezado Gabriel, espero que este e-mail o encontre bem. Estou acompanhando o orçamento...\"\n"
            "- **EXEMPLO DE MENSAGEM IDEAL (FAÇA)**: \"Gabriel, sobre o orçamento das caixas 730036: vi que a Walsywa ainda não fechou. Conseguimos cobrir a oferta da Cartonagem X se fecharmos o lote de 5k unidades hoje. O que te impede de avançar?\"\n"
            "- **DEDICAÇÃO TOTAL (DATA-DRIVEN)**: Você DEVE citar itens específicos (ex: '730036'), quantidades e os PREÇOS reais do histórico.\n"
            "- **AUTORIDADE TÉCNICA**: Desafie a concorrência (Fabricante vs Cartonagem), use Cálculo de Mackee, Teste de Compressão.\n"
            "- **TOM DE VOZ**: Natural, assertivo, comercialmente agressivo e direto. No WhatsApp, seja curto e focado na dor do cliente.\n"
            "Você DEVE responder estritamente em formato JSON no esquema abaixo, sem markdown ou textos fora do JSON:\n"
            "{\n"
            "  \"diagnostico_vendas\": {\n"
            "    \"temperatura_lead\": \"Quente\" | \"Morno\" | \"Frio\" | \"Bloqueado\",\n"
            "    \"fase_atual_funil\": \"Qualificacao\" | \"Proposta\" | \"Negociacao\" | \"Fechamento\",\n"
            "    \"dores_identificadas\": [\"lista de dores e insatisfações reais encontradas no histórico\"],\n"
            "    \"objecoes_detectadas\": [\"objeções de preço, prazo, concorrência ou técnica encontradas\"],\n"
            "    \"analise_concorrencia\": \"resumo detalhado sobre o que concorrentes oferecem e onde estamos perdendo/ganhando\",\n"
            "    \"direcionamento_estrategico\": \"orientação comercial brilhante de como o vendedor deve agir baseada em SPIN/MEDDPICC/Challenger para fechar o negócio\"\n"
            "  },\n"
            "  \"acoes_recomendadas\": [\n"
            "    {\n"
            "      \"label\": \"título do botão comercial curto e atraente (ex: 'WhatsApp: Oferecer Caixa Alternativa', máx 45 caracteres)\",\n"
            "      \"estrategia_vendas\": \"breve explicação do porquê fazer isso agora usando as técnicas de vendas\",\n"
            "      \"prompt\": \"o comando em formato de prompt executável autossuficiente para o agente executar (ex: 'Execute whatsapp_send_message com contact=\\\"[Nome]\\\", message=\\\"[Mensagem Técnica]...\\\"')\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        prompt_user = (
            f"CONTATO: {contact_name} " + (f"(Tel: {phone})" if phone else "") + "\n\n"
            "Analise o histórico RECENTE de WhatsApp e Email. Identifique os preços dos concorrentes citados (ex: R$ 0,9085), "
            "os códigos dos itens (ex: 730036) e a última dúvida do vendedor (ex: fabricante ou cartonagem). "
            "Crie 3 ações comerciais brilhantes, sendo que a primeira deve ser uma mensagem de WhatsApp que use todos esses dados reais "
            "para desafiar o preço baixo do concorrente e avançar para o fechamento. "
            "PROIBIDO USAR TEMPLATES. Seja específico e técnico.\n"
            f"IMPORTANTE: No campo 'prompt' das ações, SEMPRE inclua contact='{contact_name}'" + (f" e phone='{phone}'" if phone else "") + " para que o agente tenha os dados exatos."
        )

        try:
            # Chama o LLM router na camada FAST ou STANDARD com json_mode=True
            res = await ask_llm(
                prompt=prompt_user,
                system=system_prompt,
                history=history_serialized,
                json_mode=True,
                temperature=0.1,
                tier=LLMTier.STANDARD
            )
            
            # 3. Processa e valida o JSON retornado
            content = res.text.strip()
            # Garante que removemos blocos de código markdown desnecessários se o modelo os colocou
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            data = json.loads(content, strict=False)
            diagnostico = data.get("diagnostico_vendas", {})
            acoes = data.get("acoes_recomendadas", [])
            
            # 4. Constrói um sumário executivo em formato de tabela Markdown altamente premium
            temperatura = diagnostico.get("temperatura_lead", "Desconhecido")
            fase = diagnostico.get("fase_atual_funil", "Desconhecido")
            dores = ", ".join(diagnostico.get("dores_identificadas", [])) or "Nenhuma dor mapeada"
            objecoes = ", ".join(diagnostico.get("objecoes_detectadas", [])) or "Sem objeções explícitas"
            concorrencia = diagnostico.get("analise_concorrencia") or "Sem dados da concorrência"
            direcionamento = diagnostico.get("direcionamento_estrategico") or "Seguir follow-up padrão"
            
            # Formatação de cores e badges de temperatura
            temp_badge = "⚪ Desconhecido"
            if temperatura == "Quente":
                temp_badge = "🔴 Quente (Alta intenção)"
            elif temperatura == "Morno":
                temp_badge = "🟡 Morno (Avaliação ativa)"
            elif temperatura == "Frio":
                temp_badge = "🔵 Frio (Baixo engajamento)"
            elif temperatura == "Bloqueado":
                temp_badge = "🚫 Bloqueado (Objeções críticas)"

            summary_md = (
                "### 🎯 Diagnóstico de Vendas B2B — Metodologia LinkB2B sênior\n\n"
                "| Indicador Comercial | Diagnóstico Situacional |\n"
                "| :--- | :--- |\n"
                f"| **🔥 Temperatura do Lead** | {temp_badge} |\n"
                f"| **📊 Estágio do Negócio** | {fase} |\n"
                f"| **💡 Dores Mapeadas** | {dores} |\n"
                f"| **⚠️ Objeções Ativas** | {objecoes} |\n"
                f"| **🥊 Concorrência** | {concorrencia} |\n\n"
                "> [!NOTE]\n"
                "> **Direcionamento Estratégico (SPIN & Challenger Sale):**\n"
                f"> {direcionamento}\n\n"
                "--- \n"
                "### ⚡ Próximos Passos Recomendados pelo Coach de Vendas\n"
                "*(Selecione uma das ações estratégicas abaixo para que o Agente LinkB2B a execute automaticamente)*\n\n"
            )
            
            # Adiciona detalhes de cada ação no sumário em formato de lista estilosa
            normalized_actions = []
            for act in acoes:
                label = act.get("label", "Ação Estratégica")
                strategy = act.get("estrategia_vendas", "")
                prompt = act.get("prompt", "")
                
                summary_md += f"- **Botão: [{label}]**\n  *Estratégia:* {strategy}\n\n"
                
                normalized_actions.append({
                    "label": label,
                    "prompt": prompt
                })
                
            return {
                "ok": True,
                "actions": normalized_actions,
                "summary": summary_md
            }
            
        except Exception as e:
            log.exception("sales_strategy_service.analyze_and_suggest_actions.failed", error=str(e))
            return {
                "ok": False,
                "actions": [],
                "summary": f"Erro ao executar o diagnóstico avançado: {str(e)}"
            }

# Instância global single-source of truth
sales_strategy_service = SalesStrategyService()
