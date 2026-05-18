import React, { useState, useRef, useEffect, useCallback } from 'react';
import styles from './Drawer.module.css';
import { Spinner } from '../';
import { organizations as orgsApi } from '@/services/api';
import type { NotificationType } from '../Notification';
import { DrawerHeader, FocusedOrgView, OrgList, ConfirmModal } from './components';

interface DrawerProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    searchTerm: string;
    setSearchTerm: (term: string) => void;
    filteredOrgs: any[];
    onOrgClick: (org: any) => void;
    onOrgReset?: (orgId: number) => void;
    onOrgRenamed?: (orgId: number, newName: string) => void;
    isLoading?: boolean;
    selectedOrgId?: number | null;
    selectedOrgLogo?: string;
    activeJobId?: string | null;
    graphEmployees?: any[];
    refreshDetailsTrigger?: number; // Para forçar a recarga dos detalhes
    addNotification?: (type: NotificationType, message: string) => void;
}

const LOCAL_CACHE_KEYS = (orgId: number) => [
    `org-${orgId}-details`,
    `org-${orgId}-logo`,
    `org-${orgId}-hierarchy`,
    `pipedrive-orgs-cache`,
    `layout-cache-${orgId}`,
    `edges-cache-${orgId}`,
];

function clearLocalOrgCaches(orgId: number) {
    try {
        LOCAL_CACHE_KEYS(orgId).forEach((key) => {
            if (typeof window !== 'undefined' && window.localStorage.getItem(key)) {
                window.localStorage.removeItem(key);
            }
        });
    } catch {
        /* ignore */
    }
}

type ConfirmKind = 'reset' | 'delete' | null;

export const Drawer: React.FC<DrawerProps> = ({
    showDrawer,
    setShowDrawer,
    searchTerm,
    setSearchTerm,
    filteredOrgs,
    onOrgClick,
    onOrgReset,
    onOrgRenamed,
    isLoading = false,
    selectedOrgId = null,
    selectedOrgLogo = '',
    activeJobId = null,
    graphEmployees = [],
    refreshDetailsTrigger = 0,
    addNotification = () => {},
}) => {
    const [expandedOrgId, setExpandedOrgIdState] = useState<number | null>(() => {
        if (typeof window !== 'undefined') {
            const saved = window.localStorage.getItem('drawer-expanded-org-id');
            return saved ? Number(saved) : null;
        }
        return null;
    });

    const setExpandedOrgId = (orgId: number | null) => {
        setExpandedOrgIdState(orgId);
        if (typeof window !== 'undefined') {
            if (orgId === null) {
                window.localStorage.removeItem('drawer-expanded-org-id');
            } else {
                window.localStorage.setItem('drawer-expanded-org-id', orgId.toString());
            }
        }
    };

    // Sincroniza estado de expansão quando o localStorage é alterado externamente (ex: botão "+" no Sidebar)
    useEffect(() => {
        if (!showDrawer) return;

        const checkExpansion = () => {
            const saved = window.localStorage.getItem('drawer-expanded-org-id');
            const currentId = saved ? Number(saved) : null;
            if (currentId !== expandedOrgId) {
                setExpandedOrgIdState(currentId);
            }
        };

        // Verifica imediatamente ao abrir
        checkExpansion();

        // Escuta eventos de storage para sincronizar entre abas ou ações locais que limpam o storage
        window.addEventListener('storage', checkExpansion);
        
        // Custom event para quando clicamos no "+" (já que 'storage' não dispara na mesma aba)
        window.addEventListener('drawer_reset_expansion', checkExpansion);

        return () => {
            window.removeEventListener('storage', checkExpansion);
            window.removeEventListener('drawer_reset_expansion', checkExpansion);
        };
    }, [showDrawer, expandedOrgId]);

    const [orgDetails, setOrgDetails] = useState<Record<number, any>>(() => {
        if (typeof window !== 'undefined' && expandedOrgId) {
            const cached = window.localStorage.getItem(`org-${expandedOrgId}-details`);
            if (cached) {
                try {
                    return { [expandedOrgId]: JSON.parse(cached) };
                } catch {}
            }
        }
        return {};
    });
    const [loadingDetails, setLoadingDetails] = useState<Record<number, boolean>>({});
    
    const [activeTab, setActiveTabState] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return window.localStorage.getItem('drawer-active-tab') || 'activities';
        }
        return 'activities';
    });

    const setActiveTab = (tab: string) => {
        setActiveTabState(tab);
        if (typeof window !== 'undefined') {
            window.localStorage.setItem('drawer-active-tab', tab);
        }
    };

    // 🚀 Carregamento inicial de detalhes se já houver empresa expandida
    useEffect(() => {
        if (expandedOrgId) {
            void fetchOrgDetails(expandedOrgId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const [editingNameOrgId, setEditingNameOrgId] = useState<number | null>(null);
    const [editingNameValue, setEditingNameValue] = useState<string>('');
    const [confirmKind, setConfirmKind] = useState<ConfirmKind>(null);
    const [confirmBusy, setConfirmBusy] = useState<boolean>(false);
    const [scanningOrgId, setScanningOrgId] = useState<number | null>(null);

    const fetchOrgDetails = useCallback(async (orgId: number, force: boolean = false) => {
        if (!force && orgDetails[orgId]) return; // Já carregado

        setLoadingDetails(prev => ({ ...prev, [orgId]: true }));
        try {
            const data = await orgsApi.getOrganizationDetails(orgId);
            setOrgDetails(prev => ({ ...prev, [orgId]: data }));
            if (typeof window !== 'undefined') {
                window.localStorage.setItem(`org-${orgId}-details`, JSON.stringify(data));
            }
            if (force) {
                addNotification('success', 'Dados sincronizados com o Pipedrive.');
            }
        } catch (e: any) {
            console.error('Erro ao carregar detalhes:', e.message || e);
            if (force) {
                const msg = (e as any)?.message || 'Erro ao sincronizar. Tente novamente.';
                addNotification('error', msg);
            }
        } finally {
            setLoadingDetails(prev => ({ ...prev, [orgId]: false }));
        }
    }, [orgDetails, addNotification]);

    useEffect(() => {
        if (refreshDetailsTrigger > 0) {
            // Em nova varredura ou job explícito, zera estado local
            setOrgDetails({});
            setExpandedOrgId(null);
        }
    }, [refreshDetailsTrigger]);

    useEffect(() => {
        if (activeJobId) {
            try {
                const jobStr = typeof window !== 'undefined' ? window.localStorage.getItem('active-discovery-job') : null;
                if (jobStr) {
                    const parsed = JSON.parse(jobStr);
                    setScanningOrgId(parsed.orgId);
                }
            } catch {
                setScanningOrgId(null);
            }
        } else {
            setScanningOrgId(null);
        }
    }, [activeJobId]);

    const toggleExpand = (e: React.MouseEvent, orgId: number) => {
        e.stopPropagation();
        if (expandedOrgId === orgId) {
            setExpandedOrgId(null);
        } else {
            setExpandedOrgId(orgId);
            void fetchOrgDetails(orgId);
        }
    };

    const performReset = async (orgId: number) => {
        setConfirmBusy(true);
        try {
            await orgsApi.resetOrganization(orgId);

            clearLocalOrgCaches(orgId);
            setOrgDetails(prev => {
                const updated = { ...prev };
                delete updated[orgId];
                return updated;
            });
            setExpandedOrgId(null);

            if (onOrgReset) onOrgReset(orgId);
            addNotification('success', 'Todos os dados e cache da empresa foram resetados!');
        } catch (e: any) {
            console.error('Erro ao resetar:', e.message || e);
            addNotification('error', 'Erro ao resetar dados.');
        } finally {
            setConfirmBusy(false);
            setConfirmKind(null);
        }
    };

    const performDelete = async (orgId: number) => {
        setConfirmBusy(true);
        try {
            await orgsApi.deleteOrganization(orgId);

            clearLocalOrgCaches(orgId);
            setOrgDetails(prev => {
                const updated = { ...prev };
                delete updated[orgId];
                return updated;
            });
            setExpandedOrgId(null);

            if (onOrgReset) onOrgReset(orgId);
            addNotification('success', 'Empresa foi apagada do CRM com sucesso!');
        } catch (e: any) {
            console.error('Erro ao excluir:', e.message || e);
            addNotification('error', 'Erro ao excluir empresa.');
        } finally {
            setConfirmBusy(false);
            setConfirmKind(null);
        }
    };

    const handleRenameOrg = async (orgId: number) => {
        if (!editingNameValue || editingNameValue.trim() === '') {
            setEditingNameOrgId(null);
            return;
        }

        try {
            await orgsApi.renameOrganization(orgId, editingNameValue.trim());

            // Atualizar no local state (mutação controlada do array do pai)
            const updatedOrg = filteredOrgs.find(o => Number(o.id) === orgId);
            if (updatedOrg) {
                updatedOrg.name = editingNameValue.trim();
            }

            setOrgDetails(prev => {
                if (prev[orgId]) {
                    return {
                        ...prev,
                        [orgId]: { ...prev[orgId], name: editingNameValue.trim() },
                    };
                }
                return prev;
            });

            setEditingNameOrgId(null);

            if (onOrgRenamed) onOrgRenamed(orgId, editingNameValue.trim());
            addNotification('success', 'Nome da empresa atualizado!');
        } catch (e: any) {
            console.error('Erro ao renomear:', e.message || e);
            addNotification('error', 'Erro ao renomear empresa.');
        }
    };

    // Filtra a organização que está em foco
    const focusedOrg = expandedOrgId ? filteredOrgs.find(o => Number(o.id) === expandedOrgId) : null;

    if (!showDrawer) return null;

    return (
        <div className={styles.drawer}>
            <DrawerHeader 
                expandedOrgId={expandedOrgId}
                setExpandedOrgId={setExpandedOrgId}
                searchTerm={searchTerm}
                setSearchTerm={setSearchTerm}
                setShowDrawer={setShowDrawer}
                fetchOrgDetails={fetchOrgDetails}
                loadingDetails={loadingDetails}
                setConfirmKind={setConfirmKind}
            />

            <div className={styles.drawerList}>
                {isLoading ? (
                    <div className={styles.drawerLoading}>
                        <Spinner size={32} />
                    </div>
                ) : expandedOrgId && focusedOrg ? (
                    <FocusedOrgView 
                        focusedOrg={focusedOrg}
                        expandedOrgId={expandedOrgId}
                        orgDetails={orgDetails}
                        loadingDetails={loadingDetails}
                        activeTab={activeTab}
                        setActiveTab={setActiveTab}
                        editingNameOrgId={editingNameOrgId}
                        editingNameValue={editingNameValue}
                        setEditingNameValue={setEditingNameValue}
                        setEditingNameOrgId={setEditingNameOrgId}
                        handleRenameOrg={handleRenameOrg}
                        scanningOrgId={scanningOrgId}
                        selectedOrgId={selectedOrgId}
                        selectedOrgLogo={selectedOrgLogo}
                    />
                ) : (
                    <OrgList 
                        filteredOrgs={filteredOrgs}
                        selectedOrgId={selectedOrgId}
                        selectedOrgLogo={selectedOrgLogo}
                        graphEmployees={graphEmployees}
                        onOrgClick={onOrgClick}
                        setExpandedOrgId={setExpandedOrgId}
                        fetchOrgDetails={fetchOrgDetails}
                        toggleExpand={toggleExpand}
                        scanningOrgId={scanningOrgId}
                    />
                )}
            </div>

            <ConfirmModal 
                confirmKind={confirmKind}
                confirmBusy={confirmBusy}
                setConfirmKind={setConfirmKind}
                performDelete={performDelete}
                performReset={performReset}
                expandedOrgId={expandedOrgId}
            />
        </div>
    );
};

