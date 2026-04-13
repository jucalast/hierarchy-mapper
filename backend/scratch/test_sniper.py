import asyncio
import os
import json
import sys

# Ajustar o path ANTES dos imports de serviços
sys.path.append(os.path.join(os.getcwd(), "backend"))

from services.hierarchy.role_engine import role_engine

async def test_sniper_precision():
    print("--- Iniciando Teste de Precisao do Sniper ---")
    
    # Caso 1: Darcyr (O Orfao do Log)
    name = "Darcyr Corazzari Neto"
    company = "WEGMANN automotive GmbH"
    
    # Simulando o contexto ruidoso que causou a falha
    context = [
        f"Candidate Name: {name}",
        f"Google Page Title: {name} - Logistica / Comercial | LinkedIn",
        f"Search Snippet: Veja o perfil de {name} no LinkedIn. Especialista em Logistica na {company} Brasil. Experiencia em supply chain.",
        f"LinkedIn Status: {name} | {company}",
        f"LinkedIn Personal Bio: Atuo na area de logistica e comercial da {company}.",
        "Verified Official Role: Nao Encontrado"
    ]
    
    print(f"\n[Teste 1] Alvo: {name} | Empresa: {company}")
    
    try:
        # Chamamos o distill_role que orquestra o Sniper
        result = await role_engine.distill_role(
            name=name, 
            company=company, 
            context=context, 
            area_focus="compras"
        )
        
        clean_data = result.get("clean_data", {})
        target_profile = clean_data.get("target_profile", {})
        detected_role = target_profile.get("detected_role", "N/A")
        
        final_role = result.get("role", "N/A")
        is_valid = result.get("is_valid", False)
        
        print(f"\n--- RESULTADOS ---")
        print(f"DEBUG SNIPER (Cargo Detectado): {detected_role}")
        print(f"CARGO FINAL (Juiz): {final_role}")
        print(f"STATUS FINAL: {'APROVADO' if is_valid else 'REJEITADO'}")
        
        # O teste falha se o cargo detectado for apenas o nome da empresa ou algo generico
        forbidden_list = [company.lower(), "wegmann automotive", "professional", "n/a", "anonymous"]
        
        detected_role_low = detected_role.lower()
        if any(f in detected_role_low for f in forbidden_list) and len(detected_role_low) < len(company) + 5:
             print("\nFAILED: O Sniper ainda esta confundindo a empresa com o cargo.")
             return False
        
        if "logistica" in detected_role_low or "comercial" in detected_role_low:
            print("\nSUCCESS: O Sniper isolou o cargo corretamente!")
            return True
        else:
            print(f"\nFAILED: O cargo '{detected_role}' nao contem as palavras esperadas.")
            return False

    except Exception as e:
        print(f"ERROR NO TESTE: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_sniper_precision())
