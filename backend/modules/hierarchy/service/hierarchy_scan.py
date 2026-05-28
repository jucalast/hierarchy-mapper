"""
modules.hierarchy.service.hierarchy_scan
========================================
Módulo de raspagem automatizada do LinkedIn utilizando Playwright. (HierarchyScan)

Permite acessar a aba /people/ de qualquer empresa do LinkedIn,
rolar a página dinamicamente, clicar no botão "Exibir mais resultados"
incansavelmente e extrair todos os perfis estruturados.
"""

import asyncio
import random
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from core.observability.logging_config import get_logger
from core.config import settings

log = get_logger(__name__)

class HierarchyScanService:
    """Serviço de HierarchyScan: extração de pessoas de páginas do LinkedIn via Playwright."""

    def __init__(
        self,
        session_cookie: Optional[str] = None,
        headless: Optional[bool] = None,
        max_clicks: int = 20,
        click_delay_min: float = 2.0,
        click_delay_max: float = 4.5
    ):
        """
        Inicializa o serviço de raspagem.

        :param session_cookie: Cookie de sessão 'li_at' do LinkedIn. Se não fornecido, lê das configurações do sistema.
        :param headless: Se deve rodar em modo invisível (headless). Se não fornecido, lê das configurações.
        :param max_clicks: Limite máximo de cliques no botão de expandir para segurança.
        :param click_delay_min: Atraso mínimo entre cliques/ações (evita detecção).
        :param click_delay_max: Atraso máximo entre cliques/ações.
        """
        self.session_cookie = session_cookie or settings.LINKEDIN_LI_AT
        
        # Se houver cookie de sessão, roda headless por padrão.
        # Se NÃO houver cookie, roda HEADFUL (headless=False) para que o usuário possa fazer login manual na tela.
        if headless is not None:
            self.headless = headless
        else:
            self.headless = settings.LINKEDIN_HEADLESS

        self.max_clicks = max_clicks
        self.click_delay_min = click_delay_min
        self.click_delay_max = click_delay_max
        self.active_page = None
        self.graceful_stop = False

    async def _setup_browser(self, playwright) -> tuple[Browser, BrowserContext, Page]:
        """Inicializa o navegador, contexto e injeta cookies se disponíveis."""
        log.info("hierarchy_scan.setup_browser", headless=self.headless)
        
        browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1280,800"
            ]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="pt-BR"
        )
        
        # Injeta cookies de sessão se fornecidos
        if self.session_cookie:
            log.info("hierarchy_scan.inject_cookie", cookie_len=len(self.session_cookie))
            cookies = [
                {
                    "name": "li_at",
                    "value": self.session_cookie,
                    "domain": ".linkedin.com",
                    "path": "/"
                },
                {
                    "name": "li_at",
                    "value": self.session_cookie,
                    "domain": ".www.linkedin.com",
                    "path": "/"
                }
            ]
            await context.add_cookies(cookies)
            
        page = await context.new_page()
        self.active_page = page
        
        # Escuta a abertura de novas abas/popups (ex: login com Google/Apple)
        def handle_page(new_page):
            asyncio.create_task(self._on_page_opened(new_page))
            
        context.on("page", handle_page)
        
        # Oculta propriedades de automação adicionais do Playwright
        await page.add_init_script(
            "const newProto = navigator.__proto__; delete newProto.webdriver; navigator.__proto__ = newProto;"
        )
        
        return browser, context, page

    async def _save_preview(self, page: Optional[Page] = None):
        """Captura um screenshot da página e salva como preview em backend/tmp/scraper_preview.jpg"""
        import os
        try:
            # Seleciona qual página fotografar (prefere a página ativa/popup se houver)
            target_page = page or self.active_page
            if self.active_page and not self.active_page.is_closed():
                target_page = self.active_page
                
            if not target_page or target_page.is_closed():
                return
                
            # Subir 4 níveis para sair de modules/hierarchy/service/ e pousar na raiz de backend/
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            tmp_dir = os.path.join(backend_dir, "tmp")
            os.makedirs(tmp_dir, exist_ok=True)
            preview_path = os.path.join(tmp_dir, "scraper_preview.jpg")
            
            # Tira um screenshot comprimido em JPEG para excelente performance
            await target_page.screenshot(path=preview_path, type="jpeg", quality=50)
            # Imprime uma tag que o leitor de subprocesso monitora para notificar o frontend
            print("[SCREENSHOT_UPDATED]")
            import sys
            sys.stdout.flush()
        except Exception as e:
            log.warning("hierarchy_scan.save_preview_error", error=str(e))

    async def _on_page_opened(self, new_page: Page):
        """Trata o evento de uma nova página/popup aberta (ex: Login do Google/Apple)."""
        if self.active_page == new_page:
            return
            
        log.info("hierarchy_scan.popup_opened", url=new_page.url)
        self.active_page = new_page
        
        # Registra o evento de fechamento
        new_page.on("close", lambda: asyncio.create_task(self._on_page_closed(new_page)))
        
        # Aguarda a página carregar e tira print
        try:
            await new_page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        await self._save_preview()

    async def _on_page_closed(self, closed_page: Page):
        """Trata o fechamento de um popup, retornando o foco para a página principal."""
        log.info("hierarchy_scan.popup_closed")
        if self.active_page == closed_page:
            pages = closed_page.context.pages
            open_pages = [p for p in pages if not p.is_closed()]
            if open_pages:
                self.active_page = open_pages[0]
            await self._save_preview()


    async def _wait_for_manual_login(self, page: Page) -> bool:
        """Navega para a página de login e espera até que o usuário esteja autenticado."""
        log.info("hierarchy_scan.manual_login_waiting", message="Aguardando login manual na tela...")
        print("\n👉 [Terminal Scraper] Navegador aberto na tela de login do LinkedIn.")
        print("👉 [Terminal Scraper] Por favor, insira suas credenciais e faça o login (resolva captchas se necessário).")
        print("👉 [Terminal Scraper] O script detectará automaticamente quando o login for concluído!")
        
        await page.goto("https://www.linkedin.com/login")
        await self._save_preview(page)
        
        # Loop de verificação de login ultra-resiliente
        # Aguarda 3 minutos (90 tentativas de 2 segundos)
        for i in range(90):
            try:
                # Se mudou para qualquer URL contendo feed ou mynetwork, ou se o global-nav estiver na tela
                current_url = page.url
                if "/feed" in current_url or "/mynetwork" in current_url or await page.query_selector("#global-nav"):
                    log.info("hierarchy_scan.manual_login_success", message="Login manual detectado com sucesso!")
                    print("\n✅ [Terminal Scraper] Login detectado com sucesso!")
                    
                    # Captura o cookie li_at gerado pelo login bem-sucedido
                    try:
                        cookies = await page.context.cookies()
                        li_at_cookie = next((c["value"] for c in cookies if c["name"] == "li_at"), None)
                        if li_at_cookie:
                            log.info("hierarchy_scan.cookie_captured", cookie_len=len(li_at_cookie))
                            print(f"[COOKIE_CAPTURED] {li_at_cookie}")
                            import sys
                            sys.stdout.flush()
                    except Exception as e:
                        log.warning("hierarchy_scan.cookie_capture_error", error=str(e))
                        
                    await self._save_preview(page)
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
            # Atualiza o preview a cada 2s do login
            await self._save_preview(page)
            
        log.error("hierarchy_scan.manual_login_timeout", error="Tempo limite de login manual atingido.")
        print("\n❌ [Terminal Scraper] Tempo limite de login atingido (180s).")
        return False

    async def _listen_to_remote_commands(self, page: Page):
        """Ouvinte em background que lê comandos via stdin do parent process para interação remota (clique e escrita)."""
        import sys
        import asyncio
        
        loop = asyncio.get_running_loop()
        
        def read_line():
            return sys.stdin.readline()
            
        try:
            while True:
                line = await loop.run_in_executor(None, read_line)
                if not line:
                    break
                
                clean_line = line.strip()
                if not clean_line:
                    continue
                
                # Direciona os cliques e teclas para a aba ativa (popup do Google se estiver aberto)
                target_page = self.active_page if (self.active_page and not self.active_page.is_closed()) else page
                
                # Comandos suportados:
                # cmd_click X Y
                # cmd_type TEXT
                # cmd_press KEY
                if clean_line.startswith("cmd_click "):
                    parts = clean_line.split()
                    if len(parts) >= 3:
                        x_pct = float(parts[1])
                        y_pct = float(parts[2])
                        
                        # Obtém a resolução real da página ativa no momento
                        viewport = target_page.viewport_size
                        if viewport:
                            width = viewport.get("width", 1280)
                            height = viewport.get("height", 800)
                        else:
                            width = 1280
                            height = 800
                            
                        # Calcula a coordenada absoluta exata
                        x = int(x_pct * width)
                        y = int(y_pct * height)
                        
                        log.info("hierarchy_scan.remote_command.click", x=x, y=y, width=width, height=height)
                        # Executa o clique
                        await target_page.mouse.click(x, y)
                        await asyncio.sleep(0.5)
                        # Tira print para atualizar a tela
                        await self._save_preview()

                        
                elif clean_line.startswith("cmd_type "):
                    text = clean_line[9:]
                    log.info("hierarchy_scan.remote_command.type", text_len=len(text))
                    # Insere o texto no elemento focado
                    await target_page.keyboard.insert_text(text)
                    await asyncio.sleep(0.5)
                    await self._save_preview()
                    
                elif clean_line.startswith("cmd_press "):
                    key = clean_line[10:]
                    log.info("hierarchy_scan.remote_command.press", key=key)
                    # Pressiona uma tecla especial (ex: Enter, Backspace)
                    await target_page.keyboard.press(key)
                    await asyncio.sleep(0.5)
                    await self._save_preview()
                    
                elif clean_line == "cmd_stop":
                    log.info("hierarchy_scan.remote_command.stop", message="Parada graciosa solicitada!")
                    self.graceful_stop = True
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning("hierarchy_scan.remote_command_error", error=str(e))

    async def scrape_company_people(self, company_url: str) -> List[Dict]:
        """
        Acessa a página de pessoas de uma empresa, rola, clica em carregar mais resultados e extrai perfis.

        :param company_url: URL da empresa no LinkedIn (ex: https://www.linkedin.com/company/grupobrasa/people/)
        :return: Lista de dicionários contendo os dados das pessoas.
        """
        # Garante que a URL termine com /people/ ou /people
        if not re.search(r"/people/?$", company_url):
            company_url = company_url.rstrip("/") + "/people/"

        log.info("hierarchy_scan.start_scraping", target_url=company_url)
        extracted_people = []

        async with async_playwright() as p:
            browser, context, page = await self._setup_browser(p)
            
            stdin_task = None
            try:
                # Inicia o escutador de comandos remotos do stdin para interatividade do frontend!
                stdin_task = asyncio.create_task(self._listen_to_remote_commands(page))
                
                # 1. AUTENTICAÇÃO
                if not self.session_cookie:
                    log.warning("hierarchy_scan.no_cookie", message="Nenhum cookie de sessão li_at configurado. Iniciando Modo Manual.")
                    login_ok = await self._wait_for_manual_login(page)
                    if not login_ok:
                        log.error("hierarchy_scan.auth_failed", message="Falha na autenticação manual.")
                        return []
                else:
                    # Tenta acessar diretamente a página do perfil para testar se o cookie está válido
                    log.info("hierarchy_scan.test_session", message="Testando sessão com cookie fornecido...")
                    await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
                    await self._save_preview(page)
                    
                    # Se redirecionar para a página de login/registro, o cookie expirou!
                    current_url = page.url
                    if "login" in current_url or "signup" in current_url:
                        log.error("hierarchy_scan.cookie_expired", message="O cookie li_at fornecido expirou ou é inválido!")
                        # Com o painel interativo no frontend, o login manual pode ser feito remotamente via preview em modo headless!
                        log.warning("hierarchy_scan.cookie_expired_fallback", message="Iniciando fallback para login manual remoto...")
                        login_ok = await self._wait_for_manual_login(page)
                        if not login_ok:
                            return []
                    else:
                        log.info("hierarchy_scan.session_valid", message="Sessão autenticada via cookie com sucesso!")

                # 2. NAVEGAR PARA A PÁGINA DE PESSOAS
                log.info("hierarchy_scan.navigate_target", url=company_url)
                print(f"\n🚀 [Terminal Scraper] Navegando para a aba de pessoas: {company_url}")
                await page.goto(company_url, wait_until="load")
                await self._save_preview(page)
                
                # Aguarda carregamento de elementos estruturais da aba de pessoas
                try:
                    await page.wait_for_selector(".org-people-directory", timeout=20000)
                    print("   ✅ [Terminal Scraper] Aba de pessoas carregada com sucesso!")
                except Exception:
                    # LinkedIn pode ter um layout diferente ou bloquear
                    log.warning("hierarchy_scan.directory_selector_timeout", message="Seletor .org-people-directory não apareceu. Continuando mesmo assim...")
                    print("   ⚠️ [Terminal Scraper] Aba demorou para responder. Iniciando expansão direta...")

                await self._save_preview(page)

                # 3. LOOP "INCANSÁVEL" DE ROLAGEM E CLIQUES NO BOTÃO "EXIBIR MAIS"
                click_count = 0
                consecutive_no_new_data = 0
                last_people_count = 0
                
                log.info("hierarchy_scan.expansion_loop_start", max_clicks=self.max_clicks)
                print("   🔄 [Terminal Scraper] Iniciando rolagem e expansão incansável...")

                while click_count < self.max_clicks and not self.graceful_stop:
                    # Rola até o final para carregar mais itens preguiçosos
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    
                    # Atraso anti-bloqueio aleatório
                    await asyncio.sleep(random.uniform(self.click_delay_min, self.click_delay_max))
                    await self._save_preview(page)

                    # Verifica a quantidade atual de pessoas na página
                    current_people_cards = await self._find_people_cards(page)
                    current_count = len(current_people_cards)
                    log.info("hierarchy_scan.scroll_status", current_profiles_found=current_count, clicks=click_count)
                    print(f"      📊 [Progresso] Colaboradores na página: {current_count} | Expansões: {click_count}")

                    # Se não houve novas pessoas E não achamos o botão, paramos muito mais rápido!
                    if current_count == last_people_count:
                        consecutive_no_new_data += 1
                        if consecutive_no_new_data >= 2:
                            # Se não mudou a contagem em 2 ciclos e não tem botão, encerra!
                            show_more_button = await self._find_show_more_button(page)
                            if not show_more_button:
                                log.info("hierarchy_scan.no_more_results", message="Sem novos resultados e botão não encontrado. Fim da página.")
                                print("      🛑 [Status] Fim dos resultados atingido (fim dos colaboradores). Encerrando...")
                                break
                            
                            # Se o quórum de parada por não aumento atingir 5 mesmo com tentativas de botão, encerra
                            if consecutive_no_new_data >= 5:
                                log.info("hierarchy_scan.quorum_reached", message="Nenhum novo perfil carregado após várias tentativas. Encerrando.")
                                print("      🛑 [Status] Quórum de parada atingido (fim dos resultados).")
                                break
                    else:
                        consecutive_no_new_data = 0
                        last_people_count = current_count

                    # Procura pelo botão "Exibir mais resultados"
                    show_more_button = await self._find_show_more_button(page)
                    
                    if show_more_button:
                        log.info("hierarchy_scan.click_button", index=click_count + 1)
                        print(f"      🖱️ [Ação] Clicando no botão 'Exibir mais resultados' (clique {click_count + 1})...")
                        try:
                            await show_more_button.scroll_into_view_if_needed()
                            await show_more_button.click(force=True)
                            click_count += 1
                            await self._save_preview(page)
                            await asyncio.sleep(random.uniform(self.click_delay_min, self.click_delay_max))
                        except Exception as e:
                            log.warning("hierarchy_scan.click_error", error=str(e))
                            print("      ⚠️ [Status] Falha ao clicar no botão nesta rolagem. Tentando novamente...")
                            await asyncio.sleep(1)
                    else:
                        # Se não achou o botão de clique, talvez esteja carregando por rolagem infinita.
                        # Rola um pouco para cima e para baixo para garantir o disparo
                        await page.evaluate("window.scrollBy(0, -300)")
                        await asyncio.sleep(0.5)
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(2)
                        
                        # Verifica novamente se o botão apareceu
                        show_more_button_retry = await self._find_show_more_button(page)
                        if not show_more_button_retry:
                            log.info("hierarchy_scan.no_button_found", message="Botão 'Exibir mais' não encontrado. Rolando mais...")
                            print("      🔍 [Status] Botão não encontrado nesta rolagem. Rolando página...")

                # 4. EXTRAÇÃO DOS DADOS FINAIS
                log.info("hierarchy_scan.extraction_start")
                print("\n⚙️ [Terminal Scraper] Iniciando extração dos dados estruturados...")
                await self._save_preview(page)
                final_cards = await self._find_people_cards(page)
                
                for card in final_cards:
                    profile_data = await self._parse_profile_card(card)
                    if profile_data and profile_data.get("name"):
                        # Evita duplicatas se as rotas/seleções baterem mais de uma vez
                        if not any(p.get("linkedin_url") == profile_data["linkedin_url"] for p in extracted_people):
                            extracted_people.append(profile_data)
                            print(f"   👤 [Extraído] {profile_data['name']} - {profile_data['role']}")
                            
                log.info("hierarchy_scan.extraction_done", total_extracted=len(extracted_people))
                print(f"\n🎉 [Terminal Scraper] Extração concluída! Total extraído: {len(extracted_people)} colaboradores.")
                await self._save_preview(page)

            except Exception as e:
                log.exception("hierarchy_scan.fatal_error", error=str(e))
            finally:
                if stdin_task:
                    try:
                        stdin_task.cancel()
                    except Exception:
                        pass
                # Mantém o navegador aberto por 5 segundos antes de fechar caso queira olhar a UI final
                await asyncio.sleep(5)
                log.info("hierarchy_scan.closing_browser")
                await browser.close()

        return extracted_people

    async def _find_show_more_button(self, page: Page):
        """Procura o botão 'Exibir mais resultados' de forma altamente resiliente."""
        # Seletor de classe padrão do LinkedIn para botões de paginação infinita
        btn = await page.query_selector("button.scaffold-finite-scroll__load-button")
        if btn and await btn.is_visible() and await btn.is_enabled():
            return btn

        # XPaths textuais resilientes a idiomas
        xpaths = [
            "//button[contains(., 'Exibir mais')]",
            "//button[contains(., 'Show more')]",
            "//button[contains(., 'See more')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'exibir mais')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show more')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'see more')]"
        ]
        for xpath in xpaths:
            elements = await page.query_selector_all(f"xpath={xpath}")
            for el in elements:
                if await el.is_visible() and await el.is_enabled():
                    return el
        return None

    async def _find_people_cards(self, page: Page) -> List:
        """Encontra todos os cartões de pessoas na página com seletores flexíveis."""
        card_selectors = [
            "li.org-people-profiles-module__profile-item",
            "li.org-people-profile-card__profile-card-spacing",
            ".org-people-directory__profile-list-item",
            ".artdeco-card div.artdeco-entity-lockup"
        ]
        
        for selector in card_selectors:
            elements = await page.query_selector_all(selector)
            if elements:
                return elements
        
        # Fallback supremo: qualquer div que contenha link para /in/
        elements = await page.query_selector_all("div:has(a[href*='/in/'])")
        return elements

    async def _parse_profile_card(self, card) -> Optional[Dict]:
        """Extrai os dados de um cartão de perfil individual."""
        try:
            # 1. URL do Perfil do LinkedIn
            anchor = await card.query_selector("a[href*='/in/']")
            if not anchor:
                return None
                
            raw_href = await anchor.get_attribute("href")
            if not raw_href:
                return None
                
            # Limpa parâmetros de query na URL (ex: ?miniProfileId=...)
            linkedin_url = raw_href.split("?")[0].rstrip("/")
            if "linkedin.com/in/" not in linkedin_url:
                # Transforma caminhos relativos em absolutos
                if linkedin_url.startswith("/in/"):
                    linkedin_url = "https://www.linkedin.com" + linkedin_url
                else:
                    return None

            # 2. Nome da Pessoa
            # Tenta pegar o elemento que tipicamente contém o título/nome
            name = None
            name_selectors = [
                ".org-people-profile-card__profile-title",
                ".artdeco-entity-lockup__title",
                "a[href*='/in/'] .lt-line-clamp",
                ".lt-line-clamp--multi",
                "div.artdeco-entity-lockup__title a"
            ]
            for sel in name_selectors:
                el = await card.query_selector(sel)
                if el:
                    raw_name = await el.inner_text()
                    if raw_name:
                        # Limpa sufixos de conexão (ex: "João da Silva • 2º" ou " • 3º e +")
                        name = re.sub(r"\s*•\s*\d+º(?:º)?.*$", "", raw_name).strip()
                        name = re.sub(r"\s+[\d]º$", "", name).strip()
                        break

            if not name:
                # Fallback: pega o texto da tag âncora principal
                name = await anchor.inner_text()
                name = re.sub(r"\s*•\s*\d+º(?:º)?.*$", "", name).strip()
                name = re.sub(r"\s+[\d]º$", "", name).strip()
                if not name:
                    return None

            # 3. Cargo / Headline
            role = ""
            role_selectors = [
                ".artdeco-entity-lockup__subtitle",
                ".org-people-profile-card__profile-subtitle",
                ".lt-line-clamp--multi"
            ]
            for sel in role_selectors:
                el = await card.query_selector(sel)
                if el:
                    raw_role = await el.inner_text()
                    if raw_role and raw_role.strip() != name:
                        role = raw_role.strip()
                        break

            # 4. Avatar (Foto do perfil)
            avatar_url = ""
            img = await card.query_selector("img")
            if img:
                src = await img.get_attribute("src")
                # Filtra avatares padrão do LinkedIn / placeholders vazios
                if src and not src.startswith("data:image"):
                    avatar_url = src

            # 5. Localização / Conexões comuns (Informações extras se existirem)
            location = ""
            loc_selectors = [
                ".artdeco-entity-lockup__caption",
                ".org-people-profile-card__profile-location"
            ]
            for sel in loc_selectors:
                el = await card.query_selector(sel)
                if el:
                    raw_loc = await el.inner_text()
                    if raw_loc:
                        location = raw_loc.strip()
                        break

            return {
                "name": name,
                "role": role or "Profissional no LinkedIn",
                "linkedin_url": linkedin_url,
                "avatar": avatar_url,
                "location": location
            }

        except Exception as e:
            log.warning("hierarchy_scan.parse_card_error", error=str(e))
            return None
