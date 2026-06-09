import React, { useState, useRef, useEffect, useCallback } from 'react';
import styles from './Drawer.module.css';
import { Spinner } from '../';
import { organizations as orgsApi, hierarchy as hierarchyApi } from '@/services/api';
import type { NotificationType } from '../Notification';
import { DrawerHeader, FocusedOrgView, OrgList, ConfirmModal, OrgDetailsModal } from './components';

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
    onOrgDomainChanged?: (oldDomain: string, newDomain: string) => void;
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
    const [confirmBusy, setConfirmBusy] = useState(false);
    const [showDetailsModal, setShowDetailsModal] = useState(false);
    const [scanningOrgId, setScanningOrgId] = useState<number | null>(null);

    const fetchedOrgsRef = useRef<Record<number, boolean>>({});

    const fetchOrgDetails = useCallback(async (orgId: number, force: boolean = false) => {
        if (!force && fetchedOrgsRef.current[orgId]) return; // Já buscado nesta sessão

        setLoadingDetails(prev => ({ ...prev, [orgId]: true }));
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
        setLoadingDetails(prev => ({ ...prev, [orgId]: false }));
    }, [addNotification]);

    useEffect(() => {
        if (refreshDetailsTrigger > 0) {
            // Em nova varredura atualiza os detalhes em vez de fechar
            if (expandedOrgId) {
                void fetchOrgDetails(expandedOrgId, true);
            }
        }
    }, [refreshDetailsTrigger]);

    useEffect(() => {
        const handleTimelineChanged = () => {
            if (expandedOrgId) {
                void fetchOrgDetails(expandedOrgId, true);
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
            } else {
                addNotification('error', 'Erro ao remover contato.');
            }
        } catch(e: any) {
            addNotification('error', e.message || 'Erro ao remover contato.');
            throw e;
        }
    };

    const handleDiscoverEmail = async (person: any, orgId: number) => {
        const contactName = person.name;
        const orgName = focusedOrg?.name || '';
        const domain = focusedOrg?.domain || orgDetails[orgId]?.domain || orgDetails[orgId]?.org?.website || '';

        addNotification('info', `Buscando e-mail profissional para ${contactName}...`);
        try {
            const res = await hierarchyApi.discoverEmail({
                contact_name: contactName,
                org_name: orgName,
                domain: domain || undefined
            });

            if (res.ok && res.recommended) {
                addNotification('success', `E-mail descoberto: ${res.recommended}`);

                // 1. Se o contato tem emp_id, atualiza no banco local de hierarquia!
                if (person.emp_id) {
                    try {
                        await hierarchyApi.updateEmployeeDetails(person.emp_id, {
                            email: res.recommended
                        });
                    } catch (err: any) {
                        console.error("Erro ao salvar email no banco local:", err);
                    }
                }

                // 2. Se está cadastrado no Pipedrive, atualiza o Pipedrive também!
                if (person.sources?.includes('pipedrive')) {
                    try {
                        await handleUpdateInPipedrive({ ...person, email: [{ value: res.recommended, primary: true }] }, orgId);
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
                                email: [{ value: res.recommended, primary: true }]
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
            } else {
                addNotification('error', res.error || `Não foi possível encontrar um e-mail válido para ${contactName}.`);
            }
        } catch (e: any) {
            console.error('Erro ao descobrir e-mail:', e);
            addNotification('error', e.message || 'Erro ao processar descoberta de e-mail.');
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
                onOpenDetailsModal={() => setShowDetailsModal(true)}
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
                        handleUpdateOrg={handleUpdateOrg}
                        scanningOrgId={scanningOrgId}
                        selectedOrgId={selectedOrgId}
                        selectedOrgLogo={selectedOrgLogo}
                        graphEmployees={graphEmployees}
                        onEditEmployee={onEditEmployee}
                        onSaveToPipedrive={(person) => handleSaveToPipedrive(person, expandedOrgId!)}
                        onUpdateInPipedrive={(person) => handleUpdateInPipedrive(person, expandedOrgId!)}
                        onDeleteFromPipedrive={(person) => handleDeleteFromPipedrive(person, expandedOrgId!)}
                        onDiscoverEmail={(person) => handleDiscoverEmail(person, expandedOrgId!)}
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
    );
};

