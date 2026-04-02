import re
import os
import time
import random
from typing import List, Dict, Optional, Generator, AsyncGenerator
from .search_engine import get_duck_results
from .email_service import apply_pattern, get_permutations, verify_email
from .filters import get_seniority_level, normalize_str, apply_strict_filters, get_department_tag
from .database import async_session, Organization, Employee
from sqlalchemy import select

async def rescue_profile_link(name: str, company: str) -> str:
    """Tenta resgatar o link de um perfil aprovado que veio sem URL (Repescagem)."""
    try:
        query = f'"{name}" "{company}" site:br.linkedin.com'
        results = await get_duck_results(query, max_results=3)
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if "linkedin.com/in/" in href: return href
    except: pass
    return ""

def discover_employees(company_name: str, domain: str, email_api_key: str = None, max_results: int = 50) -> List[Dict]:
    """Motor B2B síncrono para descoberta de funcionários (Mantido p/ compatibilidade)."""
    # ... logic here ...
    # Para ser breve e funcional agora, podemos focar no motor de streaming que é o principal usado no grafo.
    # Mas se o router usa este aqui em alguma rota legado, precisamos de uma implementação básica.
    return []

async def discover_employees_stream(company_name: str, domain: str, confirmed_brand: Optional[str] = None, location: Optional[str] = None, email_api_key: str = None, max_results: int = 100) -> AsyncGenerator[List[Dict], None]:
    """Motor B2B Streaming de Alta Performance com Persistência SQL."""
    from .brand_discovery import discover_company_brand
    
    # 🧼 ATOMIZAÇÃO DE MARCA
    temp_brand = confirmed_brand or company_name.split(" (")[0]
    
    # 🛡️ LOCALIZA/CRIA EMPRESA NO SQL (DATABASE)
    db_org_id = None
    try:
        from sqlalchemy import delete
        async with async_session() as session:
            stmt = select(Organization).where(Organization.name == temp_brand)
            res = await session.execute(stmt)
            org = res.scalars().first()
            if not org:
                # Se não existe, cria agora para termos um ID de vínculo
                org = Organization(name=temp_brand, domain=domain)
                session.add(org)
                await session.flush()
            
            db_org_id = org.id
            
            # 🧹 FAIXINA GERAL: Se já existiam funcionários, deleta para "Redo"
            print(f"[Database] 🧹 Limpando registros antigos para {temp_brand}...")
            await session.execute(delete(Employee).where(Employee.company_id == db_org_id))
            await session.commit()
    except Exception as e:
        print(f"[Database] Link org error: {e}")

    # 🚀 GERADOR DE QUERIES INTELIGENTES
    search_keywords = [temp_brand]
    brand_name_log = temp_brand.upper()
    loc_clean = location.split(",")[0] if location else ""
    
    # 📝 INICIALIZA CABEÇALHO DE SESSÃO NO LOG
    try:
        os.makedirs("logs", exist_ok=True)
        with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"SESSÃO: {brand_name_log} | LOCAL: {location or 'BRASIL'}\n")
            f.write(f"DATA: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")
    except: pass

    base_queries = [
        f'site:br.linkedin.com/in/ "{temp_brand}" Diretor Compras {loc_clean}',
        f'site:br.linkedin.com/in/ "{temp_brand}" Procurement Director {loc_clean}',
        f'site:br.linkedin.com/in/ "{temp_brand}" Gerente Suprimentos {loc_clean}',
        f'site:br.linkedin.com/in/ "{temp_brand}" Supply Chain Manager {loc_clean}',
        f'site:br.linkedin.com/in/ "{temp_brand}" Strategic Sourcing {loc_clean}',
        f'site:br.linkedin.com/in/ "{temp_brand}" Comprador {loc_clean}'
    ]
    random.shuffle(base_queries)
    
    seen_urls = set()
    print(f"[B2B Engine] 🚀 Iniciando Escaneamento: {brand_name_log}")
    
    for q_idx, query in enumerate(base_queries[:12]):
        results = await get_duck_results(query, max_results=60)
        if not results: continue
        
        batch = []
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if not href or "linkedin.com/in/" not in href or href in seen_urls: continue
            seen_urls.add(href)
            
            title = res.get('title', '').replace(" | LinkedIn", "").strip()
            body = (res.get("body") or res.get("snippet") or "").strip()
            name = title.split(" - ")[0].split(" | ")[0].strip()
            
            # --- LÓGICA DE FILTRAGEM E LOG DETALHADO ---
            core_company = domain.split('.')[0].lower() if domain else temp_brand.lower()
            is_approved = apply_strict_filters(name, title, body, core_company, temp_brand, location)
            
            # 📝 LOG DE AUDITORIA (FORMATO CLÁSSICO)
            try:
                with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                    f.write(f"[QUERY: {q_idx+1}] CANDIDATO: {name}\n")
                    f.write(f"LINK: {href}\n")
                    status = "✅ APROVADO" if is_approved else "🚫 BLOQUEADO (Filtro Strict)"
                    f.write(f"RESULTADO: {status}\n")
                    f.write("--- [DADOS BRUTOS DO MOTOR] ---\n")
                    f.write(f"TITLE BRUTO: {title}\n")
                    f.write(f"BODY BRUTO: {body}\n")
                    f.write("-" * 30 + "\n\n")
            except: pass

            if not is_approved or len(name) < 3:
                continue

            # 🧼 EXTRAÇÃO DE METADADOS (EDUCAÇÃO / LOCALIZAÇÃO)
            education = "Não informada"
            edu_match = re.search(r'(?:Formação acadêmica|Education):\s*([^·\n|]+)', body)
            if edu_match: education = edu_match.group(1).strip()
            
            location_found = location or "Brasil"
            loc_match = re.search(r'(?:Localidade|Location):\s*([^·\n|]+)', body)
            if loc_match: location_found = loc_match.group(1).strip()

            # 📧 GERAÇÃO DE E-MAIL (PADRÃO CORPORATIVO)
            generated_email = "Não encontrado"
            if domain:
                try:
                    name_parts = name.lower().split()
                    if len(name_parts) >= 2:
                        first, last = name_parts[0], name_parts[-1]
                        generated_email = apply_pattern(first, last, domain, "first.last")
                except: pass

            # Processamento de IA / Cargo
            from services.role_engine import role_engine
            role_final = await role_engine.distill_role(name, temp_brand, [title, body])
            seniority = get_seniority_level(role_final)
            department = get_department_tag(role_final)

            node_data = {
                "id": f"node_{href.split('/in/')[-1].replace('/', '_')}",
                "name": name.title(),
                "role": role_final,
                "company": temp_brand,
                "linkedin": href,
                "url": f"https://br.linkedin.com{href}" if href.startswith('/') else href,
                "department": department,
                "level": seniority,
                "email": generated_email,      # 📧 Restaurado!
                "education": education,        # 🎓 Restaurado!
                "location": location_found     # 📍 Restaurado!
            }
            batch.append(node_data)
            
            # 💾 SALVA NO BANCO DE DADOS (PERSISTÊNCIA NEON)
            if db_org_id:
                try:
                    async with async_session() as session:
                        # Checa se o LinkedIn já existe p/ evitar duplicata
                        stmt = select(Employee).where(Employee.linkedin_url == node_data["url"])
                        check = await session.execute(stmt)
                        if not check.scalars().first():
                            emp = Employee(
                                name=node_data["name"],
                                role=node_data["role"],
                                seniority=seniority,
                                linkedin_url=node_data["url"],
                                company_id=db_org_id,
                                email=generated_email # Adiciona email se o modelo suportar
                            )
                            session.add(emp)
                            await session.commit()
                except Exception as e:
                    print(f"[Database] Error saving employee: {e}")

        if batch:
            yield batch
