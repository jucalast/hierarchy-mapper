"use client";

import React, { useEffect, useState, useMemo } from 'react';
import ReactFlow, { 
    Background, 
    Controls, 
    MiniMap,
    useNodesState,
    useEdgesState,
    Node,
    Edge,
    MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';
import styles from './NetworkGraph.module.css';

import { SupplyChainNode } from './nodes/SupplyChainNode';
import { getLayoutedElements, calculateEdges } from '@/utils/layout';
import { useHierarchy } from '@/hooks/useHierarchy';

export default function NetworkGraph({ defaultCnpj = "" }: { defaultCnpj?: string }) {

    const nodeTypes = useMemo(() => ({
        supplyChain: SupplyChainNode
    }), []);

    const edgeTypes = useMemo(() => ({}), []);

    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [theme, setTheme] = useState("light");
    const [cnpj, setCnpj] = useState(defaultCnpj);
    const [domainTarget, setDomainTarget] = useState("");
    const [confirmedBrand, setConfirmedBrand] = useState("");
    const [step, setStep] = useState<"input" | "confirm" | "scanning">("input");

    const { 
        rawEmployees, rawBackendEdges, loading, discovering, brandOptions, error, setError,
        fetchHierarchy, discoverBrand, refineHierarchy, updateEmployee, loadStoredHierarchy
    } = useHierarchy();
    
    // 🛡️ SEGURANÇA E FORMATAÇÃO
    const sanitizeVal = (val: any) => {
        if (!val || typeof val !== "string") return "";
        const junk = ["not provided", "n/a", "unknown", "null", "none"];
        return junk.includes(val.toLowerCase().trim()) ? "" : val;
    };
    const formatCnpj = (val: string) => {
        if (!val) return "";
        const clean = val.replace(/\D/g, "");
        if (clean.length !== 14) return val;
        return `${clean.slice(0, 2)}.${clean.slice(2, 5)}.${clean.slice(5, 8)}/${clean.slice(8, 12)}-${clean.slice(12)}`;
    };

    // 🟠 PIPEDRIVE SYNC STATE
    const [syncingTasks, setSyncingTasks] = useState(false);
    const [pipedriveOrgs, setPipedriveOrgs] = useState<any[]>([]);
    const [loadingOrgs, setLoadingOrgs] = useState(false);
    const [showDrawer, setShowDrawer] = useState(false);
    const [enrichingIds, setEnrichingIds] = useState<Set<number>>(new Set());
    const [orgOptions, setOrgOptions] = useState<any | null>(null); // Opções de filiais p/ seleção
    // scanDomain removido para usar o domainTarget original do usuário

    const handleUpdatePipedrive = async (orgId: number, data: any) => {
        try {
            const resp = await fetch(`http://127.0.0.1:8000/api/v1/pipedrive/organizations/${orgId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    address: data.address,
                    // Aqui você pode adicionar campos customizados de CNPJ se souber o ID no Pipedrive
                })
            });
            console.log("Pipedrive Sync:", await resp.json());
        } catch (e) { console.error("Sync error", e); }
    };

    const handleEnrichCorp = async (e: React.MouseEvent, org: any) => {
        e.stopPropagation();
        const orgId = Number(org.id);
        if (enrichingIds.has(orgId)) return;

        setEnrichingIds((prev) => new Set(prev).add(orgId));
        try {
            const query = `name=${encodeURIComponent(org.name)}${org.address ? `&address=${encodeURIComponent(org.address)}` : ''}`;
            const resp = await fetch(`http://127.0.0.1:8000/api/v1/intelligence/enrich?${query}`);
            const data = await resp.json();
            
            if (data.success) {
                const main = data.main_option;
                // 🛡️ SE FOR UM MATCH EXATO OU SÓ TIVER UMA OPÇÃO, JÁ SALVA DIRETO!
                if (data.is_match || (data.other_options?.length === 0)) {
                    const cleanCnpj = formatCnpj(sanitizeVal(main.cnpj));
                    const cleanDomain = sanitizeVal(main.domain);
                    
                    setConfirmedBrand(org.name); // 🎯 Marca o foco visual na empresa clicada
                    setPipedriveOrgs(prev => prev.map(o => 
                        Number(o.id) === orgId ? { ...o, cnpj: cleanCnpj, domain: cleanDomain, address: main.address || o.address } : o
                    ));
                    setDomainTarget(cleanDomain); 
                    setCnpj(cleanCnpj);
                    handleUpdatePipedrive(orgId, { ...main, cnpj: cleanCnpj, domain: cleanDomain });
                } else {
                    // Tem opções e não há match exato! Mostra pra escolher
                    setOrgOptions({ orgId, orgName: org.name, options: [main, ...data.other_options] });
                }
            }
        } catch (err) {
            console.error("Enrichment error", err);
        } finally {
            setEnrichingIds(prev => {
                const n = new Set(prev);
                n.delete(orgId);
                return n;
            });
        }
    };


    const pickOption = (option: any) => {
        if (!orgOptions) return;
        const { orgId, orgName } = orgOptions;
        
        const cleanCnpj = sanitizeVal(option.cnpj);
        const cleanDomain = sanitizeVal(option.domain);
        
        setConfirmedBrand(orgName); // 🎯 Marca o foco na empresa certa após seleção
        setPipedriveOrgs(prev => prev.map(o => 
            Number(o.id) === orgId ? { ...o, cnpj: cleanCnpj, domain: cleanDomain, address: option.address || o.address } : o
        ));
        
        setDomainTarget(cleanDomain); 
        setCnpj(cleanCnpj);
        
        handleUpdatePipedrive(orgId, { ...option, cnpj: cleanCnpj, domain: cleanDomain });
        setOrgOptions(null);
    };

    const fetchPipedriveOrgs = async () => {
        setLoadingOrgs(true);
        try {
            const resp = await fetch('http://127.0.0.1:8000/api/v1/pipedrive_sync', { method: 'POST' }); // Dummy check test
            // Re-fetch real orgs (com cache-buster para forçar os 500)
            const orgsResp = await fetch(`http://127.0.0.1:8000/api/v1/pipedrive/organizations?_=${Date.now()}`);
            const data = await orgsResp.json();
            // 🛡️ VALIDAÇÃO DE SEGURANÇA: Garante que é um Array
            setPipedriveOrgs(Array.isArray(data) ? data : []);
        } catch (e) {
            console.error("Erro ao carregar empresas do Pipedrive", e);
            setPipedriveOrgs([]); // Fallback
        } finally {
            setLoadingOrgs(false);
        }
    };

    useEffect(() => {
        fetchPipedriveOrgs();
    }, []);

    const handleOrgClick = (org: any) => {
        // 🛡️ APENAS PREENCHE OS INPUTS CENTRAIS (SEM DISPARAR O SCAN IMEDIATO)
        setConfirmedBrand(org.name);
        const targetCnpj = org.cnpj || "";
        const targetDomain = org.domain || "";
        
        setCnpj(targetCnpj);
        setDomainTarget(targetDomain); 
        
        // 🔄 AUTOCARGA: Busca o que já está no banco se houver ID
        if (org.id) {
            loadStoredHierarchy(Number(org.id));
        }
        
        setStep("input"); 
        setShowDrawer(false); 
        
        console.log(`[Frontend] 🎯 Dados carregados: ${org.name}. Pronto para conferência.`);
    };

    // 🌗 DARK MODE LOGIC
    useEffect(() => {
        const savedTheme = localStorage.getItem("theme") || "light";
        setTheme(savedTheme);
        document.documentElement.setAttribute("data-theme", savedTheme);
    }, []);

    const [copied, setCopied] = useState(false);

    // 🕵️ HOVER PREVIEW STATE
    const [hoveredNode, setHoveredNode] = useState<{ id: string, x: number, y: number, data: any } | null>(null);
    const [previewData, setPreviewData] = useState<any>(null);
    const [previewLoading, setPreviewLoading] = useState(false);
    const [previewCache, setPreviewCache] = useState<Record<string, any>>({});

    const handleNodeMouseEnter = async (event: React.MouseEvent, node: Node) => {
        if (node.id === 'root_company') return;
        
        setHoveredNode({ id: node.id, x: event.clientX, y: event.clientY, data: node.data });

        if (previewCache[node.id]) {
            setPreviewData(previewCache[node.id]);
            return;
        }

        const personUrl = node.data.url || node.data.linkedin;
        if (!personUrl) return;

        setPreviewLoading(true);
        try {
            const roleHint = node.data?.role || "";
            const companyHint = node.data?.company || "";
            const url = `http://127.0.0.1:8000/api/v1/proxy/preview?url=${encodeURIComponent(personUrl)}&role_hint=${encodeURIComponent(roleHint)}&company_hint=${encodeURIComponent(companyHint)}`;
            
            const resp = await fetch(url);
            const data = await resp.json();
            
            if (!data.error) {
                setPreviewData(data);
                setPreviewCache(prev => ({ ...prev, [node.id]: data }));
                
                // 🔄 SYNC INTELLIGENCE: Atualiza o cargo real no gráfico em tempo real
                if (data.role && data.role !== "Colaborador" && data.role !== node.data.role) {
                   console.log(`[Sync] Resgatado cargo oficial de ${data.name}: ${data.role}`);
                   updateEmployee(node.id, { role: data.role });
                   setNodes(nds => nds.map(n => 
                       n.id === node.id ? { ...n, data: { ...n.data, role: data.role } } : n
                   ));
                }
            }
        } catch (e) {
            console.error("Preview error", e);
        } finally {
            setPreviewLoading(false);
        }
    };

    const handleNodeMouseMove = (event: React.MouseEvent, node: Node) => {
        if (hoveredNode && hoveredNode.id === node.id) {
            setHoveredNode({ ...hoveredNode, x: event.clientX, y: event.clientY });
        }
    };

    const handleNodeMouseLeave = () => {
        setHoveredNode(null);
        setPreviewData(null);
        setPreviewLoading(false);
    };

    const toggleTheme = () => {
        const newTheme = theme === "light" ? "dark" : "light";
        setTheme(newTheme);
        localStorage.setItem("theme", newTheme);
        document.documentElement.setAttribute("data-theme", newTheme);
    };

    const handleCopyDebugData = () => {
        if (rawEmployees.length === 0) return;
        
        let output = `===== B2B INTELLIGENCE REPORT: ${confirmedBrand || "SCAN"} =====\n`;
        output += `Data: ${new Date().toLocaleString('pt-BR')}\n`;
        output += `Total de Profissionais: ${rawEmployees.length}\n`;
        output += `--------------------------------------------------\n\n`;

        const body = rawEmployees.map(emp => {
            // Ignora o nó raiz se for puramente da empresa
            if (emp.level === 0 || emp.id === "root_company") return null;

            // Encontrar quem é o superior imediato no pool de funcionários bruto
            const parent = rawEmployees.find(p => p.id === emp.manager_id);
            
            let seniorityLabel = "Professional";
            switch (emp.level) {
                case 6: seniorityLabel = "Board / C-Level"; break;
                case 5: seniorityLabel = "Director / Regional Head"; break;
                case 4: seniorityLabel = "Manager / Group Leader"; break;
                case 3: seniorityLabel = "Coordinator / Project Owner"; break;
                case 2: seniorityLabel = "Specialist / Senior / Engineer"; break;
                case 1: seniorityLabel = "Operational / Support"; break;
            }

            return `👤 ${emp.name.toUpperCase()}\n` +
                   `   - Cargo: ${emp.role}\n` +
                   `   - Hierarquia: Tier ${emp.level} (${seniorityLabel})\n` +
                   `   - Departamento: ${emp.department || "Operations"}\n` +
                   `   - Conectado a: ${parent ? `${parent.name} (${parent.role})` : "Entidade Matriz"}\n` +
                   `   - LinkedIn: ${emp.linkedin || "N/A"}\n` +
                   `   - Email: ${emp.email || "N/A"}\n`;
        }).filter(Boolean).join("\n");

        navigator.clipboard.writeText(output + body);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const syncPipedriveTasks = async () => {
        setSyncingTasks(true);
        try {
            const resp = await fetch('http://127.0.0.1:8000/api/v1/pipedrive_sync', {
                method: 'POST'
            });
            const data = await resp.json();
            alert(data.message || "Tarefas sincronizadas!");
        } catch (e) {
            alert("Erro ao sincronizar tarefas: " + e);
        } finally {
            setSyncingTasks(false);
        }
    };

    // 🔄 Efeito de Auto-Layout (Dispara sempre que o time cresce)
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

    // 🚀 MAIN SEARCH HANDLER (Conecta Descoberta -> Confirmação -> Scan)
    const handleSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (step === "input") {
            // STEP 1: DESCOBRIR MARCA E DOMÍNIO
            if (!cnpj) { setError("Insira o CNPJ da empresa"); return; }
            try {
                const brand = await discoverBrand(cnpj, domainTarget);
                if (brand) {
                    setConfirmedBrand(brand);
                    setStep("confirm");
                } else {
                    setError("Empresa não encontrada. Tente informar o domínio manualmente.");
                }
            } catch (err) {
                setError("Erro de conexão.");
            }
        } else if (step === "confirm") {
            // STEP 2: INICIAR SCAN COMPLETO (LINKEDIN)
            if (!confirmedBrand) { setError("Nome da marca inválido."); return; }
            setStep("scanning");
            fetchHierarchy(cnpj, domainTarget, confirmedBrand);
        }
    };

    return (
        <div className={styles.container}>
            {/* --- BARD SIDENAV (Minimalist Navigation) --- */}
            <aside className={styles.sidenav}>
                <div 
                    className={`${styles.navIcon} ${showDrawer ? styles.navIconActive : ''}`} 
                    onClick={() => setShowDrawer(!showDrawer)}
                    title="Minhas Empresas (Pipedrive)"
                >
                    <span className="google-symbols" style={{ color: '#ec4899' }}>
                        business
                    </span>
                </div>
                
                <div className={`${styles.navIcon} ${styles.navIconActive}`} onClick={() => { setStep("input"); setNodes([]); setEdges([]); }}>
                    <span className="google-symbols">edit_square</span>
                </div>
                <div 
                    className={`${styles.navIcon} ${loading ? styles.navIconDisabled : ''}`} 
                    onClick={() => rawEmployees.length > 0 && !loading && refineHierarchy(rawEmployees)}
                    title="Refinar Hierarquia com Groq IA"
                >
                    <span className="google-symbols" style={{ color: rawEmployees.length > 0 ? '#10b981' : 'inherit' }}>
                        psychology
                    </span>
                </div>
                <div style={{ flex: 1 }}></div>

                {/* 🚀 PIPEDRIVE SYNC BUTTON */}
                <div 
                    className={`${styles.navIcon} ${syncingTasks ? styles.navIconActive : ''}`} 
                    onClick={syncPipedriveTasks}
                    title="Perdoar Atrasos (Pipedrive)"
                >
                    <span className="google-symbols" style={{ color: syncingTasks ? '#3b82f6' : '#60a5fa' }}>
                        {syncingTasks ? "sync" : "published_with_changes"}
                    </span>
                </div>
                
                {/* 🌗 DARK MODE TOGGLE */}
                <div className={styles.navIcon} onClick={toggleTheme} title="Trocar Tema">
                    <span className="google-symbols">
                        {theme === "light" ? "dark_mode" : "light_mode"}
                    </span>
                </div>

                {/* 📋 DEBUG COPY BUTTON */}
                <div 
                    className={`${styles.navIcon} ${copied ? styles.navIconActive : ''}`} 
                    onClick={handleCopyDebugData} 
                    title="Copiar Dados (Debug)"
                >
                    <span className="google-symbols">
                        {copied ? "done_all" : "content_copy"}
                    </span>
                </div>

                <div className={styles.navIcon}>
                    <span className="google-symbols">settings_2</span>
                </div>
                <div className={styles.navIcon}>
                    <span className="google-symbols">help</span>
                </div>
            </aside>

            {/* --- PIPEDRIVE COMPANY DRAWER --- */}
            {showDrawer && (
                <div className={styles.drawer}>
                    <div className={styles.drawerHeader}>
                        <h3>Empresas Pipedrive ({loadingOrgs ? '...' : pipedriveOrgs.length})</h3>
                        <button onClick={() => setShowDrawer(false)} className={styles.closeBtn}>
                            <span className="google-symbols">close</span>
                        </button>
                    </div>
                    
                    <div className={styles.drawerSearch}>
                        <span className="google-symbols">filter_list</span>
                        <input type="text" placeholder="Filtrar carteira..." className={styles.drawerInput} />
                    </div>

                    <div className={styles.drawerList}>
                        {loadingOrgs ? (
                            <div className={styles.drawerLoading}>Buscando carteira...</div>
                        ) : orgOptions ? (
                            <div className={styles.selectionPanel}>
                                <div className={styles.selectionHeader}>
                                    <button onClick={() => setOrgOptions(null)} className={styles.backBtn}>
                                        <span className="google-symbols">arrow_back</span>
                                    </button>
                                    <span>Selecione a Filial Correta</span>
                                </div>
                                {orgOptions.options.map((opt: any, i: number) => (
                                    <div key={i} className={styles.optionItem} onClick={() => pickOption(opt)}>
                                        <span className={styles.optAddress}>{opt.address}</span>
                                        <div className={styles.optTags}>
                                            <span className={styles.orgTag}>{opt.cnpj}</span>
                                            <span className={styles.orgTag}>{opt.domain}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : pipedriveOrgs.map(org => (
                            <div 
                                key={org.id} 
                                className={styles.orgItem}
                                onClick={() => handleOrgClick(org)}
                            >
                                <div className={styles.orgInfo}>
                                    <span className={styles.orgName}>{org.name}</span>
                                    {org.address && (
                                        <span className={styles.orgAddress}>
                                            <span className="google-symbols" style={{fontSize: '12px'}}>location_on</span>
                                            {org.address}
                                        </span>
                                    )}
                                    <div className={styles.orgExtra}>
                                        {org.cnpj && <span className={styles.orgTag}>{org.cnpj}</span>}
                                        {org.domain && <span className={styles.orgTag} style={{background: 'rgba(99, 102, 241, 0.1)', color: '#6366f1'}}>{org.domain}</span>}
                                    </div>
                                    <span className={styles.orgDetail}>ID: {org.id} • {org.people_count || 0} contatos</span>
                                </div>
                                <button 
                                    className={`${styles.enrichBtn} ${enrichingIds.has(Number(org.id)) ? styles.enriching : ''}`}
                                    onClick={(e) => handleEnrichCorp(e, org)}
                                    title="Investigar Dados Corporativos (IA)"
                                >
                                    <span className="google-symbols">
                                        {enrichingIds.has(Number(org.id)) ? "autorenew" : "magic_button"}
                                    </span>
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* --- MAIN DASHBOARD AREA --- */}
            <main className={styles.mainContent}>
                {/* --- FLOATING SEARCH (CHAT STYLE) --- */}
                <div className={styles.searchContainer}>
                    {error && (
                        <div className={styles.error}>
                            <span className="google-symbols" style={{fontSize: '20px'}}>report</span>
                            {error}
                        </div>
                    )}
                    
                    <form onSubmit={handleSearch} className={styles.searchBox}>
                        <span className="google-symbols" style={{color: '#6c757d'}}>search</span>
                        
                        {step === "input" ? (
                            <>
                                <input 
                                    type="text" 
                                    value={cnpj}
                                    onChange={(e) => setCnpj(e.target.value)}
                                    placeholder="CNPJ (ex: 07.526.557/0001-00)"
                                    className={styles.input}
                                />
                                <div className={styles.divider}></div>
                                <input 
                                    type="text" 
                                    value={domainTarget}
                                    onChange={(e) => setDomainTarget(e.target.value)}
                                    placeholder="Domínio (opcional)"
                                    className={styles.input}
                                />
                            </>
                        ) : (
                            <div className={styles.confirmState}>
                                <span className={styles.confirmLabel}>Minerar LinkedIn como:</span>
                                <input 
                                    type="text" 
                                    value={confirmedBrand}
                                    onChange={(e) => setConfirmedBrand(e.target.value)}
                                    className={styles.brandInput}
                                />
                                <button 
                                    type="button" 
                                    onClick={() => {
                                        setStep("input");
                                        setError(null);
                                    }} 
                                    className={styles.backBtn}
                                >
                                    <span className="google-symbols">undo</span>
                                </button>
                            </div>
                        )}

                        <button type="submit" disabled={loading || discovering} className={styles.button}>
                            <span className="google-symbols">{step === "input" ? 'magic_button' : 'refresh'}</span>
                            {discovering ? 'Buscando Marca...' : 
                             (step === "input" ? 'Descobrir' : 
                             (rawEmployees.length > 0 ? 'Refazer Scan' : 'Iniciar Scan'))}
                        </button>
                    </form>

                    {/* BRAND SUGGESTIONS (CHIPS) */}
                    {step === "confirm" && brandOptions.length > 0 && (
                        <div className={styles.optionsContainer}>
                            <span className={styles.optionHint}>Sugestões da IA:</span>
                            {brandOptions.map(opt => (
                                <button 
                                    key={opt.name} 
                                    onClick={() => setConfirmedBrand(opt.name)}
                                    className={`${styles.chip} ${confirmedBrand === opt.name ? styles.chipActive : ''}`}
                                >
                                    {opt.logo && (
                                        <img 
                                            src={opt.logo} 
                                            alt="" 
                                            className={styles.chipLogo} 
                                            onError={(e) => {
                                                // Fallback em tempo real se a imagem falhar (ex: Hotlink block)
                                                const initials = opt.name.split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase();
                                                e.currentTarget.src = `https://ui-avatars.com/api/?name=${initials}&background=6366f1&color=fff&bold=true&rounded=true&size=128`;
                                            }}
                                        />
                                    )}
                                    <div className={styles.chipInfo}>
                                        <span className={styles.chipName}>{opt.name}</span>
                                        {opt.followers !== "N/A" && (
                                            <span className={styles.chipFollowers}>
                                                <span className="google-symbols" style={{fontSize: '12px'}}>group</span>
                                                {opt.followers}
                                            </span>
                                        )}
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* --- FLOATING LEGEND --- */}
                <div className={styles.legend}>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: '#6366f1'}}></div>
                        <span>Executivo (VIP/C-Level)</span>
                    </div>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: '#8b5cf6'}}></div>
                        <span>Gestão (Gerentes)</span>
                    </div>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: '#0ea5e9'}}></div>
                        <span>Coordenação</span>
                    </div>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: '#22c55e'}}></div>
                        <span>Analítico</span>
                    </div>
                </div>

                {/* --- REACT FLOW GRAPH --- */}
                <div className={styles.graphWrapper}>
                    <ReactFlow 
                        nodes={nodes} 
                        edges={edges} 
                        nodeTypes={nodeTypes}
                        edgeTypes={edgeTypes}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        onNodeMouseEnter={handleNodeMouseEnter}
                        onNodeMouseMove={handleNodeMouseMove}
                        onNodeMouseLeave={handleNodeMouseLeave}
                        fitView
                        attributionPosition="bottom-right"
                    >
                        <Controls />
                        <Background 
                            gap={24} 
                            size={1.5} 
                            color={theme === "dark" ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.1)"} 
                        />
                    </ReactFlow>
                </div>
            </main>

            {/* 💎 HOVER PREVIEW INTEL CARD */}
            {hoveredNode && (
                <div 
                    className={styles.hoverPreview}
                    style={{ 
                        left: hoveredNode.x + 20, 
                        top: hoveredNode.y > 400 ? hoveredNode.y - 340 : hoveredNode.y + 40,
                        opacity: hoveredNode ? 1 : 0,
                        transition: 'opacity 0.2s ease, transform 0.2s ease'
                    }}
                >
                    {previewLoading ? (
                        <div className={styles.previewLoader}>
                            <div className={styles.shimmer}></div>
                            <div className={styles.shimmerText}></div>
                        </div>
                    ) : previewData ? (
                        <div className={styles.previewContent}>
                            <div className={styles.previewImageWrapper}>
                                {previewData.image && (
                                    <img 
                                        src={`http://127.0.0.1:8000/api/v1/proxy/image?url=${encodeURIComponent(previewData.image)}`} 
                                        alt="" 
                                        className={styles.previewImage} 
                                        onError={(e) => {
                                            const initials = (previewData.name || "P").split(' ').map((n: string) => n[0]).join('').slice(0, 2).toUpperCase();
                                            e.currentTarget.src = `https://ui-avatars.com/api/?name=${initials}&background=0A66C2&color=fff&bold=true&size=200`;
                                        }}
                                    />
                                )}
                            </div>
                            
                            <div className={styles.previewInfo}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                                    <h4 className={styles.previewName} style={{ margin: 0 }}>{previewData.name || previewData.name}</h4>
                                    <span className="google-symbols" style={{ color: '#0095f6', fontSize: '18px', fontVariationSettings: "'FILL' 1" }}>verified</span>
                                </div>
                                
                                {/* Cargo da Pessoa */}
                                <p className={styles.previewRole} style={{ marginBottom: '8px', color: '#6c757d' }}>{previewData.role}</p>

                                {/* Nome da Empresa + Logo (Lado a Lado) */}
                                {previewData.company && previewData.company.toLowerCase() !== "linkedin" && (
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', background: 'rgba(10, 102, 194, 0.05)', padding: '6px 10px', borderRadius: '8px', width: 'fit-content' }}>
                                        <img 
                                            src={`https://logo.clearbit.com/${domainTarget || 'linkedin.com'}`} 
                                            alt="" 
                                            style={{ width: '18px', height: '18px', borderRadius: '4px', objectFit: 'contain', background: '#fff' }}
                                            onError={(e) => {
                                                const target = e.currentTarget;
                                                if (target.src.includes('clearbit')) {
                                                    // 🛡️ Segundo Escudo: Google Favicons ( sz=64 )
                                                    target.src = `https://www.google.com/s2/favicons?sz=64&domain=${domainTarget || 'linkedin.com'}`;
                                                } else if (target.src.includes('google')) {
                                                    // 🚩 Terceiro Escudo: UI Avatars ( Iniciais em Alta Resolução )
                                                    target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(confirmedBrand || 'Company')}&background=0A66C2&color=fff&size=64&bold=true`;
                                                }
                                            }}
                                        />
                                        <span style={{ color: '#0A66C2', fontWeight: 600, fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                                            {previewData.company}
                                        </span>
                                    </div>
                                )}

                                <p className={styles.previewDesc}>{previewData.description}</p>
                                
                                <div className={styles.previewMeta}>
                                    <div className={styles.previewLink}>
                                        <span className="google-symbols" style={{fontSize: '14px'}}>verified</span>
                                        LinkedIn Intel
                                    </div>
                                    <span className={styles.previewTime}>10/10 Accuracy</span>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className={styles.previewCompact}>
                            <p className={styles.previewDesc}>{hoveredNode.data?.role}</p>
                            <small>Passe o mouse para mais detalhes...</small>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

