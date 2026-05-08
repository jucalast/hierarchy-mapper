"""
Serviço de Estratégia e Consultoria de Vendas B2B.
Analisa a situação atual do negócio, histórico de comunicações (WhatsApp, E-mail) e dados do CRM
usando as melhores metodologias de vendas (MEDDPICC, SPIN Selling, Challenger Sale) para sugerir
ações comerciais de alta performance de forma dinâmica.
"""
import json
import re
from typing import Any, Dict, List
from core.logging_config import get_logger
from services.ai.llm.router import ask_llm
from services.ai.llm.base import LLMTier

log = get_logger(__name__)

class SalesStrategyService:
    """
    Serviço dedicado à inteligência comercial B2B.
    Aplica técnicas consagradas de vendas para diagnosticar negócios e gerar planos de ação impecáveis.
    """

    async def analyze_and_suggest_actions(self, messages: List[Dict[str, Any]], org_id: int | None = None) -> Dict[str, Any]:
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
                            # Resume conteúdos gigantescos de ferramentas para poupar contexto
                            if len(tool_content) > 1500:
                                tool_content = tool_content[:1500] + "... [conteúdo truncado]"
                            text_parts.append(f"[Resultado da ferramenta '{tool_name}': {tool_content}]")
                content = "\n".join(text_parts)
            
            history_serialized.append({
                "role": role,
                "content": str(content)
            })

        # 2. Constrói o Prompt Estratégico de Vendas B2B sênior
        system_prompt = (
            "Você é o Diretor Comercial de B2B e Coach de Vendas Sênior da J.Ferres. "
            "Sua missão é analisar o histórico de investigações, dados do CRM Pipedrive e mensagens (WhatsApp/Email) "
            "para diagnosticar o estado real do negócio e sugerir as melhores ações comerciais possíveis, "
            "utilizando técnicas consagradas de vendas:\n\n"
            "## METODOLOGIAS DE VENDAS EXIGIDAS:\n"
            "1. **SPIN Selling**: Identifique a Situação, Problemas latentes do cliente (atrasos de entrega, problemas de qualidade com fornecedor atual, caixas rasgando, etc.), "
            "as Implicações desses problemas (parada de linha de fábrica, reclamações de clientes finais) e a Necessidade de Solução.\n"
            "2. **MEDDPICC**: Identifique a Dor Principal (Pain), os Critérios de Decisão (Decision Criteria - ex: preço, resistência do material, lead time), "
            "quem é o Decisor/Comprador Econômico (Economic Buyer), e a Concorrência (Competition).\n"
            "3. **Challenger Sale**: Crie abordagens onde o vendedor assume o controle, 'ensina' o cliente sobre valor técnico de embalagem, "
            "'customiza' a proposta comercial para o perfil do decisor e 'desafia' objeções rasas de preço mostrando o custo real de desperdício.\n\n"
            "## SUAS REGRAS DE GERAÇÃO DE AÇÕES COMERCIAIS:\n"
            "- **Evitar Duplicações (CRÍTICO)**: Se o contato com quem conversamos no histórico (ex: Gabriel) já está listado nos contatos atuais do CRM, "
            "NUNCA sugira criá-lo. O usuário odeia redundâncias.\n"
            "- **Concluir Atividades Obsoletas e Adicionar Notas (CRÍTICO)**: Se houver qualquer tarefa pendente no Pipedrive de 'cobrar orçamento', 'ligar', 'follow-up' ou similar, "
            "e a conversa correspondente já tiver acontecido nas mensagens (ex: você já cobrou, enviou proposta, discutiu preços), você DEVE sugerir "
            "uma ação para marcar essa atividade específica como concluída (usando 'pipedrive_update_task' com o ID da atividade e done=true) "
            "E criar uma nota rica de resumo comercial (usando 'pipedrive_create_note' no deal_id real) registrando as dores/objeções levantadas pelo cliente (como a objeção de preço do orçamento caro e o desconto de 9% discutido). "
            "O 'label' desta ação específica DEVE ser obrigatoriamente no formato: 'Concluir atividade pendente · [Assunto da Tarefa]'. "
            "Exemplo: se a tarefa pendente tem o assunto 'Ligar para Gabriel', o label deve ser exatamente: 'Concluir atividade pendente · Ligar para Gabriel'.\n"
            "   Exemplo de Prompt da ação: 'Execute pipedrive_update_task com activity_id=[ID_NUMERICO_REAL] e done=true e execute pipedrive_create_note no deal_id=[ID_NUMERICO_REAL] com content=\"Resumo da negociação:...\"' (substitua sempre as expressões em colchetes por IDs numéricos reais encontrados nas buscas, nunca escreva a palavra genérica 'ID' no prompt)\n"
            "- **Tratar Objeções de Preço com Inteligência**: Se o contato reclamou que o orçamento ficou caro ou acima de concorrentes:\n"
            "  * NÃO peça reuniões genéricas de follow-up. Sugira contornar a objeção focando em valor técnico, renegociação de lote ou especificações alternativas (ex: papelão Kraft de outra gramatura, menos resistente mas mais barato, ou reduzir aba da caixa).\n"
            "  * Crie um plano de 5 tarefas de negociação de preço estruturado de forma excelente no Pipedrive.\n"
            "- **Templates de Copys Perfeitos**: Se sugerir enviar e-mail ou mensagem no WhatsApp, forneça o copy EXATO, profissional, caloroso, personalizado "
            "e altamente persuasivo, citando dados específicos ditos pelo próprio contato (valores negociados, nomes, termos).\n\n"
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
            "      \"prompt\": \"o comando em formato de prompt executável autossuficiente para o agente executar (ex: 'Execute whatsapp_send_message com contact=\\\"Gabriel\\\", message=\\\"Olá Gabriel...\\\"')\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        prompt_user = (
            "Com base no histórico da investigação comercial fornecido nas mensagens, "
            "aplique as metodologias SPIN, MEDDPICC e Challenger Sale para extrair o diagnóstico comercial detalhado do negócio "
            "e formular as 3 a 5 ações mais brilhantes possíveis. Identifique contatos e IDs reais envolvidos. "
            "Lembre-se de retornar apenas o JSON puro."
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
            
            data = json.loads(content)
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
