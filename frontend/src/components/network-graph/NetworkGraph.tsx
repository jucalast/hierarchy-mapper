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
import { apiGet } from '../../services/config';
import { Avatar } from '../ui';
import { ChatPanel } from '../chat/ChatPanel';
import { PreferencesView } from '../layout/PreferencesView';
import { HierarchyScanView } from '../hierarchy-scan/HierarchyScanView';
import { GraphCanvas } from './GraphCanvas';
import { HierarchyDiscoveryOverlay } from './HierarchyDiscoveryOverlay';
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

    // CRM Sync
    const {
        pipedriveOrgs, setPipedriveOrgs, searchTerm, setSearchTerm,
        loadingOrgs, filteredOrgs, fetchPipedriveOrgs, handleOrgRenamed,
        uniqueStages, activeStageFilter, setActiveStageFilter
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
    // O scanOrgId agora é mantido pelo contexto global para sobreviver à navegação
    const isScanForCurrentOrg = scan.scanOrgId !== null && scan.scanOrgId === currentOrgId;
    const [previewExpanded, setPreviewExpanded] = useState(false);

    // ✅ Força modo 'scan' se houver um scan ativo nesta empresa ao carregar a página/navegar
    useEffect(() => {
        if (isScanForCurrentOrg && scan.isScanning) {
            setMappingMode('scan');
        }
    }, [isScanForCurrentOrg, scan.isScanning, setMappingMode]);

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
        isScanning: isScanForCurrentOrg && scan.isScanning,
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
            resetHierarchy();
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
            if (!currentOrgId) {
                addNotification('error', 'Nenhuma organização selecionada para iniciar a varredura.');
                return;
            }
            let peopleUrl = confirmedLinkedInUrl.trim();
            if (!peopleUrl.endsWith('/people/')) {
                peopleUrl = peopleUrl.replace(/\/+$/, '') + '/people/';
            }
            const sessionCookie = localStorage.getItem('linkedin_li_at_cookie') || '';
            scan.startScan(currentOrgId, peopleUrl, sessionCookie, areaFocus, productFocus, selectedModel);
            addNotification('info', 'Iniciando varredura do LinkedIn...');
        } else {
            handleSearch(e as any);
        }
    }, [mappingMode, cnpj, confirmedLinkedInUrl, scan, handleSearch, addNotification, areaFocus, productFocus, selectedModel, currentOrgId]);

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

    // O efeito que limpava scanOrgId foi removido intencionalmente
    // para evitar que o scan desapareça da UI indevidamente.

    // ✅ NOVO: Limpa o grafo quando a varredura inicia do zero ou recebe comando de limpeza
    useEffect(() => {
        if (scan.isScanning && scan.scanResults.length === 0) {
            console.log("[NetworkGraph] 🧹 Limpando grafo para nova varredura.");
            const existingRootOnly = rawEmployeesRef.current.filter(e => e.id === 'root_company');
            setRawEmployees([...existingRootOnly]);
            setRawBackendEdges([]);
        }
    }, [scan.isScanning, scan.scanResults.length, setRawEmployees, setRawBackendEdges]);

    // ✅ NOVO: Detecta a conclusão do scan do LinkedIn para atualizar o agente e rodar o Analista de IA automaticamente
    const wasScanningRef = useRef(false);
    useEffect(() => {
        if (isScanForCurrentOrg) {
            if (scan.isScanning) {
                wasScanningRef.current = true;
            } else if (wasScanningRef.current) {
                wasScanningRef.current = false;
                console.log("[NetworkGraph] 🏁 Mapeamento pelo método scan finalizado. Sincronizando e ativando Analista de IA...");
                
                const handleScanCompletion = async () => {
                    // 1. Carrega a hierarquia final consolidada do banco
                    const freshData = await loadStoredHierarchy(currentOrgId!, true);
                    const employeesToRefine = (freshData && freshData.nodes && freshData.nodes.length > 0)
                        ? freshData.nodes
                        : rawEmployees;

                    // 2. Formata e despacha o evento para o agente de chat identificar o fim do scan
                    const formattedContacts = scan.scanResults.map(p => ({
                        name: p.name,
                        role: p.role || '',
                        email: p.email || undefined,
                        department: undefined,
                        temperature: undefined,
                        level: 0,
                        decision_maker: [
                            'compras', 'procurement', 'suprimentos', 'logística', 'logistica',
                            'supply chain', 'supply', 'materiais', 'aquisição', 'aquisicao',
                            'estoque', 'sourcing'
                        ].some(k => (p.role || '').toLowerCase().includes(k)),
                    }));

                    window.dispatchEvent(new CustomEvent('hierarchy_scan_done', {
                        detail: {
                            orgId: currentOrgId,
                            orgName: confirmedBrand || "",
                            chatPrompted: true, // Garante que o chat agent processe a finalização
                            contacts: formattedContacts,
                        },
                    }));

                    // 3. Executa o Analista de IA automaticamente após um pequeno delay para corrigir visualmente a hierarquia do grafo
                    setTimeout(() => {
                        console.log("[NetworkGraph] 🤖 Executando automaticamente o Analista de IA para o scan concluído...");
                        refineHierarchy(employeesToRefine);
                    }, 600);
                };

                void handleScanCompletion();
            }
        }
    }, [isScanForCurrentOrg, scan.isScanning, currentOrgId, confirmedBrand, loadStoredHierarchy, scan.scanResults, rawEmployees, refineHierarchy]);

    // Trata resultados de varredura
    useEffect(() => {
        // Apenas substitui os nós em tempo real se o scan estiver EM ANDAMENTO.
        // Quando terminar (isScanning=false), o componente buscará a versão final processada do banco.
        if (!loading && isScanForCurrentOrg && scan.isScanning && scan.scanResults && scan.scanResults.length > 0) {
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
        }
    }, [!loading, isScanForCurrentOrg, scan.scanResults, scan.isScanning, confirmedBrand, confirmedLogo, domainTarget, partners, setRawEmployees, setRawBackendEdges]);

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

    // Reconnection & Initial Load logic
    useEffect(() => {
        if (hasAttemptedReconnect.current) return;
        hasAttemptedReconnect.current = true;

        const checkLastOrg = async () => {
            const match = pathname.match(/\/org\/(\d+)/);
            let orgId: number | null = null;
            let org: any = null;

            if (match && match[1]) {
                orgId = parseInt(match[1]);
                const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
                if (cachedOrgsStr) {
                    try {
                        const list = JSON.parse(cachedOrgsStr);
                        if (Array.isArray(list)) {
                            org = list.find((o: any) => Number(o.id) === orgId || Number(o.pipedrive_id) === orgId || Number(o.local_id) === orgId);
                        }
                    } catch (e) {
                        console.error(e);
                    }
                }
                
                if (!org) {
                    try {
                        const { organizations } = await import('@/services/api');
                        const res = await organizations.getOrganizationDetails(orgId);
                        if (res && res.org) org = res.org;
                    } catch (e) {
                        console.error("Erro ao buscar detalhes da org da URL no boot:", e);
                    }
                }
            }

            if (!org) {
                const lastOrgStr = localStorage.getItem('last-viewed-org');
                if (lastOrgStr && lastOrgStr !== "NaN" && lastOrgStr !== "undefined") {
                    try {
                        org = JSON.parse(lastOrgStr);
                        if (org && org.id) orgId = Number(org.id);
                    } catch (e) {
                        console.error(e);
                    }
                }
            }

            if (org && orgId) {
                try {
                    const cleanOrgName = org.name || "";
                    setConfirmedBrand(cleanOrgName);
                    setConfirmedLogo(org.logo || "");

                    let targetCnpj = org.cnpj || "";
                    const onlyNums = targetCnpj.replace(/\D/g, '');
                    if (onlyNums.length >= 5) {
                        setCnpj(formatCnpj(targetCnpj));
                    }
                    setDomainTarget(org.domain || "");
                    setCurrentOrgId(orgId);
                    setChatOrgId(orgId);
                    useChatStore.getState().setCurrentOrgId(orgId);
                    localStorage.setItem('last-viewed-org', JSON.stringify(org));

                    const lUrl = org.linkedin_url || org.linkedin || "";
                    if (lUrl) setConfirmedLinkedInUrl(lUrl);

                    const data = await loadStoredHierarchy(orgId, true);
                    if (data && data.nodes && data.nodes.length > 0) {
                        setStep("confirm");
                        const rootLinkedin = data.nodes[0]?.linkedin || data.nodes[0]?.url;
                        if (rootLinkedin && rootLinkedin.startsWith('http')) {
                            setConfirmedLinkedInUrl(rootLinkedin);
                        }
                        setTimeout(() => setShouldFitView(true), 100);
                    } else if (org.linkedin_url || org.linkedin || (org.cnpj && org.domain)) {
                        setStep("confirm");
                    } else {
                        setStep("input");
                    }
                } catch (e) {
                    console.error("[Last Org Check] Erro", e);
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
                        useChatStore.getState().setCurrentOrgId(orgId);
                    }

                    const reconnected = await reconnectToActiveJob(addNotification);
                    if (!reconnected) {
                        console.warn("[Job Check] Job expirou no backend.");
                        setStep("confirm");
                    }
                } catch (e) {
                    console.error("[Job Check] Erro", e);
                    if (pathname !== '/') {
                        checkLastOrg();
                    } else {
                        setStep("input");
                        setConfirmedBrand("");
                        setConfirmedLogo("");
                        setCnpj("");
                        setDomainTarget("");
                    }
                }
            } else {
                if (pathname !== '/') {
                    checkLastOrg();
                } else {
                    setStep("input");
                    setConfirmedBrand("");
                    setConfirmedLogo("");
                    setCnpj("");
                    setDomainTarget("");
                }
            }
        };

        checkActiveJob();
    }, [
        reconnectToActiveJob, addNotification, setStep, setConfirmedBrand, setConfirmedLogo,
        setCnpj, setDomainTarget, setCurrentOrgId, setChatOrgId, loadStoredHierarchy, setShouldFitView, pathname
    ]);

    // Sincroniza a empresa baseando-se no pathname (URL) ao navegar entre rotas
    useEffect(() => {
        if (!hasAttemptedReconnect.current) return;

        const match = pathname.match(/\/org\/(\d+)/);
        console.log(`[Router Sync Effect] pathname: "${pathname}", match: ${match ? match[1] : 'null'}`);
        if (match && match[1]) {
            const orgId = parseInt(match[1]);
            if (currentOrgId !== orgId) {
                console.log(`[Router Sync] Navigating from org ${currentOrgId} to ${orgId}. Clearing old organization state immediately.`);
                
                // Immediately reset states so that no stale organization cache is displayed
                resetHierarchy();
                setCurrentOrgId(orgId);
                setChatOrgId(orgId);
                useChatStore.getState().setCurrentOrgId(orgId);

                // Reset Discovery workflow states immediately
                setStep("input");
                setCnpj("");
                setDomainTarget("");
                setConfirmedBrand("");
                setConfirmedLogo("");
                setBrandOptions([]);

                const syncOrgFromUrl = async () => {
                    try {
                        let org = pipedriveOrgs.find(o => Number(o.id) === orgId);
                        if (!org) {
                            const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
                            if (cachedOrgsStr) {
                                try {
                                    const list = JSON.parse(cachedOrgsStr);
                                    if (Array.isArray(list)) {
                                        org = list.find((o: any) => Number(o.id) === orgId || Number(o.pipedrive_id) === orgId || Number(o.local_id) === orgId);
                                    }
                                } catch (e) {
                                    console.error(e);
                                }
                            }
                        }
                        if (!org) {
                            const { organizations } = await import('@/services/api');
                            const res = await organizations.getOrganizationDetails(orgId);
                            if (res && res.org) org = res.org;
                        }

                        if (org) {
                            console.log(`[Router Sync] Organization details fetched for org ${orgId}. Applying details.`);
                            localStorage.setItem('last-viewed-org', JSON.stringify(org));

                            const jobDataStr = localStorage.getItem('active-discovery-job');
                            if (jobDataStr) {
                                try {
                                    const jobData = JSON.parse(jobDataStr);
                                    if (Number(jobData.orgId) === orgId) {
                                        setStep("loading");
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
                                        if (reconnected) return;
                                        setStep("initial");
                                    }
                                } catch (e) {
                                    console.error(e);
                                }
                            }

                            const data = await loadStoredHierarchy(orgId, true);
                            const hasNodes = data && data.nodes && data.nodes.length > 0;

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
                        } else {
                            console.warn(`[Router Sync] Organization details NOT found for org ${orgId}. Leaving UI cleared.`);
                        }
                    } catch (e) {
                        console.error(e);
                    }
                };
                void syncOrgFromUrl();
            }
        }
    }, [pathname, currentOrgId, pipedriveOrgs, resetHierarchy, setNodes, setEdges, loadStoredHierarchy, setConfirmedBrand, setConfirmedLogo, setCnpj, setDomainTarget, setConfirmedLinkedInUrl, setStep, setShouldFitView, setProductFocus, setAreaFocus, reconnectToActiveJob, addNotification]);

    // Handlers
    const handleOrgClick = useCallback(async (org: any, openChat = false) => {
        router.push(`/org/${org.id}`);
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
                isScanActive={isScanForCurrentOrg && scan.isScanning}
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
                            uniqueStages={uniqueStages}
                            activeStageFilter={activeStageFilter}
                            onNavigateToRoot={handleNavigateToRoot}
                            setActiveStageFilter={setActiveStageFilter}
                            totalOrgsCount={pipedriveOrgs.length}
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
                                        fitViewHandler={<FitViewHandler shouldFitView={shouldFitView} nodes={nodes} setShouldFitView={setShouldFitView} />}
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
                                            isScanForCurrentOrg && scan.isScanning ? (
                                                <ScanTerminalPanel consoleLogs={scan.consoleLogs} isVisible={true} />
                                            ) : undefined
                                        }
                                        scanPreview={
                                            isScanForCurrentOrg && scan.isScanning ? (
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
                                        isScanning={isScanForCurrentOrg && scan.isScanning}
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
                                                            name: p.name,
                                                            logo: getAvatarUrl(p),
                                                            followers: p.department || 'Pendente',
                                                            type: 'person',
                                                            id: p.id,
                                                            originalEmployee: p,
                                                            // Expõe o LinkedIn real para o NormalToolbar usar diretamente via opt.url
                                                            url: p.linkedin_url || p.linkedin || p.url || undefined,
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
                                <MessagesView key={`${pathname}?view=messages`} onBack={() => setActiveView('graph')} orgId={currentOrgId} />
                            )}
                            {activeView === 'ligacao' && (
                                <LigacaoView onBack={() => setActiveView('graph')} initialData={ligacaoData} />
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
                                    // Só expõe o estado do scan se ele pertencer à empresa atual
                                    isScanning={isScanForCurrentOrg && scan.isScanning}
                                    scanProgress={isScanForCurrentOrg ? scan.scanProgress : 0}
                                    consoleLogs={isScanForCurrentOrg ? scan.consoleLogs : []}
                                    hasPreview={isScanForCurrentOrg && scan.hasPreview}
                                    previewUrl={isScanForCurrentOrg ? scan.previewUrl : ''}
                                    scanResults={isScanForCurrentOrg ? scan.scanResults : []}
                                    scanError={isScanForCurrentOrg ? scan.scanError : null}
                                    onStartScan={(url, cookie) => {
                                        if (currentOrgId) {
                                            scan.startScan(currentOrgId, url, cookie, areaFocus, productFocus, selectedModel);
                                        }
                                    }}
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
