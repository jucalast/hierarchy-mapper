import asyncio
import os
import json
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))
from services.hierarchy.role_engine import role_engine

async def run_test(name, company, title, body):
    print(f"\n--- Teste: {name} | Empresa: {company} ---")
    context = [
        f"Candidate Name: {name}",
        f"Google Page Title: {title}",
        f"Search Snippet: {body}",
        f"LinkedIn Status: {name} | {company}",
        f"LinkedIn Personal Bio: {body}",
        "Verified Official Role: Nao Encontrado"
    ]
    
    result = await role_engine.distill_role(name, company, context)
    detected = result.get("clean_data", {}).get("target_profile", {}).get("detected_role", "N/A")
    print(f"DEBUG SNIPER (Cargo Detectado): {detected}")
    return detected

async def main():
    company = "WEGMANN automotive GmbH"
    
    # Caso A: Sucesso (Ja vimos que funciona com contexto bom)
    await run_test(
        "Darcyr Neto", 
        company, 
        "Darcyr Neto - Logistica / Comercial | LinkedIn", 
        "Especialista em Logistica na Wegmann Brasil."
    )
    
    # Caso B: FALHA IDENTIFICADA (Onde o Sniper se confunde)
    # Aqui o cargo nao esta explicito no inicio, e o nome da empresa esta colado.
    await run_test(
        "Darcyr Neto", 
        company, 
        "Darcyr Neto - WEGMANN automotive GmbH", 
        "Veja o perfil de Darcyr Neto no LinkedIn. Wegmann Automotive GmbH - Jundiai, SP."
    )

if __name__ == "__main__":
    asyncio.run(main())
