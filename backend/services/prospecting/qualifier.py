"""
Qualificação de prospects por IA usando o ICP da J.Ferres.

Fluxo:
1. LLM extrai dados estruturados do snippet do LinkedIn (segmento, porte, exportação)
2. get_icp_score() calcula score 0-100 com base no ICP definido em business_context.py
3. get_cold_outreach_angle() define o melhor ângulo de abordagem
"""
from __future__ import annotations

import json
from typing import Optional

from core.logging_config import get_logger
from services.ai.business_context import get_icp_score, get_cold_outreach_angle
from services.ai.llm import ask_llm, LLMTier

log = get_logger(__name__)

_EXTRACTION_PROMPT = """\
Analise o perfil da empresa e retorne APENAS um JSON válido.

EMPRESA: {company_name}
SNIPPET LINKEDIN: {description}
LOCALIZAÇÃO: {location}
URL LINKEDIN: {linkedin_url}

JSON esperado (sem markdown, sem texto extra):
{{
  "segment": "setor em português (ex: Autopeças, Máquinas industriais, Ferramentas, Logística)",
  "size_label": "pequena | média | grande",
  "employee_count": "faixa estimada como string (ex: '50-200', '500+')",
  "exports": true ou false,
  "has_purchasing_dept": true ou false,
  "known_suppliers": [],
  "description_pt": "descrição objetiva da empresa em 1-2 frases",
  "relevance_signal": "principal sinal de relevância para embalagem industrial, ou null"
}}

Use apenas o que está no texto. Não invente dados."""


async def qualify_prospect(
    company_name: str,
    description: str = "",
    location: str = "",
    linkedin_url: str = "",
) -> dict:
    """
    Qualifica um lead usando extração via LLM + ICP scoring existente.
    Retorna todos os campos de qualificação necessários para salvar no ProspectLead.
    """
    enriched = await _extract_company_data(company_name, description, location, linkedin_url)

    icp_result = get_icp_score({
        "segment": enriched.get("segment", ""),
        "size": enriched.get("size_label", ""),
        "exports": enriched.get("exports", False),
        "has_purchasing_dept": enriched.get("has_purchasing_dept", False),
        "known_suppliers": enriched.get("known_suppliers", []),
    })

    angle = get_cold_outreach_angle({
        "name": company_name,
        "segment": enriched.get("segment", ""),
        "exports": enriched.get("exports", False),
    })

    return {
        "segment": enriched.get("segment"),
        "size_label": enriched.get("size_label"),
        "employee_count": enriched.get("employee_count"),
        "exports": enriched.get("exports", False),
        "has_purchasing_dept": enriched.get("has_purchasing_dept", False),
        "description_pt": enriched.get("description_pt"),
        "relevance_signal": enriched.get("relevance_signal"),
        "icp_score": icp_result["score"],
        "icp_tier": icp_result["tier"],
        "icp_reasons": icp_result["reasons"],
        "icp_penalties": icp_result["penalties"],
        "icp_recommendation": icp_result["recommendation"],
        "outreach_angle": angle,
    }


async def _extract_company_data(
    company_name: str,
    description: str,
    location: str,
    linkedin_url: str,
) -> dict:
    prompt = _EXTRACTION_PROMPT.format(
        company_name=company_name,
        description=description or "Não disponível",
        location=location or "Não informado",
        linkedin_url=linkedin_url or "—",
    )

    try:
        result = await ask_llm(prompt, json_mode=True, tier=LLMTier.FAST)
        if result and result.text:
            text = result.text.strip()
            # Remove markdown fence se presente
            if "```" in text:
                parts = text.split("```")
                text = parts[1] if len(parts) > 1 else parts[0]
                if text.startswith("json"):
                    text = text[4:].strip()
            return json.loads(text)
    except Exception as e:
        log.warning("prospect.qualify.llm_failed", company=company_name, error=str(e))

    # Fallback: retorna dados mínimos sem IA
    return {
        "segment": _guess_segment(description),
        "size_label": "média",
        "employee_count": "Desconhecido",
        "exports": False,
        "has_purchasing_dept": False,
        "known_suppliers": [],
        "description_pt": (description[:200] if description else ""),
        "relevance_signal": None,
    }


def _guess_segment(text: str) -> str:
    """Heurística simples quando a IA falha."""
    text_lower = text.lower()
    keywords = {
        "Autopeças": ["autopeça", "automotivo", "veículo", "automotive"],
        "Máquinas industriais": ["máquina", "equipamento", "industrial"],
        "Ferramentas": ["ferramenta", "tool", "instrumento"],
        "Motores e componentes": ["motor", "redutor", "transmissão", "componente"],
        "Logística": ["logística", "transporte", "frete"],
        "Metalurgia": ["metal", "aço", "ferro", "alumínio"],
    }
    for segment, kws in keywords.items():
        if any(k in text_lower for k in kws):
            return segment
    return "Industrial"
