"use client";

import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { useReactFlow, ReactFlowProvider } from 'reactflow';
import { PanelRight, PanelRightOpen, LogOut } from 'lucide-react';
import { getAvatarUrl, getProxiedUrl } from '../../utils/avatarUtils';

import { ConfirmModal } from '../ui/ConfirmModal';
import graphStyles from './styles/Graph.module.css';
import haStyles from './styles/HumanAnalysis.module.css';
import sidebarStyles from '../layout/Sidebar.module.css';
import headerStyles from '../layout/Header.module.css';

// Hooks
import { useHierarchy } from '@/hooks/useHierarchy';
import { useLocalStorage } from '@/hooks/useLocalStorage';
import { useProspecting } from '@/hooks/useProspecting';
import { useNetworkFlow } from '@/hooks/useNetworkFlow';
import { useGraphPersistence } from '@/hooks/useGraphPersistence';
import { useDiscoveryWorkflow } from '@/hooks/useDiscoveryWorkflow';
import { usePipedriveSync } from '@/hooks/usePipedriveSync';
import { useNotifications } from '@/contexts/NotificationContext';
import { NotificationContainer } from '../ui/Notification';

// Components
import { Sidebar } from '../layout/Sidebar';
import { ProspectingView } from '../prospecting/ProspectingView';
import { Header } from '../layout/Header';
import { Drawer } from '../ui/Drawer';
import { ChatPanel } from '../chat/ChatPanel';
import { WhatsAppView } from '../whatsapp/WhatsAppView';
import { PreferencesView } from '../layout/PreferencesView';
import { GraphCanvas } from './GraphCanvas';
import { DiscoveryWorkflowOverlay } from './DiscoveryWorkflowOverlay';
import { FloatingToolbar } from './FloatingToolbar';
import { SmartBackground } from './components/SmartBackground';
import { FitViewHandler } from './components/FitViewHandler';
import { TriggerNotifications } from '../ui/TriggerNotifications';
import { API_BASE_URL } from '@/services/config';

const styles = { ...graphStyles, ...haStyles, ...sidebarStyles, ...headerStyles };

const cleanName = (name: string) => {
    if (!name) return "";
    return name
        .replace(/\|?\s*Linked\s*In/gi, '') // Remove "| LinkedIn", "LinkedIn", "Linked In"
        .replace(/\(\s*LinkedIn\s*\)/gi, '') // Remove "(LinkedIn)"
        .trim();
};

const formatCnpj = (val: string) => {
    const s = val.replace(/\D/g, '').slice(0, 14);
    if (s.length <= 2) return s;
    if (s.length <= 5) return `${s.slice(0, 2)}.${s.slice(2)}`;
    if (s.length <= 8) return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5)}`;
    if (s.length <= 12) return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8)}`;
    return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`;
};

function NetworkGraphContent({ onLogout }: { onLogout?: () => void }) {
    const { addNotification, notifications, removeNotification } = useNotifications();
    const { saveGraphState, getStableId } = useGraphPersistence();
    const [theme, setTheme] = useState("dark");
    const [currentOrgId, setCurrentOrgId] = useState<number | null>(null);
    const [chatOrgId, setChatOrgId] = useState<number | null>(null);
    const [prospectHoveredLeadId, setProspectHoveredLeadId] = useState<string | null>(null);
    const hasAttemptedReconnect = useRef(false);

    // CRM Sync
    const {
        pipedriveOrgs, setPipedriveOrgs, searchTerm, setSearchTerm,
        loadingOrgs, filteredOrgs, fetchPipedriveOrgs, handleOrgRenamed
    } = usePipedriveSync();

    // Hierarchy Data
    const hierarchy = useHierarchy();
    const {
        rawEmployees, rawBackendEdges, loading, discovering, brandOptions, setBrandOptions,
        activeJobId, stopHierarchyScan, cancelDiscovery, resetHierarchy,
        reconnectToActiveJob, approveCandidate, refineHierarchy, smartSyncPipedrive,
        loadStoredHierarchy
    } = hierarchy;

    // Discovery Workflow
    const discovery = useDiscoveryWorkflow({
        useHierarchy: hierarchy,
        currentOrgId,
        setCurrentOrgId,
        setChatOrgId,
        rawEmployees,
        fetchPipedriveOrgs,
        setPipedriveOrgs
    });

    const {
        step, setStep, cnpj, setCnpj, domainTarget, setDomainTarget,
        productFocus, setProductFocus, areaFocus, setAreaFocus,
        confirmedBrand, setConfirmedBrand, confirmedLogo, setConfirmedLogo,
        confirmedFollowers, setConfirmedFollowers, refreshDrawerTrigger, setRefreshDrawerTrigger,
        enrichingIds, handleSearch, handleBrandSelect, handleAutoEnrich, resetWorkflow
    } = discovery;

    // Network Flow
    const {
        nodes, setNodes, edges, setEdges,
        onNodesChange, onEdgesChange, onConnect,
        shouldFitView, setShouldFitView
    } = useNetworkFlow({
        rawEmployees,
        rawBackendEdges,
        currentOrgId,
        confirmedBrand,
        confirmedLogo,
        getStableId
    });

    // UI States
    const [showDrawer, setShowDrawer] = useState(false);
    const [showChat, setShowChat] = useState(false);
    const [activeView, setActiveView] = useLocalStorage<'graph' | 'whatsapp' | 'prospecting' | 'preferences'>('active-view', 'graph');
    const [activeChatInfo, setActiveChatInfo] = useLocalStorage<{ name: string, id?: string } | null>('active-chat-info', null);
    const prospecting = useProspecting();
    const [confirmModal, setConfirmModal] = useState<{ isOpen: boolean, empId: string | null }>({ isOpen: false, empId: null });

    // Sync UI states to localStorage
    useEffect(() => {
        const savedDrawer = localStorage.getItem("show-drawer") === "true";
        const savedChat = localStorage.getItem("show-chat") === "true";
        setShowDrawer(savedDrawer);
        setShowChat(savedChat);
    }, []);

    const handleSetShowDrawer = (val: boolean) => {
        setShowDrawer(val);
        localStorage.setItem("show-drawer", val.toString());
    };

    const handleSetShowChat = (val: boolean) => {
        setShowChat(val);
        localStorage.setItem("show-chat", val.toString());
    };

    // Persistence & Theme
    useEffect(() => {
        if (nodes.length > 0) saveGraphState(nodes, edges);
    }, [nodes, edges, saveGraphState]);

    useEffect(() => {
        const savedTheme = localStorage.getItem("preferred-theme") || "dark";
        setTheme(savedTheme);
        document.documentElement.setAttribute("data-theme", savedTheme);
    }, []);

    // Reconnection & Initial Load logic
    useEffect(() => {
        if (hasAttemptedReconnect.current) return;
        hasAttemptedReconnect.current = true;

        const checkLastOrg = async () => {
            const lastOrgStr = localStorage.getItem('last-viewed-org');
            if (lastOrgStr) {
                if (lastOrgStr === "NaN" || lastOrgStr === "undefined") {
                    localStorage.removeItem('last-viewed-org');
                    setConfirmedBrand("");
                    setStep("input");
                    return;
                }
                try {
                    const org = JSON.parse(lastOrgStr);
                    const cleanOrgName = org.name || "";
                    setConfirmedBrand(cleanOrgName);
                    setConfirmedLogo(org.logo || "");

                    let targetCnpj = org.cnpj || "";
                    const onlyNums = targetCnpj.replace(/\D/g, '');
                    if (onlyNums.length >= 5) {
                        setCnpj(formatCnpj(targetCnpj));
                    }
                    setDomainTarget(org.domain || "");
                    setCurrentOrgId(Number(org.id));
                    setChatOrgId(Number(org.id));

                    if (org.id) {
                        const data = await loadStoredHierarchy(Number(org.id), true);
                        if (data && data.nodes && data.nodes.length > 0) {
                            setStep("confirm");
                            setTimeout(() => setShouldFitView(true), 100);
                        } else {
                            setStep("input");
                        }
                    } else {
                        setStep("input");
                    }
                } catch (e) {
                    console.error("[Last Org Check] Erro ao verificar last-viewed-org:", e);
                    setConfirmedBrand("");
                    setStep("input");
                }
            } else {
                setConfirmedBrand("");
                setStep("input");
            }
        };

        const checkActiveJob = async () => {
            const jobDataStr = localStorage.getItem('active-discovery-job');
            if (jobDataStr && jobDataStr !== "NaN" && jobDataStr !== "undefined") {
                try {
                    const jobData = JSON.parse(jobDataStr);
                    const { job_id, brand, logo, domain, orgId } = jobData;
                    console.log(`[Job Check] Detectado Job Ativo para ${brand}. Carregando dados prévios...`);

                    if (orgId) {
                        const data = await loadStoredHierarchy(Number(orgId), true);
                        if (data && data.nodes && data.nodes.length > 0) {
                            console.log(`[Job Check] ${data.nodes.length} nós restaurados do banco.`);
                        }
                    }

                    setStep("scanning");
                    setConfirmedBrand(brand);
                    if (orgId) {
                        setCurrentOrgId(orgId);
                        setChatOrgId(orgId);
                    }

                    const reconnected = await reconnectToActiveJob(addNotification);
                    if (!reconnected) {
                        console.warn("[Job Check] Job expirou no backend.");
                        setStep("confirm");
                    }
                } catch (e) {
                    console.error("[Job Check] Erro", e);
                    checkLastOrg();
                }
            } else {
                checkLastOrg();
            }
        };

        checkActiveJob();
    }, [
        reconnectToActiveJob, addNotification, setStep, setConfirmedBrand, setConfirmedLogo,
        setCnpj, setDomainTarget, setCurrentOrgId, setChatOrgId, loadStoredHierarchy, setShouldFitView
    ]);

    // Handlers
    const handleOrgClick = useCallback(async (org: any, openChat = false) => {
        setActiveView('graph');
        if (openChat) handleSetShowChat(true);
        resetHierarchy();
        setNodes([]);
        setEdges([]);
        setCurrentOrgId(Number(org.id));
        if (openChat) setChatOrgId(Number(org.id));
        localStorage.setItem('last-viewed-org', JSON.stringify(org));
        
        // Reset total de estados antes de carregar a nova empresa
        setStep("input");
        setCnpj("");
        setDomainTarget("");
        setConfirmedBrand("");
        setConfirmedLogo("");
        setBrandOptions([]);

        try {
            if (org.id) {
                // 1. CHECAR SE EXISTE JOB ATIVO NESTA EMPRESA
                const jobDataStr = localStorage.getItem('active-discovery-job');
                if (jobDataStr) {
                    try {
                        const jobData = JSON.parse(jobDataStr);
                        if (Number(jobData.orgId) === Number(org.id)) {
                            setStep("loading");
                            const reconnected = await reconnectToActiveJob(addNotification);
                            if (reconnected) {
                                return;
                            } else {
                                setStep("initial");
                            }
                        }
                    } catch (e) {
                        console.error("[Job Check] Erro de parse no jobData", e);
                    }
                }

                // 2. SE NÃO TIVER JOB ATIVO, CARREGA OS DADOS SALVOS NORMALMENTE
                console.log('Attempting to load hierarchy for pipedrive_id:', org.id);
                const data = await loadStoredHierarchy(Number(org.id), true);
                const hasNodes = data && data.nodes && data.nodes.length > 0;
                const isProspecting = org.source === "prospecting";

                if (hasNodes) {
                    setConfirmedBrand(cleanName(org.name || ""));
                    setConfirmedLogo(org.logo || "");
                    setCnpj(formatCnpj(org.cnpj || ""));
                    setDomainTarget(org.domain || "");
                    setStep("confirm");
                    setShouldFitView(true);
                } else if (isProspecting && (org.domain || org.linkedin || org.linkedin_url)) {
                    setConfirmedBrand(cleanName(org.name || ""));
                    setConfirmedLogo(org.logo || "");
                    setCnpj(formatCnpj(org.cnpj || ""));
                    setDomainTarget(org.domain || "");
                    setStep("confirm");
                } else {
                    setConfirmedBrand(cleanName(org.name || ""));
                    setConfirmedLogo(org.logo || "");
                    setStep("input");
                }

                if (org.product_focus) setProductFocus(org.product_focus);
                if (org.category === "compras" || org.category === "logistica") setAreaFocus(org.category);
            }
        } catch (e) {
            console.error("Critical error in handleOrgClick:", e);
        }
    }, [
        resetHierarchy, setNodes, setEdges, setActiveView, setStep, setCnpj, setDomainTarget,
        setConfirmedBrand, setConfirmedLogo, setBrandOptions, reconnectToActiveJob, addNotification,
        loadStoredHierarchy, setProductFocus, setAreaFocus, setShouldFitView
    ]);

    const handleOrgReset = useCallback((orgId: number) => {
        console.log(`[Graph] Resetando UI para organização ${orgId}...`);
        setPipedriveOrgs(prev => prev.filter(org => Number(org.id) !== orgId && Number(org.local_id) !== orgId));
        setNodes([]);
        setEdges([]);
        resetWorkflow();
        resetHierarchy();
    }, [setPipedriveOrgs, setNodes, setEdges, resetWorkflow, resetHierarchy]);

    const handleNewCompany = useCallback(() => {
        // Abre o drawer e garante que ele volte para a lista (limpando cache de expansão)
        handleSetShowDrawer(true);
        localStorage.removeItem('drawer-expanded-org-id');
        
        // Notifica o Drawer para resetar o estado interno de expansão
        window.dispatchEvent(new CustomEvent('drawer_reset_expansion'));
        
        setActiveView('graph');
        setNodes([]);
        setEdges([]);
        resetWorkflow();
        resetHierarchy();
    }, [setActiveView, setNodes, setEdges, resetWorkflow, resetHierarchy]);

    return (
        <div className={styles.container} data-theme={theme}>
            
            <Sidebar
                showDrawer={showDrawer}
                setShowDrawer={handleSetShowDrawer}
                theme={theme}
                onToggleTheme={() => {
                    const newTheme = theme === "dark" ? "light" : "dark";
                    setTheme(newTheme);
                    localStorage.setItem("preferred-theme", newTheme);
                    document.documentElement.setAttribute("data-theme", newTheme);
                }}
                onReset={handleNewCompany}
                onCopyData={() => {
                    const data = { nodes, edges };
                    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
                    addNotification('info', "Dados do grafo copiados!");
                }}
                onRefine={() => {
                    if (localStorage.getItem('active-discovery-job')) {
                        addNotification('warning', "Aguarde o mapeamento atual terminar antes de utilizar o Analista de IA.");
                        return;
                    }
                    refineHierarchy(rawEmployees);
                }}
                onSmartSync={async () => {
                    const res = await smartSyncPipedrive();
                    if (res && res.status === 'success') {
                        addNotification('success', "Sincronização com Pipedrive concluída!");
                        fetchPipedriveOrgs(); // Refresh the list
                    }
                }}
                onOpenProspecting={() => setActiveView(activeView === 'prospecting' ? 'graph' : 'prospecting')}
                isProspecting={activeView === 'prospecting'}
                onOpenPreferences={() => setActiveView(activeView === 'preferences' ? 'graph' : 'preferences')}
                isPreferences={activeView === 'preferences'}
            />

            <div className={styles.mainWrapper}>
                <header className={styles.globalHeader}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className={styles.globalHeaderTitle}>LINKB2B Hierarchy Mapper</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: 'auto' }}>
                        <TriggerNotifications
                            apiBase={API_BASE_URL}
                            onOpenChat={(orgId, orgName) => {
                                handleOrgClick({ id: orgId, name: orgName }, true);
                            }}
                        />
                        {(activeView === 'graph' || activeView === 'prospecting') && (
                            <button
                                onClick={() => handleSetShowChat(!showChat)}
                                className={`${styles.navIcon}`}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    cursor: 'pointer',
                                    padding: '8px',
                                    borderRadius: '8px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    color: showChat ? 'var(--sw-text-base)' : 'var(--sw-text-muted)'
                                }}
                                title={showChat ? "Fechar Assistente" : "Abrir Assistente"}
                            >
                                {showChat ? <PanelRightOpen size={20} /> : <PanelRight size={20} />}
                            </button>
                        )}
                        {onLogout && (
                            <button
                                onClick={onLogout}
                                className={`${styles.navIcon}`}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    cursor: 'pointer',
                                    padding: '8px',
                                    borderRadius: '8px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    color: 'var(--sw-text-muted)',
                                    transition: 'all 0.2s ease',
                                }}
                                onMouseEnter={(e) => {
                                    e.currentTarget.style.color = '#f87171';
                                    e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)';
                                }}
                                onMouseLeave={(e) => {
                                    e.currentTarget.style.color = 'var(--sw-text-muted)';
                                    e.currentTarget.style.background = 'transparent';
                                }}
                                title="Sair da Conta"
                            >
                                <LogOut size={20} />
                            </button>
                        )}
                    </div>
                </header>

                <div className={styles.contentWrapper}>
                    <Drawer
                        showDrawer={showDrawer}
                        setShowDrawer={handleSetShowDrawer}
                        filteredOrgs={filteredOrgs}
                        isLoading={loadingOrgs}
                        searchTerm={searchTerm}
                        setSearchTerm={setSearchTerm}
                        onOrgClick={handleOrgClick}
                        selectedOrgId={currentOrgId}
                        onOrgRenamed={handleOrgRenamed}
                        selectedOrgLogo={confirmedLogo}
                        activeJobId={activeJobId}
                        graphEmployees={rawEmployees}
                        refreshDetailsTrigger={refreshDrawerTrigger}
                        addNotification={addNotification}
                        onOrgReset={handleOrgReset}
                    />

                    <div className={styles.mainContent}>
                        <NotificationContainer notifications={notifications} removeNotification={removeNotification} />
                        <Header
                            confirmedBrand={confirmedBrand}
                        />

                        <div className={styles.graphWrapper}>
                            {activeView === 'graph' && (
                                <>
                                    <GraphCanvas
                                        nodes={nodes}
                                        edges={edges}
                                        onNodesChange={onNodesChange}
                                        onEdgesChange={onEdgesChange}
                                        onConnect={onConnect}
                                        fitViewHandler={<FitViewHandler shouldFitView={shouldFitView} nodes={nodes} />}
                                        smartBackground={<SmartBackground />}
                                    />
                                    
                                    <DiscoveryWorkflowOverlay
                                        error={null}
                                        handleSearch={handleSearch}
                                        cnpj={cnpj}
                                        setCnpj={setCnpj}
                                        confirmedBrand={confirmedBrand}
                                        setConfirmedBrand={setConfirmedBrand}
                                        confirmedLogo={confirmedLogo}
                                        setConfirmedLogo={setConfirmedLogo}
                                        confirmedFollowers={confirmedFollowers}
                                        setConfirmedFollowers={setConfirmedFollowers}
                                        domainTarget={domainTarget}
                                        setDomainTarget={setDomainTarget}
                                        productFocus={productFocus}
                                        setProductFocus={setProductFocus}
                                        areaFocus={areaFocus}
                                        setAreaFocus={setAreaFocus}
                                        handleAutoEnrich={handleAutoEnrich}
                                        enrichingIds={enrichingIds}
                                        discovering={discovering}
                                        loading={loading}
                                        step={step}
                                        brandOptions={brandOptions}
                                        onBrandSelect={handleBrandSelect}
                                        hasMapping={nodes.length > 0}
                                        stopHierarchyScan={() => stopHierarchyScan(addNotification)}
                                        cancelDiscovery={cancelDiscovery}
                                        activeJobId={activeJobId}
                                        showDrawer={showDrawer}
                                        showChat={showChat}
                                        approveCandidate={async (id) => {
                                            await approveCandidate(id);
                                            addNotification('success', "Perfil aprovado.");
                                        }}
                                        rejectCandidate={(id) => setConfirmModal({ isOpen: true, empId: id })}
                                        humanAnalysisContent={(() => {
                                            const pending = rawEmployees.filter(e => e.role === 'Análise Humana');
                                            if (pending.length === 0) return null;
                                            const layerClasses = [styles.stackLayer0, styles.stackLayer1, styles.stackLayer2];
                                            return (
                                                <div
                                                    className={styles.humanAnalysisTrigger}
                                                    onClick={() => {
                                                        const isShowing = brandOptions.length > 0 && brandOptions[0]?.type === 'person';
                                                        if (isShowing) { setBrandOptions([]); return; }
                                                        setBrandOptions(pending.map(p => ({
                                                            name: p.name, logo: getAvatarUrl(p), followers: p.department || 'Pendente',
                                                            type: 'person', id: p.id, originalEmployee: p
                                                        })));
                                                    }}
                                                >
                                                    <div className={styles.humanAnalysisAvatarStack}>
                                                        <div className={styles.humanAnalysisNotification}>
                                                            {pending.length}
                                                        </div>
                                                        {pending.slice(0, 3).map((p, i) => {
                                                            const avatarUrl = getAvatarUrl(p);
                                                            return (
                                                                <div
                                                                    key={p.id}
                                                                    className={`${styles.humanAnalysisStackedAvatar} ${layerClasses[i]}`}
                                                                >
                                                                    <img
                                                                        src={avatarUrl || '/imagem_linkedin.png'}
                                                                        alt={p.name}
                                                                        style={{ width: '100%', height: '100%', objectFit: 'cover', transform: avatarUrl ? 'none' : 'scale(1.6)' }}
                                                                        onError={(e) => {
                                                                             const img = e.currentTarget as HTMLImageElement;
                                                                             img.src = '/imagem_linkedin.png';
                                                                             img.style.transform = 'scale(1.6)';
                                                                        }}
                                                                    />
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    />
                                </>
                            )}

                            {activeView === 'whatsapp' && (
                                <WhatsAppView 
                                    chatName={activeChatInfo?.name || "WhatsApp"} 
                                    chatId={activeChatInfo?.id}
                                    onBack={() => setActiveView('graph')}
                                    theme={theme}
                                />
                            )}
                            {activeView === 'prospecting' && (
                                <>
                                    <ProspectingView
                                        coords={prospecting.coords}
                                        onMapClick={prospecting.setCoords}
                                        radiusKm={prospecting.radiusKm}
                                        leads={prospecting.leads}
                                        selectedLead={prospecting.selectedLead}
                                        onLeadClick={(lead) => {
                                            prospecting.setSelectedLead(lead);
                                        }}
                                        onLeadClose={() => prospecting.setSelectedLead(null)}
                                        onApproveLead={prospecting.approveLead}
                                        onRejectLead={prospecting.rejectLead}
                                        session={prospecting.session}
                                    />
                                    <div className={styles.bottomToolbarRow}>
                                        <FloatingToolbar
                                            error={null}
                                            handleSearch={() => {}}
                                            cnpj=""
                                            setCnpj={() => {}}
                                            confirmedBrand=""
                                            setConfirmedBrand={() => {}}
                                            confirmedLogo=""
                                            setConfirmedLogo={() => {}}
                                            confirmedFollowers=""
                                            setConfirmedFollowers={() => {}}
                                            domainTarget=""
                                            setDomainTarget={() => {}}
                                            productFocus=""
                                            setProductFocus={() => {}}
                                            areaFocus="compras"
                                            setAreaFocus={() => {}}
                                            handleAutoEnrich={() => {}}
                                            enrichingIds={new Set()}
                                            discovering={false}
                                            loading={false}
                                            step="initial"
                                            brandOptions={[]}
                                            onBrandSelect={() => {}}
                                            isSidebarOpen={showDrawer}
                                            isChatOpen={showChat}
                                            
                                            // Modo Prospecção
                                            isProspectingMode={true}
                                            prospectCoords={prospecting.coords}
                                            prospectRadiusKm={prospecting.radiusKm}
                                            onProspectRadiusChange={prospecting.setRadiusKm}
                                            onProspectGeolocate={prospecting.geolocate}
                                            prospectGeoLoading={prospecting.geoLoading}
                                            onProspectSearch={prospecting.startSearch}
                                            onProspectStop={prospecting.stopSearch}
                                            prospectSearching={prospecting.searching}
                                            prospectSession={prospecting.session}
                                            prospectLeadsCount={prospecting.leads.length}
                                            prospectTierACount={prospecting.leads.filter(l => l.icp_tier === 'A').length}
                                            prospectError={prospecting.error}
                                            prospectCityName={prospecting.cityName}
                                            onProspectCepLookup={prospecting.lookupCep}
                                            prospectSelectedLead={prospecting.selectedLead}
                                            prospectPendingLeads={prospecting.leads.filter(l => l.status === 'pending')}
                                            onProspectSelectLead={prospecting.setSelectedLead}
                                            onProspectApproveLead={prospecting.approveLead}
                                            onProspectRejectLead={prospecting.rejectLead}
                                            onProspectCloseLead={() => prospecting.setSelectedLead(null)}
                                            prospectCep={prospecting.cep}
                                            onProspectCepChange={prospecting.setCep}
                                        />
                                    </div>
                                </>
                            )}
                            {activeView === 'preferences' && (
                                <PreferencesView onBack={() => setActiveView('graph')} />
                            )}
                        </div>
                    </div>

                    {showChat && (activeView === 'graph' || activeView === 'prospecting') && (
                        <ChatPanel
                            showChat={showChat}
                            setShowChat={handleSetShowChat}
                            selectedOrgId={currentOrgId}
                            selectedOrgName={confirmedBrand || pipedriveOrgs.find(o => Number(o.id) === currentOrgId)?.name || "Empresa"}
                            theme={theme}
                            onToggleTheme={() => {
                                const newTheme = theme === "dark" ? "light" : "dark";
                                setTheme(newTheme);
                                localStorage.setItem("preferred-theme", newTheme);
                                document.documentElement.setAttribute("data-theme", newTheme);
                            }}
                            selectedOrgLogo={confirmedLogo || pipedriveOrgs.find(o => Number(o.id) === currentOrgId)?.logo || ""}
                        />
                    )}
                </div>
            </div>

            <ConfirmModal
                isOpen={confirmModal.isOpen}
                onCancel={() => setConfirmModal({ isOpen: false, empId: null })}
                onConfirm={async () => {
                    if (confirmModal.empId) {
                        await hierarchy.rejectCandidate(confirmModal.empId);
                        addNotification('info', "Perfil descartado.");
                    }
                    setConfirmModal({ isOpen: false, empId: null });
                }}
                title="Descartar Perfil"
                message="Tem certeza que deseja remover este perfil da análise humana?"
            />
        </div>
    );
}

export default function NetworkGraph(props: any) {
    return (
        <ReactFlowProvider>
            <NetworkGraphContent {...props} />
        </ReactFlowProvider>
    );
}
