"use client";

import React, { useEffect, useState, useMemo, useRef, useCallback, startTransition } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useReactFlow, ReactFlowProvider } from 'reactflow';
import { PanelRight, PanelRightOpen, LogOut } from 'lucide-react';
import { getAvatarUrl, getProxiedUrl } from '../../utils/avatarUtils';

import { ConfirmModal } from '../ui/ConfirmModal';
import { MessagesView } from '../messages/MessagesView';
import { LigacaoView } from '../ligacao/LigacaoView';
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
import { apiGet } from '../../services/config';
import { Avatar } from '../ui';
import { ChatPanel } from '../chat/ChatPanel';
import { PreferencesView } from '../layout/PreferencesView';
import { HierarchyScanView } from '../hierarchy-scan/HierarchyScanView';
import { GraphCanvas } from './GraphCanvas';
import { HierarchyDiscoveryOverlay } from './HierarchyDiscoveryOverlay';
import { NetworkGraphLayout } from './NetworkGraphLayout';
import { useChatStore } from '@/store/chatStore';
import { FloatingToolbar } from './FloatingToolbar';
import { SmartBackground } from './components/SmartBackground';
import { FitViewHandler } from './components/FitViewHandler';
import { ModelSelector } from '../chat/ModelSelector';
import { useGlobalHierarchyScan } from '@/contexts/HierarchyScanContext';
import { ScanTerminalPanel } from './components/ScanTerminalPanel';
import { ScanPreviewBubble } from './components/ScanPreviewBubble';
import { TriggerNotifications } from '../ui/TriggerNotifications';
import { API_BASE_URL } from '@/services/config';
import { EmployeeDetailsModal } from './components/EmployeeDetailsModal';

const styles = { ...graphStyles, ...haStyles, ...sidebarStyles, ...headerStyles };

import { useRouterSync } from '@/hooks/useRouterSync';

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

function NetworkGraphContent({ 
    onLogout, 
    currentUser, 
    tasksForToday, 
    onToggleChat 
}: { 
    onLogout?: () => void;
    currentUser?: { name: string; avatar: string | null } | null;
    tasksForToday?: number;
    onToggleChat?: () => void;
}) {
    const pathname = usePathname() || '/';
    const router = useRouter();
    const searchParams = useSearchParams();

    const { addNotification, notifications, removeNotification } = useNotifications();
    const { saveGraphState, getStableId } = useGraphPersistence();
    const [theme, setTheme] = useState("dark");
    const [currentOrgId, setCurrentOrgId] = useState<number | null>(null);
    const [chatOrgId, setChatOrgId] = useState<number | null>(null);
    const [prospectHoveredLeadId, setProspectHoveredLeadId] = useState<string | null>(null);
    const hasAttemptedReconnect = useRef(false);
    const currentPathRef = useRef(pathname);
    currentPathRef.current = pathname;

    // CRM Sync
    const {
        pipedriveOrgs, setPipedriveOrgs, searchTerm, setSearchTerm,
        loadingOrgs, taskSummary, filteredOrgs, fetchPipedriveOrgs, handleOrgRenamed,
        uniqueStages, activeStageFilter, setActiveStageFilter
    } = usePipedriveSync();

    // Hierarchy Data
    const hierarchy = useHierarchy();
    const {
        rawEmployees, rawBackendEdges, discovering, brandOptions, setBrandOptions,
        activeJobId, stopHierarchyScan, cancelDiscovery, resetHierarchy,
        reconnectToActiveJob, approveCandidate, refineHierarchy, smartSyncPipedrive,
        deleteEmployee
    } = hierarchy;

    useEffect(() => {
        // Evita disparar contagem zerada enquanto as orgs ainda estão carregando (ex: navegação entre páginas)
        if (loadingOrgs && pipedriveOrgs.length === 0) return;

        const brToday = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Sao_Paulo' });
        let count = 0;
        pipedriveOrgs.forEach((org: any) => {
            const summary = taskSummary[Number(org.id)];
            if (summary && !summary.overdue_count && summary.next_due_date === brToday) {
                count++;
            }
        });
        window.dispatchEvent(new CustomEvent('update_tasks_today', { detail: count }));
    }, [pipedriveOrgs, taskSummary, loadingOrgs]);

    // Discovery Workflow
    const discovery = useDiscoveryWorkflow({
        useHierarchy: hierarchy,
        currentOrgId,
        setCurrentOrgId,
        setChatOrgId,
        rawEmployees,
        fetchPipedriveOrgs,
        setPipedriveOrgs,
        pathname
    });

    const {
        step, setStep, cnpj, setCnpj, domainTarget, setDomainTarget,
        productFocus, setProductFocus, areaFocus, setAreaFocus,
        confirmedBrand, setConfirmedBrand, confirmedLogo, setConfirmedLogo,
        confirmedFollowers, setConfirmedFollowers, refreshDrawerTrigger, setRefreshDrawerTrigger,
        enrichingIds, handleSearch, handleBrandSelect, handleAutoEnrich, resetWorkflow,
        selectedModel, setSelectedModel, strictMode, setStrictMode,
        mappingMode, setMappingMode, confirmedLinkedInUrl, setConfirmedLinkedInUrl, partners
    } = discovery;

    // HierarchyScan Integration
    const scan = useGlobalHierarchyScan();
    // Estado de scan isolado para a empresa atual — persiste independente de outras empresas sendo escaneadas
    const currentScanState = scan.getScanState(currentOrgId ?? 0);
    const isScanForCurrentOrg = currentScanState.isScanning;
    const [previewExpanded, setPreviewExpanded] = useState(false);

    // scopedScan: adapter com API flat para os componentes filhos (NetworkGraphLayout).
    // Encapsula as chamadas multi-org, expondo apenas o escopo da empresa atual.
    const scopedScan = useMemo(() => ({
        ...currentScanState,
        startScan: scan.startScan,
        stopScan: () => { if (currentOrgId) scan.stopScan(currentOrgId); },
        handleImageClick: (e: React.MouseEvent<HTMLImageElement>) => { if (currentOrgId) scan.handleImageClick(currentOrgId, e); },
        sendText: (text: string) => { if (currentOrgId) scan.sendText(currentOrgId, text); },
        pressEnter: () => { if (currentOrgId) scan.pressEnter(currentOrgId); },
        pressBackspace: () => { if (currentOrgId) scan.pressBackspace(currentOrgId); },
        resetScan: () => { if (currentOrgId) scan.resetScan(currentOrgId); },
        scanOrgId: currentOrgId ?? null,
    }), [currentScanState, scan, currentOrgId]);

    // Sincroniza mappingMode com o estado de scan:
    // 'scan' quando há scan ativo nesta empresa, 'discovery' em qualquer outro caso.
    useEffect(() => {
        if (isScanForCurrentOrg) {
            setMappingMode('scan');
        } else {
            setMappingMode('discovery');
        }
    }, [isScanForCurrentOrg, setMappingMode]);

    // Network Flow
    // IMPORTANTE: editEmployee DEVE ser memoizado com useCallback para não recriar a cada render
    // e disparar o useEffect do useNetworkFlow em loop infinito.
    const handleEditEmployee = useCallback(
        (id: string) => setEditEmployeeModal({ isOpen: true, empId: id }),
        []
    );

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
        getStableId,
        deleteEmployee,
        editEmployee: handleEditEmployee,
        isScanning: isScanForCurrentOrg,
        discovering: discovering,
    });

    // UI States
    const [showDrawer, setShowDrawer] = useState(false);
    const [ligacaoData, setLigacaoData] = useState<any>(null);
    
    // O Chat agora é gerenciado pelo Layout global para ser persistente.
    // Usamos um evento customizado para abrir o chat a partir de ações no Grafo.
    const handleSetShowChat = (val: boolean) => {
        window.dispatchEvent(new CustomEvent('toggle_chat', { detail: { open: val } }));
    };
    


    // Reset drawer expansion and organization states when leaving organization routes
    useEffect(() => {
        const isOrgRoute = pathname.match(/\/org\/(\d+)/);
        console.log(`[NetworkGraph Reset Effect] pathname: "${pathname}", isOrgRoute: ${!!isOrgRoute}`);
        if (!isOrgRoute) {
            console.log('[NetworkGraph Reset Effect] Resetting all organization states client-side.');
            if (typeof window !== 'undefined') {
                localStorage.removeItem('drawer-expanded-org-id');
                localStorage.removeItem('last-viewed-org');
                localStorage.setItem('show-drawer', 'true');
                window.dispatchEvent(new CustomEvent('drawer_reset_expansion'));
            }
            // Sync global state to null so useHierarchy returns EMPTY_ARRAY
            useChatStore.getState().setCurrentOrgId(null);

            // Reset local states unconditionally to clear the UI
            setCurrentOrgId(null);
            setChatOrgId(null);
            resetWorkflow();
            setShowDrawer(true);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pathname]);


    const activeView = useMemo(() => {
        if (pathname.startsWith('/prospecting')) return 'prospecting';
        if (pathname.startsWith('/settings')) return 'preferences';
        if (pathname.startsWith('/messages')) return 'messages';
        if (pathname.startsWith('/linkedin-scrape')) return 'linkedin-scrape';
        if (pathname.startsWith('/ligacao') || searchParams?.get('view') === 'ligacao') return 'ligacao';
        if (searchParams?.get('view') === 'messages') return 'messages';
        return 'graph';
    }, [pathname, searchParams]);

    const setActiveView = useCallback((view: 'graph' | 'prospecting' | 'preferences' | 'messages' | 'linkedin-scrape' | 'ligacao') => {
        if (view === 'graph') {
           if (currentOrgId) router.push(`/org/${currentOrgId}`);
           else router.push('/');
        } else if (view === 'prospecting') {
           router.push('/prospecting');
        } else if (view === 'preferences') {
           router.push('/settings');
        } else if (view === 'messages') {
           // Se estiver dentro de uma empresa, mantém o contexto da org
           if (currentOrgId) router.push(`/org/${currentOrgId}?view=messages`);
           else router.push('/messages');
        } else if (view === 'linkedin-scrape') {
           router.push('/linkedin-scrape');
        } else if (view === 'ligacao') {
           if (currentOrgId) router.push(`/org/${currentOrgId}?view=ligacao`);
           else router.push('/?view=ligacao');
        }
    }, [router, currentOrgId]);

    const handleNavigateToRoot = useCallback(() => {
        // Limpa todos os estados relacionados à empresa selecionada
        setCurrentOrgId(null);
        setChatOrgId(null);
        resetWorkflow();
        
        // Navega para a raiz
        router.push('/');
    }, [router, resetWorkflow]);

    const [unreadCount, setUnreadCount] = useState(0);
    const prospecting = useProspecting();
    const [confirmModal, setConfirmModal] = useState<{ isOpen: boolean, empId: string | null }>({ isOpen: false, empId: null });
    const [editEmployeeModal, setEditEmployeeModal] = useState<{ isOpen: boolean, empId: string | null }>({ isOpen: false, empId: null });


    // Wrapper para suportar mapeamento por busca/IA (Discovery) ou varredura (Scan)
    const handleSearchOrScan = useCallback(async (e?: React.FormEvent) => {
        if (e) e.preventDefault();
        if (mappingMode === 'scan') {
            if (!cnpj) {
                addNotification('error', 'O CNPJ é obrigatório para iniciar o mapeamento por varredura.');
                return;
            }
            if (!confirmedLinkedInUrl) {
                addNotification('error', 'Nenhum link do LinkedIn confirmado para realizar a varredura.');
                return;
            }
            if (!currentOrgId) {
                addNotification('error', 'Nenhuma organização selecionada para iniciar a varredura.');
                return;
            }
            let peopleUrl = confirmedLinkedInUrl.trim();
            if (!peopleUrl.endsWith('/people/')) {
                peopleUrl = peopleUrl.replace(/\/+$/, '') + '/people/';
            }
            const sessionCookie = localStorage.getItem('linkedin_li_at_cookie') || '';

            // 🧹 Limpa apenas os caches de layout (posições x/y antigas). A limpeza dos nós
            // em si é feita pelo evento 'clear_nodes' do backend (via connectionManager),
            // sincronizada com o momento real em que o backend apaga os funcionários antigos.
            localStorage.removeItem(`layout-cache-${currentOrgId}`);
            localStorage.removeItem(`edges-cache-${currentOrgId}`);

            scan.startScan(currentOrgId, peopleUrl, sessionCookie, areaFocus, productFocus, selectedModel);
            addNotification('info', 'Iniciando varredura do LinkedIn...');
        } else {
            handleSearch(e as any);
        }
    }, [mappingMode, cnpj, confirmedLinkedInUrl, scan.startScan, handleSearch, addNotification, areaFocus, productFocus, selectedModel, currentOrgId]);

    // Trata erros de varredura
    useEffect(() => {
        if (currentScanState.scanError) {
            addNotification('error', `Erro na varredura: ${currentScanState.scanError}`);
        }
    }, [currentScanState.scanError, addNotification]);

    // O efeito que limpava scanOrgId foi removido intencionalmente
    // para evitar que o scan desapareça da UI indevidamente.

    // 🌐 Unificação discovery/scan: tanto a varredura do LinkedIn quanto o discovery
    // por IA agora alimentam o grafo via connectionManager (mesmo WebSocket por job_id,
    // mesmo merge/dedup robusto, mesmo refinamento único pós-conclusão). useHierarchyScan
    // conecta ao connectionManager internamente — não há mais tradução manual de
    // scanResults para nós do grafo aqui.

    // Polling de mensagens não lidas (para o badge no header — filtra por org atual)
    useEffect(() => {
        const check = async () => {
            try {
                const { communication } = await import('@/services/api');
                const resp = await communication.fetchTrackedContacts(undefined, currentOrgId);
                setUnreadCount((resp as any).unread_count || 0);
            } catch { /* silencioso */ }
        };
        void check();
        const interval = window.setInterval(check, 30_000);
        return () => window.clearInterval(interval);
    }, [currentOrgId]);

    // Sync UI states to localStorage
    useEffect(() => {
        const savedDrawer = localStorage.getItem("show-drawer") === "true";
        setShowDrawer(savedDrawer);

        const openDrawerHandler = () => {
            setShowDrawer(true);
            localStorage.setItem("show-drawer", "true");
        };
        window.addEventListener('drawer_open', openDrawerHandler);
        return () => window.removeEventListener('drawer_open', openDrawerHandler);
    }, []);

    const handleSetShowDrawer = (val: boolean) => {
        setShowDrawer(val);
        localStorage.setItem("show-drawer", val.toString());
    };

    useEffect(() => {
        const handleOpenLigacaoView = (e: any) => {
            if (e.detail) {
                let enrichedDetail = { ...e.detail };
                if (rawEmployees && rawEmployees.length > 0) {
                    const normalizeName = (name: string) => name ? name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim() : '';
                    const contactName = normalizeName(e.detail.contact_name);
                    
                    // Tentativa 1: Busca exata ignorando acentos e case
                    let emp = rawEmployees.find((n: any) => normalizeName(n.name) === contactName);
                    
                    // Tentativa 2: Busca por substring (ex: 'Edson' ou 'Edson Magalhaes')
                    if (!emp) {
                        emp = rawEmployees.find((n: any) => normalizeName(n.name).includes(contactName) || contactName.includes(normalizeName(n.name)));
                    }

                    if (emp) {
                        enrichedDetail.profile_pic = emp.profile_pic || emp.photo || emp.avatar_url || emp.avatar;
                        enrichedDetail.originalEmployee = emp;
                        enrichedDetail.linkedin = emp.linkedin || emp.linkedin_url;
                        enrichedDetail.email = emp.email;
                    }
                    
                    // Adiciona o avatar da empresa caso seja uma ligação PABX
                    const rootEmp = rawEmployees.find((n: any) => n.id === 'root_company');
                    if (rootEmp) {
                        enrichedDetail.company_logo = rootEmp.logo || rootEmp.company_logo || rootEmp.profile_pic || rootEmp.avatar;
                    }
                }

                setLigacaoData(enrichedDetail);
                try {
                    sessionStorage.setItem('active-ligacao-data', JSON.stringify(enrichedDetail));
                } catch (err) {
                    console.error("Failed to save ligacao data to sessionStorage", err);
                }
            }
            
            // Tenta obter orgId da URL se o estado estiver vazio
            let orgId = currentOrgId;
            if (!orgId) {
                const match = window.location.pathname.match(/\/org\/(\d+)/);
                if (match) orgId = parseInt(match[1]);
            }

            if (orgId) router.push(`/org/${orgId}?view=ligacao`);
            else router.push('/?view=ligacao');
            
            setShowDrawer(false);
        };
        window.addEventListener('open_ligacao_view', handleOpenLigacaoView);
        return () => window.removeEventListener('open_ligacao_view', handleOpenLigacaoView);
    }, [currentOrgId, router, rawEmployees]);

    // Carrega dados de ligação persistidos ao montar (ex: após refresh/navegação)
    useEffect(() => {
        if (activeView === 'ligacao' && !ligacaoData) {
            const saved = sessionStorage.getItem('active-ligacao-data');
            if (saved) {
                try {
                    setLigacaoData(JSON.parse(saved));
                } catch (e) {
                    console.error("Failed to parse saved ligacao data", e);
                }
            }
        }
    }, [activeView, ligacaoData]);

    // Persistence & Theme
    useEffect(() => {
        // Evita salvar estado transiente/incompleto onde há múltiplos nós mas 0 arestas
        if (nodes.length > 1 && edges.length === 0) return;
        if (nodes.length > 0) saveGraphState(nodes, edges);
    }, [nodes, edges, saveGraphState]);

    useEffect(() => {
        const savedTheme = localStorage.getItem("preferred-theme") || "dark";
        setTheme(savedTheme);
        document.documentElement.setAttribute("data-theme", savedTheme);

        const handleThemeChanged = (e: CustomEvent<string>) => {
            if (e.detail) {
                setTheme(e.detail);
            }
        };
        window.addEventListener('theme_changed', handleThemeChanged as EventListener);
        return () => window.removeEventListener('theme_changed', handleThemeChanged as EventListener);
    }, []);

    // Hook para sincronização de roteamento e restauração de dados
    useRouterSync({
        pathname,
        currentOrgId,
        setCurrentOrgId,
        setChatOrgId,
        pipedriveOrgs,
        hierarchy,
        discovery,
        setShouldFitView,
        addNotification
    });

    // Handlers
    const handleOrgClick = useCallback(async (org: any, openChat = false) => {
        startTransition(() => {
            router.push(`/org/${org.id}`);
        });
        if (openChat) handleSetShowChat(true);
    }, [router, handleSetShowChat]);

    const handleOrgReset = useCallback((orgId: number) => {
        console.log(`[Graph] Resetando UI para organização ${orgId}...`);
        setPipedriveOrgs(prev => prev.filter(org => Number(org.id) !== orgId && Number(org.local_id) !== orgId));
        setNodes([]);
        setEdges([]);
        resetWorkflow();
        resetHierarchy();
        if (currentOrgId === orgId) {
            setCurrentOrgId(null);
            localStorage.removeItem('last-viewed-org');
            router.push('/');
        }
    }, [setPipedriveOrgs, setNodes, setEdges, resetWorkflow, resetHierarchy, currentOrgId, router]);

    const handleNewCompany = useCallback(() => {
        // Abre o drawer e garante que ele volte para a lista (limpando cache de expansão)
        handleSetShowDrawer(true);
        localStorage.removeItem('drawer-expanded-org-id');
        
        // Notifica o Drawer para resetar o estado interno de expansão
        window.dispatchEvent(new CustomEvent('drawer_reset_expansion'));
        
        // Limpa UI imediatamente ANTES de navegar para evitar flash do step "confirm"
        setCurrentOrgId(null);
        setNodes([]);
        setEdges([]);
        resetWorkflow();
        resetHierarchy();
        localStorage.removeItem('last-viewed-org');
        
        router.push('/');
    }, [router, setNodes, setEdges, resetWorkflow, resetHierarchy]);

    return (
        <NetworkGraphLayout
            theme={theme}
            setTheme={setTheme}
            showDrawer={showDrawer}
            handleSetShowDrawer={handleSetShowDrawer}
            activeView={activeView}
            setActiveView={setActiveView}
            currentUser={currentUser}
            tasksForToday={tasksForToday}
            onToggleChat={onToggleChat as any}
            onLogout={onLogout as any}
            handleNewCompany={handleNewCompany}
            refineHierarchy={refineHierarchy}
            smartSyncPipedrive={smartSyncPipedrive}
            hierarchy={hierarchy}
            discovery={discovery}
            scan={scopedScan}
            isScanForCurrentOrg={isScanForCurrentOrg}
            filteredOrgs={filteredOrgs}
            loadingOrgs={loadingOrgs}
            searchTerm={searchTerm}
            setSearchTerm={setSearchTerm}
            handleOrgClick={handleOrgClick}
            currentOrgId={currentOrgId}
            handleOrgRenamed={handleOrgRenamed}
            confirmedLogo={discovery.confirmedLogo}
            activeJobId={activeJobId}
            rawEmployees={rawEmployees}
            pipedriveOrgs={pipedriveOrgs}
            addNotification={addNotification}
            handleOrgReset={handleOrgReset}
            setEditEmployeeModal={setEditEmployeeModal}
            uniqueStages={uniqueStages}
            activeStageFilter={activeStageFilter}
            setActiveStageFilter={setActiveStageFilter}
            confirmedBrand={discovery.confirmedBrand}
            unreadCount={unreadCount}
            notifications={notifications}
            removeNotification={removeNotification}
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            shouldFitView={shouldFitView}
            setShouldFitView={setShouldFitView}
            handleSearchOrScan={handleSearchOrScan}
            handleAutoEnrich={handleAutoEnrich}
            enrichingIds={enrichingIds}
            stopHierarchyScan={stopHierarchyScan}
            cancelDiscovery={cancelDiscovery}
            approveCandidate={approveCandidate}
            setConfirmModal={setConfirmModal}
            previewExpanded={previewExpanded}
            setPreviewExpanded={setPreviewExpanded}
            selectedModel={selectedModel}
            setSelectedModel={setSelectedModel}
            strictMode={strictMode}
            setStrictMode={setStrictMode}
            confirmModal={confirmModal}
            editEmployeeModal={editEmployeeModal}
            ligacaoData={ligacaoData}
            prospecting={prospecting}
            fetchPipedriveOrgs={fetchPipedriveOrgs}
            mappingMode={mappingMode}
            setMappingMode={setMappingMode}
            confirmedLinkedInUrl={discovery.confirmedLinkedInUrl}
            areaFocus={discovery.areaFocus}
            productFocus={discovery.productFocus}
            SmartBackground={SmartBackground}
            FitViewHandler={FitViewHandler}
        />
    );
}

export default function NetworkGraph(props: any) {
    return (
        <ReactFlowProvider>
            <NetworkGraphContent {...props} />
        </ReactFlowProvider>
    );
}
