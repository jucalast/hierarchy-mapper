"""
services.external.groq_service
==============================

Refatorado para usar o LLM Router (services.ai.llm). Mantém TODAS as APIs
públicas usadas pelo código existente:
    - GroqService.ask(prompt, json_mode)
    - refine_hierarchy_ai(employees)
    - expand_product_to_b2b_terms(product_focus)
    - evaluate_lead_temperature(activities_text, notes_text)

Os prompts e regras de negócio permanecem idênticos; mudou só o caminho
de execução (fallback Gemini → Groq → Claude com circuit breaker e cache).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from core.observability.logging_config import get_logger
from core.llm import LLMTier, ask_llm
from core.llm.base import NoProviderAvailableError

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Classe de compatibilidade — mesmo shape usado em outras partes do código.
# ---------------------------------------------------------------------------

class GroqService:
    """Wrapper mantido por compat. Delega ao LLM Router."""

    def __init__(self, api_key: str | None = None):
        # api_key é ignorado — a chave vem de settings (centralizado)
        self.api_key = api_key

    async def ask(self, prompt: str, json_mode: bool = False, tier: LLMTier = LLMTier.FAST) -> Dict[str, Any]:
        try:
            result = await ask_llm(
                prompt=prompt,
                json_mode=json_mode,
                tier=tier,
            )
        except NoProviderAvailableError as e:
            return {"error": str(e)}
        except Exception as e:  # defensivo
            log.exception("groq_service.ask.failed")
            return {"error": str(e)}

        if json_mode:
            return result.json_data if isinstance(result.json_data, dict) else {
                "response": result.text
            }
        return {"response": result.text}


# ---------------------------------------------------------------------------
# Helpers de alto nível usados pelo pipeline
# ---------------------------------------------------------------------------

async def refine_hierarchy_ai(employees: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Usa IA para analisar cargos e definir hierarquia real (senioridade + manager_id).
    Mantém 100% das regras de negócio originais.
    """
    if not employees:
        return []

    # Prepara lista simplificada para economizar tokens
    employee_data = []
    for emp in employees:
        if emp.get("id") == "root_company":
            continue
        employee_data.append(
            {
                "id": emp["id"],
                "name": emp.get("name"),
                "role": emp.get("role"),
                "department": emp.get("department", "Outros"),
                "level": emp.get("level", 5),
                "bio": (emp.get("education", "") or "")[:350],
            }
        )

    prompt = f"""
Você é um especialista em Estruturas Organizacionais B2B. Sua tarefa é refinar um organograma definindo a senioridade (level) e quem responde a quem (manager_id).

REGRAS DE senioridade (level):
6: Sócio / CEO / VP / Board / Fundador.
5: Diretores / Superintendentes.
4: Gerentes / Heads / Lead / Gestores / Chefes.
3: Coordenadores / Supervisores / Especialistas Sêniores / Líderes.
1: Assistentes / Auxiliares / Estagiários / Operacional.
2: Analistas / Compradores / Engenheiros / Default (Tudo que não se encaixa acima).

🛡️ PROTEÇÃO DE SÓCIOS (LEVEL 6):
- Se um funcionário já possui Level 6 ou pertence ao departamento "Quadro de Sócios (QSA)", ele é IMUTÁVEL.
- NUNCA rebaixe o nível de um sócio.
- NUNCA subordine um Sócio a outra pessoa que não seja a "root_company".

REGRAS DE CONEXÃO (manager_id):
1. PRIORIDADE VERTICAL: Um funcionário deve reportar para alguém de nível SUPERIOR.
2. PRIORIDADE DEPARTAMENTAL: Busque primeiro um líder no MESMO departamento.
3. TRANSVERSALIDADE: Se não houver líder no mesmo departamento, ele deve reportar para a "Diretoria Executiva", "Quadro de Sócios (QSA)" ou "Executive Management".
4. FALLBACK FINAL: Se não houver nenhum líder humano disponível acima dele, conecte a "root_company".
5. DISTRIBUIÇÃO: Não sobrecarregue um único gerente se houver outros do mesmo nível e departamento. Distribua os subordinados.

INSTRUÇÕES - ANÁLISE DE BIO:
- Use a "bio" para validar se o cargo condiz. Se a bio diz "gestor de 20 pessoas" mas o cargo é "Analista", promova para o nível de Gerencial (4).

RETORNO OBRIGATÓRIO:
- Retorne APENAS o JSON. Use exatamente os IDs enviados.
- Todo funcionário deve ter um 'manager_id'.

FUNCIONÁRIOS PARA ANALISAR:
{json.dumps(employee_data, ensure_ascii=False)}

FORMATO DE RESPOSTA (JSON):
{{
  "hierarchy": [
    {{ "id": "...", "level": 4, "manager_id": "...", "role_refinado": "..." }}
  ]
}}
"""

    try:
        result = await ask_llm(
            prompt=prompt,
            system="Você é um assistente de RH que gera organogramas e responde apenas em JSON estrito.",
            json_mode=True,
            tier=LLMTier.DEEP,
        )
    except NoProviderAvailableError as e:
        log.warning("refine_hierarchy_ai.no_provider", error=str(e))
        return []
    except Exception:
        log.exception("refine_hierarchy_ai.failed")
        return []

    data = result.json_data or {}
    if isinstance(data, dict):
        if "hierarchy" in data and isinstance(data["hierarchy"], list):
            return data["hierarchy"]
        if "employees" in data and isinstance(data["employees"], list):
            return data["employees"]
        for v in data.values():
            if isinstance(v, list):
                return v
    if isinstance(data, list):
        return data
    return []


async def expand_product_to_b2b_terms(product_focus: str) -> List[str]:
    """Traduz um produto genérico em 4 termos técnicos B2B."""
    if not product_focus or len(product_focus) < 2:
        return []

    prompt = f"""
Traduza o foco de busca "{product_focus}" em 4 termos técnicos em inglês e português que um comprador (Procurement) usaria no LinkedIn para se descrever ou descrever sua categoria.

Exemplo: "Papelão" -> ["Packaging", "Embalagens", "Indirects", "Supply Chain"]
Exemplo: "Segurança" -> ["Loss Prevention", "Prevenção de Perdas", "Facilities", "Indiretos"]
Exemplo: "Sistemas" -> ["IT Procurement", "SaaS", "Indirects", "Hardware"]

RETORNE APENAS UM ARRAY JSON SIMPLES DE STRINGS: ["Termo1", "Termo2", "Termo3", "Termo4"]
"""

    try:
        result = await ask_llm(
            prompt=prompt,
            system="Você é um especialista em Compras e Procurement B2B. Responda apenas com um array JSON de strings.",
            json_mode=True,
            temperature=0.3,
            tier=LLMTier.FAST,
        )
    except Exception:
        log.exception("expand_product_to_b2b_terms.failed")
        return [product_focus]

    data = result.json_data
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return [str(x) for x in v]
    return [product_focus]


async def evaluate_lead_temperature(activities_text: str, notes_text: str) -> str:
    """Classifica o lead em Quente/Morno/Frio/Sem Contato."""
    if not (activities_text or "").strip() and not (notes_text or "").strip():
        return "Sem Contato"

    prompt = f"""
Analise o histórico de um lead no CRM (atividades e notas) e decida a temperatura atual deste lead.

Regras:
- "Quente": Demonstrou interesse claro, pediu orçamento, marcou reunião recentemente ou está em negociação ativa.
- "Morno": Teve algum contato, respondeu e-mail ou pediu pra retornar depois, mas sem compromisso claro.
- "Frio": Contato distante sem resposta, recusou educadamente, ou sem contato há muito tempo.
- "Sem Contato": Nenhuma ou poucas notas que indiquem conversa real.

Atividades:
{activities_text}

Notas:
{notes_text}

RETORNE APENAS UMA DAS 4 PALAVRAS, SEM ASPAS OU PONTUAÇÕES: Quente, Morno, Frio, ou Sem Contato.
"""

    try:
        result = await ask_llm(
            prompt=prompt,
            system="Você é um classificador especializado em leads B2B de compras (temperatura).",
            temperature=0.2,
            tier=LLMTier.FAST,
        )
    except Exception:
        log.exception("evaluate_lead_temperature.failed")
        return "Sem Contato"

    res_str = (result.text or "").strip()
    for t in ("Quente", "Morno", "Frio", "Sem Contato"):
        if t.lower() in res_str.lower():
            return t
    return res_str or "Sem Contato"


__all__ = [
    "GroqService",
    "refine_hierarchy_ai",
    "expand_product_to_b2b_terms",
    "evaluate_lead_temperature",
]
