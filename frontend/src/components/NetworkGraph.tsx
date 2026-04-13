"use client";

import React, { useEffect, useState, useMemo, useRef } from 'react';
import ReactFlow, {
    Controls,
    useNodesState,
    useEdgesState,
    Node,
    Background,
    BackgroundVariant,
    useStore,
    useReactFlow
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


export default function NetworkGraph({ defaultCnpj = "" }: { defaultCnpj?: string }) {


    const nodeTypes = useMemo(() => ({
        supplyChain: SupplyChainNode
    }), []);

    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [theme, setTheme] = useState("dark");
    const [step, setStep] = useState("input");


    const [cnpj, setCnpj] = useState(defaultCnpj);
    const [domainTarget, setDomainTarget] = useState("");
    const [productFocus, setProductFocus] = useState("");
    const [currentOrgId, setCurrentOrgId] = useState<number | null>(null);
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
        activeJobId, fetchHierarchy, discoverBrand, discoverBrandStream, cancelDiscovery, refineHierarchy, loadStoredHierarchy,
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
    const [enrichingIds, setEnrichingIds] = useState<Set<number>>(new Set());
    const [shouldFitView, setShouldFitView] = useState(false);

    // 🔔 NOTIFICATION STATE
    const [notifications, setNotifications] = useState<Array<{ id: string; type: NotificationType; message: string }>>([]);
    const addNotification = (type: NotificationType, message: string) => {
        const id = Math.random().toString(36).substring(2, 9);
        setNotifications(prev => [...prev, { id, type, message }]);
    };
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
        } catch (e) { console.error("Sync error", e); }
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
                    return; // Retorna aqui se tiver cache válido
                }
            } catch (e) { console.error("Cache parsing error", e); }
        }
        // Só tenta fetch do backend se não tiver cache
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
                    
                    // Reconectar ao job em andamento
                    const reconnected = await reconnectToActiveJob((type, msg) => {
                        addNotification(type, msg);
                    });
                    
                    if (reconnected) {
                        setStep("loading");
                        setConfirmedBrand(brand);
                        if (orgId) {
                            setCurrentOrgId(orgId);
                        }
                    }
                } catch (e) {
                    console.error("[Job Check] Erro ao verificar job ativo:", e);
                    localStorage.removeItem('active-discovery-job');
                }
            }
        };

        checkActiveJob();
    }, []); // ✅ Dependency array vazio - executa apenas na montagem

    // 🔄 Verificar job caso o usuário mude de empresa via Drawer
    useEffect(() => {
        if (!currentOrgId) return;

        const checkActiveJobForOrg = async () => {
            const jobDataStr = localStorage.getItem('active-discovery-job');
            if (jobDataStr) {
                try {
                    const jobData = JSON.parse(jobDataStr);
                    const { brand, orgId } = jobData;
                    
                    // Se o job ativo no localStorage for desta empresa e o step não for loading
                    if (orgId === currentOrgId && step !== "loading" && step !== "graph") {
                        // Reconectar ao job em andamento se ele for desta empresa
                        const reconnected = await reconnectToActiveJob((type, msg) => {
                            addNotification(type, msg);
                        });
                        
                        if (reconnected) {
                            setStep("loading");
                            setConfirmedBrand(brand);
                        }
                    }
                } catch (e) {
                    console.error("[Job Check] Erro ao verificar job ativo ao trocar empresa:", e);
                }
            }
        };

        checkActiveJobForOrg();
    }, [currentOrgId, step, reconnectToActiveJob, addNotification]);

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
            
            // Salva no Cache para a próxima vez
            if (list.length > 0) {
                localStorage.setItem("pipedrive-orgs-cache", JSON.stringify(list));
            }
        } catch (e) {
            console.error("Erro ao carregar empresas do Pipedrive", e);
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

            if (org.id) {
                console.log('Attempting to load hierarchy for pipedrive_id:', org.id);
                const data = await loadStoredHierarchy(Number(org.id), true);
                if (data && data.status === "cached") {
                    setStep("confirm"); // Mostra o header mas já com os dados no grafo
                    setShouldFitView(true); // 📍 Auto fit view após carregar dados
                }
            }
        } catch (e) {
            console.error("Critical error in handleOrgClick:", e);
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
            fetchHierarchy(
                cnpj, 
                domainTarget, 
                confirmedBrand, 
                confirmedLogo, 
                productFocus,
                areaFocus,
                addNotification,
                partners,
                currentOrgId
            );
        }
    };

    useEffect(() => {
        if (rawEmployees.length === 0) return;
        const uiNodes: Node[] = rawEmployees.map(emp => ({
            id: emp.id,
            type: 'supplyChain',
            position: { x: 0, y: 0 },
            data: { ...emp, isRoot: emp.level === 0 },
        }));
        const finalEdges = calculateEdges(uiNodes, rawBackendEdges);
        const { layoutedNodes, layoutedEdges } = getLayoutedElements(uiNodes, finalEdges);
        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
    }, [rawEmployees, rawBackendEdges, setNodes, setEdges]);

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
            `stored-hierarchy-${orgId}`
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
            } catch (e) {
                console.error("Erro ao atualizar cache", e);
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
                onReset={() => { setStep("input"); setNodes([]); setEdges([]); }}
                onCopyData={handleCopyData}
                onRefine={() => refineHierarchy(rawEmployees)}
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
                graphEmployees={rawEmployees}
            />

            <main className={styles.mainContent}>
                <Header confirmedBrand={confirmedBrand} />


                <div className={styles.graphWrapper}>
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        nodeTypes={nodeTypes}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
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
                />
            </main>

            <NotificationContainer 
                notifications={notifications} 
                removeNotification={removeNotification} 
            />
        </div>

    );
}
