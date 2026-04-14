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

import 'reactflow/dist/style.css';
import styles from './NetworkGraph.module.css';

import { FloatingToolbar } from './FloatingToolbar';
import { SupplyChainNode } from './nodes/SupplyChainNode';
import { getLayoutedElements, calculateEdges } from '@/utils/layout';
import { useHierarchy } from '@/hooks/useHierarchy';

// Modular Components
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { Drawer } from './Drawer';
import { ChatPanel } from './ChatPanel';
import { NotificationContainer, NotificationType } from './Notification';


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

export default function NetworkGraph({ defaultCnpj = "" }: { defaultCnpj?: string }) {

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
                        const lObj = JSON.parse(localStorage.getItem('last-viewed-org') || '{}');
                        if (lObj.id) cacheId = lObj.id.toString();
                        else if (lObj.name) cacheId = lObj.name;
                    } catch(e) {}
                    
                    const positionsCacheKey = `layout-cache-${cacheId}`;
                    let cachedPositions: Record<string, {x:number, y:number}> = {};
                    
                    try { 
                        const cached = localStorage.getItem(positionsCacheKey);
                        if (cached) cachedPositions = JSON.parse(cached);
                    } catch(e) {}
                    
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
                        const lObj = JSON.parse(localStorage.getItem('last-viewed-org') || '{}');
                        if (lObj.id) cacheId = lObj.id.toString();
                        else if (lObj.name) cacheId = lObj.name;
                    } catch(e) {}
                    
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
                        const lObj = JSON.parse(localStorage.getItem('last-viewed-org') || '{}');
                        if (lObj.id) cacheId = lObj.id.toString();
                        else if (lObj.name) cacheId = lObj.name;
                    } catch(e) {}
                    
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
        smartSyncPipedrive, confirmIntelligence, resetHierarchy, reconnectToActiveJob
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
    const [showDrawer, setShowDrawer] = useState(false);
    const [showChat, setShowChat] = useState(false);
    const [enrichingIds, setEnrichingIds] = useState<Set<number>>(new Set());
    const [shouldFitView, setShouldFitView] = useState(false);

    // 🔔 NOTIFICATION STATE
    const [notifications, setNotifications] = useState<Array<{ id: string; type: NotificationType; message: string }>>([]);
    const addNotification = useCallback((type: NotificationType, message: string) => {
        const id = Math.random().toString(36).substring(2, 9);
        setNotifications(prev => [...prev, { id, type, message }]);
    }, []);
    const removeNotification = (id: string) => {
        setNotifications(prev => prev.filter(n => n.id !== id));
    };

    const filteredOrgs = useMemo(() => {
        return pipedriveOrgs.filter(org => 
            org.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            org.domain?.toLowerCase().includes(searchTerm.toLowerCase())
        );
    }, [pipedriveOrgs, searchTerm]);

    const handleUpdatePipedrive = async (orgId: number, data: any) => {
        try {
            await fetch(`http://127.0.0.1:8000/api/v1/pipedrive/organizations/${orgId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cnpj: data.cnpj,
                    domain: data.domain,
                    address: data.address
                })
            });
        } catch (e: any) { console.error("Sync error:", (e as Error).message || e); }
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
                try {
                    const jobData = JSON.parse(jobDataStr);
                    const { brand, orgId } = jobData;
                    
                    // Mudar o state pra loading imediatamente para evitar re-loops
                    setStep("loading");

                    // Reconectar ao job em andamento
                    const reconnected = await reconnectToActiveJob((type, msg) => {
                        addNotification(type, msg);
                    });
                    
                    if (reconnected) {
                        setConfirmedBrand(brand);
                        if (orgId) {
                            setCurrentOrgId(orgId);
                        }
                    } else {
                        checkLastOrg(); // Tenta o fallback caso o reconnected retorne false
                    }
                } catch (e: any) {
                    console.error("[Job Check] Erro ao verificar job ativo:", (e as Error).message || e);
                    localStorage.removeItem('active-discovery-job');
                    checkLastOrg(); // Erro? cai pro fallback
                }
            } else {
                checkLastOrg(); // Sem job? Tenta recarregar a última org visualizada
            }
        };

        const checkLastOrg = async () => {
            const lastOrgStr = localStorage.getItem('last-viewed-org');
            if (lastOrgStr) {
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
                } catch(e) {
                    console.error("[Last Org Check] Erro ao verificar last-viewed-org:", (e as Error).message || e);
                    setStep("initial");
                }
            } else {
                setStep("initial");
            }
        };

        checkActiveJob();
    }, []); // ✅ Dependency array vazio - executa apenas na montagem

    /* === REMOVIDO loop checkActiveJobForOrg pois está nativamente dentro do handleOrgClick gora === */

    const fetchPipedriveOrgs = async () => {
        // Se já temos cache, não limpamos para não dar flicker na UI
        if (pipedriveOrgs.length === 0) setLoadingOrgs(true);
        try {
            // Sincronização em background (Pipedrive -> DB Local)
            fetch('http://127.0.0.1:8000/api/v1/pipedrive_sync', { method: 'POST' }).catch(() => {});
            
            const orgsResp = await fetch(`http://127.0.0.1:8000/api/v1/pipedrive/organizations?_=${Date.now()}`);
            
            // Check do status HTTP
            if (!orgsResp.ok) {
                console.warn(`[Pipedrive API] HTTP ${orgsResp.status}: ${orgsResp.statusText}`);
                if (pipedriveOrgs.length === 0) setPipedriveOrgs([]);
                setLoadingOrgs(false);
                return;
            }
            
            const data = await orgsResp.json();
            console.log("[Pipedrive API] Data Received:", data);
            const list = Array.isArray(data) ? data : [];
            setPipedriveOrgs(list);
            
            // Revalida o cache com a versão real do banco
            if (list.length > 0) {
                localStorage.setItem("pipedrive-orgs-cache", JSON.stringify(list));
            } else {
                localStorage.removeItem("pipedrive-orgs-cache");
            }
        } catch (e: any) {
            console.warn("[NetworkGraph] Erro ao carregar empresas do Pipedrive:", (e as Error).message || e);
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
            console.log("[Graph] VOLTAR CLICADO - Restaurando estado anterior");
            // Restaurar estado anterior se existir
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
        if (currentOrgId && cnpj) {
            console.log("[Graph] Persistindo escolha no Banco Local...");
            const result = await confirmIntelligence({
                name: cleanName(name),
                cnpj: cnpj,
                domain: domainTarget,
                address: "", // O backend já tem se for enriquecido
                pipedrive_id: currentOrgId,
                linkedin_url: brandObj.url || "",
                logo_url: logo,
                partners: partners
            });

            // Se deu sucesso, atualiza a lista do Drawer localmente para evitar duplicados ou dados velhos
            if (result && result.status !== "error") {
                const isUpdate = result.is_update || result.status === "updated";
                addNotification('success', isUpdate ? "Empresa atualizada com sucesso!" : "Empresa integrada com sucesso!");
                
                setPipedriveOrgs(prev => prev.map(org => 
                    Number(org.id) === currentOrgId 
                    ? { ...org, cnpj, domain: domainTarget, logo: logo, linkedin: brandObj.url, name: cleanName(name) }
                    : org
                ));
            } else {
                addNotification('error', "Erro ao salvar dados da empresa.");
            }
        }
    };

    const handleOrgClick = async (org: any) => {
        console.log('--- HANDLE ORG CLICK START ---', org.name);
        resetHierarchy(); // 🧹 Limpa os dados do hook
        setNodes([]); // 🧹 Limpa os nodes do grafo
        setEdges([]); // 🧹 Limpa as edges do grafo
        setStep("input");

        try {
            const cleanOrgName = cleanName(org.name || "");
            setConfirmedBrand(cleanOrgName); 
            setConfirmedLogo(org.logo || ""); 
            setConfirmedFollowers("");
            
            let targetCnpj = org.cnpj || "";
            const onlyNums = targetCnpj.replace(/\D/g, '');
            if (onlyNums.length < 5) {
                targetCnpj = ""; 
            }

            setCnpj(formatCnpj(targetCnpj));
            setDomainTarget(org.domain || ""); 
            setProductFocus(""); 
            setCurrentOrgId(Number(org.id));
            localStorage.setItem('last-viewed-org', JSON.stringify(org));

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
                if (data && data.nodes && data.nodes.length > 0) {
                    setStep("confirm"); // Mostra o header mas já com os dados no grafo
                    setShouldFitView(true); // 📍 Auto fit view após carregar dados
                } else if (data && data.status === "new" || data && data.status === "empty") {
                    setStep("input"); // Fica pronto para mapear se não tinha nada no BD e não tem job ativo
                } else if (data && data.status === "cached") {
                    setStep("confirm");
                    setShouldFitView(true);
                }
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
            const query = `name=${encodeURIComponent(confirmedBrand || "Empresa")}&cnpj=${encodeURIComponent(cnpj)}`;
            const resp = await fetch(`http://127.0.0.1:8000/api/v1/intelligence/enrich?${query}&force=true`);
            const data = await resp.json();

            if (data.success && data.main_option) {
                const main = data.main_option;
                const cleanDomain = sanitizeVal(main.domain);
                const cleanCnpj = formatCnpj(sanitizeVal(main.cnpj));

                if (cleanDomain) setDomainTarget(cleanDomain);
                if (cleanCnpj) setCnpj(cleanCnpj);

                // Sincronização e Atualização local removidas daqui. 
                // Acontecerão apenas no handleBrandSelect (Confirmação).
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
        
        let uiNodes: Node[] = rawEmployees.map(emp => {
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
        } catch(e) {}

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
        } catch(e) {}

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
            finalNodes = uiNodes.map(n => ({...n, position: cachedPositions[getStableId(n)]}));
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
        
        // 🔄 Limpar dados antigos da empresa na lista do drawer
        setPipedriveOrgs(prev => prev.map(org => 
            Number(org.id) === orgId 
            ? { ...org, cnpj: null, domain: null, logo: null, linkedin: null, name: org.name }
            : org
        ));
        
        // 🗑️ Limpar cache local (localStorage)
        const cacheKeys = [
            `org-${orgId}-details`,
            `org-${orgId}-logo`,
            `org-${orgId}-hierarchy`,
            `hierarchy-${orgId}`,
            `stored-hierarchy-${orgId}`,
            `edges-cache-${orgId}`
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
        <div className={styles.container}>
            <Sidebar 
                showDrawer={showDrawer}
                setShowDrawer={setShowDrawer}
                theme={theme}
                onToggleTheme={toggleTheme}
                onReset={() => { setStep("input"); setNodes([]); setEdges([]); localStorage.removeItem('last-viewed-org'); }}
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
            />


            <Drawer 
                showDrawer={showDrawer}
                setShowDrawer={setShowDrawer}
                searchTerm={searchTerm}
                setSearchTerm={setSearchTerm}
                filteredOrgs={filteredOrgs}
                onOrgClick={handleOrgClick}
                onOrgReset={handleOrgReset}
                onOrgRenamed={handleOrgRenamed}
                isLoading={loadingOrgs}
                selectedOrgId={currentOrgId}
                activeJobId={activeJobId}
                graphEmployees={rawEmployees}
                refreshDetailsTrigger={refreshDrawerTrigger}
                addNotification={addNotification}
            />

            <div className={styles.mainWrapper}>
                <Header 
                    confirmedBrand={confirmedBrand}
                    showChat={showChat}
                    onToggleChat={() => setShowChat(!showChat)}
                />
                
                <div className={styles.contentWrapper}>
                    <main className={styles.mainContent}>
                        <NotificationContainer 
                            notifications={notifications} 
                            removeNotification={removeNotification} 
                        />

                        <div className={styles.graphWrapper}>
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
                        <Controls position="bottom-right" />


                    </ReactFlow>



                        </div>

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
                        />
                    </main>
                    
                    {showChat && (
                        <ChatPanel 
                            showChat={showChat}
                            setShowChat={setShowChat}
                            selectedOrgId={currentOrgId}
                            selectedOrgName={confirmedBrand}
                            theme={theme}
                            onToggleTheme={toggleTheme}
                        />
                    )}
                </div>
            </div>
        </div>

    );
}
