"""
Teste direto do endpoint WhatsApp — rode com:
    cd backend && python test_wa.py
"""
import asyncio
import httpx

API_BASE = "http://localhost:8000/api/v1"
WA_BASE  = "http://localhost:3000/api"   # ajuste se a porta for diferente

# Contato que estava retornando 0 mensagens
TEST_NAME   = "Gabriel"
TEST_PHONE  = None   # será lido da API de contatos se None

async def test_wa_direct():
    async with httpx.AsyncClient(timeout=30) as client:

        # 1. Verifica status do serviço WA
        print("\n=== 1. Status WhatsApp ===")
        try:
            r = await client.get(f"{WA_BASE}/status")
            print(f"Status: {r.status_code} → {r.text[:300]}")
        except Exception as e:
            print(f"ERRO ao conectar no WA: {e}")
            return

        # 2. Busca chats
        print("\n=== 2. GET /chats ===")
        r = await client.get(f"{WA_BASE}/chats")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            body = r.json()
            print(f"Chaves no JSON: {list(body.keys()) if isinstance(body, dict) else 'lista direta'}")
            if isinstance(body, list):
                chats = body
            else:
                chats = body.get("chats") or body.get("result") or body.get("data") or []
            print(f"Total chats: {len(chats)}")
            print("\nPrimeiros 5 chats:")
            for c in chats[:5]:
                print(f"  name={c.get('name')!r:30}  id={c.get('id')!r}")

            # 3. Filtra por nome
            print(f"\n=== 3. Filtrando por '{TEST_NAME}' ===")
            search = TEST_NAME.lower()
            def id_str(c):
                cid = c.get("id", "")
                if isinstance(cid, dict):
                    return cid.get("_serialized", "") or cid.get("user", "")
                return str(cid) if cid else ""
            matches = [c for c in chats if search in (c.get("name", "") or id_str(c)).lower()]
            print(f"Matches: {len(matches)}")
            for m in matches:
                print(f"  → {m.get('name')!r}  id={m.get('id')!r}")

            if matches:
                best = matches[0]
                raw_id = best.get("id")
                if isinstance(raw_id, dict):
                    chat_id = raw_id.get("_serialized", "") or raw_id.get("user", "")
                else:
                    chat_id = str(raw_id) if raw_id else ""
                print(f"\n=== 4. GET /chats/{chat_id}/messages ===")
                r2 = await client.get(f"{WA_BASE}/chats/{chat_id}/messages?limit=50")
                print(f"Status: {r2.status_code}")
                if r2.status_code == 200:
                    msgs = r2.json().get("messages", [])
                    print(f"Mensagens recebidas: {len(msgs)}")
                    for m in msgs[:3]:
                        print(f"  [{m.get('fromMe')}] {m.get('body', '')[:80]!r}")
                else:
                    print(f"Erro: {r2.text[:300]}")
        else:
            print(f"Erro /chats: {r.text[:300]}")

        # 5. Testa o endpoint da IA diretamente
        print("\n=== 5. POST /ai/chat (deal_status Walsywa) ===")
        try:
            r = await client.post(f"{API_BASE}/ai/chat", json={
                "message": "como está o andamento desse negócio?",
                "conversation_id": 887,
                "selected_companies": [{"id": 1, "name": "Walsywa"}],
            }, timeout=60)
            print(f"Status: {r.status_code}")
            # Resposta é NDJSON streaming — lê as primeiras linhas
            for i, line in enumerate(r.text.splitlines()):
                if line.strip():
                    print(f"  chunk {i}: {line[:120]}")
                if i > 15:
                    print("  ...")
                    break
        except Exception as e:
            print(f"Erro no chat: {e}")

asyncio.run(test_wa_direct())
