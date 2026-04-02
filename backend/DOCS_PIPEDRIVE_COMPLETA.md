# 📘 BÍBLIA DEFINITIVA: INTEGRAÇÃO PIPEDRIVE CRM & B2B INTELLIGENCE

Este documento é a especificação técnica exaustiva para a integração de alta fidelidade entre o **B2B Hierarchy Mapper** e o **Pipedrive CRM**. Ele serve como guia para desenvolvedores, arquitetos de dados e integradores.

---

## 🚀 1. VISÃO GERAL DA ARQUITETURA

Nossa integração segue o modelo **"Enrich-and-Inject"**. O motor OSINT extrai e purifica a hierarquia, enquanto esta camada de integração garante que cada "Node" do gráfico se torne um ponto de contato acionável no CRM.

### Estrutura de Objetos (Mapeamento de 1ª Classe)
- **Organização (Organization):** O hub central da conta. Criado uma única vez por domínio de empresa.
- **Pessoa (Person):** O lead enriquecido com cargo purificado pela nossa IA.
- **Negócio (Deal):** A oportunidade de venda aberta no funil para cada stakeholder chave.
- **Atividade (Activity):** O registro histórico de quando o scan foi feito e o que foi descoberto.

---

## 🔐 2. AUTENTICAÇÃO E SEGURANÇA (MASTERING AUTH)

O Pipedrive suporta dois pilares de autenticação. Nossa arquitetura deve ser híbrida:

### A. Integração via API Token (Integração Direta/Privada)
Para o robô que injeta leads vindos do Scanner.
- **API v1:** URL base: `https://api.pipedrive.com/v1/`
  - *Sintaxe:* `POST /persons?api_token=xyz`
- **API v2:** URL base: `https://api.pipedrive.com/v2/`
  - *Header Sugerido:* `x-api-token: seu_token` (Mais seguro, evita logs de URL com tokens).

### B. OAuth 2.0 (Aplicações em Escala)
Necessário para apps de marketplace.
1. **Redirect URI:** Pipedrive envia o `code`.
2. **Token Exchange:** Backend troca `code` por `access_token` e `refresh_token`.
3. **Renewal:** Tokens expiram em 1 hora. O sistema deve gerenciar o refresh automático via cron ou middleware.

---

## 📂 3. DICIONÁRIO DE DADOS (ENTIDADES CORE)

### 👤 Pessoa (Person)
Campos obrigatórios e recomendados para a nossa captura:
| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `name` | String | Nome completo extraído do LinkedIn. |
| `org_id` | Integer | ID da Organização vinculada. |
| `email` | Array | Lista de emails corporativos (gerados por nossa lógica de probabilidade). |
| `phone` | Array | Telefones identificados. |
| `label` | Integer | Senioridade (C-Level=1, VP=2, etc). |
| `visible_to` | Integer | Permissões (3 = Empresa inteira). |

### 🏢 Organização (Organization)
| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `name` | String | Razão Social ou Marca Identificada (Böttcher, Nouryon). |
| `address` | String | Endereço completo (BrasilAPI). |
| `owner_id` | Integer | ID do vendedor responsável no Pipedrive. |

---

## 🧠 4. CONFIGURAÇÃO DE CAMPOS CUSTOMIZADOS (O PULO DO GATO)

O Pipedrive é limitado por padrão. Precisamos "ensinar" ele a entender os nossos dados de IA. 

**IDs de Campos que precisaremos criar via API (`POST /personFields`):**
1. **LinkedIn Profile URL:** `text` (Ex: `https://br.linkedin.com/in/helen-lima`)
2. **Cargo Purificado (IA):** `text` (Ex: `Gerente de Planejamento e Custos`)
3. **Departamento OSINT:** `enum` (Logística, Suprimentos, TI, RH)
4. **ID do Scan Original:** `integer` (Para rastreabilidade)

---

## 📡 5. WEBHOOKS v2 (SISTEMA NERVOSO CENTRAL)

Para não sermos apenas um "enviador de dados", o sistema deve ouvir o Pipedrive.

### Exemplo de Payload Recebido (create.deal)
```json
{
  "meta": {
    "action": "create",
    "entity": "deal",
    "company_id": "12345",
    "timestamp": "2026-04-02T12:00:00.000Z",
    "version": "2.0"
  },
  "data": {
    "id": 999,
    "title": "Deal de Teste",
    "status": "open",
    "org_id": 50,
    "person_id": 80
  }
}
```

### Eventos Críticos para Assinar:
- `change.deal`: Se um negócio entrar em "Lost", podemos disparar uma IA para analisar o porquê ou sugerir um novo stakeholder na mesma conta.
- `create.person`: Quando um vendedor cadastrar alguém manualmente, podemos disparar o Scanner para enriquecer o cargo dele automaticamente.

---

## 🚦 6. RATE LIMITING E PERFORMANCE (LIMITES TÉCNICOS)

O Pipedrive é rigoroso. Nossa camada `pipedrive_service.py` deve implementar:

| Ponto de Falha | Código HTTP | Solução Corretiva |
| :--- | :--- | :--- |
| **Limite de Taxa** | `429` | Implementar `Exponential Backoff` (Girar a cada 2s). |
| **Token Inválido** | `401` | Disparar alerta imediato no Slack/Email do Admin. |
| **Entidade Grande** | `413` | Truncar textos longos de snippets da IA antes do envio. |

---

## ⚙️ 7. LÓGICA DE SINCRONIZAÇÃO (BEST PRACTICES)

### Algoritmo de "Upsert" (Update or Insert)
Para evitar 10 registros da mesma pessoa, o robô faz:
1. **BUSCA:** Procure por `Person` via `GET /persons/search?term=email_do_lead`.
2. **DECISÃO:**
   - **Encontrou?** Use `PUT /persons/{id}` para atualizar com o cargo purificado mais recente.
   - **Não encontrou?** Use `POST /persons` para criar do zero.

---

## 🛠️ 8. FERRAMENTAS PARA O DESENVOLVEDOR

- **Postman Collection:** [Pipedrive API Postman](https://pipedrive.readme.io/docs/run-pipedrive-api-in-postman-or-insomnia)
- **API Explorer:** `https://developers.pipedrive.com/docs/api/v1/`
- **Log de Auditoria:** Nosso backend deve salvar cada `request_id` do Pipedrive no arquivo `logs/pipedrive_sync.log`.

---

## 🏁 9. CHECKLIST DE IMPLANTAÇÃO

- [ ] Gerou API Token no Pipedrive Sandbox.
- [ ] Criou Campos Customizados (LinkedIn, Cargo IA).
- [ ] Configurou Webhook no Pipedrive apontando para nosso túnel (Ngrok/LocalTunnel).
- [ ] Validou o Pipeline de Senioridade (Mapear 'C-Level' para Labels coloridas).

---
*Documentação gerada automaticamente para o projeto LINKB2B - Abril 2026.*
