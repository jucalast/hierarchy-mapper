"""
modules.agent.service.core.pipelines.call
===========================================
Pipeline de Ligação (Call) do agente CRM.
"""
from typing import Any
from modules.agent.service.core.pipelines.base import BasePipeline

class CallPipeline(BasePipeline):
    """Pipeline voltada para ligações telefônicas (Calls)."""
    name = "Call"
    description = "Pipeline para ligações e roteiros de voz"

    _call_keys = [
        "ligar", "realizar ligação", "fazer ligação", "ligar para",
        "ligação", "telefonar", "call",
    ]

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        s = subject.lower()
        t = (act_type or "").lower()

        # Travas para evitar que comunicações escritas caiam em ligação
        _writing_indicators = ["email", "e-mail", "whatsapp", "mensagem", "mandar msg", "apresentação", "apresentar"]
        if t in ("email", "mensagem") or any(w in s for w in _writing_indicators):
            return False

        # Ativa se o tipo for ligação ou se houver palavra-chave sem indicadores de escrita
        return t == "call" or t == "ligação" or any(k in s for k in cls._call_keys)

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → obter número de telefone REAL do CRM (nunca invente)\n"
            f"  2. generate_call_script(contact_name, phone) → (OBRIGATÓRIO) roteiro da ligação telefônica baseada no histórico\n"
            f"  3. Apresente ao João o roteiro e o número confirmado para aprovação\n"
            f"  4. pipedrive_update_task(activity_id={act_id}, done=true) → marcar após execução e registrar nota\n"
            f"⛔ PROIBIDO: nunca invente ou assuma um número de telefone — use APENAS o retornado pelo CRM.\n"
            f"⛔ PROIBIDO: não envie emails ou mensagens diretas sem que o usuário solicite explicitamente — o foco aqui é a ligação telefônica.\n\n"
        )
