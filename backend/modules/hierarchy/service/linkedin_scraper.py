"""
modules.hierarchy.service.linkedin_scraper
=============================================
Orquestra o scraping de hierarquia via LinkedIn como um background job (ARQ),
desacoplado do ciclo de vida de qualquer conexão HTTP/WS — assim um reload de
página não mata o subprocesso de scraping em andamento.

Progresso é publicado no canal Redis `job_updates_{job_id}` (mesmo formato que
o antigo SSE) e comandos interativos (clique/digitação/parada graciosa) chegam
pelo canal `scraper_commands_{job_id}`.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import unicodedata
import uuid
import queue as thread_queue
from typing import Optional

from sqlalchemy import select, delete, and_, not_, or_, func

from core.infra.database import async_session
from core.observability.logging_config import get_logger
from models.organization.organization import Organization
from models.people.employee import Employee
from api.v1.schemas import EmployeeNode
from .graph_builder import assign_managers, reparent_subordinates
from .filters import get_seniority_level

log = get_logger(__name__)


def _clean_name(s: str) -> str:
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    ).strip()


def _names_match(n1: str, n2: str) -> bool:
    n1_clean, n2_clean = _clean_name(n1), _clean_name(n2)
    if n1_clean == n2_clean:
        return True
    parts1, parts2 = n1_clean.split(), n2_clean.split()
    if not parts1 or not parts2:
        return False
    if len(parts1) == 1 and parts1[0] == parts2[0]:
        return True
    if len(parts2) == 1 and parts2[0] == parts1[0]:
        return True
    if parts1[0] == parts2[0] and parts1[-1] == parts2[-1]:
        return True
    return False


def _normalize_linkedin(url: str) -> str:
    if not url:
        return ''
    url = url.split('?')[0].rstrip('/')
    url = url.replace('http://', 'https://')
    if 'linkedin.com' in url:
        parts = url.split('linkedin.com')
        return 'linkedin.com' + parts[1]
    return url


async def run_linkedin_scrape(
    redis,
    job_id: str,
    company_url: str,
    session_cookie: Optional[str] = None,
    headless: bool = True,
    area_focus: Optional[str] = None,
    product_focus: Optional[str] = None,
    model: Optional[str] = None,
):
    """Executa o scraping do LinkedIn e transmite progresso via Redis pub/sub."""
    channel = f"job_updates_{job_id}"
    command_channel = f"scraper_commands_{job_id}"

    async def publish(payload: dict):
        await redis.publish(channel, json.dumps(payload, ensure_ascii=False))

    async def send_log(message: str, msg_type: str = "log"):
        await publish({"type": msg_type, "message": message})
        try:
            await redis.publish("linkedin_scan_logs", json.dumps({"message": message}, ensure_ascii=False))
        except Exception:
            pass

    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    tmp_dir = os.path.join(backend_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    unique_id = str(uuid.uuid4())
    output_filepath = os.path.join(tmp_dir, f"hierarchy_scan_{unique_id}.json")

    python_exe = sys.executable
    script_path = os.path.join(backend_dir, "scripts", "test_hierarchy_scan.py")
    cmd = [python_exe, "-X", "utf8", script_path, company_url, output_filepath, "--no-delay"]

    env = os.environ.copy()
    if session_cookie:
        env["LINKEDIN_LI_AT"] = session_cookie
    env["LINKEDIN_HEADLESS"] = "true" if headless else "false"

    preview_path = os.path.join(tmp_dir, "scraper_preview.jpg")
    if os.path.exists(preview_path):
        try:
            os.remove(preview_path)
        except Exception:
            pass

    # 🏢 IDENTIFICAÇÃO DA ORGANIZAÇÃO (CONTEXTO)
    db_org = None
    async with async_session() as session:
        clean_url = company_url.split("/people/")[0].split("?")[0].rstrip("/")
        res = await session.execute(
            select(Organization).where(
                (Organization.linkedin_url.contains(clean_url)) |
                (func.lower(Organization.name).contains(clean_url.split("/")[-1].replace("-", " ")))
            )
        )
        db_org = res.scalars().first()

        if db_org:
            await send_log(f"[Agent] Empresa identificada: {db_org.name} (ID: {db_org.id})")
        else:
            await send_log(f"[Agent] Empresa não encontrada no banco. Criando registro temporário para {clean_url.split('/')[-1]}...")
            db_org = Organization(
                name=clean_url.split("/")[-1].replace("-", " ").title(),
                linkedin_url=company_url,
                source="discovery_scan"
            )
            session.add(db_org)
            await session.commit()
            await session.refresh(db_org)

        # Limpa funcionários do mapeamento anterior para começar do zero.
        # Mesma regra do b2b_scanner.py: preserva sócios/QSA e decisões humanas explícitas.
        await session.execute(
            delete(Employee).where(
                and_(
                    Employee.company_id == db_org.id,
                    not_(
                        or_(
                            Employee.department == "Quadro de Sócios (QSA)",
                            Employee.department.ilike("%Sócio%"),
                            Employee.department.ilike("%Societário%"),
                            Employee.department.ilike("%Conselho%"),
                            Employee.seniority == 6,
                            Employee.role.ilike("Aprovado%"),
                            Employee.role == "Reprovado",
                            Employee.department == "Reprovado",
                        )
                    )
                )
            )
        )
        await session.commit()
        await publish({"type": "clear_nodes"})

        # 🌳 Pool de hierarquia em memória: começa com quem sobreviveu à limpeza
        # (decisões manuais preservadas), e cresce conforme cada perfil é aprovado.
        hierarchy_pool: list = []
        res_survivors = await session.execute(select(Employee).where(Employee.company_id == db_org.id))
        for sv in res_survivors.scalars().all():
            try:
                hierarchy_pool.append(EmployeeNode(
                    id=f"node_{sv.id}",
                    name=sv.name or "Colaborador",
                    role=sv.role or "Professional",
                    department=sv.department or "Operations",
                    manager_id=sv.manager_id,
                    level=sv.seniority or 2,
                ))
            except Exception:
                continue

    # ─── Compatibilidade Windows: subprocess via thread + asyncio.Queue ───
    # asyncio.create_subprocess_exec NÃO funciona no WindowsSelectorEventLoop.
    line_queue: thread_queue.Queue = thread_queue.Queue()
    process_ref: dict = {}

    def run_scraper():
        """Roda o subprocesso em thread bloqueante e enfileira linhas."""
        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
            )
            process_ref["proc"] = proc
            for line in proc.stdout:  # type: ignore[union-attr]
                line_queue.put(("line", line.rstrip()))
            # Stdout fechou — enfileira "done" ANTES de proc.wait()
            rc = proc.poll()
            line_queue.put(("done", rc if rc is not None else 0))
            proc.wait()
        except Exception as exc:
            line_queue.put(("error", str(exc)))

    # 🔒 Inscreve no canal de comandos ANTES de iniciar o subprocesso — garante que
    # nenhum "stop"/"interact" disparado pelo usuário logo após o início seja
    # perdido (o Redis pub/sub não enfileira mensagens para subscribers tardios).
    command_pubsub = redis.pubsub()
    await command_pubsub.subscribe(command_channel)

    # 🔒 Checagem de flag durável: cobre o caso em que o usuário clicou em "parar"
    # enquanto o job ainda estava na fila do ARQ (antes de existir qualquer listener
    # de pub/sub). Se já havia uma solicitação de stop pendente, nem inicia o scraper.
    if await redis.exists(f"scraper_stop_requested_{job_id}"):
        await send_log("[Agent] Varredura cancelada antes de iniciar (stop solicitado).", "error")
        await publish({"type": "done"})
        try:
            await command_pubsub.unsubscribe(command_channel)
        except Exception:
            pass
        return

    scraper_thread = threading.Thread(target=run_scraper, daemon=True)
    scraper_thread.start()

    async def _wait_for_proc(timeout: float = 5.0):
        """Aguarda o subprocesso estar disponível em process_ref (fecha a janela entre
        scraper_thread.start() e o Popen() de fato popular process_ref dentro da thread)."""
        waited = 0.0
        while waited < timeout:
            proc = process_ref.get("proc")
            if proc:
                return proc
            await asyncio.sleep(0.05)
            waited += 0.05
        return process_ref.get("proc")

    async def command_listener():
        """Escuta comandos interativos (click/type/press/stop) e os repassa ao stdin do subprocesso."""
        try:
            async for message in command_pubsub.listen():
                if not message or message.get('type') != 'message':
                    continue
                data = message['data']
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                try:
                    cmd_payload = json.loads(data)
                except Exception:
                    continue

                proc = process_ref.get("proc") or await _wait_for_proc()
                action = cmd_payload.get("action")

                if not proc or proc.poll() is not None:
                    # Subprocesso já terminou — stop ainda pode abortar o AI filter
                    if action == "stop":
                        process_ref["stop_requested"] = True
                    else:
                        log.warning("hierarchy.linkedin_scrape.command_dropped", job_id=job_id, action=action)
                    continue

                line_to_send = None
                if action == "click" and cmd_payload.get("x") is not None and cmd_payload.get("y") is not None:
                    line_to_send = f"cmd_click {cmd_payload['x']} {cmd_payload['y']}\n"
                elif action == "type" and cmd_payload.get("text"):
                    safe_text = str(cmd_payload["text"]).replace("\n", " ")
                    line_to_send = f"cmd_type {safe_text}\n"
                elif action == "press" and cmd_payload.get("key"):
                    line_to_send = f"cmd_press {cmd_payload['key']}\n"
                elif action == "stop":
                    line_to_send = "cmd_stop\n"
                    process_ref["stop_requested"] = True

                if line_to_send:
                    try:
                        proc.stdin.write(line_to_send)
                        proc.stdin.flush()
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await command_pubsub.unsubscribe(command_channel)
            except Exception:
                pass

    listener_task = asyncio.create_task(command_listener())

    try:
        await send_log("[Agent] Inicializando motor de automação Playwright...")
        loop = asyncio.get_running_loop()

        returncode = 0
        while True:
            try:
                kind, payload = await loop.run_in_executor(
                    None,
                    lambda: line_queue.get(timeout=10)
                )
            except Exception:
                proc = process_ref.get("proc")
                if proc and proc.poll() is not None:
                    returncode = proc.returncode or 0
                    await send_log("[Agent] Processo finalizado. Iniciando processamento...")
                    break
                await send_log("[Agent] Aguardando resposta do scraper...")
                continue

            if kind == "done":
                returncode = payload
                break
            elif kind == "error":
                await send_log(f"[Agent Fatal] Erro ao iniciar scraper: {payload}", "error")
                return
            else:
                line: str = payload
                if not line:
                    continue
                if "[SCREENSHOT_UPDATED]" in line:
                    await publish({"type": "screenshot"})
                elif line.startswith("[COOKIE_CAPTURED] "):
                    cookie_val = line.split("[COOKIE_CAPTURED] ")[1].strip()
                    await publish({"type": "cookie", "cookie": cookie_val})
                else:
                    await send_log(line)

        if returncode != 0:
            await send_log(f"[Agent Error] O processo secundário encerrou com código de erro {returncode}", "error")
            return

        if not os.path.exists(output_filepath):
            await send_log("[Agent Error] O arquivo de resultados não foi gerado pelo Scraper.", "error")
            await publish({"type": "done"})
            return

        with open(output_filepath, "r", encoding="utf-8") as f:
            results_data = json.load(f)

        # Aborta antes de iniciar o AI filter se stop foi solicitado
        if process_ref.get("stop_requested") or await redis.exists(f"scraper_stop_requested_{job_id}"):
            await send_log("[Agent] Varredura interrompida pelo usuário. Encerrando sem processar IA.")
            await publish({"type": "done"})
            return

        if results_data:
            await send_log(f"[AI Filter] Iniciando processamento inteligente de {len(results_data)} perfis...")

            # Deduplica por linkedin_url
            unique_employees = []
            seen_urls = set()
            for emp in results_data:
                url = emp.get("linkedin_url")
                if url:
                    clean_url_emp = url.split("?")[0].rstrip("/")
                    if clean_url_emp not in seen_urls:
                        seen_urls.add(clean_url_emp)
                        unique_employees.append(emp)
                else:
                    unique_employees.append(emp)

            # 🚀 PROCESSAMENTO COM ROLE_ENGINE (Em Lotes de 10 para Performance)
            nodes_to_yield = []
            async with async_session() as session:
                stmt_rej = select(Employee).where(
                    Employee.company_id == db_org.id,
                    (Employee.role == "Reprovado") | (Employee.department == "Reprovado")
                )
                res_rej = await session.execute(stmt_rej)
                rejected_urls = {emp.linkedin_url.split("?")[0].rstrip("/") for emp in res_rej.scalars().all() if emp.linkedin_url}

                # Prepara candidatos válidos
                valid_candidates = []
                for idx, emp in enumerate(unique_employees):
                    emp_url = emp.get("linkedin_url", "").split("?")[0].rstrip("/")
                    if emp_url in rejected_urls:
                        await send_log(f"⏩ [Ignorado] {emp.get('name')} já foi reprovado anteriormente.")
                        continue

                    valid_candidates.append({
                        "idx": idx,
                        "name": emp.get("name"),
                        "role": emp.get("role"),
                        "linkedin_url": emp_url,
                        "context": [
                            f"--- DADOS RASPADO DO LINKEDIN ---",
                            f"NOME: {emp.get('name')}",
                            f"CARGO EXIBIDO: {emp.get('role')}",
                            f"LOCALIZAÇÃO: {emp.get('location', 'Brasil')}",
                            f"PERFIL: {emp_url}"
                        ],
                        "emp_raw": emp
                    })

                from .role_engine import role_engine

                CHUNK_SIZE = 20
                chunks = [valid_candidates[i:i + CHUNK_SIZE] for i in range(0, len(valid_candidates), CHUNK_SIZE)]
                await send_log(f"🧠 [AI] Processando {len(valid_candidates)} perfis em {len(chunks)} lote(s) de até {CHUNK_SIZE}...")

                async def _process_chunk_and_return(chunk):
                    result = await role_engine.distill_roles_batch_v2(
                        chunk,
                        db_org.name,
                        area_focus=area_focus or "compras",
                        product_focus=product_focus or "Geral B2B"
                    )
                    return chunk, result

                chunk_tasks = [asyncio.create_task(_process_chunk_and_return(ch)) for ch in chunks]

                approved_tasks = []
                approved_candidates_data = []
                rejected_candidates = []

                try:
                    # Exibe ✅/❌ conforme cada lote termina (sem esperar todos)
                    for coro in asyncio.as_completed(chunk_tasks):
                        try:
                            chunk, chunk_results = await coro
                        except Exception as e:
                            await send_log(f"⚠️ [Erro no Lote] {str(e)}", "error")
                            continue

                        for c in chunk:
                            res = chunk_results.get(c['idx'])
                            if not res or not res.get("is_valid"):
                                await send_log(f"❌ [Filtrado] {c['name']} ({c['role']})")
                                rejected_candidates.append(c)
                                continue

                            emp_name = res.get("proper_name", c['name'])
                            await send_log(f"✅ [Aprovado] {emp_name} -> {res.get('role', c['role'])} ({res.get('department', 'A validar')})")
                            approved_candidates_data.append({
                                "res": res,
                                "candidate": c,
                                "emp_name": emp_name
                            })

                            if db_org and db_org.domain:
                                try:
                                    name_parts = emp_name.split()
                                    first_name = name_parts[0] if name_parts else ""
                                    last_name = name_parts[-1] if len(name_parts) > 1 else ""
                                    if first_name and last_name:
                                        from core.external.email_service import discover_and_validate_email
                                        approved_tasks.append(discover_and_validate_email(
                                            first=first_name,
                                            last=last_name,
                                            domain=db_org.domain,
                                            do_smtp=True
                                        ))
                                    else:
                                        approved_tasks.append(asyncio.sleep(0, result=None))
                                except Exception:
                                    approved_tasks.append(asyncio.sleep(0, result=None))
                            else:
                                approved_tasks.append(asyncio.sleep(0, result=None))

                    # Marca todas as rejeições no banco em uma única query
                    if rejected_candidates:
                        all_emps_rej_res = await session.execute(
                            select(Employee).where(Employee.company_id == db_org.id)
                        )
                        all_emps_rej = all_emps_rej_res.scalars().all()
                        changed = False
                        for c in rejected_candidates:
                            norm_url = _normalize_linkedin(c.get('linkedin_url'))
                            existing_rej = next(
                                (e for e in all_emps_rej if
                                 (norm_url and _normalize_linkedin(e.linkedin_url) == norm_url) or
                                 _names_match(e.name, c['name'])),
                                None
                            )
                            if existing_rej:
                                existing_rej.role = "Reprovado"
                                existing_rej.department = "Reprovado"
                                changed = True
                        if changed:
                            await session.commit()

                    email_results = await asyncio.gather(*approved_tasks)

                    for idx, data in enumerate(approved_candidates_data):
                            res = data['res']
                            c = data['candidate']
                            emp_name = data['emp_name']
                            emp_email_data = email_results[idx]
                            emp_email = emp_email_data.get("email") if emp_email_data else None

                            final_role = res.get("role", c['role'])
                            dept = res.get("department", "A validar")
                            score = res.get("matching_score", 50)
                            evidence = res.get("evidence")
                            emp_url = c['linkedin_url']
                            emp_raw = c['emp_raw']

                            fallback_loc = "Brasil"
                            if db_org and db_org.address:
                                normalized = db_org.address.replace(",", " - ")
                                addr_parts = [p.strip() for p in normalized.split(" - ") if p.strip()]
                                if len(addr_parts) >= 2:
                                    city = addr_parts[-2].title()
                                    state = addr_parts[-1].upper()
                                    fallback_loc = f"{city}, {state}, Brasil" if len(state) == 2 else f"{city}, {state}"
                                else:
                                    fallback_loc = db_org.address

                            emp_loc = emp_raw.get("location")
                            if not emp_loc or emp_loc == "Localização não identificada":
                                emp_loc = fallback_loc

                            norm_emp_url = _normalize_linkedin(emp_url)
                            all_emps_res = await session.execute(
                                select(Employee).where(Employee.company_id == db_org.id)
                            )
                            all_emps = all_emps_res.scalars().all()

                            existing = next((e for e in all_emps if norm_emp_url and _normalize_linkedin(e.linkedin_url) == norm_emp_url), None)

                            if not existing:
                                matches = [e for e in all_emps if _names_match(e.name, emp_name)]
                                if len(matches) == 1:
                                    existing = matches[0]
                                    await send_log(f"🔗 [Vinculado] {emp_name} encontrado no banco (como {existing.name}). Mesclando perfil do LinkedIn...")

                            # Busca no Pipedrive para obter pipedrive_id, email e telefone.
                            # Se existing já foi encontrado, enriquece o registro — não cria novo.
                            from modules.crm.service.pipedrive_service import pipedrive_service
                            if db_org and db_org.pipedrive_id:
                                try:
                                    pd_search = await pipedrive_service._request(
                                        "GET",
                                        "persons/search",
                                        params={"term": emp_name, "exact_match": 0, "limit": 5}
                                    )
                                    if pd_search and pd_search.status_code == 200:
                                        d = pd_search.json()
                                        items = d.get("data", {}).get("items") or []
                                        for i_item in items:
                                            p = i_item.get("item", {})
                                            p_org = p.get("organization")
                                            if p_org and str(p_org.get("id")) == str(db_org.pipedrive_id):
                                                n1, n2 = _clean_name(emp_name), _clean_name(p.get("name", ""))
                                                if n1 in n2 or n2 in n1 or _names_match(emp_name, p.get("name", "")):
                                                    pd_email = p.get("primary_email")
                                                    if pd_email:
                                                        emp_email = pd_email

                                                    pd_phones = p.get("phones")
                                                    pd_phone = pd_phones[0] if pd_phones and len(pd_phones) > 0 else None
                                                    pd_id = str(p.get("id"))

                                                    if existing:
                                                        # Enriquece o registro já encontrado (nunca insere duplicado)
                                                        if not existing.pipedrive_id:
                                                            existing.pipedrive_id = pd_id
                                                        if not existing.email and pd_email:
                                                            existing.email = pd_email
                                                        if not existing.phone and pd_phone:
                                                            existing.phone = pd_phone
                                                        await session.commit()
                                                        await send_log(f"🔗 [Pipedrive] {emp_name} enriquecido com dados do Pipedrive.")
                                                    else:
                                                        new_emp = Employee(
                                                            name=emp_name,
                                                            role=final_role,
                                                            department=dept,
                                                            linkedin_url=emp_url,
                                                            profile_pic=emp_raw.get("avatar"),
                                                            location=emp_loc,
                                                            company_id=db_org.id,
                                                            is_discovery=1,
                                                            source="pipedrive",
                                                            matching_score=score,
                                                            evidence=evidence,
                                                            description=c['role'],
                                                            email=emp_email,
                                                            phone=pd_phone,
                                                            pipedrive_id=pd_id,
                                                        )
                                                        session.add(new_emp)
                                                        await session.commit()
                                                        await session.refresh(new_emp)
                                                        existing = new_emp
                                                        await send_log(f"🔗 [Pipedrive] {emp_name} encontrado no Pipedrive. Importado e mesclado.")
                                                    break
                                except Exception:
                                    pass

                            is_new = existing is None
                            if is_new:
                                final_pic = emp_raw.get("avatar")
                                if not final_pic and emp_url:
                                    from modules.intelligence.service.preview_service import get_url_preview
                                    try:
                                        preview = await get_url_preview(emp_url, fast_mode=True)
                                        if preview and preview.get("image"):
                                            final_pic = preview.get("image")
                                    except Exception:
                                        pass

                                new_emp = Employee(
                                    name=emp_name,
                                    role=final_role,
                                    department=dept,
                                    linkedin_url=emp_url,
                                    profile_pic=final_pic,
                                    location=emp_loc,
                                    company_id=db_org.id,
                                    is_discovery=1,
                                    source="discovery_scan",
                                    matching_score=score,
                                    evidence=evidence,
                                    description=c['role'],
                                    email=emp_email,
                                )
                                session.add(new_emp)
                                await session.commit()
                                await session.refresh(new_emp)
                                existing = new_emp

                            employee_id = f"node_{existing.id}"
                            avatar_to_yield = existing.profile_pic

                            if not is_new:
                                # 🛡️ PROTEÇÃO: Não sobrescreve se o contato já foi aprovado ou se o novo status é "pior"
                                current_is_valid = existing.role and "análise humana" not in existing.role.lower() and "reprovado" not in existing.role.lower()
                                new_is_vague = "análise humana" in final_role.lower()

                                if current_is_valid and new_is_vague:
                                    await send_log(f"ℹ️ [Preservado] {emp_name} já possui cargo definido.")
                                else:
                                    if len(emp_name) > len(existing.name):
                                        existing.name = emp_name

                                    existing.role = final_role
                                    existing.department = dept
                                    existing.linkedin_url = emp_url
                                    existing.matching_score = score
                                    existing.evidence = evidence
                                    existing.email = existing.email or emp_email
                                    existing.description = c['role']
                                    existing.company_id = db_org.id

                                    final_pic = emp_raw.get("avatar") or existing.profile_pic
                                    if not final_pic and emp_url:
                                        from modules.intelligence.service.preview_service import get_url_preview
                                        try:
                                            preview = await get_url_preview(emp_url, fast_mode=True)
                                            if preview and preview.get("image"):
                                                final_pic = preview.get("image")
                                        except Exception:
                                            pass

                                    if not existing.profile_pic:
                                        existing.profile_pic = final_pic
                                    if not existing.location or existing.location == "Localização não identificada":
                                        existing.location = emp_loc
                                    if not existing.evidence:
                                        existing.evidence = evidence
                                    if not existing.email:
                                        existing.email = emp_email

                                    if not existing.linkedin_url:
                                        existing.linkedin_url = emp_url
                                        if existing.source == "pipedrive":
                                            existing.source = "pipedrive + scan"

                                    await session.commit()

                                employee_id = f"node_{existing.id}"
                                avatar_to_yield = final_pic

                            # 🌳 Calcula manager_id em tempo real (mesma heurística do discovery),
                            # ao invés de deixar o nó "solto" até um refinamento posterior.
                            node_level = await get_seniority_level(final_role)
                            reparented_dicts = []
                            try:
                                emp_node = EmployeeNode(
                                    id=employee_id, name=emp_name, role=final_role,
                                    department=dept, level=node_level or 2,
                                )
                                emp_node.manager_id = await assign_managers(emp_node, hierarchy_pool)
                                reparented = reparent_subordinates(emp_node, hierarchy_pool)
                                hierarchy_pool.append(emp_node)

                                existing.manager_id = emp_node.manager_id
                                existing.seniority = emp_node.level
                                await session.commit()

                                for r in reparented:
                                    try:
                                        r_db_id = int(r["id"].split("_", 1)[1])
                                        r_emp = await session.get(Employee, r_db_id)
                                        if r_emp:
                                            r_emp.manager_id = r["manager_id"]
                                    except Exception:
                                        continue
                                if reparented:
                                    await session.commit()
                                    reparented_dicts = reparented
                            except Exception:
                                emp_node = None

                            node = {
                                "id": employee_id,
                                "name": emp_name,
                                "role": final_role,
                                "department": dept,
                                "company": db_org.name,
                                "linkedin": emp_url,
                                "avatar": avatar_to_yield,
                                "profile_pic": avatar_to_yield,
                                "location": emp_loc,
                                "matching_score": score,
                                "observations": c['role'],
                                "evidence": evidence,
                                "email": (existing.email if existing else None) or emp_email,
                                "pipedrive_id": int(existing.pipedrive_id) if existing and existing.pipedrive_id and str(existing.pipedrive_id).isdigit() else None,
                                "source": existing.source if existing else "discovery_scan",
                                "level": emp_node.level if emp_node else node_level,
                                "manager_id": emp_node.manager_id if emp_node else None,
                            }
                            nodes_to_yield.append(node)
                            if reparented_dicts:
                                nodes_to_yield.extend(reparented_dicts)

                except Exception as e:
                    await send_log(f"⚠️ [Erro no Processamento] {str(e)}", "error")

                if nodes_to_yield:
                    await publish({"type": "batch", "nodes": nodes_to_yield})

            await send_log("🎉 Processamento concluído!")

        if db_org:
            from modules.agent.service.tools.intelligence import batch_discover_and_validate_org_emails
            asyncio.create_task(batch_discover_and_validate_org_emails(db_org.id))

        await publish({"type": "done"})

        try:
            os.remove(output_filepath)
        except Exception:
            pass

    except Exception as e:
        log.exception("hierarchy.linkedin_scrape.failed", job_id=job_id, error=str(e))
        try:
            await publish({"type": "error", "message": f"[Agent Fatal Error] Falha na transmissão: {str(e)}"})
        except Exception:
            pass
    finally:
        listener_task.cancel()
        try:
            await listener_task
        except (asyncio.CancelledError, Exception):
            pass

        proc = process_ref.get("proc")
        if proc:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
