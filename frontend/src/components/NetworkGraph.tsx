"use client";

import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import ReactFlow, {
    Controls,
    useNodesState,
    useEdgesState,
    applyNodeChanges,
    applyEdgeChanges,
    Node,
    Edge,
    NodeChange,
    EdgeChange,
    Background,
    BackgroundVariant,
    useStore,
    useReactFlow,
    Connection,
    addEdge
} from 'reactflow';
import { Users, PanelRight, PanelRightOpen, LogOut } from 'lucide-react';
import { getAvatarUrl, getProxiedUrl } from '../utils/avatarUtils';

import 'reactflow/dist/style.css';
import { ConfirmModal } from './ConfirmModal';
import styles from './NetworkGraph.module.css';

import { FloatingToolbar } from './FloatingToolbar';
import { SupplyChainNode } from './nodes/SupplyChainNode';
import { getLayoutedElements, calculateEdges } from '@/utils/layout';
import { useHierarchy } from '@/hooks/useHierarchy';

// Modular Components
import { Sidebar } from './Sidebar';
import { ProspectingView } from './prospecting/ProspectingView';
import { Header } from './Header';
import { Drawer } from './Drawer';
import { ChatPanel } from './ChatPanel';
import { TriggerNotifications } from './TriggerNotifications';
import { API_BASE_URL } from '@/services/config';
import { WhatsAppView } from './WhatsAppView';
import { PreferencesView } from './PreferencesView';
import { NotificationContainer, NotificationType } from './Notification';
import { organizations as orgsApi, hierarchy as hierarchyApi, api } from '@/services/api';
import { useProspecting } from '@/hooks/useProspecting';


// --- SMART BACKGROUND COMPONENT ---
// This component adjusts the grid gap based on zoom to prevent it from becoming too dense when zooming out.
const SmartBackground = () => {
    // Get the current zoom from the ReactFlow store
    const transform = useStore((s) => s.transform);
    const zoom = transform[2];

    // Calculate a gap that stops shrinking after zoom 0.5
    // Visual gap = gap * zoom. If we want visual gap >= 20px, then gap = 20 / zoom.
    // We'll base it on 40px standard.
    const baseGap = 44;
    const minZoomForScale = 0.5;
    const effectiveGap = zoom < minZoomForScale ? (baseGap * minZoomForScale) / zoom : baseGap;

    return (
        <Background
            variant={BackgroundVariant.Lines}
            gap={effectiveGap}
            size={1}
            color="rgba(255, 255, 255, 0.05)"
        />
    );
};

// --- FIT VIEW HANDLER (dentro do ReactFlow context) ---
const FitViewHandler = ({ shouldFitView, nodes }: { shouldFitView: boolean; nodes: Node[] }) => {
    const { fitView } = useReactFlow();
    useEffect(() => {
        if (shouldFitView && nodes.length > 0) {
            setTimeout(() => {
                fitView({ padding: 0.2, duration: 800 });
            }, 100);
        }
    }, [shouldFitView, nodes, fitView]);

    return null; // Componente invisível, apenas gerencia o fitView
};

// Movido para fora do componente para evitar o warning #002 do React Flow
// Congelado para garantir estabilidade absoluta através de renders
const nodeTypes = Object.freeze({
    supplyChain: SupplyChainNode
});

// Edge types também congelados para estabilidade
const edgeTypes = Object.freeze({});

export default function NetworkGraph({ defaultCnpj = "", onLogout }: { defaultCnpj?: string, onLogout?: () => void }) {

    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);

    const onNodesChange = useCallback(
        (changes: NodeChange[]) => {
            setNodes((nds) => {
                const nextNodes = applyNodeChanges(changes, nds);
                return nextNodes;
            });

            // Depois que reagiu state asiosamente dispara update
            setTimeout(() => {
                setNodes((currentNds) => {
                    let cacheId = "default";
                    try {
                        const raw = localStorage.getItem('last-viewed-org');
                        if (raw && raw !== "NaN" && raw !== "undefined") {
                            const lObj = JSON.parse(raw);
                            if (lObj.id) cacheId = lObj.id.toString();
                            else if (lObj.name) cacheId = lObj.name;
                        }
                    } catch (e) { }

                    const positionsCacheKey = `layout-cache-${cacheId}`;
                    let cachedPositions: Record<string, { x: number, y: number }> = {};

                    try {
                        const cached = localStorage.getItem(positionsCacheKey);
                        if (cached) cachedPositions = JSON.parse(cached);
                    } catch (e) { }

                    const getStableId = (n: any) => n?.data?.linkedin || n?.data?.name || n?.id;

                    // Somente os nós que estão renderizados agora
                    currentNds.forEach(node => {
                        // Não salvar posições de nós que estão selecionados se for apenas um select
                        cachedPositions[getStableId(node)] = { x: node.position.x, y: node.position.y };
                    });

                    localStorage.setItem(positionsCacheKey, JSON.stringify(cachedPositions));
                    return currentNds;
                });
            }, 100);
        },
        [setNodes]
    );

    const onEdgesChange = useCallback(
        (changes: EdgeChange[]) => {
            setEdges((eds) => {
                const nextEdges = applyEdgeChanges(changes, eds);

                // Salvar edições de conexões no localStorage
                setTimeout(() => {
                    let cacheId = "default";
                    try {
                        const raw = localStorage.getItem('last-viewed-org');
                        if (raw && raw !== "NaN" && raw !== "undefined") {
                            const lObj = JSON.parse(raw);
                            if (lObj.id) cacheId = lObj.id.toString();
                            else if (lObj.name) cacheId = lObj.name;
                        }
                    } catch (e) { }

                    const edgesCacheKey = `edges-cache-${cacheId}`;
                    const customEdges: Record<string, string> = {};

                    // Usar setNodes de forma não intrusiva apenas para ler a lista atual de nós
                    setNodes(currentNds => {
                        const getStableId = (n: any) => n?.data?.linkedin || n?.data?.name || n?.id;

                        currentNds.forEach(node => {
                            const incomingEdge = nextEdges.find(e => e.target === node.id);
                            if (incomingEdge) {
                                const parentNode = currentNds.find(n => n.id === incomingEdge.source);
                                customEdges[getStableId(node)] = parentNode ? getStableId(parentNode) : incomingEdge.source;
                            } else {
                                customEdges[getStableId(node)] = "NONE";
                            }
                        });
                        localStorage.setItem(edgesCacheKey, JSON.stringify(customEdges));
                        return currentNds;
                    });
                }, 100);

                return nextEdges;
            });
        },
        [setEdges, setNodes]
    );

    const onConnect = useCallback(
        (params: Connection) => {
            setEdges((eds) => {
                // A node typically only has one manager, so we remove any existing incoming edge to the target
                const filteredEdges = eds.filter(e => e.target !== params.target);
                const nextEdges = addEdge(
                    { ...params, animated: false, style: { stroke: '#6e7681', strokeWidth: 1.5 } },
                    filteredEdges
                );

                setTimeout(() => {
                    let cacheId = "default";
                    try {
                        const raw = localStorage.getItem('last-viewed-org');
                        if (raw && raw !== "NaN" && raw !== "undefined") {
                            const lObj = JSON.parse(raw);
                            if (lObj.id) cacheId = lObj.id.toString();
                            else if (lObj.name) cacheId = lObj.name;
                        }
                    } catch (e) { }

                    const edgesCacheKey = `edges-cache-${cacheId}`;
                    const customEdges: Record<string, string> = {};

                    setNodes(currentNds => {
                        const getStableId = (n: any) => n?.data?.linkedin || n?.data?.name || n?.id;

                        currentNds.forEach(node => {
                            const incomingEdge = nextEdges.find(e => e.target === node.id);
                            if (incomingEdge) {
                                const parentNode = currentNds.find(n => n.id === incomingEdge.source);
                                customEdges[getStableId(node)] = parentNode ? getStableId(parentNode) : incomingEdge.source;
                            } else {
                                customEdges[getStableId(node)] = "NONE";
                            }
                        });
                        localStorage.setItem(edgesCacheKey, JSON.stringify(customEdges));
                        return currentNds;
                    });
                }, 100);

                return nextEdges;
            });
        },
        [setEdges, setNodes]
    );
    const [theme, setTheme] = useState("dark");
    const [step, setStep] = useState("input");


    const [cnpj, setCnpj] = useState(defaultCnpj);
    const [domainTarget, setDomainTarget] = useState("");
    const [productFocus, setProductFocus] = useState("");
    const [currentOrgId, setCurrentOrgId] = useState<number | null>(null);
    const [refreshDrawerTrigger, setRefreshDrawerTrigger] = useState(0);
    const [confirmedBrand, setConfirmedBrand] = useState("");
    const [confirmedLogo, setConfirmedLogo] = useState("");
    const [confirmedFollowers, setConfirmedFollowers] = useState("");
    const [areaFocus, setAreaFocus] = useState<"compras" | "logistica">("compras");
    const [partners, setPartners] = useState<any[]>([]);

    // 🔄 Guardar estado anterior para poder restaurar quando volta
    const [previousSearchState, setPreviousSearchState] = useState<{
        brandOptions: any[];
        cnpj: string;
        domainTarget: string;
    } | null>(null);

    const [prospectHoveredLeadId, setProspectHoveredLeadId] = useState<string | null>(null);

    // 🛡️ FLAG para evitar reconexão infinita
    const hasAttemptedReconnect = useRef(false);

    // 🎨 THEME PERSISTENCE
    useEffect(() => {
        const savedTheme = localStorage.getItem("preferred-theme") || "dark";
        setTheme(savedTheme);
        document.documentElement.setAttribute("data-theme", savedTheme);
    }, []);

    const {
        rawEmployees, rawBackendEdges, loading, discovering, brandOptions, error, setError,
        activeJobId, fetchHierarchy, stopHierarchyScan, discoverBrand, discoverBrandStream, cancelDiscovery, refineHierarchy, loadStoredHierarchy,
        smartSyncPipedrive, confirmIntelligence, resetHierarchy, reconnectToActiveJob, setBrandOptions, approveCandidate, rejectCandidate
    } = useHierarchy();

    // 🛡️ SEGURANÇA E FORMATAÇÃO
    const sanitizeVal = (val: any) => {
        if (!val || typeof val !== "string") return "";
        const junk = ["not provided", "n/a", "unknown", "null", "none"];
        return junk.includes(val.toLowerCase().trim()) ? "" : val;
    };
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

    // 🟠 PIPEDRIVE SYNC STATE
    const [pipedriveOrgs, setPipedriveOrgs] = useState<any[]>([]);
    const [searchTerm, setSearchTerm] = useState("");
    const [loadingOrgs, setLoadingOrgs] = useState(true);
    const [taskSummary, setTaskSummary] = useState<Record<number, { next_due_date: string; overdue_count: number; pending_count: number }>>({});


    // 💾 PERSISTENCE FOR DRAWER AND CHAT
    const [showDrawer, setShowDrawer] = useState(false);
    const [showChat, setShowChat] = useState(false);
    const [activeView, setActiveView] = useState<'graph' | 'whatsapp' | 'prospecting' | 'preferences'>('graph');
    const prospecting = useProspecting();


    const [activeChatInfo, setActiveChatInfo] = useState<{ name: string, id?: string } | null>(null);

    // 💾 PERSISTENCE FOR DRAWER AND CHAT
    useEffect(() => {
        const savedDrawer = localStorage.getItem("show-drawer") === "true";
        const savedChat = localStorage.getItem("show-chat") === "true";
        setShowDrawer(savedDrawer);
        setShowChat(savedChat);
    }, []);

    // Centraliza as notificações de prospecção
    useEffect(() => {
        if (prospecting.error) {
            addNotification('error', prospecting.error);
        }
    }, [prospecting.error]);

    // Garante que leads pendentes sejam carregados ao abrir a view de prospecção
    useEffect(() => {
        if (activeView === 'prospecting' && prospecting.leads.length === 0 && !prospecting.searching) {
            prospecting.refreshPendingLeads();
        }
    }, [activeView]);

    const handleProspectSearch = async () => {
        try {
            await prospecting.startSearch();
        } catch (e: any) {
            if (!prospecting.error) addNotification('error', e.message || "Erro ao iniciar busca");
        }
    };

    const handleProspectCepLookup = async (cep: string) => {
        if (prospecting.leads.some(l => l.status === 'pending')) return;
        try {
            await prospecting.lookupCep(cep);
        } catch (e: any) {
            if (!prospecting.error) addNotification('error', e.message || "Erro ao buscar CEP");
        }
    };

    const handleProspectMapClick = (coords: { lat: number; lng: number }) => {
        if (prospecting.leads.some(l => l.status === 'pending')) return;
        prospecting.setCoords(coords);
    };

    // Sync Drawer state to localStorage
    const handleSetShowDrawer = (val: boolean) => {
        setShowDrawer(val);
        localStorage.setItem("show-drawer", val.toString());
    };

    // Sync Chat state to localStorage
    const handleSetShowChat = (val: boolean) => {
        setShowChat(val);
        localStorage.setItem("show-chat", val.toString());
    };

    const [enrichingIds, setEnrichingIds] = useState<Set<number>>(new Set());
    const [shouldFitView, setShouldFitView] = useState(false);

    // 🔔 NOTIFICATION STATE
    const [confirmModal, setConfirmModal] = useState<{isOpen: boolean, empId: string | null}>({isOpen: false, empId: null});
    const [notifications, setNotifications] = useState<Array<{ id: string; type: NotificationType; message: string }>>([]);
    const addNotification = useCallback((type: NotificationType, message: string) => {
        const id = Math.random().toString(36).substring(2, 9);
        setNotifications(prev => [...prev, { id, type, message }]);
    }, []);
    const removeNotification = (id: string) => {
        setNotifications(prev => prev.filter(n => n.id !== id));
    };

    const filteredOrgs = useMemo(() => {
        const seen = new Set<number>();
        return pipedriveOrgs
            .filter(org => {
                const id = Number(org.id);
                if (!id || seen.has(id)) return false;
                seen.add(id);
                return (
                    org.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    org.domain?.toLowerCase().includes(searchTerm.toLowerCase())
                );
            })
            .map(org => ({
                ...org,
                _taskSummary: taskSummary[Number(org.id)] || null,
            }))
            .sort((a, b) => {
                const ta = a._taskSummary;
                const tb = b._taskSummary;
                // Sem tarefas vai pro final
                if (!ta && !tb) return 0;
                if (!ta) return 1;
                if (!tb) return -1;
                // Atrasadas primeiro
                const aOverdue = ta.overdue_count > 0;
                const bOverdue = tb.overdue_count > 0;
                if (aOverdue !== bOverdue) return aOverdue ? -1 : 1;
                // Depois por data mais próxima
                return ta.next_due_date.localeCompare(tb.next_due_date);
            });
    }, [pipedriveOrgs, searchTerm, taskSummary]);

    const handleUpdatePipedrive = async (orgId: number, data: any) => {
        try {
            await orgsApi.updateOrganization(orgId, {
                cnpj: data.cnpj,
                domain: data.domain,
                address: data.address,
            });
        } catch (e: any) {
            console.error('Sync error:', (e as Error).message || e);
        }
    };

    useEffect(() => {
        // 🚀 Cache Speed: Tenta carregar do localStorage primeiro
        const cached = localStorage.getItem("pipedrive-orgs-cache");
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    setPipedriveOrgs(parsed);
                    setLoadingOrgs(false);
                    // Não retornamos aqui. Permite que o fetchPipedriveOrgs rode em background
                    // para atualizar silenciosamente com os dados reais do banco (caso o bd tenha sido limpo, etc).
                }
            } catch (e: any) { console.error("Cache parsing error:", (e as Error).message || e); }
        }

        // Sempre busca do backend para garantir dados focados com a realidade
        fetchPipedriveOrgs();
    }, []);

    // 🔄 Verificar se há um job ativo ao montar o componente (apenas uma vez)
    useEffect(() => {
        // Evitar reconexão múltipla
        if (hasAttemptedReconnect.current) return;
        hasAttemptedReconnect.current = true;

        const checkActiveJob = async () => {
            const jobDataStr = localStorage.getItem('active-discovery-job');
            if (jobDataStr) {
                if (jobDataStr === "NaN" || jobDataStr === "undefined") {
                    localStorage.removeItem('active-discovery-job');
                    checkLastOrg();
                    return;
                }
                try {
                    const jobData = JSON.parse(jobDataStr);
                    const { brand, orgId } = jobData;

                    console.log(`[Job Check] Detectado Job Ativo para ${brand}. Carregando dados prévios...`);

                    // 1. CARREGAR DADOS DO BANCO IMEDIATAMENTE (Se houver orgId)
                    // Isso garante que os cards apareçam ANTES de qualquer coisa
                    if (orgId) {
                        const data = await loadStoredHierarchy(Number(orgId), true);
                        if (data && data.nodes && data.nodes.length > 0) {
                            console.log(`[Job Check] ${data.nodes.length} nós restaurados do banco.`);
                        }
                    }

                    // 2. Só agora mudamos para o estado visual de mapeamento
                    setStep("scanning");
                    setConfirmedBrand(brand);
                    if (orgId) setCurrentOrgId(orgId);

                    // 3. Reconectar ao WebSocket para continuar recebendo novos nós
                    const reconnected = await reconnectToActiveJob((type, msg) => {
                        addNotification(type, msg);
                    });

                    if (!reconnected) {
                        console.warn("[Job Check] Job expirou no backend.");
                        setStep("confirm"); // Mantém o que carregou do banco mas sai do modo scanning
                    }
                } catch (e: any) {
                    console.error("[Job Check] Erro na reconexão:", e);
                    localStorage.removeItem('active-discovery-job');
                    checkLastOrg();
                }
            } else {
                checkLastOrg();
            }
        };

        const checkLastOrg = async () => {
            const lastOrgStr = localStorage.getItem('last-viewed-org');
            if (lastOrgStr) {
                if (lastOrgStr === "NaN" || lastOrgStr === "undefined") {
                    localStorage.removeItem('last-viewed-org');
                    setConfirmedBrand(" ");
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
                    console.error("[Last Org Check] Erro ao verificar last-viewed-org:", (e as Error).message || e);
                    setConfirmedBrand(" "); // Sentinel para ativar modo "Nova Empresa" (Vermelho)
                    setStep("input");
                }
            } else {
                setConfirmedBrand(" "); // Sentinel para ativar modo "Nova Empresa" (Vermelho)
                setStep("input");
            }
        };

        checkActiveJob();
    }, []); // ✅ Dependency array vazio - executa apenas na montagem

    /* === REMOVIDO loop checkActiveJobForOrg pois está nativamente dentro do handleOrgClick gora === */

    const fetchTaskSummary = async () => {
        try {
            const items = await api.get<Array<{
                org_id: number;
                next_due_date: string;
                overdue_count: number;
                pending_count: number;
            }>>('/pipedrive/activities/pending-summary');
            if (Array.isArray(items)) {
                const map: Record<number, typeof items[0]> = {};
                items.forEach(i => { map[i.org_id] = i; });
                setTaskSummary(map);
            }
        } catch { /* silent — não bloqueia a UI */ }
    };

    const fetchPipedriveOrgs = async () => {
        // Se já temos cache, não limpamos para não dar flicker na UI
        if (pipedriveOrgs.length === 0) setLoadingOrgs(true);
        try {
            // Sincronização em background (Pipedrive -> DB Local) — fire & forget
            orgsApi.triggerPipedriveSync().catch(() => { /* silent */ });

            const data = await orgsApi.listOrganizations();
            console.log('[Pipedrive API] Data Received:', data);
            
            // 🔝 Ordena por ID decrescente para que as novas fiquem no topo
            const list = Array.isArray(data) 
                ? [...data].sort((a: any, b: any) => Number(b.id) - Number(a.id)) 
                : [];
                
            setPipedriveOrgs(list);
            // Busca resumo de tarefas em paralelo
            fetchTaskSummary();

            // Revalida o cache com a versão real do banco
            if (list.length > 0) {
                localStorage.setItem('pipedrive-orgs-cache', JSON.stringify(list));
            } else {
                localStorage.removeItem('pipedrive-orgs-cache');
            }
        } catch (e: any) {
            console.warn('[NetworkGraph] Erro ao carregar empresas do Pipedrive:', (e as Error).message || e);
            if (pipedriveOrgs.length === 0) setPipedriveOrgs([]);
        } finally {
            setLoadingOrgs(false);
        }
    };

    const handleBrandSelect = async (brandObj: any) => {
        console.log("[Graph] handleBrandSelect called with:", brandObj);

        // 🛑 Cancelar o stream de descoberta se ainda estiver em andamento
        if (discovering) {
            console.log("[Graph] Cancelando stream de descoberta...");
            cancelDiscovery();
        }

        if (!brandObj) {
            console.log("[Graph] VOLTAR CLICADO - Verificando se fecha carrossel ou volta step");
            
            // 🔄 Se o carrossel está aberto, o primeiro "Voltar" apenas o fecha
            if (brandOptions.length > 0) {
                setBrandOptions([]);
                // Se não estamos no input, apenas fechamos o carrossel e paramos por aqui
                if (step !== "input") return;
            }

            // Se o carrossel já estava fechado ou se estamos no input, executa a volta completa
            console.log("[Graph] Restaurando estado anterior de busca");
            if (previousSearchState) {
                console.log("[Graph] Restaurando:", previousSearchState);
                setCnpj(previousSearchState.cnpj);
                setDomainTarget(previousSearchState.domainTarget);
                // brandOptions já está no hook, então será mostrado automaticamente
            }
            setConfirmedBrand("");
            setConfirmedLogo("");
            setConfirmedFollowers("");
            setPartners([]);
            setStep("input");
            return;
        }

        // 🛡️ Se for uma PESSOA (Análise Humana), abrimos o perfil para revisão em vez de tratar como marca
        if (brandObj.type === 'person') {
            console.log("[Graph] Reviewing person:", brandObj.name);
            const linkedin = brandObj.originalEmployee?.linkedin || brandObj.originalEmployee?.url;
            if (linkedin && linkedin.startsWith('http')) {
                window.open(linkedin, '_blank');
            } else {
                addNotification('info', `Analisando ${brandObj.name} (LinkedIn não disponível)`);
            }
            return;
        }

        const name = typeof brandObj === 'string' ? brandObj : (brandObj.name || brandObj.url || "");
        const logo = brandObj.logo || "";
        const followers = brandObj.followers || "";
        const partners = brandObj.partners || [];

        console.log("[Graph] Setting Brand Data:", { name, logo, followers, partnersCount: partners.length });

        // 💾 Guardar estado anterior antes de ir para confirm
        console.log("[Graph] Guardando estado anterior para poder voltar depois");
        setPreviousSearchState({
            brandOptions: brandOptions,
            cnpj: cnpj,
            domainTarget: domainTarget
        });

        setConfirmedBrand(cleanName(name));
        setConfirmedLogo(logo);
        setConfirmedFollowers(followers);
        setPartners(partners);
        setStep("confirm");

        // 💾 PERSISTÊNCIA MANUAL: Salva no banco local ao selecionar e Sincroniza UI
        if (cnpj) {
            console.log("[Graph] Persistindo escolha no Banco Local...");
            const result = await confirmIntelligence({
                name: cleanName(name),
                cnpj: cnpj,
                domain: domainTarget,
                address: "", // O backend já tem se for enriquecido
                pipedrive_id: currentOrgId || undefined,
                linkedin_url: brandObj.url || "",
                logo_url: logo,
                partners: partners
            });

            // Se deu sucesso, atualiza a lista do Drawer localmente para evitar duplicados ou dados velhos
            if (result && result.status !== "error") {
                const isUpdate = result.is_update || result.status === "updated" || result.status === "success";
                const newOrgId = result.pipedrive_id || result.local_id; // Depende do que o backend retorna

                if (!currentOrgId && newOrgId) {
                    setCurrentOrgId(Number(newOrgId));
                }

                addNotification('success', isUpdate ? "Empresa atualizada com sucesso!" : "Empresa integrada com sucesso!");

                // Se for uma nova empresa, recarrega a lista
                if (!currentOrgId) {
                    fetchPipedriveOrgs();
                } else {
                    setPipedriveOrgs(prev => prev.map(org =>
                        Number(org.id) === currentOrgId
                            ? { ...org, cnpj, domain: domainTarget, logo: logo, linkedin: brandObj.url, name: cleanName(name) }
                            : org
                    ));
                }
            } else {
                addNotification('error', "Erro ao salvar dados da empresa.");
            }
        }
    };

    const handleOrgClick = async (org: any) => {
        setActiveView('graph'); // 🚀 VOLTAR PARA O MODO GRAFO
        console.log('--- HANDLE ORG CLICK START ---', org.name);
        resetHierarchy(); // 🧹 Limpa os dados do hook
        setNodes([]); // 🧹 Limpa os nodes do grafo
        setEdges([]); // 🧹 Limpa as edges do grafo

        try {
            setCurrentOrgId(Number(org.id));
            localStorage.setItem('last-viewed-org', JSON.stringify(org));

            // 🧹 Reset total de estados antes de carregar a nova empresa
            setStep("input");
            setCnpj("");
            setDomainTarget("");
            setConfirmedBrand("");
            setConfirmedLogo("");
            setPartners([]);
            setError(null);

            if (org.id) {
                // 1. CHECAR SE EXISTE JOB ATIVO NESTA EMPRESA
                const jobDataStr = localStorage.getItem('active-discovery-job');
                if (jobDataStr) {
                    try {
                        const jobData = JSON.parse(jobDataStr);
                        if (jobData.orgId === Number(org.id)) {
                            // Mudar o state pra loading imediatamente
                            setStep("loading");
                            const reconnected = await reconnectToActiveJob((type, msg) => {
                                addNotification(type, msg);
                            });

                            if (reconnected) {
                                console.log('[NetworkGraph] Reconectado com sucesso através do onClick no Drawer.');
                                return; // Se reconectou com sucesso, encerra e deixa a UI em "loading"
                            } else {
                                setStep("initial");
                            }
                        }
                    } catch (e: any) {
                        console.error("[Job Check] Erro de parse no jobData ao interagir com org:", (e as Error).message || e);
                    }
                }

                // 2. SE NÃO TIVER JOB ATIVO, CARREGA OS DADOS SALVOS NORMALMENTE
                console.log('Attempting to load hierarchy for pipedrive_id:', org.id);
                const data = await loadStoredHierarchy(Number(org.id), true);
                const hasNodes = data && data.nodes && data.nodes.length > 0;
                const isProspecting = org.source === "prospecting";

                console.log("[Graph] Avaliando estado:", { name: org.name, hasNodes, isProspecting, source: org.source });

                if (hasNodes) {
                    // Já foi mapeada, restaura os dados confirmados
                    setConfirmedBrand(cleanName(org.name || ""));
                    setConfirmedLogo(org.logo || "");
                    setCnpj(formatCnpj(org.cnpj || ""));
                    setDomainTarget(org.domain || "");
                    setStep("confirm");
                    setShouldFitView(true);
                } else if (isProspecting && (org.domain || org.linkedin || org.linkedin_url)) {
                    // É prospecção nova, popula tudo para o usuário clicar em Mapear
                    setConfirmedBrand(cleanName(org.name || ""));
                    setConfirmedLogo(org.logo || "");
                    setCnpj(formatCnpj(org.cnpj || ""));
                    setDomainTarget(org.domain || "");
                    setStep("confirm");
                    console.log("[Graph] Fluxo Prospecção -> confirm");
                } else {
                    // É manual ou vazia, mantém o nome mas deixa o resto para input manual
                    setConfirmedBrand(cleanName(org.name || ""));
                    setConfirmedLogo(org.logo || "");
                    setStep("input");
                    console.log("[Graph] Fluxo Manual -> input");
                }

                // Restaurar foco de produto e área (comum a todos)
                if (org.product_focus) setProductFocus(org.product_focus);
                if (org.category === "compras" || org.category === "logistica") setAreaFocus(org.category);
            }
        } catch (e: any) {
            console.error("Critical error in handleOrgClick:", (e as Error).message || e);
        }
    };

    const handleAutoEnrich = async () => {
        if (!cnpj || enrichingIds.has(999)) return;
        setError(null);
        setEnrichingIds(prev => new Set(prev).add(999));
        try {
            const data = await hierarchyApi.enrichIntelligence({
                name: confirmedBrand.trim() || 'Empresa',
                cnpj,
                force: true,
            });

            if (data.success && data.main_option) {
                const main = data.main_option;
                const cleanDomain = sanitizeVal(main.domain);
                const cleanCnpj = formatCnpj(sanitizeVal(main.cnpj));
                const officialName = sanitizeVal(main.official_name);

                if (cleanDomain) setDomainTarget(cleanDomain);
                if (cleanCnpj) setCnpj(cleanCnpj);

                // 🆕 Se não temos orgId (fluxo nova empresa via botão +),
                // o backend /enrich já criou auto no Pipedrive+DB.
                // Precisamos apenas linkar a UI com o novo org criado.
                if (!currentOrgId && cleanCnpj) {
                    console.log('[NewCompany] Empresa nova detectada. Vinculando UI...');
                    try {
                        // Atualiza a marca se temos um nome oficial
                        if (officialName) setConfirmedBrand(officialName);

                        // Aguarda um momento para o backend processar a criação
                        await new Promise(resolve => setTimeout(resolve, 500));

                        // Recarrega a lista do Drawer para incluir a nova empresa
                        await fetchPipedriveOrgs();

                        // Busca a nova org na lista para vincular ao estado
                        const rawCnpjClean = cleanCnpj.replace(/\D/g, '');
                        const orgsList = await orgsApi.listOrganizations();
                        const newOrg = Array.isArray(orgsList)
                            ? orgsList.find((o: any) => o.cnpj && o.cnpj.replace(/\D/g, '') === rawCnpjClean)
                            : null;

                        if (newOrg) {
                            setCurrentOrgId(Number(newOrg.id));
                            localStorage.setItem('last-viewed-org', JSON.stringify(newOrg));
                            if (newOrg.logo) setConfirmedLogo(newOrg.logo);
                            console.log(`[NewCompany] Vinculada! Pipedrive ID: ${newOrg.id}`);
                            addNotification('success', `Empresa '${officialName || "Nova Empresa"}' integrada com sucesso!`);
                        } else {
                            console.log("[NewCompany] Org não encontrada na lista (pode não ter sido criada no Pipedrive).");
                            addNotification('info', `Dados encontrados para o CNPJ. Prossiga com a busca.`);
                        }
                    } catch (linkErr) {
                        console.error("[NewCompany] Erro ao vincular empresa:", linkErr);
                    }
                }
            } else {
                setError("Dados não encontrados para este CNPJ.");
            }
        } catch (err) {
            setError("Erro ao consultar inteligência.");
        } finally {
            setEnrichingIds(prev => {
                const n = new Set(prev);
                n.delete(999);
                return n;
            });
        }
    };

    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        // Removed setConfirmedBrand(""); to ensure the name stays pinned in the header

        if (step === "input") {
            if (!domainTarget && !confirmedBrand) {
                setError("Insira o Domínio ou o Nome para busca no LinkedIn");
                return;
            }
            try {
                // 🔄 Usar streaming para mostrar candidatos conforme são encontrados
                await discoverBrandStream(cnpj, domainTarget, true, (candidate: any) => {
                    console.log(`[UI] Novo perfil encontrado: ${candidate.name}`);
                    // O brandOptions já será atualizado via setState no hook
                });

                // Se recebemos candidatos, o carrossel será atualizado via brandOptions
            } catch (err) {
                setError("Erro de conexão.");
            }
        } else if (step === "confirm" || step === "scanning") {
            if (!confirmedBrand) { setError("Marca inválida."); return; }

            setStep("scanning");
            setRefreshDrawerTrigger(prev => prev + 1); // Recarrega/Zera o drawer

            // Só mandamos raiz e sócios, para "zerar" os outros funcionarios já mapeados
            const rootAndPartnersOnly = rawEmployees.filter(emp => {
                const isRoot = emp.id === 'root_company' || emp.level === 0;
                const isPartner = emp.level === 6 || String(emp.id).startsWith('partner_');
                const isPartnerDept = emp.department && (
                    emp.department.includes('QSA') ||
                    emp.department.includes('Sócio') ||
                    emp.department.includes('Societário') ||
                    emp.department.includes('Conselho')
                );
                const isPartnerRole = emp.role && (
                    emp.role.includes('Sócio') ||
                    emp.role.includes('Conselho') ||
                    emp.role.includes('Board') ||
                    emp.role.includes('Fundador')
                );

                return isRoot || isPartner || isPartnerDept || isPartnerRole;
            });

            fetchHierarchy(
                cnpj,
                domainTarget,
                confirmedBrand,
                confirmedLogo,
                productFocus,
                areaFocus,
                addNotification,
                partners,
                currentOrgId,
                rootAndPartnersOnly // Passa só a raiz e sócios. O resto vai ser recarregado/reencontrado
            );
        }
    };

    useEffect(() => {
        if (rawEmployees.length === 0) return;

        // 🕵️ Filtrar 'Análise Humana' dos nós do grafo principal para não poluir
        const humanAnalysisCandidates = rawEmployees.filter(emp => emp.role === "Análise Humana");
        const visibleEmployees = rawEmployees.filter(emp => emp.role !== "Análise Humana");

        let uiNodes: Node[] = visibleEmployees.map(emp => {
            const isRootNode = emp.id === 'root_company' || emp.level === 0;
            return {
                id: emp.id,
                type: 'supplyChain',
                // Default temporário (será sobrescrito pelo getLayoutedElements se for node novo, ou local storage se já existir)
                position: { x: 0, y: 0 },
                data: { ...emp, isRoot: isRootNode, confirmedLogo: isRootNode ? confirmedLogo : undefined },
            };
        });

        let finalEdges = calculateEdges(uiNodes, rawBackendEdges);
        const getStableId = (n: any) => n?.data?.linkedin || n?.data?.name || n?.id;

        // Puxa as conexões manuais do cache
        const edgesCacheKey = `edges-cache-${currentOrgId || confirmedBrand}`;
        let cachedEdges: Record<string, string> | null = null;
        try {
            const cacheRaw = localStorage.getItem(edgesCacheKey);
            if (cacheRaw) cachedEdges = JSON.parse(cacheRaw);
        } catch (e) { }

        if (cachedEdges) {
            // Remove qualquer aresta do backend cujo filho/target foi reposicionado manualmente
            finalEdges = finalEdges.filter(e => {
                const childNode = uiNodes.find(n => n.id === e.target);
                const childStableId = childNode ? getStableId(childNode) : e.target;
                return !(childStableId in cachedEdges!);
            });

            // Adiciona as arestas customizadas
            Object.entries(cachedEdges).forEach(([childStableId, parentStableId]) => {
                if (parentStableId !== "NONE") {
                    const childNode = uiNodes.find(n => getStableId(n) === childStableId);
                    const parentNode = uiNodes.find(n => getStableId(n) === parentStableId);

                    if (childNode && parentNode) {
                        finalEdges.push({
                            id: `e-${parentNode.id}-${childNode.id}`,
                            source: parentNode.id,
                            target: childNode.id,
                            animated: false,
                            style: { stroke: '#6e7681', strokeWidth: 1.5 },
                        });
                    }
                }
            });
        }

        // Puxa o cache de posições manuais ou anteriores do localStorage
        const layoutCacheKey = `layout-cache-${currentOrgId || confirmedBrand}`;
        let cachedPositions: Record<string, { x: number, y: number }> = {};

        try {
            const cacheRaw = localStorage.getItem(layoutCacheKey);
            if (cacheRaw) cachedPositions = JSON.parse(cacheRaw);
        } catch (e) { }

        const nodesSemCache = uiNodes.filter(n => !cachedPositions[getStableId(n)]);
        const nodesComCache = uiNodes.filter(n => !!cachedPositions[getStableId(n)]);

        let finalNodes: Node[] = [];

        // Roda o algoritmo Dagre APENAS para os nós que NÃO tem posição salva no cache
        if (nodesSemCache.length > 0) {
            // Dá um "sub-layout" só para os novatos baseado no root, ou no grafo todo 
            // Para não quebrar o design do Dagre, passamos tudo pro Dagre, mas depois 
            // restauramos a posição exata X,Y dos que já estavam no cache.
            const { layoutedNodes, layoutedEdges } = getLayoutedElements(uiNodes, finalEdges);

            finalNodes = layoutedNodes.map(node => {
                const stableId = getStableId(node);
                if (cachedPositions[stableId]) {
                    // Se existia no cache, ignora a imposição do Dagre e trava de volta no lugar salvo
                    return { ...node, position: cachedPositions[stableId] };
                }
                // Se é novo, adota X,Y gerado agora e já guarda no cache pra próxima vez
                cachedPositions[stableId] = node.position;
                return node;
            });

            setEdges(layoutedEdges);
        } else {
            // Todo mundo já tinha cache
            finalNodes = uiNodes.map(n => ({ ...n, position: cachedPositions[getStableId(n)] }));
            setEdges(finalEdges);
        }

        // Salva as posições atualizadas para o futuro
        localStorage.setItem(layoutCacheKey, JSON.stringify(cachedPositions));

        setNodes(finalNodes);
    }, [rawEmployees, rawBackendEdges, setNodes, setEdges, currentOrgId, confirmedBrand, confirmedLogo]);

    const handleCopyData = () => {
        if (rawEmployees.length === 0) {
            console.warn("Sem dados para copiar.");
            return;
        }
        // Formatar para JSON legível
        const dataStr = JSON.stringify(rawEmployees, null, 2);
        navigator.clipboard.writeText(dataStr).then(() => {
            console.log("[Debug] Dados da hierarquia copiados.");
        }).catch(err => {
            console.error("Erro ao copiar para clipboard:", err);
        });
    };

    const toggleTheme = () => {

        const next = theme === "dark" ? "light" : "dark";
        setTheme(next);
        localStorage.setItem("preferred-theme", next);
        document.documentElement.setAttribute("data-theme", next);
    };

    const handleOrgReset = (orgId: number) => {
        console.log(`[Graph] Resetando UI para organização ${orgId}...`);

        // 🚀 Atualização Reativa: Remove imediatamente da lista local para que suma do Drawer sem delay
        setPipedriveOrgs(prev => prev.filter(org => Number(org.id) !== orgId && Number(org.local_id) !== orgId));

        // 🧹 Limpar absolutamente tudo quando dados são resetados
        setNodes([]);
        setEdges([]);
        setStep("input");
        setCnpj("");
        setDomainTarget("");
        setProductFocus("");
        setConfirmedBrand("");
        setConfirmedLogo("");
        setConfirmedFollowers("");
        setPartners([]);
        setPreviousSearchState(null);
        resetHierarchy();
        localStorage.removeItem('last-viewed-org');

        // 🗑️ Limpar cache local (localStorage)
        const cacheKeys = [
            `org-${orgId}-details`,
            `org-${orgId}-logo`,
            `org-${orgId}-hierarchy`,
            `hierarchy-${orgId}`,
            `stored-hierarchy-${orgId}`,
            `edges-cache-${orgId}`,
            `layout-cache-${orgId}`
        ];
        cacheKeys.forEach(key => {
            if (localStorage.getItem(key)) {
                localStorage.removeItem(key);
                console.log(`[LocalStorage] Removido: ${key}`);
            }
        });

        console.log("[Graph] UI, lista e cache completamente resetados");
    };

    const handleOrgRenamed = (orgId: number, newName: string) => {
        // 🔄 Atualizar pipedriveOrgs
        setPipedriveOrgs(prev =>
            prev.map(org =>
                Number(org.id) === orgId ? { ...org, name: newName } : org
            )
        );

        // 💾 Atualizar cache no localStorage
        const cached = localStorage.getItem("pipedrive-orgs-cache");
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                const updated = parsed.map((org: any) =>
                    Number(org.id) === orgId ? { ...org, name: newName } : org
                );
                localStorage.setItem("pipedrive-orgs-cache", JSON.stringify(updated));
                console.log(`[Graph] Nome da empresa ${orgId} atualizado em cache`);
            } catch (e: any) {
                console.error("Erro ao atualizar cache:", (e as Error).message || e);
            }
        }
    };

    return (
        <>
        <div className={styles.container}>
            <Sidebar
                showDrawer={showDrawer}
                setShowDrawer={handleSetShowDrawer}
                theme={theme}
                onToggleTheme={toggleTheme}
                onReset={() => {
                    // 🧹 Limpar Canvas: Limpa grafo e toolbar
                    setNodes([]);
                    setEdges([]);
                    setStep("input");
                    setCnpj("");
                    setDomainTarget("");
                    setProductFocus("");
                    setConfirmedBrand("");
                    setConfirmedLogo("");
                    setConfirmedFollowers("");
                    setPartners([]);
                    setCurrentOrgId(null);
                    setPreviousSearchState(null);
                    resetHierarchy();
                    setActiveView('graph');
                    setActiveChatInfo(null);
                    localStorage.removeItem('last-viewed-org');
                }}
                onCopyData={handleCopyData}
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
                onOpenProspecting={() => setActiveView(v => v === 'prospecting' ? 'graph' : 'prospecting')}
                isProspecting={activeView === 'prospecting'}
                onOpenPreferences={() => setActiveView(v => v === 'preferences' ? 'graph' : 'preferences')}
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
                                handleSetShowChat(true);
                                handleOrgClick({ id: orgId, name: orgName });
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
                                    color: showChat ? 'rgba(255, 255, 255, 1)' : 'rgba(255, 255, 255, 0.6)' 
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
                                    color: 'rgba(255, 255, 255, 0.6)',
                                    transition: 'all 0.2s ease',
                                }}
                                onMouseEnter={(e) => {
                                    e.currentTarget.style.color = '#f87171';
                                    e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)';
                                }}
                                onMouseLeave={(e) => {
                                    e.currentTarget.style.color = 'rgba(255, 255, 255, 0.6)';
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
                    {(activeView === 'graph' || activeView === 'prospecting') && (
                        <Drawer
                            showDrawer={showDrawer}
                            setShowDrawer={handleSetShowDrawer}
                            searchTerm={searchTerm}
                            setSearchTerm={setSearchTerm}
                            filteredOrgs={filteredOrgs}
                            onOrgClick={handleOrgClick}
                            onOrgReset={handleOrgReset}
                            onOrgRenamed={handleOrgRenamed}
                            isLoading={loadingOrgs}
                            selectedOrgId={currentOrgId}
                            selectedOrgLogo={confirmedLogo}
                            activeJobId={activeJobId}
                            graphEmployees={rawEmployees}
                            refreshDetailsTrigger={refreshDrawerTrigger}
                            addNotification={addNotification}
                        />
                    )}

                    <main className={styles.mainContent}>
                        <NotificationContainer
                            notifications={notifications}
                            removeNotification={removeNotification}
                        />

                        <div className={styles.graphWrapper}>
                            {activeView === 'graph' && (
                                <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', position: 'relative' }}>
                                    <Header confirmedBrand={confirmedBrand} />
                                    <div style={{ flex: 1, position: 'relative' }}>
                                        <ReactFlow
                                    nodes={nodes}
                                    edges={edges}
                                    nodeTypes={nodeTypes}
                                    edgeTypes={edgeTypes}
                                    onNodesChange={onNodesChange}
                                    onEdgesChange={onEdgesChange}
                                    onConnect={onConnect}
                                    fitView
                                    minZoom={0.1}
                                    maxZoom={1.5}
                                >
                                    <SmartBackground />
                                    <FitViewHandler shouldFitView={shouldFitView} nodes={nodes} />
                                    <Controls position="top-right" />
                                        </ReactFlow>
                                    </div>
                                </div>
                            )}
                            {activeView === 'whatsapp' && (
                                <div className={styles.whatsappContainer} style={{ height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#131313' }}>
                                    <WhatsAppView
                                        chatName={activeChatInfo?.name || "WhatsApp"}
                                        chatId={activeChatInfo?.id}
                                        onBack={() => setActiveView('graph')}
                                    />
                                </div>
                            )}
                            {activeView === 'prospecting' && (
                                <ProspectingView
                                    coords={prospecting.coords}
                                    onMapClick={handleProspectMapClick}
                                    radiusKm={prospecting.radiusKm}
                                    leads={prospecting.leads}
                                    selectedLead={prospecting.selectedLead}
                                    onLeadClick={lead => prospecting.setSelectedLead(
                                        prev => prev?.id === lead.id ? null : lead
                                    )}
                                    onLeadClose={() => prospecting.setSelectedLead(null)}
                                    onApproveLead={prospecting.approveLead}
                                    onRejectLead={prospecting.rejectLead}
                                    onLeadHover={(lead) => setProspectHoveredLeadId(lead?.id || null)}
                                    session={prospecting.session}
                                />
                            )}
                            {activeView === 'preferences' && (
                                <PreferencesView onBack={() => setActiveView('graph')} />
                            )}
                        </div>

                        {activeView === 'prospecting' && (
                            <div className={styles.bottomToolbarRow}>
                                <FloatingToolbar
                                    isProspectingMode
                                    prospectCoords={prospecting.coords}
                                    prospectRadiusKm={prospecting.radiusKm}
                                    onProspectRadiusChange={prospecting.setRadiusKm}
                                    onProspectGeolocate={prospecting.geolocate}
                                    prospectGeoLoading={prospecting.geoLoading}
                                    onProspectSearch={handleProspectSearch}
                                    onProspectStop={prospecting.stopSearch}
                                    onProspectCepLookup={handleProspectCepLookup}
                                    prospectCityName={prospecting.cityName}
                                    prospectSearching={prospecting.searching}
                                    prospectSession={prospecting.session ?? undefined}
                                    prospectLeadsCount={prospecting.leads.length}
                                    prospectTierACount={prospecting.leads.filter(l => l.icp_tier === 'A').length}
                                    prospectPendingLeads={prospecting.leads.filter(l => l.status === 'pending')}
                                    onProspectSelectLead={prospecting.setSelectedLead}
                                    prospectError={prospecting.error}
                                    prospectSelectedLead={prospecting.selectedLead}
                                    prospectHoveredLeadId={prospectHoveredLeadId}
                                    onProspectApproveLead={async (id) => {
                                        try {
                                            await prospecting.approveLead(id);
                                            addNotification('success', "Empresa aprovada e enviada ao Pipedrive!");
                                            // 🚀 Atualiza o Drawer imediatamente para mostrar a nova empresa
                                            fetchPipedriveOrgs();
                                        } catch (e: any) {
                                            addNotification('error', e.message);
                                        }
                                    }}
                                    onProspectRejectLead={async (id) => {
                                        try {
                                            await prospecting.rejectLead(id);
                                            addNotification('info', "Empresa descartada do radar.");
                                        } catch (e: any) {
                                            addNotification('error', e.message);
                                        }
                                    }}
                                    onProspectCloseLead={prospecting.setSelectedLead ? () => prospecting.setSelectedLead(null) : undefined}
                                    prospectCep={prospecting.cep}
                                    onProspectCepChange={prospecting.setCep}
                                    // props obrigatórias do toolbar (não usadas no modo prospecção)
                                    error={null} handleSearch={() => {}} cnpj="" setCnpj={() => {}}
                                    confirmedBrand="" setConfirmedBrand={() => {}} confirmedLogo=""
                                    setConfirmedLogo={() => {}} confirmedFollowers="" setConfirmedFollowers={() => {}}
                                    domainTarget="" setDomainTarget={() => {}} productFocus="" setProductFocus={() => {}}
                                    areaFocus="compras" setAreaFocus={() => {}} handleAutoEnrich={() => {}}
                                    enrichingIds={new Set()} discovering={false} loading={false}
                                    step="input" brandOptions={[]} onBrandSelect={() => {}}
                                />
                            </div>
                        )}

                        {activeView === 'graph' && (
                            <div className={styles.bottomToolbarRow}>
                                <FloatingToolbar
                                    error={error}
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
                                    hasMapping={nodes.some(n => n.id.startsWith('node_'))}
                                    stopHierarchyScan={() => stopHierarchyScan(addNotification)}
                                    cancelDiscovery={cancelDiscovery}
                                    activeJobId={activeJobId}
                                    isSidebarOpen={showDrawer} // ✅ Corrigido
                                    isChatOpen={showChat}     // ✅ Corrigido
                                    onApproveCandidate={async (id) => {
                                        try {
                                            await approveCandidate(id);
                                            addNotification('success', "Perfil aprovado e integrado ao grafo.");
                                        } catch(e: any) {
                                            addNotification('error', e.message);
                                        }
                                    }}
                                    onRejectCandidate={async (id) => {
                                        setConfirmModal({ isOpen: true, empId: id });
                                    }}
                                />

                                {/* 🎭 ANÁLISE HUMANA BADGE (Independente) */}
                                {rawEmployees.filter(e => e.role === 'Análise Humana').length > 0 && (
                                    <div 
                                        className={styles.humanAnalysisTrigger} 
                                        onClick={(e) => {
                                            e.stopPropagation();

                                            // 🔄 Lógica de Toggle: Se já estiver mostrando pessoas, fecha ao clicar de novo
                                            const isAlreadyShowingHuman = brandOptions.length > 0 && brandOptions[0]?.type === 'person';
                                            if (isAlreadyShowingHuman) {
                                                setBrandOptions([]);
                                                return;
                                            }

                                            const pending = rawEmployees.filter(e => e.role === 'Análise Humana');
                                            const candidates = pending.map(p => ({
                                                name: p.name,
                                                logo: getAvatarUrl(p),
                                                followers: p.department || (p.role === 'Análise Humana' ? 'Review Pendente' : p.role),
                                                type: 'person',
                                                id: p.id,
                                                originalEmployee: p
                                            }));
                                            setBrandOptions(candidates);
                                            // Mantemos o step atual conforme pedido pelo usuário
                                        }}
                                    >
                                 {(() => {
                                                const humanPending = rawEmployees.filter(e => e.role === 'Análise Humana');
                                                if (humanPending.length === 0) return null;
                                                
                                                // Pegamos até os 3 primeiros para o efeito de stack
                                                const stack = humanPending.slice(0, 3);
                                                
                                                return (
                                                    <div className={styles.humanAnalysisAvatarStack}>
                                                        {stack.map((node, idx) => {
                                                            const rawUrl = getAvatarUrl(node);
                                                            const proxiedUrl = getProxiedUrl(rawUrl);
                                                            
                                                            return (
                                                                <div 
                                                                    key={node.id} 
                                                                    className={`${styles.humanAnalysisStackedAvatar} ${styles[`stackLayer${idx}`]}`}
                                                                >
                                                                    {proxiedUrl ? (
                                                                        <img
                                                                            src={proxiedUrl}
                                                                            alt=""
                                                                            onError={(e) => {
                                                                                const target = e.target as HTMLImageElement;
                                                                                target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(node.name || 'P')}&background=ffab00&color=fff&bold=true&rounded=true&size=128`;
                                                                            }}
                                                                        />
                                                                    ) : (
                                                                        <div className={styles.humanAnalysisAvatarPlaceholder}>
                                                                            <Users size={idx === 0 ? 20 : 14} />
                                                                        </div>
                                                                    )}
                                                                    
                                                                    {/* O badge de notificação só aparece no avatar do topo */}
                                                                    {idx === 0 && humanPending.length > 0 && (
                                                                        <div className={styles.humanAnalysisNotification}>
                                                                            {humanPending.length}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                );
                                            })()}
                                        <div className={styles.humanAnalysisList}>
                                            <div className={styles.humanAnalysisListTitle}>Análise Humana Pendente</div>
                                            {rawEmployees.filter(e => e.role === 'Análise Humana').slice(0, 15).map((n, i) => {
                                                const rawUrl = getAvatarUrl(n);
                                                const proxiedUrl = getProxiedUrl(rawUrl);
                                                return (
                                                    <div key={i} className={styles.humanAnalysisCard}>
                                                        {proxiedUrl ? (
                                                            <img
                                                                className={styles.humanAnalysisCardAvatar}
                                                                src={proxiedUrl}
                                                                alt={n.name}
                                                                onError={(e) => {
                                                                    const target = e.target as HTMLImageElement;
                                                                    target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(n.name || 'P')}&background=ffab00&color=fff&bold=true&rounded=true&size=128`;
                                                                }}
                                                            />
                                                        ) : (
                                                            <Users 
                                                                className={styles.humanAnalysisCardAvatar}
                                                                size={14} 
                                                            />
                                                        )}
                                                        <div className={styles.humanAnalysisCardInfo}>
                                                            <div className={styles.humanAnalysisCardName}>{n.name}</div>
                                                            <div className={styles.humanAnalysisCardSub}>Cargo não identificado</div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </main>

                    {showChat && (activeView === 'graph' || activeView === 'prospecting') && (
                        <ChatPanel
                            showChat={showChat}
                            setShowChat={handleSetShowChat}
                            selectedOrgId={currentOrgId}
                            selectedOrgName={confirmedBrand}
                            selectedOrgLogo={confirmedLogo}
                            theme={theme}
                            onToggleTheme={toggleTheme}
                            onOpenWhatsApp={(info) => {
                                setActiveChatInfo(info);
                                setActiveView('whatsapp');
                            }}
                        />
                    )}

                    <ConfirmModal 
                        isOpen={confirmModal.isOpen}
                        title="Descartar Perfil"
                        message="Deseja realmente descartar este perfil? Esta ação removerá o candidato do banco de dados permanentemente."
                        confirmLabel="Descartar"
                        cancelLabel="Manter"
                        onCancel={() => setConfirmModal({ isOpen: false, empId: null })}
                        onConfirm={async () => {
                            if (confirmModal.empId) {
                                try {
                                    await rejectCandidate(confirmModal.empId);
                                    addNotification('info', "Perfil descartado com sucesso.");
                                } catch(e: any) {
                                    addNotification('error', e.message);
                                }
                            }
                            setConfirmModal({ isOpen: false, empId: null });
                        }}
                    />
                </div>
            </div>
        </div>

        </>
    );
}
