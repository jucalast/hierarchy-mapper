import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useChatStore } from '../../../store/chatStore';
import { Sparkles, X, Building2 } from 'lucide-react';
import styles from '../styles/ChatTabs.module.css';

interface CachedOrg {
  id: number;
  name?: string;
  title?: string;
  logo?: string;
  organization_logo?: string;
  logo_url?: string;
  company_logo?: string;
}

export const ChatTabs: React.FC = () => {
  const router = useRouter();
  const activeTabs = useChatStore((state) => state.activeTabs);
  const currentOrgId = useChatStore((state) => state.currentOrgId);
  const setCurrentOrgId = useChatStore((state) => state.setCurrentOrgId);
  const removeActiveTab = useChatStore((state) => state.removeActiveTab);

  const [orgDataMap, setOrgDataMap] = useState<Record<number, { name: string; logo: string }>>({});

  // Carrega informações das organizações do cache do localStorage
  useEffect(() => {
    const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
    if (!cachedOrgsStr) return;

    try {
      const list = JSON.parse(cachedOrgsStr) as CachedOrg[];
      if (Array.isArray(list)) {
        const dataMap: Record<number, { name: string; logo: string }> = {};
        list.forEach((org) => {
          const id = Number(org.id);
          if (id) {
            const name = org.name || org.title || `Empresa ${id}`;
            const logo = org.logo || org.organization_logo || org.logo_url || org.company_logo || '';
            dataMap[id] = { name, logo };
          }
        });
        setOrgDataMap(dataMap);
      }
    } catch (e) {
      console.error('Erro ao ler cache de organizações em ChatTabs:', e);
    }
  }, [activeTabs]); // Recarrega se as abas mudarem para garantir sincronização

  // Escuta alteração do cache externo de organizações (ex: quando adiciona uma nova empresa)
  useEffect(() => {
    const handleCacheUpdated = () => {
      const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
      if (!cachedOrgsStr) return;
      try {
        const list = JSON.parse(cachedOrgsStr) as CachedOrg[];
        if (Array.isArray(list)) {
          const dataMap: Record<number, { name: string; logo: string }> = {};
          list.forEach((org) => {
            const id = Number(org.id);
            if (id) {
              const name = org.name || org.title || `Empresa ${id}`;
              const logo = org.logo || org.organization_logo || org.logo_url || org.company_logo || '';
              dataMap[id] = { name, logo };
            }
          });
          setOrgDataMap(dataMap);
        }
      } catch {}
    };

    window.addEventListener('pipedrive_orgs_cache_updated', handleCacheUpdated);
    return () => window.removeEventListener('pipedrive_orgs_cache_updated', handleCacheUpdated);
  }, []);

  const handleTabClick = (orgId: number | null) => {
    setCurrentOrgId(orgId);
    // Navega para a empresa clicada para manter URL, layout e chat em sincronia
    if (orgId) {
      router.push(`/org/${orgId}`);
    }
  };

  const handleCloseTab = (e: React.MouseEvent, orgId: number) => {
    e.stopPropagation();
    removeActiveTab(orgId);
  };

  return (
    <div className={styles.tabsContainer}>
      {/* Aba Assistente Geral */}
      <button
        onClick={() => handleTabClick(null)}
        className={`${styles.tab} ${currentOrgId === null ? styles.tabActive : ''}`}
        title="Assistente Geral"
      >
        <Sparkles size={14} className={styles.tabIcon} />
        <span className={styles.tabName}>Assistente</span>
      </button>

      {/* Abas das Organizações Ativas */}
      {activeTabs.map((orgId) => {
        const orgInfo = orgDataMap[orgId] || { name: `Empresa ${orgId}`, logo: '' };
        const isActive = currentOrgId === orgId;

        return (
          <div
            key={orgId}
            onClick={() => handleTabClick(orgId)}
            className={`${styles.tab} ${isActive ? styles.tabActive : ''}`}
            title={orgInfo.name}
          >
            {orgInfo.logo ? (
              <img
                src={orgInfo.logo}
                alt={orgInfo.name}
                className={styles.tabLogo}
                onError={(e) => {
                  // Fallback se falhar ao carregar imagem
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
            ) : (
              <Building2 size={14} className={styles.tabIcon} />
            )}
            <span className={styles.tabName}>{orgInfo.name}</span>
            <button
              onClick={(e) => handleCloseTab(e, orgId)}
              className={styles.closeBtn}
              title="Fechar aba"
            >
              <X size={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
