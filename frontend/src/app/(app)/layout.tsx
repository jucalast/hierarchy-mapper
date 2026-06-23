"use client";

import React, { useState, useEffect } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { organizations as orgsApi } from '@/services/api';
import { TriggerNotifications } from '@/components/ui/TriggerNotifications';
import { API_BASE_URL, apiGet } from '@/services/config';
import { PanelRight, LogOut } from 'lucide-react';
import { Avatar } from '@/components/ui';
import { ChatPanel } from '@/components/chat/ChatPanel';
import dynamic from 'next/dynamic';
import { useBackendReady } from '@/hooks/useBackendReady';

import { HierarchyScanProvider } from '@/contexts/HierarchyScanContext';

const NetworkGraph = dynamic(() => import('@/components/network-graph/NetworkGraph'), { ssr: false });

function BackendGate({ children }: { children: React.ReactNode }) {
  const { state, elapsed } = useBackendReady();

  if (state === 'checking') {
    return (
      <div style={{
        height: '100vh', width: '100vw', background: 'var(--sw-sidebar)',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
        alignItems: 'center', gap: '8px',
        color: 'var(--sw-text-muted)', fontFamily: 'var(--font-primary)', fontSize: '12px',
        letterSpacing: '0.08em',
      }}>
        <span>CONECTANDO AO SERVIDOR{elapsed > 2 ? ` (${elapsed}s)` : '...'}</span>
      </div>
    );
  }

  if (state === 'timeout') {
    return (
      <div style={{
        height: '100vh', width: '100vw', background: 'var(--sw-sidebar)',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
        alignItems: 'center', gap: '12px',
        color: 'var(--sw-status-danger)', fontFamily: 'var(--font-primary)', fontSize: '12px',
        letterSpacing: '0.08em',
      }}>
        <span>SERVIDOR INDISPONÍVEL</span>
        <button
          onClick={() => window.location.reload()}
          style={{
            background: 'transparent', border: '1px solid var(--sw-status-danger)',
            color: 'var(--sw-status-danger)', padding: '6px 16px', cursor: 'pointer',
            fontSize: '11px', letterSpacing: '0.08em', borderRadius: '4px',
          }}
        >
          TENTAR NOVAMENTE
        </button>
      </div>
    );
  }

  return <>{children}</>;
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [showChat, setShowChat] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [currentOrg, setCurrentOrg] = useState<{ id: number; name: string; logo: string; prospectingContext?: string | null }>({ id: 0, name: "", logo: "" });
  const [isOrgLoading, setIsOrgLoading] = useState(false);
  const [currentUser, setCurrentUser] = useState<{ name: string; avatar: string | null; company_name?: string } | null>(null);
  const [tasksForToday, setTasksForToday] = useState(0);

  useEffect(() => {
    const handleUpdateTasks = (e: any) => setTasksForToday(e.detail || 0);
    window.addEventListener('update_tasks_today', handleUpdateTasks);
    return () => window.removeEventListener('update_tasks_today', handleUpdateTasks);
  }, []);

  // Escuta evento para abrir o Chat a partir de componentes filhos
  useEffect(() => {
    const handleToggleChat = (e: any) => {
      const shouldOpen = e.detail?.open ?? !showChat;
      setAndSaveShowChat(shouldOpen);
    };
    window.addEventListener('toggle_chat', handleToggleChat);
    return () => window.removeEventListener('toggle_chat', handleToggleChat);
  }, [showChat]);

  // Carrega tema, estado inicial do chat e usuário
  useEffect(() => {
    const savedTheme = localStorage.getItem("preferred-theme") as "light" | "dark";
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.setAttribute("data-theme", savedTheme);
    }
    const savedChat = localStorage.getItem("show-chat") === "true";
    setShowChat(savedChat);

    const loadUser = async () => {
      // Tenta primeiro carregar o usuário do Pipedrive (que contém o avatar)
      const pipedriveUserStr = localStorage.getItem('pipedrive-current-user');
      if (pipedriveUserStr) {
        try {
          const parsed = JSON.parse(pipedriveUserStr);
          if (parsed && parsed.name) {
            setCurrentUser({
              name: parsed.name,
              avatar: parsed.avatar || null,
              company_name: parsed.company_name || parsed.company_id?.name || parsed.company || 'Buscando...'
            });
          }
        } catch (e) {
          console.error("Erro ao parsear pipedrive-current-user:", e);
        }
      } else {
        const userName = localStorage.getItem('user_name');
        if (userName) {
          setCurrentUser({
            name: userName,
            avatar: null,
            company_name: 'LINKB2B'
          });
        }
      }

      // Busca atualizada do backend usando apiGet para garantir headers de auth
      try {
        const data = await apiGet('/pipedrive/current-user', { cache: 'no-store' });
        if (data) {
          setCurrentUser({
            ...data,
            company_name: data.company_name || data.company_id?.name || data.company || 'Buscando...'
          });
          localStorage.setItem('pipedrive-current-user', JSON.stringify(data));
        }
      } catch (err) {
        console.error('Erro ao buscar usuário atual:', err);
      }
    };

    void loadUser();
  }, []);

  // Sincroniza Contexto da Empresa baseado na URL /org/[id]
  useEffect(() => {
    const match = pathname?.match(/\/org\/(\d+)/);
    if (match && match[1]) {
      const orgId = parseInt(match[1]);
      if (!currentOrg || currentOrg.id !== orgId) {
        console.log(`[Layout AppLayout] Sincronizando contexto da empresa. Mudando de ${currentOrg?.id} para ${orgId}.`);
        
        // Inicializa estado imediatamente para evitar visualização de cache/dados antigos do Chat
        setCurrentOrg({ id: orgId, name: "Carregando...", logo: "", prospectingContext: null });
        
        // 1. Tenta buscar primeiro no cache local de organizações (onde o logo e metadados estão sempre completos)
        const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
        let cacheFound = false;
        if (cachedOrgsStr) {
          try {
            const list = JSON.parse(cachedOrgsStr);
            if (Array.isArray(list)) {
              const cachedOrg = list.find((o: any) => Number(o.id) === orgId || Number(o.pipedrive_id) === orgId || Number(o.local_id) === orgId);
              if (cachedOrg) {
                const foundLogo = cachedOrg.logo || cachedOrg.organization_logo || cachedOrg.logo_url || cachedOrg.company_logo || "";
                setCurrentOrg({
                  id: orgId,
                  name: cachedOrg.name || cachedOrg.title || "Empresa",
                  logo: foundLogo,
                  prospectingContext: cachedOrg.prospecting_context || null
                });
                cacheFound = true;
                // Do not return here. Continue to fetch from backend to get fresh prospecting_context
              }
            }
          } catch (e) {
            console.error("Erro ao ler pipedrive-orgs-cache no layout:", e);
          }
        }

        // 2. Busca atualizada do backend (sempre roda para atualizar dados voláteis como prospecting_context)
        setIsOrgLoading(true);
        orgsApi.getOrganizationDetails(orgId).then((res: any) => {
          if (res && res.org) {
            setCurrentOrg({
              id: orgId,
              name: res.org.name,
              logo: res.org.logo || res.org.logo_url || res.org.organization_logo || res.org.company_logo || res.logo || "",
              prospectingContext: res.prospecting_context || null
            });
          }
        }).catch(() => {
            if (!cacheFound) {
              setCurrentOrg({ id: orgId, name: "Empresa", logo: "", prospectingContext: null });
            }
        }).finally(() => {
            setIsOrgLoading(false);
        });
      }
    } else {
      setCurrentOrg({ id: 0, name: "", logo: "" });
      setIsOrgLoading(false);
    }
  }, [pathname, currentOrg?.id]);

  // Escuta evento para atualizar o prospectingContext quando um novo plano for gerado
  useEffect(() => {
    const handlePlanUpdated = () => {
      if (currentOrg && currentOrg.id) {
        orgsApi.getOrganizationDetails(currentOrg.id).then((res: any) => {
          if (res && res.org) {
            setCurrentOrg(prev => ({
              ...prev,
              prospectingContext: res.prospecting_context || prev.prospectingContext
            }));
          }
        }).catch(console.error);
      }
    };
    window.addEventListener('prospecting_plan_updated', handlePlanUpdated);
    return () => window.removeEventListener('prospecting_plan_updated', handlePlanUpdated);
  }, [currentOrg?.id]);

  function setAndSaveShowChat(val: boolean) {
    setShowChat(val);
    localStorage.setItem("show-chat", val.toString());
  }

  // Esconde o ChatPanel automaticamente na rota /messages (ou ?view=messages) para não conflitar com o MessagesView
  const [wasInMessages, setWasInMessages] = useState(false);
  useEffect(() => {
    const isMessages = pathname?.startsWith('/messages') || searchParams?.get('view') === 'messages';
    if (isMessages) {
      if (showChat) setShowChat(false);
      setWasInMessages(true);
    } else if (wasInMessages) {
      // Ao sair de /messages, restaura o estado salvo no localStorage
      const savedChat = localStorage.getItem("show-chat") === "true";
      setShowChat(savedChat);
      setWasInMessages(false);
    }
  }, [pathname, searchParams, wasInMessages, showChat]);

  // Escuta evento externo de alteração de tema (ex: do Sidebar no NetworkGraph)
  useEffect(() => {
    const handleThemeChanged = (e: CustomEvent<"light" | "dark">) => {
      if (e.detail && (e.detail === "light" || e.detail === "dark")) {
        setTheme(e.detail);
      }
    };
    window.addEventListener('theme_changed', handleThemeChanged as EventListener);
    return () => window.removeEventListener('theme_changed', handleThemeChanged as EventListener);
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    localStorage.setItem("preferred-theme", newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    window.dispatchEvent(new CustomEvent('theme_changed', { detail: newTheme }));
  };

  const handleLogout = () => {
    ['token','user_id','user_name','user_email','user_role','tenant_id','tenant_name']
      .forEach((k) => localStorage.removeItem(k));
    document.cookie = "token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    router.push('/login');
  };

  return (
    <HierarchyScanProvider>
      <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', overflow: 'hidden' }}>
        <div style={{ display: 'flex', flex: 1, position: 'relative', overflow: 'hidden' }}>
          <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
            {children}
            <BackendGate>
              <main style={{ height: '100%', width: '100%' }}>
                <NetworkGraph 
                  onLogout={handleLogout} 
                  currentUser={currentUser}
                  tasksForToday={tasksForToday}
                  onToggleChat={() => {
                    const newVal = !showChat;
                    setAndSaveShowChat(newVal);
                  }}
                />
              </main>
            </BackendGate>
          </div>

          <div style={{ 
            height: '100%', 
            display: 'flex',
            borderLeft: 'none'
          }}>
            <ChatPanel
              showChat={showChat}
              setShowChat={setAndSaveShowChat}
              selectedOrgId={currentOrg.id || null}
              selectedOrgName={currentOrg.name || "Assistente IA"}
              theme={theme}
              onToggleTheme={toggleTheme}
              selectedOrgLogo={currentOrg.logo || ""}
              prospectingContext={currentOrg.prospectingContext}
              isOrgLoading={isOrgLoading}
            />
          </div>
        </div>

        {/* Botão flutuante para abrir o Chat removido a pedido do usuário */}
      </div>
    </HierarchyScanProvider>
  );
}
