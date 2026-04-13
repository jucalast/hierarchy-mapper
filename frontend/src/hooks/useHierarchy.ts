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
    const [streamAbortController, setStreamAbortController] = useState<AbortController | null>(null);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);

    const cleanName = (name: string) => {
        if (!name) return "";
        return name
            .replace(/\|?\s*Linked\s*In/gi, '') // Remove "| LinkedIn", "LinkedIn", "Linked In"
            .replace(/\(\s*LinkedIn\s*\)/gi, '') // Remove "(LinkedIn)"
            .trim();
    };

    // 🛑 Função para cancelar o stream de descoberta
    const cancelDiscovery = useCallback(() => {
        if (streamAbortController) {
            console.log("[useHierarchy] 🛑 Cancelando stream de descoberta...");
            streamAbortController.abort();
            setStreamAbortController(null);
            setDiscovering(false);
        }
    }, [streamAbortController]);

    const discoverBrand = async (searchCnpj: string, explicitDomain: string = "", force: boolean = true) => {
        setDiscovering(true);
        setError(null); 
        setBrandOptions([]);
        const rawCnpj = (searchCnpj || "").replace(/\D/g, "");
        // Pode buscar se tiver CNPJ OU se tiver Domínio Explicito
        if (!rawCnpj && !explicitDomain) return null;

        try {
            const queryParams = new URLSearchParams();
            queryParams.append("cnpj", rawCnpj);
            if (explicitDomain) queryParams.append("domain", explicitDomain);
            if (force) queryParams.append("force", "true");

            const response = await fetch(`http://127.0.0.1:8000/api/v1/brand/discover?${queryParams.toString()}`);
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
            return data; 
        } catch (err: any) {
            console.error(err);
            setError("Falha na conexão com o servidor.");
            return null;
        } finally {
            setDiscovering(false);
        }
    };

    const discoverBrandStream = async (searchCnpj: string, explicitDomain: string = "", force: boolean = true, onCandidateFound?: (candidate: any) => void) => {
        setDiscovering(true);
        setError(null);
        setBrandOptions([]);
        const rawCnpj = (searchCnpj || "").replace(/\D/g, "");
        
        if (!rawCnpj && !explicitDomain) return null;

        // 🛑 Cria novo AbortController para este stream
        const controller = new AbortController();
        setStreamAbortController(controller);

        try {
            const queryParams = new URLSearchParams();
            queryParams.append("cnpj", rawCnpj);
            if (explicitDomain) queryParams.append("domain", explicitDomain);
            if (force) queryParams.append("force", "true");
            queryParams.append("stream", "true"); // Ativa o modo streaming

            const response = await fetch(`http://127.0.0.1:8000/api/v1/brand/discover?${queryParams.toString()}`, {
                signal: controller.signal // Passa o sinal do AbortController
            });
            
            if (!response.ok) {
                setError("Erro ao iniciar streaming de marcas.");
                setDiscovering(false);
                setStreamAbortController(null);
                return null;
            }

            const reader = response.body?.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            const streamedCandidates: any[] = [];

            if (!reader) {
                setError("Não foi possível ler o stream.");
                setDiscovering(false);
                setStreamAbortController(null);
                return null;
            }

            // 🔄 Lê o stream e processa cada evento
            while (true) {
                // 🛑 Verifica se o stream foi cancelado
                if (controller.signal.aborted) {
                    console.log("[Stream] ⏹️ Stream cancelado pelo usuário.");
                    break;
                }

                try {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n");
                    
                    console.log(`[Stream] Buffer recebido, linhas: ${lines.length}`);

                // Processa linhas completas
                for (let i = 0; i < lines.length - 1; i++) {
                    const line = lines[i].trim();
                    if (line.startsWith("data: ")) {
                        try {
                            const jsonStr = line.substring(6); // Remove "data: "
                            const event = JSON.parse(jsonStr);
                            console.log(`[Stream] Evento recebido:`, event);

                            if (event.type === "candidate") {
                                console.log(`[Stream] Novo candidato: ${event.name}`);
                                streamedCandidates.push(event);
                                
                                // 🔄 Atualiza IMEDIATAMENTE com os candidatos encontrados até agora
                                const cleaned = streamedCandidates
                                    .map((opt: any) => ({
                                        ...opt,
                                        name: cleanName(opt.name)
                                    }))
                                    .sort((a: any, b: any) => (b.score || 0) - (a.score || 0)); // Ordena por score
                                
                                setBrandOptions(cleaned);
                                console.log(`[Stream] 📊 Carrossel atualizado com ${cleaned.length} perfis`);

                                // Callback para atualizar o carrossel em tempo real
                                if (onCandidateFound) {
                                    onCandidateFound({
                                        ...event,
                                        name: cleanName(event.name)
                                    });
                                }
                            } else if (event.type === "complete") {
                                console.log(`[Stream] Descoberta concluída. Total: ${event.total_candidates}`);
                                
                                // 🏆 Atualiza com os candidatos ordenados por score
                                if (event.top_alternatives && event.top_alternatives.length > 0) {
                                    const finalCandidates = event.top_alternatives.map((opt: any) => ({
                                        ...opt,
                                        name: cleanName(opt.name)
                                    }));
                                    console.log(`[Stream] Finalizando com ${finalCandidates.length} candidatos ordenados por score`);
                                    setBrandOptions(finalCandidates);
                                }
                            } else if (event.error) {
                                console.error(`[Stream] Erro: ${event.error}`);
                                setError(event.error);
                            }
                        } catch (e) {
                            console.warn("Erro ao parsear evento SSE:", e);
                        }
                    }
                }

                // Mantém a última linha incompleta no buffer
                buffer = lines[lines.length - 1];
                } catch (readErr: any) {
                    // Se o erro é por AbortError, é normal (usuário cancelou)
                    if (readErr.name === "AbortError" || controller.signal.aborted) {
                        console.log("[Stream] ⏹️ Stream leitura cancelada (AbortError).");
                        break;
                    }
                    // Outros erros, relança
                    throw readErr;
                }
            }

            return { alternatives: streamedCandidates };
        } catch (err: any) {
            console.error(err);
            setError("Falha na conexão com o servidor (streaming).");
            return null;
        } finally {
            setDiscovering(false);
            setStreamAbortController(null);
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
                            animated: false
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

    const fetchHierarchy = useCallback(async (
        searchCnpj: string, 
        explicitDomain: string = "", 
        confirmedBrand: string = "", 
        confirmedLogo: string = "",
        productFocus: string = "",
        areaFocus: string = "compras",
        onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void,
        partners: any[] = [],
        orgId?: number | null
    ) => {
        setLoading(true);
        setError("");
        setRawEmployees([]);
        setRawBackendEdges([]);
        
        const rawCnpj = (searchCnpj || "").replace(/\D/g, "");
        const queryParams = new URLSearchParams();
        queryParams.append("company_name", confirmedBrand || "Empresa");
        queryParams.append("cnpj", rawCnpj);
        queryParams.append("domain", explicitDomain);
        if (confirmedBrand) queryParams.append("confirmed_brand", confirmedBrand);
        if (confirmedLogo) queryParams.append("confirmed_logo", confirmedLogo);
        if (productFocus) queryParams.append("product_focus", productFocus);
        if (areaFocus) queryParams.append("area_focus", areaFocus);

        try {
            // 1. Inicia o Job no Backend
            const startResp = await fetch(`http://127.0.0.1:8000/api/v1/jobs/start-scan?${queryParams.toString()}`, {
                method: 'POST'
            });
            const { job_id, message } = await startResp.json();
            
            if (!job_id) {
                setError("Não foi possível iniciar o scan.");
                setLoading(false);
                return;
            }

            console.log(`[Job API] Scan iniciado! ID: ${job_id}`);
            
            // 💾 Salvar job em localStorage para persistência
            const jobData = {
                job_id,
                cnpj: rawCnpj,
                domain: explicitDomain,
                brand: confirmedBrand,
                logo: confirmedLogo,
                startTime: Date.now(),
                orgId: orgId
            };
            localStorage.setItem('active-discovery-job', JSON.stringify(jobData));
            setActiveJobId(job_id);

            // Conectar ao WebSocket e monitorar
            connectToJobWebSocket(job_id, confirmedBrand, confirmedLogo, explicitDomain, partners, onNotification);

        } catch (err) {
            console.error("[Job API] Erro ao disparar scan:", err);
            setError("Falha ao comunicar com o motor de tarefas.");
            if (onNotification) onNotification('error', "Não foi possível iniciar o scan.");
            setLoading(false);
        }
    }, [refineHierarchy, setLoading, setError]);

    const connectToJobWebSocket = useCallback((
        job_id: string,
        confirmedBrand: string,
        confirmedLogo: string,
        explicitDomain: string,
        partners: any[],
        onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void
    ) => {
        // 2. Conecta no WebSocket para monitorar o progresso
        const wsUrl = `ws://127.0.0.1:8000/api/v1/jobs/ws/${job_id}`;
        const ws = new WebSocket(wsUrl);
        
        // 🏢 INICIALIZAÇÃO IMEDIATA: Root Company + Sócios (QSA)
        let currentEmployees: HierarchyEmployee[] = [
            {
                id: 'root_company',
                name: confirmedBrand || "Empresa",
                role: "Holding / Matriz",
                department: "Corporate Root",
                level: 0,
                logo: confirmedLogo,
                company_logo: confirmedLogo,
                domain: explicitDomain
            }
        ];

        // Adiciona Sócios se existirem
        partners.forEach((p, idx) => {
            currentEmployees.push({
                id: `partner_${idx}`,
                name: p.name || `Sócio ${idx + 1}`,
                role: p.role || "Sócio / Administrador",
                department: "Quadro de Sócios (QSA)",
                level: 6, // Board / C-Level
                manager_id: 'root_company',
                company: confirmedBrand
            });
        });

        // Sincroniza estado inicial para renderização instantânea
        setRawEmployees([...currentEmployees]);

        const initialEdges: Edge[] = [];
        currentEmployees.forEach(emp => {
            if (emp.manager_id) {
                initialEdges.push({
                    id: `e-${emp.manager_id}-${emp.id}`,
                    source: emp.manager_id,
                    target: emp.id,
                    animated: false
                });
            }
        });
        setRawBackendEdges(initialEdges);

        // ⏱️ TIMEOUT: Se não receber 'done' em 5 minutos, fecha a conexão
        // (Previne jobs travados ou com 0 resultados)
        const timeoutId = setTimeout(() => {
            console.log("[WebSocket] ⏱️ Timeout: Nenhuma mensagem de conclusão recebida há 5 minutos");
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
            setLoading(false);
        }, 5 * 60 * 1000); // 5 minutos

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'error') {
                    setError(data.message);
                    ws.close();
                    setLoading(false);
                    clearTimeout(timeoutId);
                    localStorage.removeItem('active-discovery-job');
                    setActiveJobId(null);
                    return;
                }

                if (data.type === 'done') {
                    console.log("[Worker] Scan finalizado via WebSocket.");
                    ws.close();
                    setLoading(false);
                    clearTimeout(timeoutId);
                    localStorage.removeItem('active-discovery-job');
                    setActiveJobId(null);
                    if (onNotification) onNotification('success', "Mapeamento concluído com sucesso!");
                    refineHierarchy(currentEmployees);
                    return;
                }

                if (data.type === 'batch' || data.type === 'initial') {
                    const incomingNodes = (data.nodes || []) as HierarchyEmployee[];
                    
                    // 🛠️ ATUALIZAÇÃO SÍNCRONA: Mantemos currentEmployees atualizado IMEDIATAMENTE.
                    incomingNodes.forEach(emp => {
                        const idx = currentEmployees.findIndex(n => n.id === emp.id);
                        if (idx > -1) {
                            // Merge de metadados para evitar perda de imagens/urls
                            const merged = { ...currentEmployees[idx], ...emp };
                            const imgFields = ['logo', 'image', 'url', 'company_logo', 'logo_url', 'brand_logo', 'avatar', 'profile_pic', 'photo'];
                            imgFields.forEach(field => {
                                if ((currentEmployees[idx] as any)[field] && !(emp as any)[field]) {
                                    (merged as any)[field] = (currentEmployees[idx] as any)[field];
                                }
                            });
                            currentEmployees[idx] = merged;
                        } else {
                            currentEmployees.push(emp);
                        }
                    });

                    // Sincroniza com o state do React para renderização
                    setRawEmployees([...currentEmployees]);

                    setRawBackendEdges(prev => {
                        const next = [...prev];
                        incomingNodes.forEach(emp => {
                            if (emp.manager_id) {
                                const edgeIdx = next.findIndex(e => e.target === emp.id);
                                const newEdge = {
                                    id: `e-${emp.manager_id}-${emp.id}`,
                                    source: emp.manager_id,
                                    target: emp.id,
                                    animated: false
                                };
                                if (edgeIdx > -1) next[edgeIdx] = newEdge;
                                else next.push(newEdge);
                            }
                        });
                        return next;
                    });
                }
            } catch (e) {
                console.error("[WS] Erro ao processar mensagem:", e);
            }
        };

        ws.onerror = () => {
            setError("Erro na conexão WebSocket com o Worker.");
            setLoading(false);
            clearTimeout(timeoutId);
        };
    }, [refineHierarchy, setLoading, setError]);

    const reconnectToActiveJob = useCallback(async (onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void) => {
        const jobDataStr = localStorage.getItem('active-discovery-job');
        if (!jobDataStr) return false;

        try {
            const jobData = JSON.parse(jobDataStr);
            const { job_id, brand, logo, domain } = jobData;

            console.log(`[Reconnect] 🔄 Reconectando ao job: ${job_id}`);
            if (onNotification) {
                onNotification('info', `Reconectado ao mapeamento em andamento (${brand})...`);
            }

            // Reconecta ao WebSocket
            connectToJobWebSocket(job_id, brand, logo, domain, [], onNotification);
            setActiveJobId(job_id);
            return true;
        } catch (e) {
            console.error("[Reconnect] Erro ao reconectar:", e);
            localStorage.removeItem('active-discovery-job');
            return false;
        }
    }, [connectToJobWebSocket]);

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
                // Limpeza de URLs para evitar Duplo Proxy (IDEMPOTÊNCIA)
                const cleanedNodes = data.nodes.map((n: any) => {
                    const cleanUrl = (url: string) => {
                        if (!url) return url;
                        if (url.includes('proxy/image?url=')) {
                            return decodeURIComponent(url.split('proxy/image?url=')[1]);
                        }
                        return url;
                    };
                    return {
                        ...n,
                        logo: cleanUrl(n.logo),
                        company_logo: cleanUrl(n.company_logo),
                        profile_pic: cleanUrl(n.profile_pic)
                    };
                });
                
                setRawEmployees(cleanedNodes);
                
                const newEdges: Edge[] = [];
                data.nodes.forEach((emp: any) => {
                    if (emp.manager_id && emp.id !== "root_company") {
                        newEdges.push({
                            id: `e-${emp.manager_id}-${emp.id}`,
                            source: emp.manager_id,
                            target: emp.id,
                            animated: false
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

    const confirmIntelligence = useCallback(async (payload: { name: string, cnpj?: string, domain?: string, address?: string, pipedrive_id?: number, linkedin_url?: string, logo_url?: string, partners?: any[] }) => {
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

    const resetHierarchy = useCallback(() => {
        setRawEmployees([]);
        setRawBackendEdges([]);
        setBrandOptions([]);
        setError(null);
    }, []);

    return { 
        rawEmployees, 
        rawBackendEdges, 
        loading, 
        discovering,
        brandOptions,
        error, 
        setError,
        activeJobId,
        discoverBrand,
        discoverBrandStream,
        cancelDiscovery,
        fetchHierarchy,
        connectToJobWebSocket,
        reconnectToActiveJob,
        loadStoredHierarchy,
        refineHierarchy,
        updateEmployee,
        smartSyncPipedrive,
        confirmIntelligence,
        resetHierarchy
    };
};
