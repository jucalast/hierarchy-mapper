"""
modules.agent.service.core.pipelines
======================================
Módulo de Pipelines / Esteiras de Execução do Agente CRM.
Exceções e tipos específicos de atividades são isolados e orquestrados aqui.
"""
from modules.agent.service.core.pipelines.registry import PipelineRegistry

__all__ = ["PipelineRegistry"]
