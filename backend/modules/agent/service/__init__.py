"""
Agente comercial LinkB2B.

Estrutura modular:
  core/           — loop de execução (loop.py), runner (runner.py), phase tracker
  prompts/        — system prompts por perfil de modelo
  tools/          — ferramentas de leitura e escrita (registry, pipedrive, communication, intelligence)
  sanitizers/     — compactação de resultados para o LLM (email, pipedrive, whatsapp)
  llm/            — adaptadores de formato (adapters.py), rate limiting (rate_limiter.py), caller
  helpers.py      — utilitários: _emit, _raw_log, _fix_corrupted_name, _get_label, etc.

API pública:
  run_agent()                 — gerador assíncrono, emite NDJSON
  resume_after_confirmation() — retoma após aprovação de ação de escrita
"""
from modules.agent.service.core.runner import run_agent, resume_after_confirmation

__all__ = ["run_agent", "resume_after_confirmation"]
