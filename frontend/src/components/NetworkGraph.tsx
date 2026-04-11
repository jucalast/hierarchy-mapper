"use client";

import React, { useEffect, useState, useMemo } from 'react';
import ReactFlow, {
    Controls,
    useNodesState,
    useEdgesState,
    Node,
    Background,
    BackgroundVariant,
    useStore
} from 'reactflow';

import 'reactflow/dist/style.css';
import styles from './NetworkGraph.module.css';

import { SupplyChainNode } from './nodes/SupplyChainNode';
import { getLayoutedElements, calculateEdges } from '@/utils/layout';
import { useHierarchy } from '@/hooks/useHierarchy';

// Modular Components
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { Drawer } from './Drawer';
import { FloatingToolbar } from './FloatingToolbar';


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

    // 🎨 THEME PERSISTENCE
    useEffect(() => {
        const savedTheme = localStorage.getItem("preferred-theme") || "dark";
        setTheme(savedTheme);
        document.documentElement.setAttribute("data-theme", savedTheme);
    }, []);

    const {
        rawEmployees, rawBackendEdges, loading, discovering, brandOptions, error, setError,
        fetchHierarchy, discoverBrand, refineHierarchy, loadStoredHierarchy,
        smartSyncPipedrive, confirmIntelligence, resetHierarchy
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
                }
            } catch (e) { console.error("Cache parsing error", e); }
        }
        fetchPipedriveOrgs();
    }, []);

    const fetchPipedriveOrgs = async () => {
        // Se já temos cache, não limpamos para não dar flicker na UI
        if (pipedriveOrgs.length === 0) setLoadingOrgs(true);
        try {
            // Sincronização em background (Pipedrive -> DB Local)
            fetch('http://127.0.0.1:8000/api/v1/pipedrive_sync', { method: 'POST' }).catch(() => {});
            
            const orgsResp = await fetch(`http://127.0.0.1:8000/api/v1/pipedrive/organizations?_=${Date.now()}`);
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

    const handleBrandSelect = (brandObj: any) => {
        console.log("[Graph] handleBrandSelect called with:", brandObj);
        if (!brandObj) {
            setConfirmedBrand("");
            setConfirmedLogo("");
            setConfirmedFollowers("");
            setStep("input");
            return;
        }
        
        const name = typeof brandObj === 'string' ? brandObj : (brandObj.name || brandObj.url || "");
        const logo = brandObj.logo || "";
        const followers = brandObj.followers || "";
        const partners = brandObj.partners || [];

        console.log("[Graph] Setting Brand Data:", { name, logo, followers, partnersCount: partners.length });
        setConfirmedBrand(cleanName(name));
        setConfirmedLogo(logo);
        setConfirmedFollowers(followers);
        setStep("confirm");

        // 💾 PERSISTÊNCIA MANUAL: Salva no banco local ao selecionar
        if (currentOrgId && cnpj) {
            console.log("[Graph] Persistindo escolha no Banco Local...");
            confirmIntelligence({
                name: cleanName(name),
                cnpj: cnpj,
                domain: domainTarget,
                address: "", // Pega do estado se houver
                pipedrive_id: currentOrgId,
                linkedin_url: brandObj.url || "",
                logo_url: logo,
                partners: partners
            });
        }
    };

    const handleOrgClick = async (org: any) => {
        console.log('--- HANDLE ORG CLICK START ---', org.name);
        resetHierarchy(); // 🧹 Limpa o grafo anterior imediatamente
        setShowDrawer(false); 
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

                if (currentOrgId) {
                    handleUpdatePipedrive(currentOrgId, { 
                        address: main.address, 
                        cnpj: cleanCnpj, 
                        domain: cleanDomain 
                    });

                    setPipedriveOrgs(prev => prev.map(o =>
                        Number(o.id) === currentOrgId ? { ...o, address: main.address, cnpj: cleanCnpj, domain: cleanDomain } : o
                    ));
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
                const result = await discoverBrand(cnpj, domainTarget, true);
                if (result && result.brand) {
                    if (result.domain && !domainTarget) {
                        setDomainTarget(result.domain);
                    }
                    
                    // Se não for Cache Hit, as alternativas aparecerão no carrossel via brandOptions
                } else {
                    setError("Empresa não encontrada no LinkedIn.");
                }
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
                areaFocus
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
            />


            <Drawer 
                showDrawer={showDrawer}
                setShowDrawer={setShowDrawer}
                searchTerm={searchTerm}
                setSearchTerm={setSearchTerm}
                filteredOrgs={filteredOrgs}
                onOrgClick={handleOrgClick}
                isLoading={loadingOrgs}
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
        </div>

    );
}
