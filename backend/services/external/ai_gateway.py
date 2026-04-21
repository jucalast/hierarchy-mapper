"""
AI Gateway — Ponto de entrada único para chamadas de IA (Gemini + Groq fallback).
Re-exporta de base_gemini_service para manter backward compatibility.

Uso:
    from services.external.ai_gateway import ask_gemini
"""
from services.external.base_gemini_service import (
    ask_gemini,
    _is_gemini_available,
    _trip_gemini_circuit,
    _reset_gemini_circuit,
)

__all__ = [
    "ask_gemini",
    "_is_gemini_available",
    "_trip_gemini_circuit",
    "_reset_gemini_circuit",
]
