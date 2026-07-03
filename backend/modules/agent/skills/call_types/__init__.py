"""
call_types package: Sub-skills de ligação telefônica.

Arquitetura: CallSkill → CallTypeRouter → [ColdCall | FollowUpCall | ProposalReturn | Gatekeeper]

O router analisa o contexto real (histórico de comunicação, estágio do funil, objetivo da atividade)
e retorna a sub-skill correta com as regras e etapas do Plano de Voo.
"""
from .router import classify_call_type, get_call_type_config, CallType

__all__ = ["classify_call_type", "get_call_type_config", "CallType"]
