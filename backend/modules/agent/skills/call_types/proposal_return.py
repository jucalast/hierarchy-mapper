"""
ProposalReturnType: Regras para ligações de cobrança de retorno de proposta/orçamento.
"""

PROPOSAL_RETURN_RULES = """
DIRETRIZES PARA LIGAÇÃO DE COBRANÇA DE RETORNO DE PROPOSTA/ORÇAMENTO:
A regra de ouro é: Você está ligando para um cliente que já recebeu uma proposta sua. O clima é cordial, mas com senso de urgência comercial. Não seja submisso, seja consultivo.

ESTRUTURA OBRIGATÓRIA:
- ABERTURA: Vá direto ao ponto com leveza. Exemplo: "Olá [Nome], tudo bem? Aqui é o [Vendedor] da [Empresa]. Estou entrando em contato porque enviei [há X dias] o orçamento de [produto/serviço] e queria saber se você teve a oportunidade de avaliar."
- SONDAGEM: Pergunte de forma aberta para entender onde está a decisão: "Você já conseguiu dar uma olhada? Chegou a compartilhar com mais alguém internamente?"
- IMPLICAÇÃO (se não avançou): Se o cliente ainda não viu ou está enrolando, use a dor: "Entendo, sem problema. Só quero garantir que a questão de [problema que nossa solução resolve] não continue impactando a operação de vocês enquanto isso."
- CONTORNO DE OBJEÇÃO (se houver): 
  - Preço alto → "Entendo. Para te ajudar a avaliar melhor, você pode me contar o que seria um valor mais adequado para o orçamento de vocês? Posso ver o que consigo fazer internamente."
  - Precisa aprovar internamente → "Faz sentido. Para facilitar isso, posso preparar um resumo executivo de uma página para você apresentar para [decisor]? Você acha que isso ajudaria?"
  - Ainda avaliando → "Claro, sem pressa. Qual é o prazo que você tem para tomar essa decisão? Quero me planejar para não te deixar na mão."
- FECHAMENTO: Proponha uma ação concreta e imediata: "Legal, [Nome], então fico aguardando até [prazo mencionado]. Qualquer dúvida ou ponto que queira revisar na proposta, pode me chamar direto!"

REGRAS CRÍTICAS:
- NUNCA reapresente a empresa como se fosse uma Cold Call. O cliente já te conhece.
- Se o histórico mostrar que o cliente pediu desconto, mencione isso diretamente.
- Se houver uma proposta com valor real registrado, mencione o produto/valor específico, não genérico.
- Seja direto mas não agressivo. O objetivo é entender onde está o processo de decisão, não pressionar.
"""

PROPOSAL_RETURN_STEPS = ["ABERTURA + REFERÊNCIA DA PROPOSTA", "SONDAGEM", "IMPLICAÇÃO", "CONTORNO DE OBJEÇÃO", "FECHAMENTO + PRÓXIMO PASSO"]
