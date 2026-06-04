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
            f"ETAPAS PARA ESTA ATIVIDADE DE LIGAÇÃO (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → obter número de telefone REAL do CRM (nunca invente)\n"
            f"     → ⚠️ SE O CONTATO NÃO TIVER TELEFONE: Use a ferramenta `find_company_contact` passando o nome da empresa e/ou CNPJ para buscar o telefone na Receita Federal e na Web. Se a ferramenta NÃO encontrar nenhum telefone, então Informe ao João no chat que o contato não possui telefone e PEÇA PARA ELE INFORMAR O NÚMERO. Você OBRIGATORIAMENTE deve escrever a frase 'PARADA ANTECIPADA' na sua resposta para destravar o sistema, e então PARE IMEDIATAMENTE após pedir! (NÃO gere script, NÃO abra a tela de ligação e é ESTRITAMENTE PROIBIDO chamar pipedrive_update_task).\n"
            f"  2. prepare_live_coaching_session(contact_name, phone) → Prepara o plano de voo (passo a passo) para a ligação usando SPIN Selling.\n"
            f"  3. open_ligacao_view() → Abra a interface de transcrição ao vivo IMEDIATAMENTE após preparar a sessão. Não peça aprovação!\n"
            f"  4. Apresente ao usuário o plano de voo gerado e informe que a tela de ligação foi aberta.\n"
            f"⛔ PROIBIDO: NUNCA chame pipedrive_update_task para esta atividade agora. A tarefa só será concluída após a ligação terminar.\n"
            f"⛔ PROIBIDO: nunca invente ou assuma um número de telefone — use APENAS o retornado pelo CRM.\n"
            f"⛔ PROIBIDO: não envie emails ou mensagens diretas sem que o usuário solicite explicitamente — o foco aqui é a ligação telefônica.\n\n"
        )
