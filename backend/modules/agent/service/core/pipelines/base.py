"""
modules.agent.service.core.pipelines.base
===========================================
Classe base para pipelines de tarefas do agente CRM.
"""
from typing import Any

class BasePipeline:
    """Classe base para as esteiras/pipelines do agente CRM."""
    name: str = "Base"
    description: str = "Pipeline base"
    intent_name: str = "base"

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        """
        Verifica se a tarefa atual atende aos critérios desta pipeline.
        
        Args:
            subject: Título da atividade no CRM.
            act_type: Tipo exato da atividade cadastrada no CRM (ex: call, email).
        """
        raise NotImplementedError

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        """
        Gera o prompt contendo as etapas determinísticas a serem injetadas.

        Args:
            subject: Título da atividade.
            act_id: ID da atividade.
            org_pd_id: ID da empresa.
            deal_id: ID do negócio.
        """
        raise NotImplementedError

    # Mapa de etapas do funil (stage_id) — fonte única para sugestões de avanço.
    STAGE_MAP_HINT = (
        "MAPA DE ETAPAS (target_stage = ID numérico): "
        "Funil 'Novos Negócios' → 2=Entrada, 18=Qualificação, 19=Contatado, 4=Reunião Agendada, "
        "26=Reunião Realizada, 27=Proposta em Andamento, 28=Em Negociação. "
        "Funil 'Carteira' → 14=Entrada, 16=Contato, 17=Proposta, 32=Programação."
    )

    @classmethod
    def stage_advancement_step(cls, step_num: Any, deal_id: Any, outcome_hint: str) -> str:
        """
        Passo final reutilizável: sugere avançar o deal para a etapa certa do funil
        de forma inteligente, com base no que acabou de ser executado.

        Chama `pipedrive_advance_deal` (write tool), que abre um card de confirmação —
        NUNCA avança automaticamente. É uma SUGESTÃO que o João aprova.
        """
        return (
            f"  {step_num}. 🎯 SUGESTÃO INTELIGENTE DE ETAPA (só APÓS a tarefa acima concluir com ok=true):\n"
            f"      Avalie se o negócio deal_id={deal_id} deve AVANÇAR de etapa no funil, com base no que ACABOU de acontecer: {outcome_hint}.\n"
            f"      → Se você ainda não sabe a ETAPA ATUAL nem o deal_id desta empresa, chame pipedrive_get_deals ANTES para descobrir.\n"
            f"      → Considere a ETAPA ATUAL do deal. É PROIBIDO sugerir a etapa atual ou uma anterior — só faz sentido AVANÇAR. Respeite o MESMO funil do deal (Novos Negócios vs Carteira).\n"
            f"      → Se o avanço se justifica, chame `pipedrive_advance_deal(deal_id={deal_id}, target_stage='<ID da etapa destino>', reason='<motivo curto e específico>')`. Isso abre um card de confirmação para o João — NÃO avança sozinho.\n"
            f"      → Se o deal já está na etapa adequada (ou mais avançada), NÃO chame a ferramenta; apenas diga em UMA linha que a etapa já está correta.\n"
            f"      {cls.STAGE_MAP_HINT}\n\n"
        )
