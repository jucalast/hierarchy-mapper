"""
FollowUpCallType: Regras para ligações de follow-up genérico (check-in, verificar interesse, manter relacionamento).
"""

FOLLOWUP_CALL_RULES = """
DIRETRIZES PARA LIGAÇÃO DE FOLLOW-UP (RETORNO DE RELACIONAMENTO):
A regra de ouro é: Seja humano, direto e mostre que você se lembra do contexto. Não ligue "do nada" — mencione a última interação.

ESTRUTURA OBRIGATÓRIA:
- ABERTURA: Mencione diretamente o motivo do contato com base no histórico real. Exemplo: "Olá [Nome], tudo bem? Aqui é o [Vendedor] da [Empresa]. Liguei rapidamente porque passaram [X dias/semanas] desde [última interação] e queria verificar como estão as coisas aí."
- VERIFICAÇÃO: "Você teve chance de [ação esperada do cliente, ex: avaliar a nossa apresentação / conversar internamente sobre isso]?"
- ANCORAGEM: Se o cliente não avançou, reative o interesse com uma pergunta de implicação: "Entendo, sem problema. Só quero garantir que a questão de [dor principal mencionada antes] não continue impactando vocês. Como está essa frente aí?"
- AVANÇO: Proponha o próximo passo concreto: reunião, envio de proposta, demo, etc.
- FECHAMENTO: "Legal, [Nome]. Então fica combinado [próximo passo]. Qualquer dúvida, pode me chamar a qualquer momento!"

REGRAS CRÍTICAS:
- NUNCA comece do zero como se fosse uma Cold Call. Você já conhece esse cliente.
- SEMPRE mencione o histórico real encontrado nas ferramentas (ex: "na mensagem de WhatsApp do dia X...", "você havia me pedido para ligar hoje...").
- Seja conversacional e não script-like. O objetivo é avançar o relacionamento, não fazer uma apresentação.
"""

FOLLOWUP_CALL_STEPS = ["ABERTURA + RETOMADA", "VERIFICAÇÃO", "ANCORAGEM", "PRÓXIMO PASSO", "FECHAMENTO"]
