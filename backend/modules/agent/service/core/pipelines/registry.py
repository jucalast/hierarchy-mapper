"""
modules.agent.service.core.pipelines.registry
==============================================
Orquestrador e registro central de pipelines para o agente CRM.
"""
from typing import Any, List, Type
from core.observability.logging_config import get_logger
from modules.agent.service.core.pipelines.base import BasePipeline
from modules.agent.service.core.pipelines.search import SearchPipeline
from modules.agent.service.core.pipelines.followup import FollowupPipeline
from modules.agent.service.core.pipelines.meeting import MeetingPipeline
from modules.agent.service.core.pipelines.quote import QuotePipeline
from modules.agent.service.core.pipelines.communication import CommunicationPipeline
from modules.agent.service.core.pipelines.call import CallPipeline
from modules.agent.service.core.pipelines.prospecting_plan import ProspectingPlanPipeline

log = get_logger(__name__)

class PipelineRegistry:
    """Registro e orquestrador de correspondência de pipelines."""
    
    # Ordem estrita de correspondência: das mais específicas para as mais gerais
    _pipelines: List[Type[BasePipeline]] = [
        ProspectingPlanPipeline,
        SearchPipeline,
        FollowupPipeline,
        MeetingPipeline,
        QuotePipeline,
        CommunicationPipeline,  # Comunicação escrita precede chamadas de voz
        CallPipeline,           # Ligações telefônicas puras
    ]

    @classmethod
    def dispatch(cls, subject: str, act_type: str, act_id: Any, org_pd_id: Any, deal_id: Any, pipeline_intent: Optional[str] = None) -> str:
        """
        Orquestra a correspondência e retorna as etapas da pipeline selecionada.
        Retorna string vazia se nenhuma pipeline for correspondida (raciocínio livre).
        """
        from typing import Optional
        subj_clean = subject.strip()
        type_clean = act_type.strip() if act_type else ""

        # 1. Tenta correspondência semântica via classificação inteligente do LLM
        if pipeline_intent and pipeline_intent != "none":
            for pipeline in cls._pipelines:
                if getattr(pipeline, "intent_name", None) == pipeline_intent:
                    log.info(
                        "agent.pipeline.dispatched.llm",
                        pipeline=pipeline.name,
                        intent=pipeline_intent,
                        subject=subj_clean,
                        act_id=act_id
                    )
                    return pipeline.build_steps(subj_clean, act_id, org_pd_id, deal_id)

        # 2. Fallback resiliente baseado em regras estáticas (Regex)
        for pipeline in cls._pipelines:
            if pipeline.matches(subj_clean, type_clean):
                log.info(
                    "agent.pipeline.dispatched",
                    pipeline=pipeline.name,
                    subject=subj_clean,
                    act_type=type_clean,
                    act_id=act_id
                )
                return pipeline.build_steps(subj_clean, act_id, org_pd_id, deal_id)

        log.info(
            "agent.pipeline.none_matched",
            subject=subj_clean,
            act_type=type_clean,
            act_id=act_id
        )
        return ""
