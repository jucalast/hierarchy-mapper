
import asyncio
import httpx
import sys
import os

# Adiciona o diretório raiz ao path para importar os módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))

from services.ai.agent_v2.tools import exec_pipedrive_get_org, exec_pipedrive_get_persons, exec_whatsapp_get_messages, _resolve_wa_chat

async def test_compare_lucas():
    print("--- Teste de Comparação Lucas (Semorin) ---")
    
    # 1. Buscar Lucas no Pipedrive (Empresa Semorin)
    print("\n1. Buscando Lucas no Pipedrive (Empresa: Semorin)...")
    res_persons = await exec_pipedrive_get_persons({"org_name": "Semorin"})
    
    lucas_pd = None
    if res_persons.get("ok"):
        for p in res_persons.get("persons", []):
            if "lucas" in p.get("name", "").lower():
                lucas_pd = p
                break
    
    if not lucas_pd:
        print("Erro: Lucas não encontrado no Pipedrive para a empresa Semorin.")
        return

    pd_phone = lucas_pd.get("phone")
    print(f"Pipedrive: Lucas encontrado! Telefone cadastrado: {pd_phone}")

    # 2. Resolver Lucas no WhatsApp
    print("\n2. Resolvendo Lucas no WhatsApp usando o telefone do Pipedrive...")
    async with httpx.AsyncClient() as client:
        chat_id, found_name = await _resolve_wa_chat(client, lucas_pd.get("name"), pd_phone)
    
    if chat_id:
        wa_phone = chat_id.split("@")[0]
        print(f"WhatsApp: Encontrado! ID do Chat: {chat_id}")
        print(f"WhatsApp: Nome no WhatsApp: {found_name}")
        print(f"WhatsApp: Número extraído: {wa_phone}")
        
        # 3. Comparação
        print("\n3. Resultado da Comparação:")
        import re
        def clean(p): return re.sub(r'\D', '', p) if p else ""
        
        clean_pd = clean(pd_phone)
        clean_wa = clean(wa_phone)
        
        print(f"  Número Pipedrive (limpo): {clean_pd}")
        print(f"  Número WhatsApp  (limpo): {clean_wa}")
        
        if clean_pd in clean_wa or clean_wa in clean_pd:
            print("  [OK] OS NUMEROS SAO COMPATIVEIS!")
        else:
            print("  [ERRO] OS NUMEROS SAO DIFERENTES!")
    else:
        print("WhatsApp: Lucas NAO foi encontrado no WhatsApp usando esse telefone.")

if __name__ == "__main__":
    asyncio.run(test_compare_lucas())
