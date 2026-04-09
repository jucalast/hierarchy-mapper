import { useState, useCallback } from 'react';
import { Edge, MarkerType } from 'reactflow';
import { HierarchyEmployee } from '@/services/api';

export const useHierarchy = () => {
    const [rawEmployees, setRawEmployees] = useState<HierarchyEmployee[]>([]);
    const [rawBackendEdges, setRawBackendEdges] = useState<Edge[]>([]);
    const [loading, setLoading] = useState(false);
    const [discovering, setDiscovering] = useState(false);
    const [brandOptions, setBrandOptions] = useState<any[]>([]);
    const [error, setError] = useState<string | null>(null);

    const cleanName = (name: string) => {
        if (!name) return "";
        return name
            .replace(/\|?\s*Linked\s*In/gi, '') // Remove "| LinkedIn", "LinkedIn", "Linked In"
            .replace(/\(\s*LinkedIn\s*\)/gi, '') // Remove "(LinkedIn)"
            .trim();
    };

    const discoverBrand = async (searchCnpj: string, explicitDomain: string = "") => {
        setDiscovering(true);
        setError(null); 
        setBrandOptions([]);
        const rawCnpj = searchCnpj.replace(/\D/g, "");
        if (!rawCnpj) return null;

        try {
            const response = await fetch(`http://127.0.0.1:8000/api/v1/brand/discover?cnpj=${rawCnpj}${explicitDomain ? `&domain=${explicitDomain}` : ''}`);
            const data = await response.json();
            
            if (!response.ok) {
                if (data.detail && data.detail.includes("429")) {
                    console.warn("BrasilAPI Rate Limit - Operando em modo de resiliência.");
                    return null;
                }
                setError(data.detail || "Erro ao buscar marcas da empresa.");
                return null;
            }

            const cleaned = (data.alternatives || []).map((opt: any) => ({
                ...opt,
                name: cleanName(opt.name)
            }));
            setBrandOptions(cleaned);
            return { 
                brand: cleanName(data.brand), 
                domain: data.detected_domain 
            }; 
        } catch (err: any) {
            console.error(err);
            setError("Falha na conexão com o servidor.");
            return null;
        } finally {
            setDiscovering(false);
        }
    };


    const refineHierarchy = useCallback(async (employees: HierarchyEmployee[]) => {
        if (!employees || employees.length === 0) return;
        setLoading(true);
        setError("");
        console.log("[useHierarchy] Iniciando refinamento automático com Groq IA...");
        try {
            const response = await fetch(`http://127.0.0.1:8000/api/v1/hierarchy/refine`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(employees)
            });
            const data = await response.json();
            if (data.nodes) {
                const refreshedNodes = data.nodes.map((emp: any) => {
                    // Fallback de segurança: Se a IA desconectar alguém, reconecta na raiz
                    if (!emp.manager_id && emp.id !== "root_company") {
                        return { ...emp, manager_id: "root_company" };
                    }
                    return emp;
                });

                setRawEmployees(refreshedNodes);
                const newEdges: Edge[] = [];
                refreshedNodes.forEach((emp: any) => {
                    if (emp.manager_id) {
                        newEdges.push({
                            id: `e-${emp.manager_id}-${emp.id}`,
                            source: emp.manager_id,
                            target: emp.id,
                            animated: false,
                            markerEnd: { type: MarkerType.ArrowClosed, color: '#30363d' },
                            style: { stroke: '#30363d', strokeWidth: 2 },
                        });
                    }
                });
                setRawBackendEdges(newEdges);
                console.log("[useHierarchy] Hierarquia refinada e reconectada com sucesso.");
            }

        } catch (err) {
            console.error(err);
            setError("Erro ao refinar hierarquia com IA.");
        } finally {
            setLoading(false);
        }
    }, []);

    const fetchHierarchy = useCallback((
        searchCnpj: string, 
        explicitDomain: string = "", 
        confirmedBrand: string = "", 
        confirmedLogo: string = "",
        productFocus: string = "",
        areaFocus: string = "compras"
    ) => {
        setLoading(true);
        setError("");
        setRawEmployees([]);
        setRawBackendEdges([]);
        
        const rawCnpj = (searchCnpj || "").replace(/\D/g, "");
        const queryParams = new URLSearchParams();
        queryParams.append("cnpj", rawCnpj);
        if (explicitDomain) queryParams.append("domain", explicitDomain);
        if (confirmedBrand) queryParams.append("confirmed_brand", confirmedBrand);
        if (confirmedLogo) queryParams.append("confirmed_logo", confirmedLogo);
        if (productFocus) queryParams.append("product_focus", productFocus);
        if (areaFocus) queryParams.append("area_focus", areaFocus);

        const apiUrl = `http://127.0.0.1:8000/api/v1/hierarchy/stream?${queryParams.toString()}`;
        const sse = new EventSource(apiUrl);

        let currentEmployees: HierarchyEmployee[] = [];

        sse.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'error') { 
                    setError(data.message); 
                    sse.close(); 
                    setLoading(false); 
                    return; 
                }
                
                if (data.type === 'done') { 
                    console.log("[Stream] Finalizado com sucesso.");
                    sse.close(); 
                    refineHierarchy(currentEmployees);
                    return; 
                }
                
                if (data.type === 'initial' || data.type === 'batch') {
                    const incomingNodes = (data.nodes || []) as HierarchyEmployee[];
                    console.log(`[Stream] Recebido lote de ${incomingNodes.length} nós.`);
                    
                    setRawEmployees(prev => {
                        const next = [...prev];
                        incomingNodes.forEach(emp => {
                            const idx = next.findIndex(n => n.id === emp.id);
                            if (idx > -1) next[idx] = emp;
                            else next.push(emp);
                        });
                        currentEmployees = next;
                        return next;
                    });

                    setRawBackendEdges(prev => {
                        const next = [...prev];
                        incomingNodes.forEach(emp => {
                            if (emp.manager_id) {
                                const edgeIdx = next.findIndex(e => e.target === emp.id);
                                const newEdge = {
                                    id: `e-${emp.manager_id}-${emp.id}`,
                                    source: emp.manager_id,
                                    target: emp.id,
                                    animated: true,
                                    markerEnd: { type: MarkerType.ArrowClosed, color: '#30363d' },
                                    style: { stroke: '#30363d', strokeWidth: 2 },
                                };
                                if (edgeIdx > -1) next[edgeIdx] = newEdge;
                                else next.push(newEdge);
                            }
                        });
                        return next;
                    });
                }
            } catch (err) {
                console.error("[Stream] Erro crítico no parsing do evento:", err);
                setError("Erro de processamento no fluxo de dados.");
            }
        };

        sse.onerror = () => { 
            sse.close(); 
            setLoading(false); 
        };
    }, [refineHierarchy]);

    const loadStoredHierarchy = useCallback(async (orgId: number, isPipedriveId: boolean = true) => {
        setLoading(true);
        setError("");
        setRawEmployees([]);
        setRawBackendEdges([]);
        try {
            const url = isPipedriveId 
                ? `http://127.0.0.1:8000/api/v1/hierarchy/pipedrive/${orgId}`
                : `http://127.0.0.1:8000/api/v1/hierarchy/${orgId}`;
                
            const resp = await fetch(url);
            const data = await resp.json();
            
            if (data.nodes && data.nodes.length > 0) {
                setRawEmployees(data.nodes);
                
                const newEdges: Edge[] = [];
                data.nodes.forEach((emp: any) => {
                    if (emp.manager_id && emp.id !== "root_company") {
                        newEdges.push({
                            id: `e-${emp.manager_id}-${emp.id}`,
                            source: emp.manager_id,
                            target: emp.id,
                            animated: false,
                            markerEnd: { type: MarkerType.ArrowClosed, color: '#30363d' },
                            style: { stroke: '#30363d', strokeWidth: 2 },
                        });
                    }
                });
                setRawBackendEdges(newEdges);
                console.log(`[Database] Carregados ${data.nodes.length} nós do banco para ${data.company_name}.`);
                return data;
            }
            return null;
        } catch (e) {
            console.error("Load hierarchy error", e);
            setError("Erro ao carregar dados do banco.");
            return null;
        } finally {
            setLoading(false);
        }
    }, []);

    const updateEmployee = useCallback((id: string, updates: Partial<HierarchyEmployee>) => {
        setRawEmployees(prev => {
            const index = prev.findIndex(e => e.id === id);
            if (index === -1) return prev;
            const updated = [...prev];
            updated[index] = { ...updated[index], ...updates };
            return updated;
        });
    }, []);

    const smartSyncPipedrive = useCallback(async () => {
        setLoading(true);
        setError("");
        try {
            const resp = await fetch(`http://127.0.0.1:8000/api/v1/pipedrive_smart_sync`, { method: 'POST' });
            const data = await resp.json();
            if (data.status === "success") {
                console.log("[Pipedrive] Smart Sync concluído:", data.message);
                return data;
            } else {
                setError(data.message || "Erro no Smart Sync.");
            }
        } catch (e) {
            console.error("Smart Sync error", e);
            setError("Erro ao conectar com Pipedrive.");
        } finally {
            setLoading(false);
        }
    }, []);

    const confirmIntelligence = useCallback(async (payload: { name: string, cnpj?: string, domain?: string, address?: string, pipedrive_id?: number }) => {
        try {
            const resp = await fetch(`http://127.0.0.1:8000/api/v1/intelligence/confirm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            return await resp.json();
        } catch (e) {
            console.error("Confirm intelligence error", e);
            return { status: "error" };
        }
    }, []);

    return { 
        rawEmployees, 
        rawBackendEdges, 
        loading, 
        discovering,
        brandOptions,
        error, 
        setError,
        discoverBrand,
        fetchHierarchy,
        loadStoredHierarchy,
        refineHierarchy,
        updateEmployee,
        smartSyncPipedrive,
        confirmIntelligence
    };
};
