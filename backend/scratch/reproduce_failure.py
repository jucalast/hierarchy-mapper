import asyncio
import os
import json
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))
from services.hierarchy.role_engine import role_engine

async def run_test(name, company, title, body):
    context = [
        f"Candidate Name: {name}",
        f"Google Page Title: {title}",
        f"Search Snippet: {body}",
        f"LinkedIn Status: {name} | {company}",
        f"LinkedIn Personal Bio: {body}"
    ]
    
    result = await role_engine.distill_role(name, company, context)
    detected = result.get("clean_data", {}).get("target_profile", {}).get("detected_role", "N/A")
    print(f"DEBUG SNIPER: {detected}")
    return detected

async def main():
    company = "WEGMANN automotive GmbH"
    
    # Este contexto aqui é projetado para "tentar" forçar o erro
    # Onde o cargo (Area de logistica) está longe do nome, e a empresa está grudada.
    print("\n--- Teste de REPRODUCAO DE FALHA ---")
    bad_context_title = "Darcyr Corazzari Neto - WEGMANN automotive GmbH"
    bad_context_body = "Darcyr Corazzari Neto. WEGMANN automotive GmbH. We are a globally active group..."
    
    res = await run_test("Darcyr Corazzari Neto", company, bad_context_title, bad_context_body)
    
    if res.lower() == company.lower() or "wegmann" in res.lower() and len(res) < 25:
        print("\n[RESULTADO] FALHA REPRODUZIDA! O Sniper retornou o nome da empresa como cargo.")
    else:
        print(f"\n[RESULTADO] O Sniper retornou '{res}'.")

if __name__ == "__main__":
    asyncio.run(main())
