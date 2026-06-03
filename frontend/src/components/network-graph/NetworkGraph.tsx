"use client";

import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useReactFlow, ReactFlowProvider, Edge } from 'reactflow';
import { HierarchyEmployee } from '@/types';
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
import { Avatar } from '../ui';
import { ChatPanel } from '../chat/ChatPanel';
import { PreferencesView } from '../layout/PreferencesView';
import { HierarchyScanView } from '../hierarchy-scan/HierarchyScanView';
import { GraphCanvas } from './GraphCanvas';
import { HierarchyDiscoveryOverlay } from './HierarchyDiscoveryOverlay';
import { FloatingToolbar } from './FloatingToolbar';
import { SmartBackground } from './components/SmartBackground';
import { FitViewHandler } from './components/FitViewHandler';
import { ModelSelector } from '../chat/ModelSelector';
import { useHierarchyScan } from '@/hooks/useHierarchyScan';
import { ScanTerminalPanel } from './components/ScanTerminalPanel';
import { ScanPreviewBubble } from './components/ScanPreviewBubble';
import { TriggerNotifications } from '../ui/TriggerNotifications';
import { API_BASE_URL } from '@/services/config';
import { EmployeeDetailsModal } from './components/EmployeeDetailsModal';

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
        loadStoredHierarchy, deleteEmployee, setRawEmployees, setRawBackendEdges
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
        enrichingIds, handleSearch, handleBrandSelect, handleAutoEnrich, resetWorkflow,
        selectedModel, setSelectedModel, strictMode, setStrictMode,
        mappingMode, setMappingMode, confirmedLinkedInUrl, setConfirmedLinkedInUrl, partners
    } = discovery;

    // HierarchyScan Integration
    const scan = useHierarchyScan();
    const [previewExpanded, setPreviewExpanded] = useState(false);

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
    });

    // UI States
    const [showDrawer, setShowDrawer] = useState(false);
    
    // O Chat agora é gerenciado pelo Layout global para ser persistente.
    // Usamos um evento customizado para abrir o chat a partir de ações no Grafo.
    const handleSetShowChat = (val: boolean) => {
        window.dispatchEvent(new CustomEvent('toggle_chat', { detail: { open: val } }));
    };
    
    const pathname = usePathname() || '/';
    const router = useRouter();
    const searchParams = useSearchParams();

    const activeView = useMemo(() => {
        if (pathname.startsWith('/prospecting')) return 'prospecting';
        if (pathname.startsWith('/settings')) return 'preferences';
        if (pathname.startsWith('/messages')) return 'messages';
        if (pathname.startsWith('/linkedin-scrape')) return 'linkedin-scrape';
        if (pathname.startsWith('/ligacao') || searchParams?.get('view') === 'ligacao') return 'ligacao';
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
           router.push('/messages');
        } else if (view === 'linkedin-scrape') {
           router.push('/linkedin-scrape');
        } else if (view === 'ligacao') {
           router.push('/?view=ligacao');
        }
    }, [router, currentOrgId]);

    const [unreadCount, setUnreadCount] = useState(0);
    const prospecting = useProspecting();
    const [confirmModal, setConfirmModal] = useState<{ isOpen: boolean, empId: string | null }>({ isOpen: false, empId: null });
    const [editEmployeeModal, setEditEmployeeModal] = useState<{ isOpen: boolean, empId: string | null }>({ isOpen: false, empId: null });

    const [currentUser, setCurrentUser] = useState<{ name: string; avatar: string | null } | null>(null);

    useEffect(() => {
        const fetchCurrentUser = async () => {
            try {
                if (typeof window !== 'undefined') {
                    const cached = window.localStorage.getItem('pipedrive-current-user');
                    if (cached) {
                        setCurrentUser(JSON.parse(cached));
                    }
                }
                
                const resp = await fetch(`${API_BASE_URL}/api/v1/pipedrive/current-user`);
                if (resp.ok) {
                    const data = await resp.json();
                    setCurrentUser(data);
                    if (typeof window !== 'undefined') {
                        window.localStorage.setItem('pipedrive-current-user', JSON.stringify(data));
                    }
                }
            } catch (err) {
                console.error('Erro ao buscar usuário do Pipedrive:', err);
            }
        };
        void fetchCurrentUser();
    }, []);

    // Wrapper para suportar mapeamento por busca/IA (Discovery) ou varredura (Scan)
    const handleSearchOrScan = useCallback((e?: React.FormEvent) => {
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
            let peopleUrl = confirmedLinkedInUrl.trim();
            if (!peopleUrl.endsWith('/people/')) {
                peopleUrl = peopleUrl.replace(/\/+$/, '') + '/people/';
            }
            const sessionCookie = localStorage.getItem('linkedin_li_at_cookie') || '';
            scan.startScan(peopleUrl, sessionCookie, areaFocus, productFocus, selectedModel);
            addNotification('info', 'Iniciando varredura do LinkedIn...');
        } else {
            handleSearch(e as any);
        }
    }, [mappingMode, cnpj, confirmedLinkedInUrl, scan, handleSearch, addNotification, areaFocus, productFocus, selectedModel]);

    // Mantém ref estável dos funcionários para evitar loop de dependência no useEffect de scanResults
    const rawEmployeesRef = useRef(rawEmployees);
    useEffect(() => {
        rawEmployeesRef.current = rawEmployees;
    }, [rawEmployees]);

    // Trata erros de varredura
    useEffect(() => {
        if (scan.scanError) {
            addNotification('error', `Erro na varredura: ${scan.scanError}`);
        }
    }, [scan.scanError, addNotification]);

    // ✅ NOVO: Limpa o grafo quando a varredura inicia do zero ou recebe comando de limpeza
    useEffect(() => {
        if (scan.isScanning && scan.scanResults.length === 0) {
            console.log("[NetworkGraph] 🧹 Limpando grafo para nova varredura.");
            const existingRootAndPartners = rawEmployeesRef.current.filter(e => e.id === 'root_company' || e.id.startsWith('partner_'));
            setRawEmployees([...existingRootAndPartners]);
            setRawBackendEdges([]);
        }
    }, [scan.isScanning, scan.scanResults.length, setRawEmployees, setRawBackendEdges]);

    // Trata resultados de varredura
    useEffect(() => {
        if (scan.scanResults && scan.scanResults.length > 0) {
            const employees: HierarchyEmployee[] = scan.scanResults.map((p) => ({
                id: p.id || Math.random().toString(36).substr(2, 9),
                name: p.name,
                role: p.role,
                department: '',
                company: confirmedBrand,
                manager_id: undefined,
                level: 0,
                linkedin: p.linkedin_url,
                avatar: p.avatar,
                profile_pic: p.avatar,
                location: p.location || '',
                observations: p.observations || '',
                evidence: p.evidence || '',
                email: p.email || '',
            }));

            const existingRootAndPartners = rawEmployeesRef.current.filter(e => e.id === 'root_company' || e.id.startsWith('partner_'));
            let baseEmployees = [...existingRootAndPartners];

            if (baseEmployees.length === 0) {
                baseEmployees.push({
                    id: 'root_company',
                    name: confirmedBrand || "Empresa",
                    role: "Holding / Matriz",
                    department: "Corporate Root",
                    level: 0,
                    logo: confirmedLogo,
                    company_logo: confirmedLogo,
                    domain: domainTarget
                });

                if (partners && partners.length > 0) {
                    partners.forEach((p: any, idx: number) => {
                        baseEmployees.push({
                            id: `partner_${idx}`,
                            name: p.name || `Sócio ${idx + 1}`,
                            role: p.role || "Sócio / Administrador",
                            department: "Quadro de Sócios (QSA)",
                            level: 6,
                            manager_id: 'root_company',
                            company: confirmedBrand
                        });
                    });
                }
            }

            const allEmployees = [...baseEmployees, ...employees];
            setRawEmployees(allEmployees);

            const initialEdges: Edge[] = [];
            allEmployees.forEach(emp => {
                if (emp.manager_id && emp.id !== "root_company") {
                    initialEdges.push({
                        id: `e-${emp.manager_id}-${emp.id}`,
                        source: emp.manager_id,
                        target: emp.id,
                        animated: false
                    });
                } else if (emp.id !== 'root_company') {
                    initialEdges.push({
                        id: `e-root_company-${emp.id}`,
                        source: 'root_company',
                        target: emp.id,
                        animated: false
                    });
                }
            });
            setRawBackendEdges(initialEdges);

            // Somente dispara o refinamento e as notificações finais quando o scan terminar de fato
            if (!scan.isScanning) {
                addNotification('success', `Varredura concluída! ${employees.length} perfis extraídos.`);
                addNotification('info', 'Processando varredura e gerando árvore hierárquica com IA...');
                refineHierarchy(allEmployees);
            }
        }
    }, [scan.scanResults, scan.isScanning, confirmedBrand, confirmedLogo, domainTarget, partners, setRawEmployees, setRawBackendEdges, addNotification, refineHierarchy]);

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

    // Persistence & Theme
    useEffect(() => {
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

                    const lUrl = org.linkedin_url || org.linkedin || "";
                    if (lUrl) setConfirmedLinkedInUrl(lUrl);

                    if (org.id) {
                        const data = await loadStoredHierarchy(Number(org.id), true);
                        if (data && data.nodes && data.nodes.length > 0) {
                            setStep("confirm");
                            const rootLinkedin = data.nodes[0]?.linkedin || data.nodes[0]?.url;
                            if (rootLinkedin && rootLinkedin.startsWith('http')) {
                                setConfirmedLinkedInUrl(rootLinkedin);
                            }
                            setTimeout(() => setShouldFitView(true), 100);
                        } else if (org.linkedin_url || org.linkedin || (org.cnpj && org.domain)) {
                            // 🚀 OTIMIZAÇÃO: Pula 'Detectar' se já temos metadados básicos ao recarregar
                            setStep("confirm");
                        } else {
                            setStep("input");
                        }
                    }
 else {
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
                    const { job_id, brand, logo, domain, orgId, cnpj } = jobData;
                    console.log(`[Job Check] Detectado Job Ativo para ${brand}. Carregando dados prévios...`);

                    if (orgId) {
                        const data = await loadStoredHierarchy(Number(orgId), true);
                        if (data && data.nodes && data.nodes.length > 0) {
                            console.log(`[Job Check] ${data.nodes.length} nós restaurados do banco.`);
                        }
                    }

                    setStep("scanning");
                    setConfirmedBrand(brand);
                    if (logo) setConfirmedLogo(logo);
                    if (domain) setDomainTarget(domain);
                    if (cnpj) {
                        const onlyNums = cnpj.replace(/\D/g, '');
                        if (onlyNums.length >= 5) {
                            setCnpj(formatCnpj(cnpj));
                        }
                    }
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
        router.push(`/org/${org.id}`);
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
                            
                            // Restaurar os dados da empresa na interface do toolbar
                            setConfirmedBrand(jobData.brand || cleanName(org.name || ""));
                            setConfirmedLogo(jobData.logo || org.logo || "");
                            
                            let targetCnpj = jobData.cnpj || org.cnpj || "";
                            const onlyNums = targetCnpj.replace(/\D/g, '');
                            if (onlyNums.length >= 5) {
                                setCnpj(formatCnpj(targetCnpj));
                            }
                            setDomainTarget(jobData.domain || org.domain || "");
                            if (org.product_focus) setProductFocus(org.product_focus);
                            if (org.category === "compras" || org.category === "logistica") setAreaFocus(org.category);
                            
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

                    const rootLinkedin = data.nodes[0]?.linkedin || data.nodes[0]?.url || org.linkedin_url || org.linkedin;
                    if (rootLinkedin && rootLinkedin.startsWith('http')) {
                        setConfirmedLinkedInUrl(rootLinkedin);
                    }
                } else if (org.linkedin_url || org.linkedin || (org.cnpj && org.domain)) {
                    // 🚀 OTIMIZAÇÃO: Se já temos LinkedIn ou (CNPJ + Domínio), pulamos o passo de "Detectar"
                    setConfirmedBrand(cleanName(org.name || ""));
                    setConfirmedLogo(org.logo || "");
                    setCnpj(formatCnpj(org.cnpj || ""));
                    setDomainTarget(org.domain || "");
                    setStep("confirm");

                    const rootLinkedin = org.linkedin_url || org.linkedin;
                    if (rootLinkedin && rootLinkedin.startsWith('http')) {
                        setConfirmedLinkedInUrl(rootLinkedin);
                    }
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
        loadStoredHierarchy, setProductFocus, setAreaFocus, setShouldFitView, setConfirmedLinkedInUrl
    ]);

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
        
        setCurrentOrgId(null);
        localStorage.removeItem('last-viewed-org');
        router.push('/');
        setNodes([]);
        setEdges([]);
        resetWorkflow();
        resetHierarchy();
    }, [router, setNodes, setEdges, resetWorkflow, resetHierarchy]);

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
                    window.dispatchEvent(new CustomEvent('theme_changed', { detail: newTheme }));
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
                    // Pass notification callback directly to handle the background job messages
                    await smartSyncPipedrive((type, msg) => {
                        addNotification(type as any, msg);
                        if (type === 'success') {
                            fetchPipedriveOrgs(); // Refresh the list
                        }
                    });
                }}
                isSmartSyncLoading={hierarchy.isSmartSyncLoading}
                onOpenProspecting={() => setActiveView(activeView === 'prospecting' ? 'graph' : 'prospecting')}
                isProspecting={activeView === 'prospecting'}
                onOpenPreferences={() => setActiveView(activeView === 'preferences' ? 'graph' : 'preferences')}
                isPreferences={activeView === 'preferences'}
                onOpenLinkedinScrape={() => setActiveView(activeView === 'linkedin-scrape' ? 'graph' : 'linkedin-scrape')}
                isLinkedinScrape={activeView === 'linkedin-scrape'}
                onOpenLigacao={() => setActiveView(activeView === 'ligacao' ? 'graph' : 'ligacao')}
                isLigacao={activeView === 'ligacao'}
                isScanActive={scan.isScanning}
            />

            <div className={styles.mainWrapper}>
                <div className={styles.contentWrapper}>
                    {activeView !== 'preferences' && activeView !== 'messages' && activeView !== 'ligacao' && (
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
                            refreshDetailsTrigger={pipedriveOrgs.length}
                            addNotification={addNotification}
                            onOrgReset={handleOrgReset}
                            onEditEmployee={(id) => setEditEmployeeModal({ isOpen: true, empId: id })}
                            onOrgDomainChanged={(oldDomain, newDomain) => {
                                // Extract the naked domains
                                const getDomain = (url: string) => {
                                    try {
                                        return new URL(url.startsWith('http') ? url : `https://${url}`).hostname.replace(/^www\./, '');
                                    } catch {
                                        return url;
                                    }
                                };
                                const cleanOld = getDomain(oldDomain);
                                const cleanNew = getDomain(newDomain);
                                
                                rawEmployees.forEach(emp => {
                                    if (emp.email && emp.email.includes(`@${cleanOld}`)) {
                                        const newEmail = emp.email.replace(`@${cleanOld}`, `@${cleanNew}`);
                                        hierarchy.updateEmployee(emp.id, { email: newEmail });
                                    }
                                });
                            }}
                        />
                    )}

                    <div className={styles.mainContent}>
                        {activeView !== 'preferences' && activeView !== 'ligacao' && (
                            <Header
                                confirmedBrand={confirmedBrand}
                                activeView={activeView}
                                onToggleMessages={() => setActiveView(activeView === 'messages' ? 'graph' : 'messages')}
                                unreadCount={unreadCount}
                            />
                        )}
                        <NotificationContainer notifications={notifications} removeNotification={removeNotification} />

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
                                    
                                    <HierarchyDiscoveryOverlay
                                        error={null}
                                        handleSearch={handleSearchOrScan}
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
                                        showChat={false}
                                        approveCandidate={async (id) => {
                                            await approveCandidate(id);
                                            addNotification('success', "Perfil aprovado.");
                                        }}
                                        rejectCandidate={(id) => setConfirmModal({ isOpen: true, empId: id })}
                                        mappingMode={mappingMode}
                                        onMappingModeChange={setMappingMode}
                                        scanTerminal={
                                            scan.isScanning ? (
                                                <ScanTerminalPanel consoleLogs={scan.consoleLogs} isVisible={true} />
                                            ) : undefined
                                        }
                                        scanPreview={
                                            scan.isScanning ? (
                                                <ScanPreviewBubble
                                                    hasPreview={scan.hasPreview}
                                                    previewUrl={scan.previewUrl}
                                                    isScanning={scan.isScanning}
                                                    expanded={previewExpanded}
                                                    onToggleExpand={() => setPreviewExpanded(v => !v)}
                                                    onImageClick={scan.handleImageClick}
                                                    onSendText={scan.sendText}
                                                    onPressEnter={scan.pressEnter}
                                                    onPressBackspace={scan.pressBackspace}
                                                    consoleLogs={scan.consoleLogs}
                                                />
                                            ) : undefined
                                        }
                                        isScanning={scan.isScanning}
                                        onStopScan={scan.stopScan}
                                        humanAnalysisContent={(() => {
                                            const pending = rawEmployees.filter(e => e.role && e.role.toLowerCase().includes('humana'));
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

                            {activeView === 'messages' && (
                                <MessagesView onBack={() => setActiveView('graph')} orgId={currentOrgId} />
                            )}
                            {activeView === 'ligacao' && (
                                <LigacaoView onBack={() => setActiveView('graph')} />
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
                                            isChatOpen={false}
                                            
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
                            {activeView === 'linkedin-scrape' && (
                                <HierarchyScanView
                                    onBack={() => setActiveView('graph')}
                                    defaultCompanyUrl={confirmedLinkedInUrl
                                        ? (confirmedLinkedInUrl.trim().endsWith('/people/')
                                            ? confirmedLinkedInUrl.trim()
                                            : confirmedLinkedInUrl.trim().replace(/\/+$/, '') + '/people/')
                                        : ''}
                                    isScanning={scan.isScanning}
                                    scanProgress={scan.scanProgress}
                                    consoleLogs={scan.consoleLogs}
                                    hasPreview={scan.hasPreview}
                                    previewUrl={scan.previewUrl}
                                    scanResults={scan.scanResults}
                                    scanError={scan.scanError}
                                    onStartScan={(url, cookie) =>
                                        scan.startScan(url, cookie, areaFocus, productFocus, selectedModel)
                                    }
                                    onStopScan={scan.stopScan}
                                    onImageClick={scan.handleImageClick}
                                    onSendText={scan.sendText}
                                    onPressEnter={scan.pressEnter}
                                    onPressBackspace={scan.pressBackspace}
                                />
                            )}
                        </div>

                        {activeView === 'graph' && (
                            <div 
                                className="dropdownDown"
                                style={{
                                    position: 'absolute',
                                    top: '68px',
                                    right: '16px',
                                    zIndex: 10,
                                }}
                            >
                                <ModelSelector
                                    model={selectedModel as any}
                                    setModel={setSelectedModel as any}
                                    strictMode={strictMode}
                                    setStrictMode={setStrictMode}
                                    theme={theme}
                                />
                            </div>
                        )}
                    </div>
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
                message="Tem certeza que deseja remover este profissional? Ele será movido para o grupo de descartados."
            />

            <EmployeeDetailsModal
                isOpen={editEmployeeModal.isOpen}
                onClose={() => setEditEmployeeModal({ isOpen: false, empId: null })}
                empId={editEmployeeModal.empId}
                rawEmployees={rawEmployees}
                handleUpdateEmployee={hierarchy.updateEmployee}
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
