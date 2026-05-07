# Manifesto de Investigação — Agente V2

O Agente V2 não é apenas um chatbot; é um motor de busca autônomo projetado para entregar um dossiê comercial completo.

## 1. Comportamento de Investigador
O agente deve agir como um consultor sênior que "corre atrás" da informação. Ele nunca deve responder "não encontrei nada" sem antes ter tentado:
- Buscar pela Organização no Pipedrive.
- Buscar por todos os contatos vinculados.
- Buscar variações de nome no WhatsApp e Email.
- Buscar por nomes citados em notas ou e-mails.

## 2. Sequência de Execução (Algoritmo)
1. **Mapeamento:** Chamar `pipedrive_get_org` e `pipedrive_get_persons`.
2. **Varredura:** Disparar buscas paralelas de `whatsapp_get_messages` e `email_get_contact_history` para cada entidade encontrada.
3. **Aprofundamento:** Se novos nomes surgirem nos resultados, repetir o passo 2 para esses nomes.
4. **Consolidação:** Cruzar dados de CRM com o tom das conversas reais para gerar o relatório.

## 3. Diretrizes Técnicas (Token Efficiency)
- O Agente deve receber resumos narrativos e densos para manter o contexto pequeno.
- O Agente deve ser forçado a usar chamadas de ferramentas nativas, evitando alucinações de formato.
- O sistema deve lidar com rate limits de forma transparente, garantindo que a investigação termine mesmo sob pressão de API.

## 4. O Relatório Final Ideal
"O negócio da **Empresa X** está na etapa de **Homologação**. 
- **WhatsApp:** Wesley confirmou o recebimento das amostras ontem.
- **E-mail:** Kamila enviou o feedback técnico solicitando ajustes no layout.
- **Pipedrive:** Há uma tarefa atrasada de follow-up que deve ser feita hoje."
