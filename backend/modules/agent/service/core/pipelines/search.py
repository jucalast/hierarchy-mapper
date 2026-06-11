"""
modules.agent.service.core.pipelines.search
=============================================
Pipeline de Mapeamento e Busca de Decisor do agente CRM.
"""
from typing import Any
from modules.agent.service.core.pipelines.base import BasePipeline

class SearchPipeline(BasePipeline):
    """Pipeline voltada para encontrar contatos decisores e mapeamento de hierarquia."""
    name = "Search"
    description = "Pipeline para mapeamento de hierarquia e localização de decisores (ICP)"

    _contact_search_keys = [
        "procurar contato", "encontrar contato", "conseguir contato",
        "buscar contato", "achar contato", "identificar contato",
        "localizar contato", "contato na rodada", "rodada de negócios",
        "encontrar decisor", "buscar decisor", "identificar decisor", "achar decisor", "decisor"
    ]

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        s = subject.lower()
        return any(k in s for k in cls._contact_search_keys)

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        _act_args = f"org_id={org_pd_id}" + (f", deal_id={deal_id}" if deal_id else "") + f", activity_id={act_id}"
        return (
            f"ESTRATÉGIA COMERCIAL: Antes de executar, pare e pense. Qual é o perfil desta empresa? Por que estamos buscando este contato?\n"
            f"ETAPAS PARA ESTA ATIVIDADE (siga com calma e inteligência, EXATAMENTE nesta ordem):\n"
            f"  1. pipedrive_get_org → (OBRIGATÓRIO) Obtenha os dados e contexto da empresa. Se a empresa já tiver um contexto salvo ou dossiê, NÃO chame deep_company_investigation. Pule direto para o passo 2.\n"
            f"  2. pipedrive_get_persons → mapear os contatos da empresa.\n"
            f"  3. evaluate_prospects → (OPCIONAL) Faça o ranking inteligente APENAS SE o plano de prospecção salvo não indicar quem é o melhor decisor, ou se você encontrou novos contatos relevantes.\n"
            f"  4. Raciocínio Estratégico → Explique em 2-3 frases por que o contato X é o melhor (senioridade, canal).\n"
            f"  5. Ação de Associação → SE o contato for [Banco Local] / sem ID Pipedrive numérico, use `pipedrive_create_person`. SE ele já tiver ID numérico, proponha vincular ao negócio via `pipedrive_update_deal`.\n"
            f"  6. Concluir a busca → `pipedrive_update_task(activity_id={act_id}, done=true)` para finalizar esta tarefa!\n"
            f"  7. Outreach ou Mapeamento → Proponha enviar apresentação (`generate_sales_message`) OU se ninguém for bom `open_hierarchy_drawer({_act_args})`.\n"
            f"⛔ PROIBIDO: NÃO crie nova tarefa de busca — marque esta atividade (id={act_id}) como concluída ao finalizar.\n\n"
        )
