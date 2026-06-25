import React, { useState, useRef, useEffect, useCallback } from 'react';
import styles from './Drawer.module.css';
import { Spinner } from '../';
import { organizations as orgsApi, hierarchy as hierarchyApi } from '@/services/api';
import type { NotificationType } from '../Notification';
import { DrawerHeader, FocusedOrgView, OrgList, ConfirmModal, OrgDetailsModal, DrawerStageTabs } from './components';
import { useGlobalHierarchyScan } from '@/contexts/HierarchyScanContext';

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
    onEditEmployee?: (empId: string) => void;
    onSaveToPipedrive?: (person: any, orgId: number) => Promise<void> | void;
    onEmailDiscovered?: (person: any, email: string) => Promise<void> | void;
    onOrgDomainChanged?: (oldDomain: string, newDomain: string) => void;
    uniqueStages?: { name: string; count: number; order_nr?: number }[];
    activeStageFilter?: string | null;
    setActiveStageFilter?: (stage: string | null) => void;
    totalOrgsCount?: number;
    onNavigateToRoot?: () => void;
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
    onEditEmployee,
    onSaveToPipedrive,
    onOrgDomainChanged,
    uniqueStages = [],
    activeStageFilter = null,
    setActiveStageFilter = () => {},
    totalOrgsCount = 0,
    onNavigateToRoot,
}) => {
    const [expandedOrgId, setExpandedOrgIdState] = useState<number | null>(null);
    const scan = useGlobalHierarchyScan();

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

    const [orgDetails, setOrgDetails] = useState<Record<number, any>>({});
    const [loadingDetails, setLoadingDetails] = useState<Record<number, boolean>>({});
    
    const [activeTab, setActiveTabState] = useState<string>('activities');

    const setActiveTab = (tab: string) => {
        setActiveTabState(tab);
        if (typeof window !== 'undefined') {
            window.localStorage.setItem('drawer-active-tab', tab);
        }
    };

    // 🚀 Carregamento inicial de detalhes e estados no client-side para evitar hydration mismatch
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const saved = window.localStorage.getItem('drawer-expanded-org-id');
            const currentId = saved ? Number(saved) : null;
            if (currentId) {
                setExpandedOrgIdState(currentId);
                const cached = window.localStorage.getItem(`org-${currentId}-details`);
                if (cached) {
                    try {
                        setOrgDetails({ [currentId]: JSON.parse(cached) });
                    } catch {}
                }
                void fetchOrgDetails(currentId);
            }
            const savedTab = window.localStorage.getItem('drawer-active-tab');
            if (savedTab) {
                setActiveTabState(savedTab);
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const [editingNameOrgId, setEditingNameOrgId] = useState<number | null>(null);
    const [editingNameValue, setEditingNameValue] = useState<string>('');
    const [confirmKind, setConfirmKind] = useState<ConfirmKind>(null);
    const [confirmBusy, setConfirmBusy] = useState(false);
    const [showDetailsModal, setShowDetailsModal] = useState(false);
    const [scanningOrgId, setScanningOrgId] = useState<number | null>(null);

    const fetchedOrgsRef = useRef<Record<number, boolean>>({});

    const fetchOrgDetails = useCallback(async (orgId: number, force: boolean = false, background: boolean = false) => {
        if (!force && !background && fetchedOrgsRef.current[orgId]) return; // Já buscado nesta sessão

        if (!background) {
            setLoadingDetails(prev => ({ ...prev, [orgId]: true }));
        }
        let attempt = 0;
        const maxAttempts = 3;

        while (attempt < maxAttempts) {
            try {
                const data = await orgsApi.getOrganizationDetails(orgId);
                setOrgDetails(prev => ({ ...prev, [orgId]: data }));
                fetchedOrgsRef.current[orgId] = true;
                if (typeof window !== 'undefined') {
                    window.localStorage.setItem(`org-${orgId}-details`, JSON.stringify(data));
                }
                if (force) {
                    addNotification('success', 'Dados sincronizados com o Pipedrive.');
                }
                break; // Sucesso, sai do loop
            } catch (e: any) {
                const errMsg = e.message || e;
                if (typeof errMsg === 'string' && (errMsg.toLowerCase().includes('cooldown') || errMsg.toLowerCase().includes('rate limit'))) {
                    attempt++;
                    if (attempt < maxAttempts) {
                        console.warn(`Rate limit do Pipedrive atingido. Tentando novamente em 2.5s (Tentativa ${attempt}/${maxAttempts})...`);
                        await new Promise(res => setTimeout(res, 2500));
                        continue; // Tenta de novo
                    }
                }
                
                console.error('Erro ao carregar detalhes:', errMsg);
                if (force) {
                    const msg = (e as any)?.message || 'Erro ao sincronizar. Tente novamente.';
                    addNotification('error', msg);
                }
                break; // Outro erro ou limite de tentativas excedido, sai do loop
            }
        }
        if (!background) {
            setLoadingDetails(prev => ({ ...prev, [orgId]: false }));
        }
    }, [addNotification]);

    useEffect(() => {
        if (refreshDetailsTrigger > 0) {
            // Em nova varredura atualiza os detalhes em vez de fechar — silenciosamente (sem notificação)
            if (expandedOrgId) {
                void fetchOrgDetails(expandedOrgId, false, true);
            }
        }
    }, [refreshDetailsTrigger]);


    useEffect(() => {
        const handleTimelineChanged = () => {
            if (expandedOrgId) {
                // background=true, force=false: atualiza silenciosamente sem notificação
                void fetchOrgDetails(expandedOrgId, false, true);
            }
        };
        window.addEventListener('crm_timeline_changed', handleTimelineChanged);
        window.addEventListener('crm_task_completed', handleTimelineChanged);
        window.addEventListener('crm_task_uncompleted', handleTimelineChanged);
        return () => {
            window.removeEventListener('crm_timeline_changed', handleTimelineChanged);
            window.removeEventListener('crm_task_completed', handleTimelineChanged);
            window.removeEventListener('crm_task_uncompleted', handleTimelineChanged);
        };
    }, [expandedOrgId, fetchOrgDetails]);

    // Helpers para checar jobs ativos no localStorage
    const getDiscoveryJobOrgId = (): number | null => {
        if (typeof window === 'undefined') return null;
        try {
            for (let _i = 0; _i < window.localStorage.length; _i++) {
                const key = window.localStorage.key(_i);
                if (key && key.startsWith('active-discovery-job-')) {
                    const jobStr = window.localStorage.getItem(key);
                    if (jobStr) {
                        const parsed = JSON.parse(jobStr);
                        if (parsed && parsed.orgId) return Number(parsed.orgId);
                    }
                }
            }
        } catch {}
        return null;
    };

    const getLinkedinScanOrgId = (): number | null => {
        try {
            const scanStr = typeof window !== 'undefined' ? window.localStorage.getItem('active-linkedin-scan') : null;
            if (scanStr) {
                const parsed = JSON.parse(scanStr);
                if (parsed && parsed.orgId) return Number(parsed.orgId);
            }
        } catch {}
        return null;
    };

    // Mantém scanningOrgId baseado no localStorage (não no currentOrgId reativo do Zustand)
    // para que o indicador persista mesmo após sair da empresa
    useEffect(() => {
        const computeScanningId = (): number | null => {
            // Scan LinkedIn em andamento (in-memory hook)
            if (scan.isScanning && scan.scanOrgId) return scan.scanOrgId;
            // LinkedIn scan persistido (detecta reload)
            const linkedinOrgId = getLinkedinScanOrgId();
            if (linkedinOrgId) return linkedinOrgId;
            // Discovery job (IA) ativo no localStorage
            return getDiscoveryJobOrgId();
        };

        const updateScanningId = () => setScanningOrgId(computeScanningId());

        const handleFinished = () => {
            // Aguarda um tick para garantir que o localStorage já foi atualizado antes de re-checar
            setTimeout(updateScanningId, 300);
        };

        updateScanningId();

        // Eventos diretos (mais rápidos que polling)
        window.addEventListener('hierarchy_scan_started', updateScanningId);
        window.addEventListener('hierarchy_scan_done', handleFinished);
        window.addEventListener('hierarchy_job_finished', handleFinished);   // Discovery WS terminou
        window.addEventListener('hierarchy_scan_cancelled', handleFinished); // Cancelado pelo usuário

        // Polling de segurança a cada 5s — captura casos onde eventos não foram disparados (ex: reload)
        const pollingInterval = setInterval(updateScanningId, 5000);

        return () => {
            window.removeEventListener('hierarchy_scan_started', updateScanningId);
            window.removeEventListener('hierarchy_scan_done', handleFinished);
            window.removeEventListener('hierarchy_job_finished', handleFinished);
            window.removeEventListener('hierarchy_scan_cancelled', handleFinished);
            clearInterval(pollingInterval);
        };
    }, [scan.isScanning, scan.scanOrgId]);

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
            await orgsApi.updateOrganization(orgId, { name: editingNameValue.trim() });

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

    const handleUpdateOrg = async (orgId: number, data: Record<string, any>) => {
        try {
            const oldDomain = orgDetails[orgId]?.domain || orgDetails[orgId]?.org?.website || '';
            await orgsApi.updateOrganization(orgId, data);

            if (data.domain && oldDomain && data.domain !== oldDomain) {
                if (onOrgDomainChanged) {
                    onOrgDomainChanged(oldDomain, data.domain);
                }
            }

            // Atualizar no local state
            const updatedOrg = filteredOrgs.find(o => Number(o.id) === orgId);
            if (updatedOrg) {
                if (data.name !== undefined) updatedOrg.name = data.name;
                if (data.domain !== undefined) updatedOrg.domain = data.domain;
                if (data.address !== undefined) updatedOrg.address = data.address;
            }

            setOrgDetails(prev => {
                if (prev[orgId]) {
                    const existingOrg = prev[orgId].org || {};
                    return {
                        ...prev,
                        [orgId]: {
                            ...prev[orgId],
                            ...data,
                            org: {
                                ...existingOrg,
                                ...data,
                                website: data.domain !== undefined ? data.domain : existingOrg.website,
                                owner_name: data.owner_name !== undefined ? data.owner_name : existingOrg.owner_name
                            }
                        },
                    };
                }
                return prev;
            });

            if (data.name && onOrgRenamed) {
                onOrgRenamed(orgId, data.name);
            }

            // Recarregar os detalhes completos do Pipedrive/DB local
            await fetchOrgDetails(orgId, true);
        } catch (e: any) {
            console.error('Erro ao atualizar empresa:', e.message || e);
            addNotification('error', 'Erro ao atualizar informações da empresa.');
            throw e;
        }
    };

    const handleSaveToPipedrive = async (person: any, orgId: number) => {
        if (onSaveToPipedrive) {
            return onSaveToPipedrive(person, orgId);
        }
        
        addNotification('info', 'Salvando contato no Pipedrive...');
        try {
            const { organizations } = await import('@/services/api');
            let email = person.email;
            if (Array.isArray(email)) email = email[0]?.value;
            if (typeof email === 'string' && (!email.includes('@') || email.includes('Sem dados'))) {
                email = null;
            }
            if (!email) email = null;
            
            let phone = person.phone;
            if (Array.isArray(phone)) phone = phone[0]?.value;
            if (typeof phone === 'string' && (!/\d/.test(phone) || phone.includes('Sem dados'))) {
                phone = null;
            }
            if (!phone) phone = null;

            const res = await organizations.createPerson({
                name: person.name,
                email,
                phone,
                org_id: orgId
            });
            
            if (res.status === 'success' || res.data) {
                addNotification('success', 'Contato salvo com sucesso no Pipedrive!');
                setOrgDetails(prev => {
                    const current = prev[orgId];
                    if (!current) return prev;
                    const newPerson = res.data || {
                        id: `temp_${Date.now()}`,
                        name: person.name,
                        ...(email ? { email: [{ value: email, primary: true }] } : {}),
                        ...(phone ? { phone: [{ value: phone, primary: true }] } : {})
                    };
                    return {
                        ...prev,
                        [orgId]: {
                            ...current,
                            persons: [...(current.persons || []), newPerson]
                        }
                    };
                });
            } else {
                addNotification('error', 'Erro ao salvar contato no Pipedrive.');
            }
        } catch(e: any) {
            addNotification('error', e.message || 'Erro ao salvar contato no Pipedrive.');
            throw e;
        }
    };

    const handleUpdateInPipedrive = async (person: any, orgId: number) => {
        addNotification('info', 'Atualizando contato no Pipedrive...');
        try {
            const { organizations } = await import('@/services/api');
            let email = person.email;
            if (Array.isArray(email)) email = email[0]?.value;
            if (typeof email === 'string' && (!email.includes('@') || email.includes('Sem dados'))) {
                email = null;
            }
            if (!email) email = null;
            
            let phone = person.phone;
            if (Array.isArray(phone)) phone = phone[0]?.value;
            if (typeof phone === 'string' && (!/\d/.test(phone) || phone.includes('Sem dados'))) {
                phone = null;
            }
            if (!phone) phone = null;
            
            let personId = person.id;
            if (typeof personId === 'string' && (personId.startsWith('mapped_') || personId.startsWith('temp_'))) {
                 const pipedrivePerson = orgDetails[orgId]?.persons?.find((p: any) => p.name?.trim().toLowerCase() === person.name?.trim().toLowerCase());
                 if (pipedrivePerson) {
                     personId = pipedrivePerson.id;
                 }
            }

            const res = await organizations.updatePerson(personId, {
                name: person.name,
                email,
                phone
            });
            
            if (res.status === 'success') {
                addNotification('success', 'Contato atualizado no Pipedrive!');
                setOrgDetails(prev => {
                    const current = prev[orgId];
                    if (!current) return prev;
                    const updatedPersons = (current.persons || []).map((p: any) => 
                        p.id === personId ? { ...p, name: person.name, email: [{ value: email, primary: true }], phone: [{ value: phone, primary: true }] } : p
                    );
                    return { ...prev, [orgId]: { ...current, persons: updatedPersons } };
                });
            } else {
                addNotification('error', 'Erro ao atualizar contato.');
            }
        } catch(e: any) {
            addNotification('error', e.message || 'Erro ao atualizar contato.');
            throw e;
        }
    };

    const handleDeleteFromPipedrive = async (person: any, orgId: number) => {
        addNotification('info', 'Removendo contato do Pipedrive...');
        try {
            const { organizations } = await import('@/services/api');
            let personId = person.id;
            if (typeof personId === 'string' && (personId.startsWith('mapped_') || personId.startsWith('temp_'))) {
                 const pipedrivePerson = orgDetails[orgId]?.persons?.find((p: any) => p.name?.trim().toLowerCase() === person.name?.trim().toLowerCase());
                 if (pipedrivePerson) {
                     personId = pipedrivePerson.id;
                 }
            }

            const res = await organizations.deletePerson(personId);
            if (res.status === 'success') {
                addNotification('success', 'Contato removido do Pipedrive!');
                setOrgDetails(prev => {
                    const current = prev[orgId];
                    if (!current) return prev;
                    const updatedPersons = (current.persons || []).filter((p: any) => p.id !== personId);
                    return { ...prev, [orgId]: { ...current, persons: updatedPersons } };
                });
                
                // Se o contato tem emp_id, limpa o email no banco local também para não reaparecer no fallback
                if (person.emp_id) {
                    try {
                        await hierarchyApi.updateEmployeeDetails(person.emp_id, { email: null as any });
                        // Avisa o frontend para recarregar o grafo
                        window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
                    } catch (e) {
                        console.error("Erro ao limpar email local:", e);
                    }
                }
            } else {
                addNotification('error', 'Erro ao remover contato.');
            }
        } catch(e: any) {
            addNotification('error', e.message || 'Erro ao remover contato.');
            throw e;
        }
    };

    const handleSaveDiscoveredEmail = async (person: any, orgId: number, discoveredEmail: string) => {
        const contactName = person.name;

        addNotification('success', `E-mail salvo: ${discoveredEmail}`);

        // 1. Se o contato tem emp_id, atualiza no banco local de hierarquia!
        if (person.emp_id) {
            try {
                await hierarchyApi.updateEmployeeDetails(person.emp_id, {
                    email: discoveredEmail
                });
            } catch (err: any) {
                console.error("Erro ao salvar email no banco local:", err);
            }
        }

        // 2. Se está cadastrado no Pipedrive, atualiza o Pipedrive também!
        if (person.sources?.includes('pipedrive')) {
            try {
                await handleUpdateInPipedrive({ ...person, email: [{ value: discoveredEmail, primary: true, label: "verified" }] }, orgId);
            } catch (err: any) {
                console.error("Erro ao atualizar email no Pipedrive:", err);
            }
        }

                // 3. Atualiza no estado local do drawer para atualizar a tela instantaneamente
                setOrgDetails(prev => {
                    const current = prev[orgId];
                    if (!current) return prev;
                    
                    const updatedPersons = (current.persons || []).map((p: any) => {
                        const isTarget = p.id === person.id || (p.name && person.name && p.name.trim().toLowerCase() === person.name.trim().toLowerCase());
                        if (isTarget) {
                            return {
                                ...p,
                                email: [{ value: discoveredEmail, primary: true, label: "verified" }]
                            };
                        }
                        return p;
                    });

                    return {
                        ...prev,
                        [orgId]: {
                            ...current,
                            persons: updatedPersons
                        }
                    };
                });

                // 4. Dispara evento para sinalizar ao pai/sistema que a hierarquia mudou
                const changeEvent = new CustomEvent('crm_timeline_changed');
                window.dispatchEvent(changeEvent);
    };

    // Filtra a organização que está em foco
    const focusedOrg = expandedOrgId ? filteredOrgs.find(o => Number(o.id) === expandedOrgId) : null;

    return (
        <div className={`${styles.drawerWrapper} ${showDrawer ? styles.drawerWrapperOpen : styles.drawerWrapperClosed}`}>
        <div className={styles.drawerInner}>
            <DrawerHeader 
                expandedOrgId={expandedOrgId}
                setExpandedOrgId={setExpandedOrgId}
                searchTerm={searchTerm}
                setSearchTerm={setSearchTerm}
                setShowDrawer={setShowDrawer}
                fetchOrgDetails={fetchOrgDetails}
                loadingDetails={loadingDetails}
                setConfirmKind={setConfirmKind}
                onOpenDetailsModal={() => setShowDetailsModal(true)}
                onNavigateToRoot={onNavigateToRoot}
            />

            {!expandedOrgId && (
                <DrawerStageTabs
                    stages={uniqueStages}
                    activeStage={activeStageFilter}
                    onSelect={setActiveStageFilter}
                    totalCount={totalOrgsCount}
                />
            )}

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
                        handleUpdateOrg={handleUpdateOrg}
                        scanningOrgId={scanningOrgId}
                        selectedOrgId={selectedOrgId}
                        selectedOrgLogo={selectedOrgLogo}
                        graphEmployees={graphEmployees}
                        onEditEmployee={onEditEmployee}
                        onSaveToPipedrive={(person) => handleSaveToPipedrive(person, expandedOrgId!)}
                        onUpdateInPipedrive={(person) => handleUpdateInPipedrive(person, expandedOrgId!)}
                        onDeleteFromPipedrive={(person) => handleDeleteFromPipedrive(person, expandedOrgId!)}
                        onEmailDiscovered={(person, email) => handleSaveDiscoveredEmail(person, expandedOrgId!, email)}
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
                )                }
            </div>

            <ConfirmModal 
                confirmKind={confirmKind}
                confirmBusy={confirmBusy}
                setConfirmKind={setConfirmKind}
                performDelete={performDelete}
                performReset={performReset}
                expandedOrgId={expandedOrgId}
            />

            <OrgDetailsModal 
                isOpen={showDetailsModal}
                onClose={() => setShowDetailsModal(false)}
                expandedOrgId={expandedOrgId}
                orgDetails={orgDetails}
                focusedOrg={focusedOrg}
                handleUpdateOrg={handleUpdateOrg}
            />
        </div>
        </div>
    );
};

