"use client";

import React, { useState, useEffect } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { organizations as orgsApi } from '@/services/api';
import { TriggerNotifications } from '@/components/ui/TriggerNotifications';
import { API_BASE_URL, apiGet } from '@/services/config';
import { PanelRight, LogOut } from 'lucide-react';
import { Avatar } from '@/components/ui';
import { ChatPanel } from '@/components/chat/ChatPanel';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [showChat, setShowChat] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [currentOrg, setCurrentOrg] = useState<{ id: number; name: string; logo: string } | null>(null);
  const [currentUser, setCurrentUser] = useState<{ name: string; avatar: string | null } | null>(null);

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
              avatar: parsed.avatar || null
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
            avatar: null
          });
        }
      }

      // Busca atualizada do backend usando apiGet para garantir headers de auth
      try {
        const data = await apiGet('/pipedrive/current-user');
        if (data) {
          setCurrentUser(data);
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
        // 1. Tenta buscar primeiro no cache local de organizações (onde o logo e metadados estão sempre completos)
        const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
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
                  logo: foundLogo
                });
                return;
              }
            }
          } catch (e) {
            console.error("Erro ao ler pipedrive-orgs-cache no layout:", e);
          }
        }

        // 2. Fallback: busca atualizada do backend
        orgsApi.getOrganizationDetails(orgId).then((res: any) => {
          if (res && res.org) {
            setCurrentOrg({
              id: orgId,
              name: res.org.name,
              logo: res.org.logo || res.org.logo_url || res.org.organization_logo || res.org.company_logo || res.logo || ""
            });
          }
        }).catch(() => {
            setCurrentOrg({ id: orgId, name: "Empresa", logo: "" });
        });
      }
    } else {
      setCurrentOrg(null);
    }
  }, [pathname, currentOrg]);

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
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', overflow: 'hidden' }}>
      {/* Global Header spans full width */}
      <header style={{ 
        height: '48px', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between', 
        padding: '0 24px',
        background: theme === 'dark' 
          ? 'linear-gradient(135deg, #1e2145 30%, #131313 80%)' 
          : 'linear-gradient(135deg, #eef2ff 30%, #f9fafb 80%)',
        borderBottom: '1px solid var(--sw-border)',
        zIndex: 100,
        transition: 'background var(--transition-fast)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ 
            fontFamily: 'Inter, sans-serif', 
            fontSize: '12px', 
            fontWeight: 600, 
            color: theme === 'dark' ? 'rgba(255,255,255,0.6)' : 'var(--sw-text-subtle)', 
            letterSpacing: '0.08em', 
            textTransform: 'uppercase' 
          }}>
            LINKB2B Hierarchy Mapper
          </span>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <TriggerNotifications
            apiBase={API_BASE_URL}
            onOpenChat={(orgId, orgName) => {
              window.dispatchEvent(new CustomEvent('toggle_chat', { detail: { open: true } }));
            }}
          />
          
          <button
            onClick={() => {
              const newVal = !showChat;
              setAndSaveShowChat(newVal);
            }}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: '8px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              color: theme === 'dark' ? 'rgba(255,255,255,0.6)' : 'var(--sw-text-subtle)',
              marginRight: '8px'
            }}
            title="Abrir Assistente"
          >
            <PanelRight size={20} />
          </button>

          {currentUser && (
            <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: '8px', 
                marginRight: '8px', 
                borderRight: `1px solid ${theme === 'dark' ? 'rgba(255,255,255,0.1)' : 'var(--sw-border)'}`, 
                paddingRight: '16px', 
                height: '24px' 
            }}>
                <Avatar
                    kind="person"
                    name={currentUser.name}
                    src={currentUser.avatar}
                    size={24}
                />
                <span style={{ fontSize: '12px', fontWeight: 500, color: theme === 'dark' ? 'white' : 'var(--sw-text-base)', opacity: 0.8 }}>
                    {currentUser.name}
                </span>
            </div>
          )}

          <button
            onClick={handleLogout}
            style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                padding: '8px',
                color: theme === 'dark' ? 'rgba(255,255,255,0.6)' : 'var(--sw-text-subtle)',
                display: 'flex',
                alignItems: 'center'
            }}
            title="Sair"
          >
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <div style={{ display: 'flex', flex: 1, position: 'relative', overflow: 'hidden' }}>
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          {children}
        </div>

        <div style={{ 
          height: '100%', 
          display: showChat ? 'flex' : 'none',
          borderLeft: '1px solid var(--sw-border)'
        }}>
          <ChatPanel
            showChat={showChat}
            setShowChat={setAndSaveShowChat}
            selectedOrgId={currentOrg?.id || null}
            selectedOrgName={currentOrg?.name || "Assistente IA"}
            theme={theme}
            onToggleTheme={toggleTheme}
            selectedOrgLogo={currentOrg?.logo || ""}
          />
        </div>
      </div>

      {/* Botão flutuante para abrir o Chat removido a pedido do usuário */}
    </div>
  );
}
