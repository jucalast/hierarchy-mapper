import asyncio
import sys
import os

# Add backend directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from sqlalchemy import select
from core.database import async_session as AsyncSessionLocal
from models import Organization, Employee
from api.v1.endpoints.hierarchy import get_stored_hierarchy_by_pipedrive

async def main():
    async with AsyncSessionLocal() as db:
        print("Connecting to DB and fetching hierarchy for Pipedrive ID 1020...")
        try:
            # Let's run the exact route logic
            # To print full exception details, we run it manually
            pipedrive_id = 1020
            stmt = select(Organization).where(Organization.pipedrive_id == pipedrive_id)
            res = await db.execute(stmt)
            org = res.scalars().first()
            
            if not org:
                # Try local ID fallback
                stmt_local = select(Organization).where(Organization.id == pipedrive_id)
                res_local = await db.execute(stmt_local)
                org = res_local.scalars().first()
                
            if not org:
                print("Organization not found in database!")
                return
                
            print(f"Found Organization: {org.name} (ID: {org.id})")
            
            # Now run get_stored_hierarchy logic
            org_id = org.id
            stmt_emp = select(Employee).where(Employee.company_id == org_id).order_by(Employee.seniority.desc())
            result_emp = await db.execute(stmt_emp)
            employees = result_emp.scalars().all()
            
            print(f"Found {len(employees)} employees in DB.")
            
            # Let's run the loop to see where it breaks
            nodes = []
            nodes.append({
                "id": "root_company", "name": org.name, "role": "Entidade Principal", "department": "Supply Chain (Matriz)", 
                "manager_id": None, "level": 0, "company_logo": org.logo_url, "logo": org.logo_url, "domain": org.domain, "cnpj": org.cnpj,
                "linkedin": org.linkedin_url
            })

            id_mapping = {}
            for emp in employees:
                new_id = f"node_{emp.id}"
                
                # Mapping by LinkedIn URL (Stable username)
                if emp.linkedin_url and '/in/' in emp.linkedin_url:
                    username = re_sub_split = emp.linkedin_url.split('/in/')[-1].split('?')[0].rstrip('/')
                    import re
                    username = re.sub(r'[^a-zA-Z0-9]', '_', username)
                    id_mapping[f"node_{username}"] = new_id
                    
                # Mapping by Name
                if emp.name:
                    import re
                    clean_name = re.sub(r'[^a-zA-Z0-9]', '_', emp.name.lower())
                    id_mapping[f"socio_{clean_name}"] = new_id
                else:
                    print(f"Warning: Employee {emp.id} has no name!")

            print("Loop 1 (Mapping) completed successfully.")
            
            for emp in employees:
                new_id = f"node_{emp.id}"
                level = emp.seniority
                
                manager_id = emp.manager_id
                if not manager_id or manager_id == "None":
                    manager_id = "root_company"
                elif manager_id in id_mapping:
                    manager_id = id_mapping[manager_id]
                elif "/" in str(manager_id) or "?" in str(manager_id):
                    import re
                    clean_m_id = f"node_{re.sub(r'[^a-zA-Z0-9]', '_', str(manager_id).split('/in/')[-1].split('?')[0].rstrip('/'))}"
                    manager_id = id_mapping.get(clean_m_id, "root_company")
                
                clean_email = emp.email
                if clean_email and clean_email.endswith("@") and org.domain:
                    clean_email = f"{clean_email}{org.domain}"

                # Calculate department tag
                from services.hierarchy.filters import get_department_tag
                dept = await get_department_tag(emp.role)

                nodes.append({
                    "id": new_id, 
                    "name": emp.name, 
                    "role": emp.role, 
                    "level": level,
                    "seniority": level,
                    "department": dept, 
                    "manager_id": manager_id, 
                    "linkedin": emp.linkedin_url, 
                    "url": emp.linkedin_url, 
                    "profile_pic": emp.profile_pic, 
                    "email": clean_email, 
                    "education": emp.description, 
                    "observations": emp.description,
                    "location": emp.location,
                    "phone": emp.phone,
                    "whatsapp_number": emp.whatsapp_number,
                    "temperature": emp.temperature
                })
            
            print("Loop 2 completed successfully. Created nodes count:", len(nodes))
            print("TEST SUCCESS")
            
        except Exception as e:
            import traceback
            print("ERROR DETECTED:")
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
