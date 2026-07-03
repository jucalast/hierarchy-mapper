"""
GatekeeperCallType: Regras para ligações cuja meta é ultrapassar o gatekeeper (recepção/PABX) para chegar ao decisor.
"""

GATEKEEPER_RULES = """
DIRETRIZES PARA ABORDAGEM DE RECEPÇÃO/PABX (GATEKEEPER):
A regra de ouro é: NÃO TENTE VENDER PARA A RECEPÇÃO. Seja cordial, profissional, e aja como quem já tem negócios com a empresa.

- ABERTURA (PABX): "Bom dia, aqui é o [Vendedor] da [Empresa]. Por gentileza, você poderia me transferir para o(a) [Nome do Decisor]?"
  - Se não souber o nome: "Por gentileza, quem é o responsável pela área de [área relevante, ex: compras de embalagens / logística]?"
- SONDAGEM (se barrar): Se o gatekeeper pedir mais informações, responda com tom corporativo natural: "É referente ao fornecimento de [produto/serviço] para a área de [área]."
- NUNCA faça o pitch de vendas para o recepcionista. Guarde os diferenciais para o decisor.
- Se transferir: Comemore internamente. Agora prepare a abertura como se fosse uma Cold Call com o decisor.
- Se não conseguir passar: "Sem problema! Você poderia me passar o ramal ou o e-mail direto do(a) [Nome/Cargo]? Obrigado!"
"""

GATEKEEPER_STEPS = ["PABX / RECEPÇÃO", "ABERTURA (COM DECISOR)", "SITUAÇÃO + PROBLEMA", "IMPLICAÇÃO", "QUALIFICAÇÃO", "NECESSIDADE", "FECHAMENTO"]
