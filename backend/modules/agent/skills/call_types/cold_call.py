"""
ColdCallType: Regras e estrutura para ligações de prospecção fria (Cold Call).
"""
from dataclasses import dataclass
from typing import List


@dataclass
class CallTypeResult:
    call_type: str          # "cold_call" | "followup_call" | "proposal_return" | "gatekeeper"
    steps_labels: List[str]  # Labels das etapas do plano de voo
    rules: str               # Regras/diretrizes para o LLM gerar o script
    objective: str           # Instrução de objetivo para o prompt


COLD_CALL_RULES = """
DIRETRIZES DA METODOLOGIA B2B "VIDA REAL" (ABORDAGEM HUMANA, DIRETA E IMERSIVA):
A regra de ouro é: FUJA de falas robóticas, jargões genéricos de telemarketing ou textões. Fale exatamente como uma pessoa real conversando na fábrica. Você deve incorporar AS EXATAS PALAVRAS E O MOLEJO que o vendedor usa na vida real.

ESTRUTURA OBRIGATÓRIA (Gere APENAS o bloco de texto curto para o vendedor ler):
- ABERTURA: "Legal [Nome do Cliente], prazer, sou vendedor da [Sua Empresa]. Sendo bem direto, nós somos especialistas em [Sua Solução/Produto Principal]. Coisas que os grandes fornecedores do mercado não conseguem ou não querem atender. Então nós entregamos [Exemplo Prático 1 do seu Produto] e [Exemplo Prático 2], que são mais personalizados. Temos ajudado empresas como a [Cliente de Referência 1 do Plano] e a [Cliente de Referência 2 do Plano] a resolver problemas com [Dor Principal que a Empresa resolve, ex: embalagens que não se adaptam], gerando avarias ou retrabalho. Você tem enfrentado algum gargalo com isso ultimamente?"
- IMPLICAÇÃO (Sem rodeios): "Legal, obrigado pelo feedback. É o seguinte, quando essas falhas acontecem, vocês já mapearam o quanto mais ou menos de operação e de dinheiro que vocês estão deixando na mesa por conta desse retrabalho ou descarte?"
- QUALIFICAÇÃO (Validação empática e investigação): "Entendi, nossa [Nome], isso é realmente bem sério, né, bem ruim. Mas e esse impacto de [Mencionar a dor dita pelo cliente na ligação, ex: 10% e dois dias perdidos] é realmente significativo. Para eu entender melhor o cenário e como podemos ajudar: quem fornece a solução atual aí para vocês, e onde exatamente a solução deles está falhando, você tem essa informação com você?"
- NECESSIDADE (Reconhecimento e Solução): "É, realmente eu imagino. Legal que vocês já fizeram esse levantamento, significa que vocês estão atentos e querendo resolver essa questão de gargalos, né? Nós atendemos clientes como a [Cliente de Referência 1 do Plano] e eles tinham exatamente esse problema. Nós aplicamos nossas soluções personalizadas e quase zeramos esses gargalos. Se eu te mostrasse em 15 minutos como fizemos isso, faria sentido para você?"
- FECHAMENTO (Primeiro): "Legal, [Nome]. Nossa, isso é muito bom né. E para te mostrar esses exemplos e como aplicamos isso na sua operação, o ideal é que a gente pudesse fazer uma reunião rápida em torno de 15 minutos. Ou terça-feira de manhã ou quinta-feira à tarde, que é o que eu tenho liberado aqui na minha agenda. O que fica melhor para você?"
- FECHAMENTO (Confirmação): "Legal, [Nome], acredito que vai ser muito bom e fica combinado então. [Dia/Horário] está anotado, eu vou te enviar o convite agora mesmo com os detalhes e já adianto o estudo do seu cenário para otimizarmos o nosso tempo, combinado?"

REGRA CRÍTICA PARA AS VARIÁVEIS (PROIBIDO DEIXAR CHAVES/COLCHETES NA SAÍDA FINAL):
Você NUNCA deve cuspir as tags [Sua Solução], [Dor Principal], [Exemplo Prático 1] ou [Cliente de Referência 1] no texto que o vendedor vai ler.
Você DEVE OBRIGATORIAMENTE substituir essas tags pelos dados reais do contexto.
O vendedor vai ler essa frase ao vivo, então ela tem que estar 100% preenchida, sem nenhum colchete ou variável vazia!
"""

COLD_CALL_STEPS = ["ABERTURA", "SITUAÇÃO + PROBLEMA", "IMPLICAÇÃO", "QUALIFICAÇÃO", "NECESSIDADE", "FECHAMENTO"]
