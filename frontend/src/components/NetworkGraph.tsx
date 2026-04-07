"use client";

import React, { useEffect, useState, useMemo } from 'react';
import ReactFlow, {
    Background,
    Controls,
    useNodesState,
    useEdgesState,
    Node,
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
import { Legend } from './Legend';
import { PersonaPreview } from './PersonaPreview';

export default function NetworkGraph({ defaultCnpj = "" }: { defaultCnpj?: string }) {

    const nodeTypes = useMemo(() => ({
        supplyChain: SupplyChainNode
    }), []);

    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [theme, setTheme] = useState("dark");
    const [hoveredNode, setHoveredNode] = useState<any>(null);
    const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
    const [step, setStep] = useState("input");
    const [cnpj, setCnpj] = useState(defaultCnpj);
    const [domainTarget, setDomainTarget] = useState("");
    const [productFocus, setProductFocus] = useState("");
    const [currentOrgId, setCurrentOrgId] = useState<number | null>(null);
    const [confirmedBrand, setConfirmedBrand] = useState("");
    const [confirmedLogo, setConfirmedLogo] = useState("");
    const [confirmedFollowers, setConfirmedFollowers] = useState("");

    // 🎨 THEME PERSISTENCE
    useEffect(() => {
        const savedTheme = localStorage.getItem("preferred-theme") || "dark";
        setTheme(savedTheme);
        document.documentElement.setAttribute("data-theme", savedTheme);
    }, []);

    const {
        rawEmployees, rawBackendEdges, loading, discovering, brandOptions, error, setError,
        fetchHierarchy, discoverBrand, refineHierarchy, loadStoredHierarchy,
        smartSyncPipedrive, confirmIntelligence
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
            await fetch(`http://localhost:8000/api/v1/pipedrive/organizations/${orgId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cnpj: data.cnpj,
                    domain: data.domain
                })
            });
        } catch (e) { console.error("Sync error", e); }
    };

    const fetchPipedriveOrgs = async () => {
        setLoadingOrgs(true);
        try {
            await fetch('http://localhost:8000/api/v1/pipedrive_sync', { method: 'POST' });
            const orgsResp = await fetch(`http://localhost:8000/api/v1/pipedrive/organizations?_=${Date.now()}`);
            const data = await orgsResp.json();
            setPipedriveOrgs(Array.isArray(data) ? data : []);
        } catch (e) {
            console.error("Erro ao carregar empresas do Pipedrive", e);
            setPipedriveOrgs([]);
        } finally {
            setLoadingOrgs(false);
        }
    };

    useEffect(() => {
        fetchPipedriveOrgs();
    }, []);

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

        console.log("[Graph] Setting Brand Data:", { name, logo, followers });
        setConfirmedBrand(cleanName(name));
        setConfirmedLogo(logo);
        setConfirmedFollowers(followers);
        setStep("confirm");
    };

    const handleOrgClick = (org: any) => {
        console.log('--- HANDLE ORG CLICK START ---', org.name);
        setShowDrawer(false); 
        setStep("input");

        try {
            setConfirmedBrand(cleanName(org.name || "")); 
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
                console.log('Attempting to load hierarchy for:', org.id);
                loadStoredHierarchy(Number(org.id)).catch(err => {
                   console.error("Hierarchy load failed:", err);
                });
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
            const query = `name=${encodeURIComponent(confirmedBrand || "Empresa")}&cnpj=${encodeURIComponent(cnpj)}&force=true`;
            const resp = await fetch(`http://localhost:8000/api/v1/intelligence/enrich?${query}`);
            const data = await resp.json();

            if (data.success && data.main_option) {
                const main = data.main_option;
                const cleanDomain = sanitizeVal(main.domain);
                const cleanCnpj = formatCnpj(sanitizeVal(main.cnpj));

                if (cleanDomain) setDomainTarget(cleanDomain);
                if (cleanCnpj) setCnpj(cleanCnpj);

                if (currentOrgId) {
                    handleUpdatePipedrive(currentOrgId, { address: main.address, cnpj: cleanCnpj, domain: cleanDomain });

                    // Persistir no Banco local
                    await confirmIntelligence({
                        name: confirmedBrand || "Empresa",
                        cnpj: cleanCnpj,
                        domain: cleanDomain,
                        address: main.address,
                        pipedrive_id: currentOrgId
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
                const brand = await discoverBrand(cnpj, domainTarget);
                if (brand) {
                } else {
                    setError("Empresa não encontrada no LinkedIn.");
                }
            } catch (err) {
                setError("Erro de conexão.");
            }
        } else if (step === "confirm" || step === "scanning") {
            if (!confirmedBrand) { setError("Marca inválida."); return; }
            setStep("scanning");
            fetchHierarchy(cnpj, domainTarget, confirmedBrand, productFocus);
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
            />

            <Drawer 
                showDrawer={showDrawer}
                setShowDrawer={setShowDrawer}
                searchTerm={searchTerm}
                setSearchTerm={setSearchTerm}
                filteredOrgs={filteredOrgs}
                onOrgClick={handleOrgClick}
            />

            <main className={styles.mainContent}>
                <div className={styles.dottedBackground} />

                <Header confirmedBrand={confirmedBrand} />

                <div className={styles.graphWrapper}>
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        nodeTypes={nodeTypes}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        onNodeMouseEnter={(_, node) => setHoveredNode(node.data)}
                        onNodeMouseLeave={() => setHoveredNode(null)}
                        onMouseMove={(e) => setMousePos({ x: e.clientX, y: e.clientY })}
                        fitView
                    >
                        <Background gap={30} color="rgba(255,255,255,0.03)" />
                        <Controls position="bottom-right" />
                    </ReactFlow>

                    {hoveredNode && (
                        <PersonaPreview 
                            data={hoveredNode} 
                            position={mousePos} 
                        />
                    )}
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
                    handleAutoEnrich={handleAutoEnrich}
                    enrichingIds={enrichingIds}
                    discovering={discovering}
                    loading={loading}
                    step={step}
                    brandOptions={brandOptions}
                    onBrandSelect={handleBrandSelect}
                />

                <Legend />
            </main>
        </div>
    );
}
