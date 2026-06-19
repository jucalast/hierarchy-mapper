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
