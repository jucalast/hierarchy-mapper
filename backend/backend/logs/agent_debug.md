# 🕵️ Investigação: proc_49d48e47 (2026-06-19 16:05:05)
**Mensagem Original**: `[ALERTA DE CONTEXTO DO SISTEMA: O usuário está na página da empresa "Indusvalves Indústria E Comércio De Válvulas E Acessórios" (org_id=1077).
REGRA CRÍTICA: Se o usuário pedir para atualizar ou concluir uma tarefa e NÃO fornecer o ID explícito na mensagem atual, VOCÊ É ESTRITAMENTE PROIBIDO de adivinhar ou usar IDs de tarefas do histórico. Você DEVE obrigatoriamente chamar a ferramenta `pipedrive_get_activities` com org_id=1077 para descobrir o ID correto antes de atualizar. Não atualize atividades cegamente.]

Gerar plano de prospecção para esta empresa`
**Org ID**: `1077` | **Preferência**: `None`

---

## 🔄 Turno 0
### 🤖 Chamada LLM
<details><summary><b>System Prompt</b> (clique para expandir)</summary>

```text
Data de Referência: 2026-06-19

Você é um Agente de Execução focado em CRM. 
O usuário enviou uma mensagem direta ou pedido pontual.
1. Prioridade Absoluta: Cumpra a ordem da forma mais ágil possível usando a ferramenta EXATA solicitada (ex: se o usuário pediu para "criar tarefa", você DEVE usar `pipedrive_create_task` e PROIBIDO usar `generate_sales_message`).
2. Fim da Burocracia: É ESTRITAMENTE PROIBIDO realizar a investigação padrão. Não chame `deep_company_investigation`, `evaluate_prospects` ou ferramentas de pesquisa a menos que explicitamente ordenado. Vá direto para a ação de escrita.
3. Fim de Turno OBRIGATÓRIO: Chame suggest_next_actions após cumprir a solicitação pontual.


[CONTEXTO DE BACKGROUND DA TAREFA ATUAL]:
O usuário pediu uma ação pontual (diretiva livre) dentro desta tarefa. As regras da diretiva livre (Fim da burocracia) são SOBERANAS e você DEVE cumpri-las e pular quaisquer investigações ou Fases obrigatórias ditadas no texto abaixo. Eis o background apenas para que você tenha contexto das regras de negócio gerais:

You are executing the Prospecting & Enrichment skill for B2B sales.
Follow these steps strictly:
1. CHECK context first (`pipedrive_get_org`). Only use Data Enrichment (`deep_company_investigation`) if you do NOT have a saved Dossier or Prospecting Plan.
2. Fetch the persons (`pipedrive_get_persons`). 

⚠️ REGRA CRÍTICA — ZERO CONTATOS:
Se `pipedrive_get_persons` retornar 0 contatos (ou nenhum contato com canal válido de comunicação):
  → Chame `open_hierarchy_drawer` IMEDIATAMENTE para abrir o mapeador de hierarquia.
  → O mapeador vai descobrir os decisores da empresa automaticamente.
  → Após o mapeamento, gere o plano de prospecção (`generate_prospecting_plan`) com os dados obtidos.
  → Em seguida, siga com a pipeline normal a partir do passo 5 (evaluate_prospects).
  → NÃO trave, NÃO encerre o turno — o mapeamento é a ação correta quando não há contatos.

3. Generate a Prospecting Plan (`generate_prospecting_plan`) if one does not exist yet. ESTA ETAPA É OBRIGATÓRIA antes de decidir quem salvar. (Pule este passo se já chamou open_hierarchy_drawer acima — o plano será gerado após o mapeamento.)
4. Output a summary of the context/Dossier and the Prospecting Plan to the user.
5. Evaluate the persons (`evaluate_prospects`) based on the Prospecting Plan to identify the most suitable decision maker(s) (o contato mais apto).
6. Apply Multithreading: Try to identify/save at least 2 key decision makers in the hierarchy to avoid single-point failure.
7. BEFORE any outreach, ensure the contact is in Pipedrive and linked to the deal:
    - If the person exists in the local DB (`[ID:LocalDB]`) and needs to be added to Pipedrive, suggest `pipedrive_create_person`.
    - If the person has a numeric Pipedrive ID but is not linked to the current deal, suggest `pipedrive_update_deal` to link them.
8. Once contacts are in Pipedrive and linked, then for any outreach (email/whatsapp), suggest creating a task in Pipedrive for sending the message (e.g., `pipedrive_create_task` with subject="Enviar Email para [Nome]").
9. Finish the task. VOCÊ É OBRIGADO A CHAMAR A FERRAMENTA `suggest_next_actions` NO FINAL PARA GERAR OS CARDS DE APROVAÇÃO (ex: concluir tarefa, enviar email). NUNCA escreva sugestões de ação diretamente em formato de texto para o usuário. Sempre use a tool `suggest_next_actions`.

[REGRA GLOBAL DE IDIOMA]: Você deve OBRIGATORIAMENTE se comunicar com o usuário em PORTUGUÊS (PT-BR) em todas as suas respostas, resumos e sugestões. Nunca responda em inglês.
```
</details>

**Contexto Recente do Histórico**:
- **USER**:
```json
[ALERTA DE CONTEXTO DO SISTEMA: O usuário está na página da empresa "Indusvalves Indústria E Comércio De Válvulas E Acessórios" (org_id=1077).
REGRA CRÍTICA: Se o usuário pedir para atualizar ou concluir uma tarefa e NÃO fornecer o ID explícito na mensagem atual, VOCÊ É ESTRITAMENTE PROIBIDO de adivinhar ou usar IDs de tarefas do histórico. Você DEVE obrigatoriamente chamar a ferramenta `pipedrive_get_activities` com org_id=1077 para descobrir o ID correto antes de atualizar. Não atualize atividades cegamente.]

Gerar plano de prospecção para esta empresa
[OBRIGATÓRIO - ESCOPO EXCLUSIVO DA EMPRESA]: Você está no chat dedicado da empresa 'Indusvalves Indústria E Comércio De Válvulas E Acessórios' (org_id=1077). Todas as suas respostas, investigações, buscas e ações de ferramentas devem ser direcionadas ESTRITAMENTE a esta empresa e seus contatos associados. Não cite, não investigue e não execute tarefas de outras empresas ou contatos fora deste escopo.

[INSTRUÇÕES DA PIPELINE]
🎯 MISSÃO: Investigar o histórico de relacionamento e gerar um Plano de Prospecção SPIN Selling completo.
ETAPAS (siga com calma e inteligência, EXATAMENTE nesta ordem):
  1. Chame `pipedrive_get_org(org_id=1077)` para coletar dados da organização e deals do CRM.
  2. Chame `pipedrive_get_persons(org_id=1077)` para mapear os contatos/decisores cadastrados.
  3. Com os contatos mapeados, chame `batch_communication_search` para buscar todo o histórico de WhatsApp e E-mail de uma só vez.
     ⚠️ OBRIGATÓRIO: Sempre execute a busca de histórico para garantir que o plano use a prospecção real do vendedor.
  4. Chame `generate_prospecting_plan(org_id=1077, force_regenerate=true)` para cruzar a investigação e gerar o plano SPIN.
  5. Apresente o plano ao usuário em formato Markdown rico no chat.
  6. Ofereça sugestões de próximas ações usando `suggest_next_actions`.
⛔ PROIBIDO: Não invente dados — use APENAS o que foi coletado nas ferramentas.
⛔ PROIBIDO: Não use placeholders genéricos — o plano deve ter nomes e dados reais.


```
### 📥 Resposta Bruta do Modelo
```json
{
  "content": [
    {
      "type": "tool_use",
      "id": "call_943a1844",
      "name": "pipedrive_get_org",
      "input": {
        "org_id": 1077
      }
    },
    {
      "type": "tool_use",
      "id": "call_025ec1e1",
      "name": "pipedrive_get_persons",
      "input": {
        "org_id": 1077
      }
    }
  ],
  "stop_reason": "tool_use",
  "_successful_provider": "gemini",
  "_successful_model": "gemini-2.5-flash-lite"
}
```
#### 🛠️ Executando: `pipedrive_get_org`
**Argumentos**: `{"org_id": 1077}`
#### 📦 Resultado da Ferramenta: `pipedrive_get_org`
```json
{
  "ok": true,
  "org": {
    "id": 1077,
    "name": "Indusvalves Indústria E Comércio De Válvulas E Acessórios"
  },
  "org_id": 1077,
  "cnpj": "07695648000179",
  "temperature": null,
  "prospecting_context": null,
  "deals": [
    {
      "id": 2656,
      "title": "Negócio - Indusvalves®",
      "status": "open",
      "stage_id": 2,
      "value": 0,
      "currency": "BRL",
      "person_id": null,
      "person_name": null,
      "updated": "2026-06-19"
    }
  ],
  "persons": [],
  "summary": "Indusvalves Indústria E Comércio De Válvulas E Acessórios | CNPJ: 07695648000179 | 1 deal(s): Negócio - Indusvalves® (open) | 0 contato(s)"
}
```

---
#### 🛠️ Executando: `pipedrive_get_persons`
**Argumentos**: `{"org_id": 1077}`
#### 📦 Resultado da Ferramenta: `pipedrive_get_persons`
```json
{
  "ok": true,
  "org": "Indusvalves Indústria E Comércio De Válvulas E Acessórios",
  "persons": [
    {
      "id": null,
      "local_id": 639,
      "name": "SERGIO ANTONIO LEMES",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 640,
      "name": "SONIA MARIA NUNES",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 637,
      "name": "Luiz Indusvalves Pessoa",
      "phone": null,
      "email": "luiz.pessoa@indusvalves.com.br",
      "email_validated": true,
      "role": "Gerente de Negócios - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [
        "Email"
      ],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 633,
      "name": "EURIVON BARBOSA HENRIQUE",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio-Administrador - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 634,
      "name": "Fabio Pereira",
      "phone": null,
      "email": "fabio.pereira@indusvalves.com.br",
      "email_validated": true,
      "role": "Vendas nacionais - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [
        "Email"
      ],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 635,
      "name": "HELIO PEREIRA LUCAS",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 636,
      "name": "JADIR ROBERTO SIGOLI",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 638,
      "name": "MAYARA SILVA LOPES",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 641,
      "name": "VERA LUCIA ALVES DA SILVA",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 642,
      "name": "WILSON LEONARDO GOSSE DA SILVA",
      "phone": null,
      "email": null,
      "email_validated": false,
      "role": "Sócio-Administrador - Setor: Quadro de Sócios (QSA)",
      "department": "Quadro de Sócios (QSA)",
      "channels": [],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    },
    {
      "id": null,
      "local_id": 646,
      "name": "Tatiana Papini",
      "phone": null,
      "email": "tatiana.papini@indusvalves.com.br",
      "email_validated": true,
      "role": "Analista de Logística - Setor: Operations",
      "department": "Operations",
      "channels": [
        "Email"
      ],
      "source": "Banco Local",
      "temperature": null,
      "prospecting_context": null
    }
  ],
  "count": 11,
  "summary": "11 contatos em Indusvalves Indústria E Comércio De Válvulas E Acessórios: SERGIO ANTONIO LEMES (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum), SONIA MARIA NUNES (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum), Luiz Indusvalves Pessoa (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: luiz.pessoa@indusvalves.com.br), EURIVON BARBOSA HENRIQUE (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum), Fabio Pereira (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: fabio.pereira@indusvalves.com.br), HELIO PEREIRA LUCAS (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum)"
}
```

---

## 🔄 Turno 1
### 🤖 Chamada LLM
<details><summary><b>System Prompt</b> (clique para expandir)</summary>

```text
Data de Referência: 2026-06-19

Você é um Agente de Execução focado em CRM. 
O usuário enviou uma mensagem direta ou pedido pontual.
1. Prioridade Absoluta: Cumpra a ordem da forma mais ágil possível usando a ferramenta EXATA solicitada (ex: se o usuário pediu para "criar tarefa", você DEVE usar `pipedrive_create_task` e PROIBIDO usar `generate_sales_message`).
2. Fim da Burocracia: É ESTRITAMENTE PROIBIDO realizar a investigação padrão. Não chame `deep_company_investigation`, `evaluate_prospects` ou ferramentas de pesquisa a menos que explicitamente ordenado. Vá direto para a ação de escrita.
3. Fim de Turno OBRIGATÓRIO: Chame suggest_next_actions após cumprir a solicitação pontual.


[CONTEXTO DE BACKGROUND DA TAREFA ATUAL]:
O usuário pediu uma ação pontual (diretiva livre) dentro desta tarefa. As regras da diretiva livre (Fim da burocracia) são SOBERANAS e você DEVE cumpri-las e pular quaisquer investigações ou Fases obrigatórias ditadas no texto abaixo. Eis o background apenas para que você tenha contexto das regras de negócio gerais:

You are executing the Prospecting & Enrichment skill for B2B sales.
Follow these steps strictly:
1. CHECK context first (`pipedrive_get_org`). Only use Data Enrichment (`deep_company_investigation`) if you do NOT have a saved Dossier or Prospecting Plan.
2. Fetch the persons (`pipedrive_get_persons`). 

⚠️ REGRA CRÍTICA — ZERO CONTATOS:
Se `pipedrive_get_persons` retornar 0 contatos (ou nenhum contato com canal válido de comunicação):
  → Chame `open_hierarchy_drawer` IMEDIATAMENTE para abrir o mapeador de hierarquia.
  → O mapeador vai descobrir os decisores da empresa automaticamente.
  → Após o mapeamento, gere o plano de prospecção (`generate_prospecting_plan`) com os dados obtidos.
  → Em seguida, siga com a pipeline normal a partir do passo 5 (evaluate_prospects).
  → NÃO trave, NÃO encerre o turno — o mapeamento é a ação correta quando não há contatos.

3. Generate a Prospecting Plan (`generate_prospecting_plan`) if one does not exist yet. ESTA ETAPA É OBRIGATÓRIA antes de decidir quem salvar. (Pule este passo se já chamou open_hierarchy_drawer acima — o plano será gerado após o mapeamento.)
4. Output a summary of the context/Dossier and the Prospecting Plan to the user.
5. Evaluate the persons (`evaluate_prospects`) based on the Prospecting Plan to identify the most suitable decision maker(s) (o contato mais apto).
6. Apply Multithreading: Try to identify/save at least 2 key decision makers in the hierarchy to avoid single-point failure.
7. BEFORE any outreach, ensure the contact is in Pipedrive and linked to the deal:
    - If the person exists in the local DB (`[ID:LocalDB]`) and needs to be added to Pipedrive, suggest `pipedrive_create_person`.
    - If the person has a numeric Pipedrive ID but is not linked to the current deal, suggest `pipedrive_update_deal` to link them.
8. Once contacts are in Pipedrive and linked, then for any outreach (email/whatsapp), suggest creating a task in Pipedrive for sending the message (e.g., `pipedrive_create_task` with subject="Enviar Email para [Nome]").
9. Finish the task. VOCÊ É OBRIGADO A CHAMAR A FERRAMENTA `suggest_next_actions` NO FINAL PARA GERAR OS CARDS DE APROVAÇÃO (ex: concluir tarefa, enviar email). NUNCA escreva sugestões de ação diretamente em formato de texto para o usuário. Sempre use a tool `suggest_next_actions`.

[REGRA GLOBAL DE IDIOMA]: Você deve OBRIGATORIAMENTE se comunicar com o usuário em PORTUGUÊS (PT-BR) em todas as suas respostas, resumos e sugestões. Nunca responda em inglês.
```
</details>

**Contexto Recente do Histórico**:
- **ASSISTANT**:
```json
[
  {
    "type": "tool_use",
    "id": "call_943a1844",
    "name": "pipedrive_get_org",
    "input": {
      "org_id": 1077
    }
  },
  {
    "type": "tool_use",
    "id": "call_025ec1e1",
    "name": "pipedrive_get_persons",
    "input": {
      "org_id": 1077
    }
  }
]
```
- **USER**:
```json
[
  {
    "type": "tool_result",
    "tool_use_id": "call_943a1844",
    "tool_name": "pipedrive_get_org",
    "content": "📝 RESUMO: Indusvalves Indústria E Comércio De Válvulas E Acessórios | CNPJ: 07695648000179 | 1 deal(s): Negócio - Indusvalves® (open) | 0 contato(s)\n\n🏢 ORG: Indusvalves Indústria E Comércio De Válvulas E Acessórios\n\n💼 DEALS:\n   • [ID:2656] Negócio - Indusvalves® | open | R$0 | Funil: Desconhecido"
  },
  {
    "type": "tool_result",
    "tool_use_id": "call_025ec1e1",
    "tool_name": "pipedrive_get_persons",
    "content": "📝 RESUMO: 11 contatos em Indusvalves Indústria E Comércio De Válvulas E Acessórios: SERGIO ANTONIO LEMES (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum), SONIA MARIA NUNES (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum), Luiz Indusvalves Pessoa (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: luiz.pessoa@indusvalves.com.br), EURIVON BARBOSA HENRIQUE (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum), Fabio Pereira (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: fabio.pereira@indusvalves.com.br), HELIO PEREIRA LUCAS (ID Pipedrive: NULO/NÃO CADASTRADO, tel: nenhum, email: nenhum)\n\n🏢 ORG: Indusvalves Indústria E Comércio De Válvulas E Acessórios\n\n👥 CONTATOS:\n   • [ID:LocalDB] SERGIO ANTONIO LEMES (sem contato) - Cargo: Sócio - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] SONIA MARIA NUNES (sem contato) - Cargo: Sócio - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] Luiz Indusvalves Pessoa (luiz.pessoa@indusvalves.com.br) - Cargo: Gerente de Negócios - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] EURIVON BARBOSA HENRIQUE (sem contato) - Cargo: Sócio-Administrador - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] Fabio Pereira (fabio.pereira@indusvalves.com.br) - Cargo: Vendas nacionais - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] HELIO PEREIRA LUCAS (sem contato) - Cargo: Sócio - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] JADIR ROBERTO SIGOLI (sem contato) - Cargo: Sócio - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] MAYARA SILVA LOPES (sem contato) - Cargo: Sócio - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] VERA LUCIA ALVES DA SILVA (sem contato) - Cargo: Sócio - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] WILSON LEONARDO GOSSE DA SILVA (sem contato) - Cargo: Sócio-Administrador - Setor: Quadro de Sócios (QSA) [Banco Local]\n   • [ID:LocalDB] Tatiana Papini (... [TRUNCADO]"
  }
]
```
### 📥 Resposta Bruta do Modelo
```json
{
  "content": [
    {
      "type": "tool_use",
      "id": "call_c33dd327",
      "name": "batch_communication_search",
      "input": {
        "org_name": "Indusvalves Indústria E Comércio De Válvulas E Acessórios",
        "contacts": [
          {
            "email": "luiz.pessoa@indusvalves.com.br",
            "name": "Luiz Indusvalves Pessoa"
          },
          {
            "email": "fabio.pereira@indusvalves.com.br",
            "name": "Fabio Pereira"
          }
        ]
      }
    }
  ],
  "stop_reason": "tool_use",
  "_successful_provider": "gemini",
  "_successful_model": "gemini-2.5-flash-lite"
}
```
#### 🛠️ Executando: `batch_communication_search`
**Argumentos**: `{"org_name": "Indusvalves Indústria E Comércio De Válvulas E Acessórios", "contacts": [{"email": "luiz.pessoa@indusvalves.com.br", "name": "Luiz Indusvalves Pessoa"}, {"email": "fabio.pereira@indusvalves.com.br", "name": "Fabio Pereira"}]}`
#### 📦 Resultado da Ferramenta: `batch_communication_search`
```json
{
  "ok": true,
  "results": [],
  "count": 0,
  "summary": "Nenhum histórico de comunicação encontrado no WhatsApp ou Email para Indusvalves Indústria E Comércio De Válvulas E Acessórios e seus contatos."
}
```

---

## 🔄 Turno 2
### 🤖 Chamada LLM
<details><summary><b>System Prompt</b> (clique para expandir)</summary>

```text
Data de Referência: 2026-06-19

Você é um Agente de Execução focado em CRM. 
O usuário enviou uma mensagem direta ou pedido pontual.
1. Prioridade Absoluta: Cumpra a ordem da forma mais ágil possível usando a ferramenta EXATA solicitada (ex: se o usuário pediu para "criar tarefa", você DEVE usar `pipedrive_create_task` e PROIBIDO usar `generate_sales_message`).
2. Fim da Burocracia: É ESTRITAMENTE PROIBIDO realizar a investigação padrão. Não chame `deep_company_investigation`, `evaluate_prospects` ou ferramentas de pesquisa a menos que explicitamente ordenado. Vá direto para a ação de escrita.
3. Fim de Turno OBRIGATÓRIO: Chame suggest_next_actions após cumprir a solicitação pontual.


[CONTEXTO DE BACKGROUND DA TAREFA ATUAL]:
O usuário pediu uma ação pontual (diretiva livre) dentro desta tarefa. As regras da diretiva livre (Fim da burocracia) são SOBERANAS e você DEVE cumpri-las e pular quaisquer investigações ou Fases obrigatórias ditadas no texto abaixo. Eis o background apenas para que você tenha contexto das regras de negócio gerais:

You are executing the Prospecting & Enrichment skill for B2B sales.
Follow these steps strictly:
1. CHECK context first (`pipedrive_get_org`). Only use Data Enrichment (`deep_company_investigation`) if you do NOT have a saved Dossier or Prospecting Plan.
2. Fetch the persons (`pipedrive_get_persons`). 

⚠️ REGRA CRÍTICA — ZERO CONTATOS:
Se `pipedrive_get_persons` retornar 0 contatos (ou nenhum contato com canal válido de comunicação):
  → Chame `open_hierarchy_drawer` IMEDIATAMENTE para abrir o mapeador de hierarquia.
  → O mapeador vai descobrir os decisores da empresa automaticamente.
  → Após o mapeamento, gere o plano de prospecção (`generate_prospecting_plan`) com os dados obtidos.
  → Em seguida, siga com a pipeline normal a partir do passo 5 (evaluate_prospects).
  → NÃO trave, NÃO encerre o turno — o mapeamento é a ação correta quando não há contatos.

3. Generate a Prospecting Plan (`generate_prospecting_plan`) if one does not exist yet. ESTA ETAPA É OBRIGATÓRIA antes de decidir quem salvar. (Pule este passo se já chamou open_hierarchy_drawer acima — o plano será gerado após o mapeamento.)
4. Output a summary of the context/Dossier and the Prospecting Plan to the user.
5. Evaluate the persons (`evaluate_prospects`) based on the Prospecting Plan to identify the most suitable decision maker(s) (o contato mais apto).
6. Apply Multithreading: Try to identify/save at least 2 key decision makers in the hierarchy to avoid single-point failure.
7. BEFORE any outreach, ensure the contact is in Pipedrive and linked to the deal:
    - If the person exists in the local DB (`[ID:LocalDB]`) and needs to be added to Pipedrive, suggest `pipedrive_create_person`.
    - If the person has a numeric Pipedrive ID but is not linked to the current deal, suggest `pipedrive_update_deal` to link them.
8. Once contacts are in Pipedrive and linked, then for any outreach (email/whatsapp), suggest creating a task in Pipedrive for sending the message (e.g., `pipedrive_create_task` with subject="Enviar Email para [Nome]").
9. Finish the task. VOCÊ É OBRIGADO A CHAMAR A FERRAMENTA `suggest_next_actions` NO FINAL PARA GERAR OS CARDS DE APROVAÇÃO (ex: concluir tarefa, enviar email). NUNCA escreva sugestões de ação diretamente em formato de texto para o usuário. Sempre use a tool `suggest_next_actions`.

[REGRA GLOBAL DE IDIOMA]: Você deve OBRIGATORIAMENTE se comunicar com o usuário em PORTUGUÊS (PT-BR) em todas as suas respostas, resumos e sugestões. Nunca responda em inglês.
```
</details>

**Contexto Recente do Histórico**:
- **ASSISTANT**:
```json
[
  {
    "type": "tool_use",
    "id": "call_c33dd327",
    "name": "batch_communication_search",
    "input": {
      "org_name": "Indusvalves Indústria E Comércio De Válvulas E Acessórios",
      "contacts": [
        {
          "email": "luiz.pessoa@indusvalves.com.br",
          "name": "Luiz Indusvalves Pessoa"
        },
        {
          "email": "fabio.pereira@indusvalves.com.br",
          "name": "Fabio Pereira"
        }
      ]
    }
  }
]
```
- **USER**:
```json
[
  {
    "type": "tool_result",
    "tool_use_id": "call_c33dd327",
    "tool_name": "batch_communication_search",
    "content": "{\"ok\": true, \"results\": [], \"count\": 0, \"summary\": \"Nenhum histórico de comunicação encontrado no WhatsApp ou Email para Indusvalves Indústria E Comércio De Válvulas E Acessórios e seus contatos.\"}"
  }
]
```
### 📥 Resposta Bruta do Modelo
```json
{
  "content": [
    {
      "type": "tool_use",
      "id": "call_31918cc6",
      "name": "generate_prospecting_plan",
      "input": {
        "org_id": 1077,
        "force_regenerate": true
      }
    }
  ],
  "stop_reason": "tool_use",
  "_successful_provider": "gemini",
  "_successful_model": "gemini-2.5-flash-lite"
}
```
#### 🛠️ Executando: `generate_prospecting_plan`
**Argumentos**: `{"org_id": 1077, "force_regenerate": true}`
