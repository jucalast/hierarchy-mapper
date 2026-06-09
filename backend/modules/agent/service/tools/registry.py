"""
Registry de ferramentas do Agente V2: TOOLS dict, execute_write_tool, get_tools_anthropic_schema.
"""
from __future__ import annotations

import json
import httpx
from typing import Any, Dict
from core.observability.logging_config import get_logger
from ._constants import WA_BASE, EMAIL_SERVICE_BASE, JFERRES_DOMAIN
from ._utils import _pipedrive_find_org, _log_activity_bg
from .pipedrive import (
    exec_pipedrive_get_org,
    exec_pipedrive_get_persons,
    exec_pipedrive_get_activities,
    exec_pipedrive_get_deals,
    exec_pipedrive_get_all_activities,
    exec_pipedrive_get_deals_without_tasks,
    exec_pipedrive_bulk_update_tasks,
)
from .communication import (
    exec_whatsapp_get_messages,
    exec_whatsapp_list_chats,
    exec_whatsapp_send_message,
    exec_email_get_inbox,
    exec_email_get_contact_history,
    exec_batch_communication_search,
)
from .intelligence import (
    exec_web_search,
    exec_find_company_contact,
    exec_prepare_live_coaching_session,
    exec_open_ligacao_view,
    exec_generate_sales_message,
    exec_generate_dossier,
    exec_update_prospecting_context,
    exec_open_hierarchy_drawer,
    exec_suggest_next_actions,
    exec_evaluate_prospects,
    exec_deep_company_investigation,
    exec_discover_and_validate_email,
)

log = get_logger(__name__)


# ─── Registry ─────────────────────────────────────────────────────────────────

TOOLS: Dict[str, Dict[str, Any]] = {
    # ── WhatsApp ──────────────────────────────────────────────────────────────
    "whatsapp_get_messages": {
        "description": "Busca mensagens recentes do WhatsApp de um contato. Retorna as últimas N mensagens (padrão 60, máx 100). É OBRIGATÓRIO passar o 'phone' se você tiver essa informação, e o 'org_name' (nome da empresa) para garantir que encontremos o contato correto mesmo que o telefone falhe.",
        "args_schema": {
            "contact": "string (NOME EXATO DA PESSOA com quem você quer falar)",
            "phone": "string recomendado (telefone com DDD)",
            "org_name": "string recomendado (nome da empresa investigada para evitar homônimos)",
            "limit": "int (padrão 60, máx 100)"
        },
        "type": "read",
        "executor": exec_whatsapp_get_messages,
    },
    "whatsapp_list_chats": {
        "description": "Lista chats do WhatsApp por nome. Use APENAS quando não souber o nome exato do contato. NÃO use para buscar histórico de um contato já identificado — para isso use whatsapp_get_messages.",
        "args_schema": {"name": "string opcional (filtrar por nome)", "limit": "int (padrão 20)"},
        "type": "read",
        "executor": exec_whatsapp_list_chats,
    },
    "whatsapp_send_message": {
        "description": "Envia uma mensagem de WhatsApp para um contato. É ALTAMENTE RECOMENDADO passar o 'phone' e o 'org_name' para garantir que a mensagem chegue ao destinatário correto, evitando homônimos.",
        "args_schema": {
            "contact": "string (OBRIGATÓRIO: nome do contato para quem a mensagem será enviada)",
            "message": "string (texto completo da mensagem — escreva de forma profissional e personalizada)",
            "phone": "string opcional (telefone com DDD)",
            "org_name": "string opcional (nome da empresa investigada)",
        },
        "type": "write",
        "executor": exec_whatsapp_send_message,
        "confirm_label": lambda args: f"WhatsApp para {args.get('contact')}: \"{args.get('message', '')[:80]}\"",
    },

    # ── Email ──────────────────────────────────────────────────────────────────
    "email_get_inbox": {
        "description": "Busca e-mails recentes da caixa de entrada geral. PROIBIDO usar para investigar e-mails de uma empresa específica ou contato — para isso, é OBRIGATÓRIO usar email_get_contact_history.",
        "args_schema": {"limit": "int (padrão 5)", "from_name": "string opcional (nome ou domínio do remetente)"},
        "type": "read",
        "executor": exec_email_get_inbox,
    },
    "email_get_contact_history": {
        "description": "Busca TODO o histórico de e-mails (caixa de entrada e enviados). ÚNICA ferramenta permitida para investigar e-mails de uma empresa ou contato. IMPORTANTE: Se você tiver o e-mail do contato (encontrado em pipedrive_get_persons), é OBRIGATÓRIO passar o 'contact_email' para garantir a precisão da busca. Se a empresa NÃO tiver contatos cadastrados, passe o 'domain' ou 'org_name'.",
        "args_schema": {
            "contact_name": "string opcional (nome do contato)",
            "contact_email": "string opcional (e-mail do contato — USE SEMPRE QUE TIVER)",
            "org_name": "string opcional (nome da empresa — ajuda no fallback)",
            "domain": "string opcional (domínio do site/email da empresa. Ex: 'empresa.com.br')",
            "limit": "int (padrão 25)",
        },
        "type": "read",
        "executor": exec_email_get_contact_history,
    },
    "batch_communication_search": {
        "description": "REALIZA BUSCA EXAUSTIVA DE HISTÓRICO (WhatsApp + Email) para múltiplos contatos e para a própria empresa de uma vez. Use esta ferramenta OBRIGATORIAMENTE quando precisar investigar o histórico de vários contatos de uma organização, em vez de chamar as ferramentas individuais repetidamente. Isso economiza tempo e sessões.",
        "args_schema": {
            "org_name": "string (nome da empresa investigada)",
            "contacts": "array de objetos (lista de contatos com 'name', 'phone' opcional e 'email' opcional)",
            "limit_wa": "int opcional (limite de msgs WA por contato, padrão 40)",
            "limit_email": "int opcional (limite de emails por contato, padrão 15)"
        },
        "type": "read",
        "executor": exec_batch_communication_search,
    },
    "email_send": {
        "description": (
            "Envia um e-mail NOVO para um destinatário. Requer confirmação. "
            "Use email_reply para responder a um thread existente. "
            "Para enviar com anexo, use attachment_name com um dos valores pré-configurados: "
            "'apresentacao_linkb2b' (apresentação LINKB2B em PDF)."
        ),
        "args_schema": {
            "to": "string (e-mail do destinatário)",
            "subject": "string (assunto do e-mail)",
            "body": "string (corpo completo — escreva profissionalmente com saudação e assinatura)",
            "contact_name": "string opcional (nome do destinatário para o log)",
            "attachment_name": "string opcional — nome do anexo pré-configurado. Valores aceitos: 'apresentacao_linkb2b'",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: (
            f"E-mail para {args.get('to')} — {args.get('subject', '')}"
            + (f" (+ anexo: {args.get('attachment_name')})" if args.get("attachment_name") else "")
        ),
    },
    "email_reply": {
        "description": "Responde a um e-mail existente usando o entryId. Prefira este ao email_send quando houver thread ativo. Requer confirmação.",
        "args_schema": {
            "entry_id": "string (entryId do e-mail original, obtido via email_get_contact_history ou email_get_inbox)",
            "body": "string (corpo da resposta — profissional, sem repetir o assunto original)",
            "subject": "string opcional (assunto original para contexto no log)",
            "contact_name": "string opcional (nome do destinatário para o log)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Responder e-mail de {args.get('contact_name', 'contato')}: \"{args.get('body', '')[:80]}\"",
    },

    # ── Pipedrive ──────────────────────────────────────────────────────────────
    "pipedrive_get_org": {
        "description": "Busca dados completos de uma organização no Pipedrive: cadastro, todos os deals e primeiros contatos. Use SEMPRE como ponto de partida ao analisar qualquer empresa.",
        "args_schema": {
            "org_name": "string (nome da empresa — use quando souber o nome)",
            "org_id": "int opcional (ID da organização no Pipedrive — use quando souber o ID numérico mas não o nome)",
        },
        "type": "read",
        "executor": exec_pipedrive_get_org,
    },
    "pipedrive_get_persons": {
        "description": "Busca todos os contatos (pessoas) de uma organização no Pipedrive com telefone, e-mail e canais disponíveis. Use para identificar com quem falar.",
        "args_schema": {
            "org_name": "string (nome da empresa — use quando souber o nome)",
            "org_id": "int opcional (ID da organização no Pipedrive — use quando souber o ID numérico mas não o nome)",
        },
        "type": "read",
        "executor": exec_pipedrive_get_persons,
    },
    "pipedrive_get_deals": {
        "description": "Busca deals de uma organização com detalhes: título, status, valor, etapa e notas recentes. Use para entender o estado comercial.",
        "args_schema": {
            "org_name": "string (nome da empresa — use quando souber o nome)",
            "org_id": "int opcional (ID da organização no Pipedrive — use quando souber o ID numérico mas não o nome)",
        },
        "type": "read",
        "executor": exec_pipedrive_get_deals,
    },
    "pipedrive_get_activities": {
        "description": "Busca atividades (pendentes e concluídas), tarefas e notas/anotações (notes) de uma organização específica no Pipedrive.",
        "args_schema": {"org_name": "string (nome da empresa)"},
        "type": "read",
        "executor": exec_pipedrive_get_activities,
    },
    "pipedrive_get_all_activities": {
        "description": "Busca TODAS as atividades pendentes do Pipedrive (hoje + atrasadas) de TODAS as empresas. Use APENAS quando o usuário perguntar sobre agenda geral, tarefas do dia ou follow-ups de todas as empresas. NUNCA use durante a investigação específica de uma empresa — para isso use pipedrive_get_activities com o nome da empresa.",
        "args_schema": {},
        "type": "read",
        "executor": exec_pipedrive_get_all_activities,
    },
    "pipedrive_get_deals_without_tasks": {
        "description": "Busca todos os negócios (deals) abertos DO USUÁRIO ATUAL no Pipedrive que NÃO possuem nenhuma tarefa/atividade pendente programada (undone_activities_count = 0). Eles podem ter atividades passadas concluídas, mas nenhuma em aberto no momento. Use para encontrar negócios esquecidos ou que precisam de follow-up.",
        "args_schema": {},
        "type": "read",
        "executor": exec_pipedrive_get_deals_without_tasks,
    },
    "pipedrive_bulk_update_tasks": {
        "description": "Atualiza tarefas em massa para todos os negócios em uma determinada etapa (stage_id) do funil. Busca negócios abertos que tenham uma tarefa contendo 'task_keyword', conclui essa tarefa e opcionalmente cria novas tarefas em sequência (concluídas ou pendentes). Use isso quando o usuário pedir para marcar uma atividade como feita para várias empresas e já agendar o próximo passo.",
        "args_schema": {
            "stage_id": "int (ID numérico da etapa no Pipedrive. Mapeamento: Novos Negócios [2: Entrada, 18: Qualificação, 19: Contatado, 4: Reunião Agendada, 26: Reunião Realizada, 27: Proposta em Andamento, 28: Em Negociação]; Carteira [14: Entrada, 16: Contato, 17: Proposta, 32: Programação])",
            "task_keyword": "string (Palavra-chave para encontrar a tarefa alvo, ex: 'encontrar contato' ou 'ciesp')",
            "create_completed_task": "string opcional (Nome de uma nova tarefa a ser criada já como concluída, ex: 'Enviar apresentação')",
            "create_pending_task": "string opcional (Nome de uma nova tarefa a ser criada como pendente para o dia seguinte, ex: 'Marcar reunião')"
        },
        "type": "write",
        "executor": None,
    },
    "pipedrive_advance_deal": {
        "description": "Move o negócio para o próximo estágio do funil de vendas, ou para um estágio específico. Use quando uma etapa-chave foi concluída (ex: reunião realizada, proposta enviada).",
        "args_schema": {
            "deal_id": "int (ID do negócio no Pipedrive)",
            "target_stage": "string ('next' para avançar automaticamente para a próxima etapa ou o ID numérico da etapa destino)",
            "reason": "string opcional (motivo do avanço para registrar como nota no deal)"
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Avançar deal #{args.get('deal_id')} para '{args.get('target_stage')}'",
    },
    "pipedrive_update_deal": {
        "description": "Atualiza campos de um deal no Pipedrive (stage_id, status, value etc.). Requer confirmação.",
        "args_schema": {
            "deal_id": "int (ID do deal)",
            "fields": "dict (campos a atualizar, ex: {\"stage_id\": 5, \"status\": \"won\"})",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Atualizar deal #{args.get('deal_id')} → {args.get('fields')}",
    },
    "pipedrive_create_task": {
        "description": "Cria uma nova atividade/tarefa no Pipedrive vinculada a um deal ou empresa. Requer confirmação.",
        "args_schema": {
            "subject": "string (título da tarefa)",
            "task_type": "string (call | meeting | task | deadline — use 'call' para ligações, 'task' para tarefas genéricas)",
            "due_date": "string opcional (data no formato YYYY-MM-DD)",
            "note": "string opcional (descrição ou instruções)",
            "deal_id": "int opcional (ID do deal — preferível se souber)",
            "org_name": "string opcional (nome da empresa — usado para resolver o deal se deal_id não for fornecido)",
            "person_id": "int opcional (MUITO IMPORTANTE: O ID numérico da pessoa. Se o usuário pedir para atribuir/relacionar uma pessoa e você não tiver o ID exato, PARE e chame 'pipedrive_get_persons' primeiro para encontrá-lo. Nunca passe null se a intenção for atribuir alguém.)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Criar tarefa: '{args.get('subject')}' ({args.get('type', 'task')}) em {args.get('due_date', 'sem data')}",
    },
    "pipedrive_update_task": {
        "description": "Atualiza ou conclui uma atividade existente no Pipedrive. Requer confirmação.",
        "args_schema": {
            "activity_id": "int (ID da atividade)",
            "done": "bool opcional (MUITO IMPORTANTE: passe true se o usuário pedir para 'marcar', 'concluir' ou 'fechar' a tarefa)",
            "due_date": "string opcional (reagendar — formato YYYY-MM-DD)",
            "note": "string opcional (atualizar descrição)",
            "subject": "string opcional (novo título)",
            "person_id": "int opcional (MUITO IMPORTANTE: O ID numérico da pessoa. Se o usuário pedir para atribuir/relacionar uma pessoa e você não tiver o ID exato, PARE e chame 'pipedrive_get_persons' primeiro para encontrá-lo. Nunca passe null se a intenção for atribuir alguém.)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: (
            f"Concluir atividade #{args.get('activity_id')}" if args.get("done")
            else f"Atualizar atividade #{args.get('activity_id')}"
        ),
    },
    "pipedrive_create_note": {
        "description": "Adiciona uma nota a um deal no Pipedrive. Use para registrar decisões, informações importantes ou resumo de conversas. Requer confirmação.",
        "args_schema": {
            "deal_id": "int (ID do deal)",
            "content": "string (texto da nota — seja descritivo e objetivo)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Criar nota no deal #{args.get('deal_id')}: \"{args.get('content', '')[:60]}\"",
    },
    "pipedrive_create_person": {
        "description": "Cria um novo contato (pessoa) no Pipedrive vinculado a uma organização. Requer confirmação.",
        "args_schema": {
            "name": "string (nome completo do contato)",
            "email": "string opcional (endereço de e-mail)",
            "phone": "string opcional (número de telefone)",
            "org_id": "int opcional (ID da organização no Pipedrive)",
            "org_name": "string opcional (nome da empresa para vincular)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Adicionar contato: '{args.get('name')}'" + (f" na empresa '{args.get('org_name')}'" if args.get("org_name") else ""),
    },

    # ── Busca de Contato na Internet ──────────────────────────────────────────
    "find_company_contact": {
        "description": (
            "Busca dados de contato de uma empresa via Receita Federal (BrasilAPI) e web search. "
            "Use quando: (1) o mapeamento de hierarquia não encontrou nenhum contato com telefone/email; "
            "ou (2) o contato existe mas não tem canal cadastrado. "
            "Retorna telefone(s) da Receita Federal, email cadastrado, endereço e snippets de web. "
            "Se encontrar dados, use pipedrive_create_person para salvar o contato."
        ),
        "args_schema": {
            "org_name": "string — nome da empresa",
            "cnpj": "string opcional — CNPJ da empresa (14 dígitos, com ou sem formatação)",
        },
        "type": "read",
        "executor": exec_find_company_contact,
    },

    # ── Geração de Scripts e Planos de Voo ──────────────────────────────────────
    "prepare_live_coaching_session": {
        "description": (
            "Gera um plano de voo (passo a passo) para a ligação usando SPIN Selling. "
            "CONDIÇÕES OBRIGATÓRIAS para chamar (TODAS devem ser verdadeiras):\n"
            "  1. A descrição da tarefa é EXPLICITAMENTE uma ligação.\n"
            "  2. Você JÁ executou buscas necessárias no Pipedrive.\n"
            "  3. Você tem um telefone válido. (IMPORTANTE: Se o CRM não tiver telefone, USE a ferramenta 'find_company_contact' ANTES desta tool para descobrir o número).\n"
            "PROIBIDO descrever o roteiro em texto antes de chamar esta tool.\n"
            "MUITO IMPORTANTE: Esta ferramenta DEVE SER CHAMADA SEMPRE ANTES de 'open_ligacao_view'."
        ),
        "args_schema": {
            "contact_name": "string — nome do contato",
            "phone": "string — telefone",
            "activity_id": "string opcional — ID da atividade/tarefa no Pipedrive",
            "profile_pic": "string opcional — URL da foto/avatar do contato (se disponível no Pipedrive ou no mapeamento)",
        },
        "type": "read",
        "executor": exec_prepare_live_coaching_session,
    },
    "open_ligacao_view": {
        "description": (
            "Abre a interface de ligação ao vivo (LigacaoView). "
            "REGRA DE OURO: Você é ESTRITAMENTE PROIBIDO de chamar esta ferramenta sem antes ter chamado 'prepare_live_coaching_session'. "
            "Requer confirmação do usuário via card. "
            "Passe APENAS o nome do contato, o telefone e o activity_id opcional. O sistema resgatará o plano de voo automaticamente da memória ou banco."
        ),
        "args_schema": {
            "contact_name": "string — nome do contato a ser ligado",
            "phone": "string — número de telefone (obtido do CRM ou find_company_contact)",
            "activity_id": "string opcional — ID da atividade/tarefa no Pipedrive",
        },
        "type": "write",
        "executor": exec_open_ligacao_view,
        "confirm_label": lambda args: (
            f"Iniciar Ligacao com {args.get('contact_name', 'contato')} • {args.get('phone', 'sem numero')}"
        ),
    },
    "generate_sales_message": {
        "description": "Usa o Coach de Vendas Sênior para gerar um rascunho de mensagem (WhatsApp ou E-mail) altamente estratégico baseado no histórico real. Use quando identificar que o canal preferido de contato é digital (WhatsApp/Email).",
        "args_schema": {
            "contact_name": "string (nome da pessoa)",
            "channel": "string ('whatsapp' ou 'email')",
            "goal": "string (o que você quer alcançar com essa mensagem, ex: 'cobrar retorno da cotação x')",
        },
        "type": "read",
        "executor": exec_generate_sales_message,
    },

    # ── Consolidação ──────────────────────────────────────────────────────────
    "update_prospecting_context": {
        "description": "Salva o contexto qualitativo e a temperatura do lead na base de dados (Ex: 'Lead morno, trazido pelo usuário da feira X'). Use SEMPRE que descobrir a origem de um lead manual ou aprender uma informação vital de relacionamento.",
        "args_schema": {
            "org_id": "int opcional (ID da empresa)",
            "person_id": "int opcional (ID da pessoa)",
            "temperature": "string opcional ('cold', 'warm', 'hot', 'contacted')",
            "context": "string (texto descritivo detalhando o contexto, origem ou relação)",
        },
        "type": "read", # Read para não precisar de confirmação para salvar memória interna
        "executor": exec_update_prospecting_context,
    },
    "generate_dossier": {
        "description": (
            "Chame esta ferramenta UMA VEZ, após ter esgotado TODAS as fontes "
            "(Pipedrive + WhatsApp + Email de todos os contatos + busca por empresa). "
            "Ela sinaliza o início da consolidação. No turno seguinte, gere o dossiê final completo."
        ),
        "args_schema": {},
        "type": "read",
        "executor": exec_generate_dossier,
    },
    "open_hierarchy_drawer": {
        "description": (
            "Abre o mapeador de hierarquia para uma empresa, solicitando ao usuário que inicie o mapeamento de contatos e decisores. "
            "REGRA DE OURO: ANTES de chamar esta ferramenta, você DEVE OBRIGATORIAMENTE concluir as buscas no Pipedrive (org, persons, deals, activities) e o histórico de comunicações (whatsapp_get_messages e email_get_contact_history). "
            "Só chame open_hierarchy_drawer se, APÓS concluir essas buscas, constatar que: (1) não há contatos cadastrados; ou (2) os contatos existentes não possuem telefone/e-mail válido nem histórico de comunicação relevante que resolva a tarefa."
        ),
        "args_schema": {
            "org_name": "string (nome da empresa)",
            "org_id": "int opcional (ID da empresa no Pipedrive)",
            "deal_id": "int opcional (ID do deal associado)",
            "activity_id": "int opcional (ID da atividade original relacionada)",
            "pre_task_id": "int opcional (ID da tarefa 'Encontrar decisor' criada no Pipedrive antes de abrir o mapeador — será marcada como concluída após o mapeamento)",
        },
        "type": "read",
        "executor": exec_open_hierarchy_drawer,
    },
    "suggest_next_actions": {
        "description": (
            "Gera um conjunto personalizado de próximos passos executáveis baseados no contexto REAL do negócio. "
            "O serviço analisa automaticamente o histórico da conversa (dados do Pipedrive, WhatsApp, Email) e "
            "gera 5-8 sugestões cobrindo TODAS as categorias: mensagens, tarefas CRM, agendamento de reuniões, "
            "atualização de deals, estratégias. "
            "QUANDO CHAMAR: após qualquer investigação concluída, ao final de um follow-up enviado, "
            "ou quando o usuário pede próximos passos. "
            "PODE passar 'actions' como array vazio [] — o serviço extrai contexto do histórico automaticamente. "
            "IMPORTANTE: inclua no array 'actions' apenas se você já sabe as ações específicas com IDs; "
            "caso contrário, passe [] e o serviço gerará as sugestões com base no histórico."
        ),
        "args_schema": {
            "actions": "array (pode ser vazio []) — o serviço gera sugestões automaticamente a partir do histórico. Se quiser pré-definir alguma ação específica com IDs concretos, inclua objetos com 'label' e 'prompt'."
        },
        "type": "read",
        "executor": exec_suggest_next_actions,
    },

    "deep_company_investigation": {
        "description": "Realiza uma investigação profunda sobre a empresa criando um Dossiê Pré-Abordagem. Busca no banco, dados de CNPJ (Receita Federal) e Web. Retorna um dossiê consolidado em 'data'.",
        "args_schema": {
            "org_name": "string (nome da empresa)",
            "cnpj": "string opcional (CNPJ da empresa, se disponível)",
        },
        "type": "read",
        "executor": exec_deep_company_investigation,
    },
    # ── Web ────────────────────────────────────────────────────────────────────
    "web_search_external": {
        "description": "Pesquisa informações EXTERNAS na internet (notícias, mercado, concorrentes). PROIBIDO usar durante investigação de uma empresa específica. PROIBIDO usar para buscar dados de negócios, deals, contatos ou histórico de comunicação — use as ferramentas Pipedrive/WhatsApp/Email para isso.",
        "args_schema": {"query": "string (termos de busca)"},
        "type": "read",
        "executor": exec_web_search,
    },
    "evaluate_prospects": {
        "description": "Analisa todos os contatos aprovados e mapeados no banco de dados local para uma organização e identifica quais pessoas ou grupos são as melhores opções para prospectar com base no produto oferecido.",
        "args_schema": {
            "org_name": "string (nome da empresa)",
            "org_id": "int opcional (ID da empresa no Pipedrive)"
        },
        "type": "read",
        "executor": exec_evaluate_prospects,
    },
    "discover_and_validate_email": {
        "description": "Descobre e valida o e-mail profissional de um contato usando o domínio da empresa e pesquisa na web. Gera padrões comuns (joao.moura, j.moura) e verifica se o e-mail é válido via DNS.",
        "args_schema": {
            "contact_name": "string (nome completo do contato)",
            "org_name": "string opcional (nome da empresa)",
            "domain": "string opcional (domínio da empresa — ex: empresa.com.br)"
        },
        "type": "read",
        "executor": exec_discover_and_validate_email,
    },
}


# ─── Schema para API Anthropic ────────────────────────────────────────────────

def get_tools_anthropic_schema() -> list:
    """Gera o schema no formato Anthropic/Claude para todas as ferramentas."""
    schemas = []
    for name, meta in TOOLS.items():
        args = meta.get("args_schema", {})
        properties: dict = {}
        required: list = []

        for k, desc in args.items():
            desc_lower = desc.lower()
            # Mapeamento de tipos mais robusto
            if "int" in desc_lower:
                prop_type = "integer"
            elif "bool" in desc_lower:
                prop_type = "boolean"
            elif "array" in desc_lower:
                prop_type = "array"
            elif "dict" in desc_lower or "object" in desc_lower or "campos" in desc_lower:
                prop_type = "object"
            else:
                prop_type = "string"

            if prop_type == "array":
                properties[k] = {"type": "array", "items": {"type": "object"}, "description": desc}
            else:
                properties[k] = {"type": prop_type, "description": desc}

            # Se não for opcional e não tiver padrão, é obrigatório
            # Exception: 'limit' e 'contact_name'/'org_name' em buscas flexíveis
            is_optional = "opcional" in desc_lower or "padrão" in desc_lower or "optional" in desc_lower
            if not is_optional and k != "limit":
                required.append(k)

        schema: dict = {
            "name": name,
            "description": meta["description"],
            "input_schema": {
                "type": "object",
                "properties": properties,
            },
        }
        if required:
            schema["input_schema"]["required"] = required

        schemas.append(schema)
    return schemas


# ─── Executor de ferramentas de ESCRITA (após confirmação) ────────────────────

async def execute_write_tool(tool_name: str, args: Dict[str, Any], org_id=None, messages: list | None = None) -> Dict[str, Any]:
    """Executa uma ferramenta de escrita após confirmação do usuário."""

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    if tool_name == "whatsapp_send_message":
        result = await exec_whatsapp_send_message(args, org_id=org_id, attachment_path=args.get("attachment_path"))
        if result.get("ok"):
            await _log_activity_bg(
                "whatsapp_sent",
                {
                    "to_name": args.get("contact_name") or args.get("contact", ""),
                    "to_phone": args.get("phone", ""),
                    "message_preview": args.get("message", "")[:200],
                },
                org_id=org_id,
            )
        return result

    # ── Ligação ao vivo ───────────────────────────────────────────────────────────────────────
    elif tool_name == "open_ligacao_view":
        return await exec_open_ligacao_view(args, org_id=org_id, messages=messages)

    # ── Email: envio novo ──────────────────────────────────────────────────────
    elif tool_name == "email_send":
        import os as _os
        from modules.ai.service.context.business_context_service import BusinessContextService
        
        to = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")

        # Busca contexto para pegar anexo padrão e assinatura
        ctx = await BusinessContextService.get_tenant_context()
        
        # Resolve attachment_name → caminho absoluto via settings ou contexto
        attachment_paths: list[str] = []
        
        # Adiciona anexo customizado feito pelo usuário na confirmação
        user_attachment_path = args.get("attachment_path")
        if user_attachment_path and _os.path.exists(user_attachment_path):
            attachment_paths.append(user_attachment_path)
            
        # Prioriza 'apresentacao_linkb2b' se mencionado no body ou se veio nos args
        att_name = args.get("attachment_name", "")
        if not att_name and any(kw in body.lower() for kw in ["apresentação", "pdf", "anexo"]):
            att_name = "apresentacao_linkb2b"

        if att_name:
            # Se o agente pediu 'apresentacao', usamos o PDF configurado no banco
            if "apresentacao" in att_name.lower():
                path = ctx.get("presentation_path")
                if path and _os.path.exists(path):
                    attachment_paths.append(path)
            else:
                # Fallback legado para compatibilidade
                try:
                    from core.config import settings as _s
                    _ATTACHMENT_MAP = {
                        "apresentacao_linkb2b": getattr(_s, "LINKB2B_PRESENTATION_PATH", ""),
                    }
                    path = _ATTACHMENT_MAP.get(att_name, "")
                    if path and _os.path.exists(path):
                        attachment_paths.append(path)
                except Exception:
                    pass

        # Append signature se houver imagem configurada
        final_body = body
        sig_path = ctx.get("signature_path")
        if sig_path and _os.path.exists(sig_path):
            try:
                import base64 as _base64
                from pathlib import Path as _Path
                ext = _Path(sig_path).suffix.lower().replace(".", "")
                if ext in ("png", "jpg", "jpeg", "gif"):
                    with open(sig_path, "rb") as f:
                        b64_data = _base64.b64encode(f.read()).decode()
                    mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"
                    sig_html = f'<br><br><img src="data:{mime};base64,{b64_data}" style="max-width: 400px; height: auto;" />'
                    if sig_html not in final_body:
                        final_body += sig_html
            except Exception as sig_err:
                import logging as _log
                _log.warning(f"Erro ao embutir assinatura: {sig_err}")
        else:
             # Se não tem imagem, coloca uma assinatura de texto profissional se não houver
             if "J.Ferres" not in final_body:
                 final_body += "<br><br>--<br><b>João Luccas</b><br>Equipe Comercial J.Ferres"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"{EMAIL_SERVICE_BASE}/send",
                    json={"to": to, "subject": subject, "body": final_body, "attachment_paths": attachment_paths or None},
                )
                ok = r.status_code in (200, 201, 202)
                if ok:
                    await _log_activity_bg(
                        "email_sent",
                        {"to_name": args.get("contact_name", to), "to_email": to, "subject": subject, "message_preview": body[:200]},
                        org_id=org_id,
                        status="awaiting_reply",
                    )
                return {"ok": ok, "result": f"E-mail enviado para {to}" if ok else f"Falha (HTTP {r.status_code})"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Email: resposta ────────────────────────────────────────────────────────
    elif tool_name == "email_reply":
        from modules.ai.service.context.business_context_service import BusinessContextService
        entry_id = args.get("entry_id", "")
        body = args.get("body", "")
        
        # Busca contexto para pegar assinatura
        ctx = await BusinessContextService.get_tenant_context()

        attachment_paths: list[str] = []
        user_attachment_path = args.get("attachment_path")
        if user_attachment_path and _os.path.exists(user_attachment_path):
            attachment_paths.append(user_attachment_path)
            
        if not entry_id or not body:
            return {"ok": False, "error": "entry_id e body são obrigatórios"}
            
        # Prioriza 'apresentacao_linkb2b' se mencionado no body
        if any(kw in body.lower() for kw in ["apresentação", "pdf", "anexo"]):
            path = ctx.get("presentation_path")
            if path and _os.path.exists(path):
                attachment_paths.append(path)

        # Append signature se houver imagem configurada
        final_body = body
        sig_path = ctx.get("signature_path")
        if sig_path and _os.path.exists(sig_path):
            try:
                import base64 as _base64
                from pathlib import Path as _Path
                ext = _Path(sig_path).suffix.lower().replace(".", "")
                if ext in ("png", "jpg", "jpeg", "gif"):
                    with open(sig_path, "rb") as f:
                        b64_data = _base64.b64encode(f.read()).decode()
                    mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"
                    sig_html = f'<br><br><img src="data:{mime};base64,{b64_data}" style="max-width: 400px; height: auto;" />'
                    if sig_html not in final_body:
                        final_body += sig_html
            except Exception as sig_err:
                import logging as _log
                _log.warning(f"Erro ao embutir assinatura no reply: {sig_err}")
        else:
             if "J.Ferres" not in final_body:
                 final_body += "<br><br>--<br><b>João Luccas</b><br>Equipe Comercial J.Ferres"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"{EMAIL_SERVICE_BASE}/reply",
                    json={"entry_id": entry_id, "body": final_body, "reply_all": True, "attachment_paths": attachment_paths or None},
                )
                ok = r.status_code in (200, 201, 202)
                if ok:
                    await _log_activity_bg(
                        "email_reply_sent",
                        {
                            "to_name": args.get("contact_name", "Contato"),
                            "subject": args.get("subject", "Re: resposta"),
                            "message_preview": body[:200],
                            "is_reply": True,
                        },
                        org_id=org_id,
                        status="completed",
                    )
                return {"ok": ok, "result": "Resposta enviada" if ok else f"Falha (HTTP {r.status_code})"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: atualizar deal ──────────────────────────────────────────────
    elif tool_name == "pipedrive_advance_deal":
        return await exec_pipedrive_advance_deal(args, org_id=org_id)

    elif tool_name == "pipedrive_bulk_update_tasks":
        return await exec_pipedrive_bulk_update_tasks(args)

    elif tool_name == "pipedrive_update_deal":
        deal_id = args.get("deal_id")
        fields = args.get("fields", {})
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            result = await pipedrive_service.update_deal(int(deal_id), fields)
            ok = result.get("success", False)
            if ok:
                try:
                    await pipedrive_service.make_request(
                        "POST", "notes",
                        json={"content": f"✅ Deal atualizado via Assistente V2.\nAlterações: {json.dumps(fields, ensure_ascii=False)}", "deal_id": deal_id}
                    )
                except Exception:
                    pass
            return {"ok": ok, "result": "Deal atualizado" if ok else f"Erro: {result.get('error', 'desconhecido')}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: criar tarefa ────────────────────────────────────────────────
    elif tool_name == "pipedrive_create_task":
        subject = args.get("subject", "Atividade")
        # "task_type" é o nome canônico (renomeado de "type" para evitar conflito com JSON Schema)
        task_type = args.get("task_type") or args.get("type", "task")
        due_date = args.get("due_date", "")
        note = args.get("note", "")
        deal_id = args.get("deal_id")
        org_name = args.get("org_name", "")

        type_map = {"tarefa": "task", "ligação": "call", "ligar": "call", "reunião": "meeting", "prazo": "deadline"}
        task_type = type_map.get(str(task_type).lower(), task_type)

        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            pd_org_id = org_id
            if not deal_id and (org_name or pd_org_id):
                if not pd_org_id and org_name:
                    match, pd_org_id = await _pipedrive_find_org(org_name)
                if pd_org_id:
                    details = await pipedrive_service.get_organization_details(pd_org_id)
                    deals = details.get("deals", []) if isinstance(details, dict) else []
                    open_deal = next((d for d in deals if d.get("status") == "open"), deals[0] if deals else None)
                    if open_deal:
                        deal_id = open_deal.get("id")

            data: dict = {"subject": subject, "type": task_type, "note": note}
            if deal_id:
                data["deal_id"] = int(deal_id)
            if pd_org_id:
                data["org_id"] = int(pd_org_id)
            if due_date:
                data["due_date"] = due_date
            if args.get("person_id"):
                data["person_id"] = int(args["person_id"])

            result = await pipedrive_service.create_activity(data)
            ok = result.get("success", False)
            act_id = (result.get("data") or {}).get("id")
            return {
                "ok": ok,
                "activity_id": act_id,
                "result": f"Tarefa '{subject}' criada (ID: {act_id})" if ok else f"Erro: {result.get('error', 'desconhecido')}",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: atualizar tarefa ────────────────────────────────────────────
    elif tool_name == "pipedrive_update_task":
        activity_id = args.get("activity_id")
        if not activity_id:
            return {"ok": False, "error": "activity_id é obrigatório"}
        data: dict = {}
        if args.get("done") in (True, "true", 1, "1"):
            data["done"] = 1
        if args.get("due_date"):
            data["due_date"] = args["due_date"]
        if args.get("note"):
            data["note"] = args["note"]
        if args.get("subject"):
            data["subject"] = args["subject"]
        if args.get("person_id"):
            data["person_id"] = int(args["person_id"])
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            ok = await pipedrive_service.update_activity(int(activity_id), data)
            return {"ok": ok, "result": "Atividade atualizada" if ok else "Erro ao atualizar"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: criar nota ──────────────────────────────────────────────────
    elif tool_name == "pipedrive_create_note":
        deal_id = args.get("deal_id")
        content = args.get("content", "")
        if not deal_id or not content:
            return {"ok": False, "error": "deal_id e content são obrigatórios"}
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            r = await pipedrive_service.make_request(
                "POST", "notes",
                json={"content": content, "deal_id": int(deal_id)}
            )
            ok = r is not None and r.status_code in (200, 201)
            return {"ok": ok, "result": "Nota criada" if ok else f"Erro (HTTP {getattr(r, 'status_code', '?')})"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: criar pessoa/contato ────────────────────────────────────────
    elif tool_name == "pipedrive_create_person":
        name = args.get("name") or args.get("contact_name")
        email = args.get("email")
        phone = args.get("phone")
        arg_org_id = args.get("org_id")
        org_name = args.get("org_name")
        if not name:
            return {"ok": False, "error": "Nome é obrigatório"}
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            pd_org_id = org_id or arg_org_id
            if not pd_org_id and org_name:
                match, resolved_id = await _pipedrive_find_org(org_name)
                if resolved_id:
                    pd_org_id = resolved_id
            target_org_id = pd_org_id

            result = await pipedrive_service.create_person(
                name=name,
                email=email,
                phone=phone,
                org_id=int(target_org_id) if target_org_id else None,
            )
            ok = result.get("success", False)
            person_id = (result.get("data") or {}).get("id")

            if ok and target_org_id:
                try:
                    details = await pipedrive_service.get_organization_details(int(target_org_id))
                    deals = details.get("deals", []) if isinstance(details, dict) else []
                    open_deal = next((d for d in deals if d.get("status") == "open"), deals[0] if deals else None)
                    if open_deal:
                        deal_id = int(open_deal.get("id"))
                        await pipedrive_service.make_request(
                            "POST", "notes",
                            json={"content": f"👤 Novo contato adicionado via Assistente V2: {name} ({email or 'sem email'})", "deal_id": deal_id}
                        )
                        if person_id:
                            # 1. Tenta vincular como contato principal se estiver vazio
                            if not open_deal.get("person_id"):
                                await pipedrive_service.update_deal(deal_id, {"person_id": person_id})
                            
                            # 2. Adiciona OBRIGATORIAMENTE como participante (resolve múltiplos contatos no mesmo deal)
                            await pipedrive_service.add_participant(deal_id, person_id)
                except Exception as e:
                    log.warning("pipedrive_create_person.link_failed", error=str(e))
            return {"ok": ok, "result": f"Contato '{name}' adicionado com sucesso" if ok else f"Erro ao adicionar contato: {result.get('error', 'desconhecido')}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"Ferramenta desconhecida: {tool_name}"}
