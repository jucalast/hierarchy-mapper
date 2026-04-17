from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from sqlalchemy import select, delete, or_
from services.intelligence.intelligence_service import intelligence_service
from core.database import async_session
from models import Organization, Employee
from api.v1.schemas import ConfirmEnrichRequest

router = APIRouter()

@router.get("/enrich")
async def enrich_company_data(
    name: str = Query(..., description="Nome da empresa"),
    address: Optional[str] = Query(None, description="Pista de endereço para filtrar filiais"),
    cnpj: Optional[str] = Query(None, description="CNPJ fornecido manualmente"),
    force: bool = Query(False, description="Forçar nova busca ignorando cache")
):
    """Endpoint para descobrir CNPJ, Domínio e Selecionar Filiais via OSINT + IA."""
    try:
        return await intelligence_service.enrich_company(name, hint_address=address, force_refresh=force, cnpj=cnpj)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm")
async def confirm_enrich_data(payload: ConfirmEnrichRequest):
    """Persiste a escolha manual do usuário vinculando o Perfil do LinkedIn à Organização e sincroniza com Pipedrive."""
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        
        async with async_session() as session:
            # 🕵️ BUSCA DE DEDUPLICAÇÃO REFINADA (Prioridade Sequencial)
            org = None
            
            # 1. Tenta pelo Pipedrive ID (O mais seguro)
            if payload.pipedrive_id:
                stmt = select(Organization).where(Organization.pipedrive_id == payload.pipedrive_id)
                res = await session.execute(stmt)
                org = res.scalars().first()
            
            # 2. Se não achou, tenta pelo CNPJ (Identificador único nacional)
            if not org and payload.cnpj:
                clean_cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "")
                stmt = select(Organization).where(Organization.cnpj == clean_cnpj)
                res = await session.execute(stmt)
                found_by_cnpj = res.scalars().first()
                if found_by_cnpj:
                    org = found_by_cnpj
                    print(f"[Intelligence] 🎯 Deduplicação via CNPJ: {clean_cnpj}")
            
            # 3. Se ainda não achou, tenta pelo Nome (Apenas se não houver conflito de CNPJ)
            if not org and payload.name:
                from sqlalchemy import func
                stmt = select(Organization).where(func.lower(Organization.name) == payload.name.lower())
                res = await session.execute(stmt)
                found_by_name = res.scalars().first()
                # Só reutilizamos se o registro encontrado NÃO tiver um CNPJ diferente ou PD ID diferente
                if found_by_name:
                    if not found_by_name.cnpj or (payload.cnpj and found_by_name.cnpj == payload.cnpj.replace(".", "").replace("/", "").replace("-", "")):
                        org = found_by_name
                        print(f"[Intelligence] 📝 Deduplicação via Nome: {payload.name}")
                    else:
                        print(f"[Intelligence] 🛡️ Nome coincide ({payload.name}) mas CNPJ é diferente. Criando novo registro.")
            
            # 🚀 SINCRONIZAÇÃO/CRIAÇÃO PIPEDRIVE
            was_manually_created = False
            target_pid = payload.pipedrive_id
            
            if not target_pid:
                print(f"[Intelligence] 🚀 Criando nova empresa no Pipedrive: {payload.name}")
                target_pid = await pipedrive_service.create_organization({
                    "name": payload.name,
                    "address": payload.address,
                    "domain": payload.domain,
                    "cnpj": payload.cnpj
                })
                was_manually_created = True

            # 🕵️ VÍNCULO COM REGISTRO LOCAL
            if not org:
                print(f"[Intelligence] 🆕 Criando novo registro local para: {payload.name}")
                org = Organization(pipedrive_id=target_pid)
                session.add(org)
            else:
                # Se achamos um registro mas ele já tem um Pipedrive ID diferente do que acabamos de criar...
                if was_manually_created and org.pipedrive_id and org.pipedrive_id != target_pid:
                    print(f"[Intelligence] ⚠️ Conflito: Registro local '{org.name}' já está vinculado ao Pipedrive ID {org.pipedrive_id}. Criando NOVO registro local para evitar overwrite.")
                    org = Organization(pipedrive_id=target_pid)
                    session.add(org)
                else:
                    print(f"[Intelligence] 🤝 Vinculando dados ao registro local ID {org.id}: {org.name}")
                    org.pipedrive_id = target_pid
            
            # ✍️ ATRIBUIÇÃO DE DADOS (Agora no registro correto)
            if payload.name: org.name = payload.name
            if payload.cnpj: org.cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "")
            if payload.domain: org.domain = payload.domain
            if payload.address: org.address = payload.address
            if payload.linkedin_url: org.linkedin_url = payload.linkedin_url
            if payload.logo_url: org.logo_url = payload.logo_url
            
            await session.commit()
            await session.refresh(org)

            # 👥 SALVAMENTO DE SÓCIOS (QSA)
            if payload.partners:
                # Limpa p/ evitar duplicados
                await session.execute(delete(Employee).where(Employee.company_id == org.id, Employee.department == "Quadro de Sócios (QSA)"))
                
                for p in payload.partners:
                    new_p = Employee(
                        name=p.get("name"),
                        role=p.get("role", "Sócio"),
                        department="Quadro de Sócios (QSA)",
                        seniority=6, # Nível de Sócio é 6 (Admin/Owner)
                        company_id=org.id
                    )
                    session.add(new_p)
                await session.commit()
            
            # 🚀 ATUALIZAÇÃO PIPEDRIVE (se já existia ou foi criado)
            if target_pid:
                pipedrive_data = {
                    "address": payload.address,
                    "domain": payload.domain,
                    "cnpj": payload.cnpj,
                    "linkedin_url": payload.linkedin_url,
                    "logo_url": payload.logo_url,
                    "name": payload.name
                }
                await pipedrive_service.update_organization(target_pid, pipedrive_data)

            return {
                "status": "success", 
                "message": f"Organização '{payload.name}' mapeada e sincronizada com sucesso.",
                "local_id": org.id,
                "pipedrive_id": target_pid
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
