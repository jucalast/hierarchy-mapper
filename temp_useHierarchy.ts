import { useState, useCallback, useRef, useEffect } from 'react';
import { Edge } from 'reactflow';
import type { HierarchyEmployee } from '@/types';
import {
    hierarchy as hierarchyApi,
    jobs as jobsApi,
    organizations as orgsApi,
} from '@/services/api';

export const useHierarchy = () => {
    const [rawEmployees, setRawEmployees] = useState<HierarchyEmployee[]>([]);
    const [rawBackendEdges, setRawBackendEdges] = useState<Edge[]>([]);
    const [loading, setLoading] = useState(false);
    const [discovering, setDiscovering] = useState(false);
    const [brandOptions, setBrandOptions] = useState<any[]>([]);
    const currentEmployeesRef = useRef<HierarchyEmployee[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [streamAbortController, setStreamAbortController] = useState<AbortController | null>(null);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);

    // Auto-reconecta ao WebSocket se houver um job ativo persistido no localStorage
    useEffect(() => {
        const saved = localStorage.getItem('active-discovery-job');
        if (!saved) return;
        let jobData: any;
        try { jobData = JSON.parse(saved); } catch { return; }
        const { job_id, brand, logo, domain, orgId, chatPrompted } = jobData;
        if (!job_id) return;
        console.log('[useHierarchy] Reconectando ao job:', job_id);
        setLoading(true);
        setActiveJobId(job_id);
        // Reconecta sem initialEmployees â€” o WebSocket vai repassar os dados
        connectToJobWebSocket(job_id, brand || '', logo || '', domain || '', [], undefined, undefined, orgId, chatPrompted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const cleanName = (name: string) => {
        if (!name) return "";
        return name
            .replace(/\|?\s*Linked\s*In/gi, '') // Remove "| LinkedIn", "LinkedIn", "Linked In"
            .replace(/\(\s*LinkedIn\s*\)/gi, '') // Remove "(LinkedIn)"
            .trim();
    };

    // ðŸ›‘ FunÃ§Ã£o para cancelar o stream de descoberta
    const cancelDiscovery = useCallback(() => {
        if (streamAbortController) {
            console.log("[useHierarchy] ðŸ›‘ Cancelando stream de descoberta...");
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
        // Pode buscar se tiver CNPJ OU se tiver DomÃ­nio Explicito
        if (!rawCnpj && !explicitDomain) return null;

        try {
            const data = await hierarchyApi.discoverBrand({
                cnpj: rawCnpj,
                domain: explicitDomain || undefined,
                force,
            });

            const cleaned = ((data as any).alternatives || []).map((opt: any) => ({
                ...opt,
                name: cleanName(opt.name)
            }));
            setBrandOptions(cleaned);
            return data;
        } catch (err: any) {
            const msg = err?.message || String(err);
            if (msg.includes('429')) {
                console.warn('BrasilAPI Rate Limit - Operando em modo de resiliÃªncia.');
                return null;
            }
            console.error(msg);
            setError(err?.detail || 'Erro ao buscar marcas da empresa.');
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

        // ðŸ›‘ Cria novo AbortController para este stream
        const controller = new AbortController();
        setStreamAbortController(controller);

        try {
            const streamUrl = hierarchyApi.getDiscoverBrandStreamUrl({
                cnpj: rawCnpj,
                domain: explicitDomain || undefined,
                force,
            });

            const response = await fetch(streamUrl, {
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
                setError("NÃ£o foi possÃ­vel ler o stream.");
                setDiscovering(false);
                setStreamAbortController(null);
                return null;
            }

            // ðŸ”„ LÃª o stream e processa cada evento
            while (true) {
                // ðŸ›‘ Verifica se o stream foi cancelado
                if (controller.signal.aborted) {
                    console.log("[Stream] â¹ï¸ Stream cancelado pelo usuÃ¡rio.");
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
                                
                                // ðŸ”„ Atualiza IMEDIATAMENTE com os candidatos encontrados atÃ© agora
                                const cleaned = streamedCandidates
                                    .map((opt: any) => ({
                                        ...opt,
                                        name: cleanName(opt.name)
                                    }))
                                    .sort((a: any, b: any) => (b.score || 0) - (a.score || 0)); // Ordena por score
                                
                                setBrandOptions(cleaned);
                                console.log(`[Stream] ðŸ“Š Carrossel atualizado com ${cleaned.length} perfis`);

                                // Callback para atualizar o carrossel em tempo real
                                if (onCandidateFound) {
                                    onCandidateFound({
                                        ...event,
                                        name: cleanName(event.name)
                                    });
                                }
                            } else if (event.type === "complete") {
                                console.log(`[Stream] Descoberta concluÃ­da. Total: ${event.total_candidates}`);
                                
                                // ðŸ† Atualiza com os candidatos ordenados por score
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

                // MantÃ©m a Ãºltima linha incompleta no buffer
                buffer = lines[lines.length - 1];
                } catch (readErr: any) {
                    // Se o erro Ã© por AbortError, Ã© normal (usuÃ¡rio cancelou)
                    if (readErr.name === "AbortError" || controller.signal.aborted) {
                        console.log("[Stream] â¹ï¸ Stream leitura cancelada (AbortError).");
                        break;
                    }
                    // Outros erros, relanÃ§a
                    throw readErr;
                }
            }

            return { alternatives: streamedCandidates };
        } catch (err: any) {
            console.error(err.message || err);
            setError("Falha na conexÃ£o com o servidor (streaming).");
            return null;
        } finally {
            setDiscovering(false);
            setStreamAbortController(null);
        }
    };


    const refineHierarchy = useCallback(async (employees: HierarchyEmployee[]) => {
        if (!employees || employees.length === 0) return;
        
        // ðŸš« ProteÃ§Ã£o: NÃ£o permite rodar a inteligÃªncia enquanto um Discovery/Scanner Job estiver rodando em background
        if (localStorage.getItem('active-discovery-job')) {
            console.warn("[useHierarchy] O Analista de IA focou ignorado pois um mapeamento jÃ¡ estÃ¡ em andamento.");
            // Agora o toast Ã© chamado no frontend, entÃ£o apenas ignoramos a execuÃ§Ã£o
            return;
        }

        setLoading(true);
        setError("");
        console.log("[useHierarchy] Iniciando refinamento automÃ¡tico com Groq IA...");
        try {
            const data = await hierarchyApi.refineHierarchy(employees);
            if (data.nodes) {
                const refreshedNodes = data.nodes.map((emp: any) => {
                    // Fallback de seguranÃ§a: Se a IA desconectar alguÃ©m, reconecta na raiz
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
                
                // ðŸ§¹ LIMPA o cache de layouts e arestas anteriores
                // Quando a hierarquia Ã© refinada, todas as posiÃ§Ãµes e conexÃµes antigas ficam invÃ¡lidas
                // Por isso, removemos TODOS os caches para forÃ§ar o recalcul do layout no prÃ³ximo render
                const keysToDelete: string[] = [];
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && (key.startsWith('layout-cache-') || key.startsWith('edges-cache-'))) {
                        keysToDelete.push(key);
                    }
                }
                keysToDelete.forEach(key => localStorage.removeItem(key));
                console.log(`[useHierarchy] Limpou ${keysToDelete.length} caches de layout/arestas antigas.`);
                console.log("[useHierarchy] Hierarquia refinada e reconectada com sucesso.");
            }

        } catch (err: any) {
            console.error(err.message || err);
            setError("Erro ao refinar hierarquia com IA.");
        } finally {
            setLoading(false);
        }
    }, []);

    const stopHierarchyScan = useCallback(async (onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void) => {
        if (!activeJobId) {
            console.warn("[stopHierarchyScan] Nenhum job em andamento para cancelar.");
            return;
        }
        
        try {
            await jobsApi.cancelJob(activeJobId);
            console.log('[Job API] Mapeamento abortado com sucesso.');
            if (onNotification) {
                onNotification('error', 'Mapeamento cancelado pelo usuÃ¡rio.');
            }
            setError(''); // Opcionalmente limpar erro se nÃ£o quiser display duplicado
        } catch (e) {
            console.warn('[Job API] Erro ao tentar abortar o job:', (e as any).message || e);
            if (onNotification) {
                onNotification('error', 'Erro ao cancelar o mapeamento.');
            }
        } finally {
            setLoading(false);
            localStorage.removeItem('active-discovery-job');
            setActiveJobId(null);
        }
    }, [activeJobId, setLoading, setError]);

    const fetchHierarchy = useCallback(async (
        searchCnpj: string, 
        explicitDomain: string = "", 
        confirmedBrand: string = "", 
        confirmedLogo: string = "",
        productFocus: string = "",
        areaFocus: string = "compras",
        onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void,
        partners: any[] = [],
        orgId?: number | null,
        initialEmployees?: HierarchyEmployee[],
        model?: string,
        strictMode?: boolean
    ) => {
        setLoading(true);
        setError("");
        setRawBackendEdges([]);

        // Ao iniciar novo scan, limpa imediatamente entradas de "AnÃ¡lise Humana" de scans anteriores.
        // Se hÃ¡ initialEmployees (root + sÃ³cios), usa-os como base; caso contrÃ¡rio, zera tudo.
        setRawEmployees(initialEmployees && initialEmployees.length > 0 ? initialEmployees : []);
        
        const rawCnpj = (searchCnpj || "").replace(/\D/g, "");

        try {
            // 1. Inicia o Job no Backend
            const { job_id } = await jobsApi.startScan({
                company_name: confirmedBrand || 'Empresa',
                cnpj: rawCnpj,
                domain: explicitDomain,
                confirmed_brand: confirmedBrand,
                confirmed_logo: confirmedLogo,
                product_focus: productFocus,
                area_focus: areaFocus,
                model: model || undefined,
                strict_mode: strictMode !== undefined ? strictMode : undefined,
            });

            if (!job_id) {
                setError("NÃ£o foi possÃ­vel iniciar o scan.");
                setLoading(false);
                return;
            }

            console.log(`[Job API] Scan iniciado! ID: ${job_id}`);
            
            // ðŸš€ Identifica se foi originado pelo Chat Panel
            const pending = localStorage.getItem('pending-hierarchy-continuation');
            let chatPrompted = false;
            if (pending) {
                try {
                    const parsed = JSON.parse(pending);
                    if (parsed && (parsed.org_id === orgId || Number(parsed.org_id) === Number(orgId))) {
                        chatPrompted = true;
                    }
                } catch {}
            }

            // ðŸ’¾ Salvar job em localStorage para persistÃªncia
            const jobData = {
                job_id,
                cnpj: rawCnpj,
                domain: explicitDomain,
                brand: confirmedBrand,
                logo: confirmedLogo,
                startTime: Date.now(),
                orgId: orgId,
                chatPrompted: chatPrompted
            };
            localStorage.setItem('active-discovery-job', JSON.stringify(jobData));
            setActiveJobId(job_id);
            // Notifica o chat que o scan iniciou (para o HierarchyMappingCard atualizar status)
            window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));

            // Conectar ao WebSocket e monitorar
            connectToJobWebSocket(job_id, confirmedBrand, confirmedLogo, explicitDomain, partners, onNotification, initialEmployees, orgId, chatPrompted);

        } catch (err: any) {
            console.error("[Job API] Erro ao disparar scan:", err.message || err);
            setError("Falha ao comunicar com o motor de tarefas.");
            if (onNotification) onNotification('error', "NÃ£o foi possÃ­vel iniciar o scan.");
            setLoading(false);
        }
    }, [refineHierarchy, setLoading, setError]);

    const connectToJobWebSocket = useCallback((
        job_id: string,
        confirmedBrand: string,
        confirmedLogo: string,
        explicitDomain: string,
        partners: any[],
        onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void,
        initialEmployees?: HierarchyEmployee[],
        orgId?: number | null,
        chatPrompted?: boolean
    ) => {
        // 2. Conecta no WebSocket para monitorar o progresso
        const wsUrl = jobsApi.getJobWebSocketUrl(job_id);
        const ws = new WebSocket(wsUrl);
        
        let currentEmployees: HierarchyEmployee[] = [];

        if (initialEmployees && initialEmployees.length > 0) {
            // Usa o que jÃ¡ foi mapeado (Ãºtil para reconexÃ£o)
            currentEmployees = [...initialEmployees];
            console.log(`[WS] Inicializando com ${currentEmployees.length} funcionÃ¡rios prÃ©-existentes.`);
        } else {
            // ðŸ¢ INICIALIZAÃ‡ÃƒO IMEDIATA: Root Company + SÃ³cios (QSA)
            currentEmployees = [
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

            // Adiciona SÃ³cios se existirem
            partners.forEach((p, idx) => {
                currentEmployees.push({
                    id: `partner_${idx}`,
                    name: p.name || `SÃ³cio ${idx + 1}`,
                    role: p.role || "SÃ³cio / Administrador",
                    department: "Quadro de SÃ³cios (QSA)",
                    level: 6, // Board / C-Level
                    manager_id: 'root_company',
                    company: confirmedBrand
                });
            });
        }

        // Sincroniza estado inicial para renderizaÃ§Ã£o instantÃ¢nea
        currentEmployeesRef.current = [...currentEmployees];
        setRawEmployees([...currentEmployees]);

        const initialEdges: Edge[] = [];
        currentEmployees.forEach(emp => {
            if (emp.manager_id && emp.id !== "root_company") {
                initialEdges.push({
                    id: `e-${emp.manager_id}-${emp.id}`,
                    source: emp.manager_id,
                    target: emp.id,
                    animated: false,
                    style: { stroke: '#6e7681', strokeWidth: 1.5 }
                });
            }
        });
        setRawBackendEdges(initialEdges);

        // â±ï¸ WATCHDOG TIMEOUT: Se nÃ£o receber NENHUMA mensagem (nem ping/batch) em 5 minutos, fecha a conexÃ£o
        let timeoutId: NodeJS.Timeout;
        let scanDoneDispatched = false; // Flag para nÃ£o disparar hierarchy_scan_done duas vezes
        
        const dispatchScanDone = (fromDone: boolean) => {
            if (scanDoneDispatched) return;
            scanDoneDispatched = true;
            window.dispatchEvent(new CustomEvent('hierarchy_scan_done', {
                detail: {
                    orgId: orgId,
                    orgName: confirmedBrand,
                    chatPrompted: chatPrompted,
                    contacts: currentEmployeesRef.current
                        .filter(e => 
                            e.id !== 'root_company' && 
                            e.name &&
                            (e as any).role !== 'Reprovado' &&
                            (e as any).department !== 'Reprovado'
                        )
                        .map(e => ({
                            name: e.name,
                            role: (e as any).role || '',
                            email: (e as any).email || undefined,
                            department: (e as any).department || undefined,
                            temperature: (e as any).temperature || undefined,
                            level: (e as any).level,
                            decision_maker: [
                                'compras', 'procurement', 'suprimentos', 'logÃ­stica', 'logistica',
                                'supply chain', 'supply', 'materiais', 'aquisiÃ§Ã£o', 'aquisicao',
                                'estoque', 'sourcing'
                            ].some(k => ((e as any).role || '').toLowerCase().includes(k) || ((e as any).department || '').toLowerCase().includes(k)),
                        })),
                },
            }));
            if (!fromDone) {
                console.warn('[WebSocket] hierarchy_scan_done disparado por fallback (conexÃ£o encerrada antes do done)');
            }
        };
        
        const resetTimeout = () => {
            if (timeoutId) clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                console.log("[WebSocket] â±ï¸ Timeout: Nenhuma mensagem recebida hÃ¡ 5 minutos");
                if (ws.readyState === WebSocket.OPEN) {
                    ws.close();
                }
                // Despacha evento mesmo no timeout para nÃ£o travar o HierarchyMappingCard
                dispatchScanDone(false);
                setLoading(false);
                localStorage.removeItem('active-discovery-job');
                setActiveJobId(null);
            }, 5 * 60 * 1000); // 5 minutos sem atividade
        };
        resetTimeout();

        ws.onclose = () => {
            console.log("[WebSocket] ConexÃ£o encerrada pelo servidor.");
            clearTimeout(timeoutId);
            // Se o scan nÃ£o terminou normalmente (chatPrompted e sem done), notifica o card
            if (chatPrompted) {
                dispatchScanDone(false);
            }
            setLoading(false);
            localStorage.removeItem('active-discovery-job');
            setActiveJobId(null);
            
            // Dispara refinamento final como medida de seguranÃ§a se a conexÃ£o caiu
            setTimeout(() => {
                refineHierarchy(currentEmployeesRef.current);
            }, 500);
        };

        ws.onmessage = (event) => {
            resetTimeout();
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
                    if (onNotification) onNotification('success', "Mapeamento concluÃ­do com sucesso!");
                    // Notifica o chat agent que o mapeamento terminou, passando os contatos reais
                    dispatchScanDone(true);
                    ws.close(); // Isso vai disparar o ws.onclose, que faz a limpeza e o refineHierarchy.
                    return;
                }

                if (data.type === 'batch' || data.type === 'initial') {
                    const incomingNodes = (data.nodes || []) as HierarchyEmployee[];
                    
                    incomingNodes.forEach(emp => {
                        const idx = currentEmployeesRef.current.findIndex(n => 
                            String(n.id) === String(emp.id) || 
                            (n.linkedin && emp.linkedin && n.linkedin === emp.linkedin) ||
                            (n.name === emp.name && n.role === emp.role)
                        );
                        
                        if (idx > -1) {
                            if (currentEmployeesRef.current[idx].role?.startsWith('Aprovado') || currentEmployeesRef.current[idx].role === 'Reprovado') {
                                return;
                            }

                            const oldId = currentEmployeesRef.current[idx].id;
                            const merged = { ...emp, ...currentEmployeesRef.current[idx] };
                            merged.role = emp.role || merged.role;
                            merged.department = emp.department || merged.department;
                            merged.level = emp.level || merged.level;
                            merged.manager_id = emp.manager_id || merged.manager_id;

                            // Garante que o ID do backend prevalece se o local for provisÃ³rio (ex: partner_0)
                            if (String(oldId).startsWith('partner_') && !String(emp.id).startsWith('partner_')) {
                                merged.id = emp.id;
                            } else if (String(oldId).startsWith('partner_') && String(emp.id).startsWith('partner_')) {
                                const localParts = String(oldId).split('_');
                                const empParts = String(emp.id).split('_');
                                if (empParts[1] && empParts[1] !== localParts[1]) {
                                    merged.id = emp.id;
                                }
                            }

                            const newId = merged.id;
                            if (String(oldId) !== String(newId)) {
                                console.log(`[useHierarchy] Atualizando ID provisÃ³rio: ${oldId} -> ${newId}`);
                                // Atualiza manager_id de outros nÃ³s que apontavam para o ID antigo
                                currentEmployeesRef.current.forEach(other => {
                                    if (String(other.manager_id) === String(oldId)) {
                                        other.manager_id = newId;
                                    }
                                });
                                // Atualiza as arestas correspondentes
                                setRawBackendEdges(prev => {
                                    return prev.map(edge => {
                                        let updated = false;
                                        const newEdge = { ...edge };
                                        if (String(edge.source) === String(oldId)) {
                                            newEdge.source = newId;
                                            updated = true;
                                        }
                                        if (String(edge.target) === String(oldId)) {
                                            newEdge.target = newId;
                                            updated = true;
                                        }
                                        if (updated) {
                                            newEdge.id = `e-${newEdge.source}-${newEdge.target}`;
                                        }
                                        return newEdge;
                                    });
                                });
                            }
                            
                            const imgFields = ['logo', 'image', 'url', 'company_logo', 'logo_url', 'brand_logo', 'avatar', 'profile_pic', 'photo'];
                            imgFields.forEach(field => {
                                if ((currentEmployeesRef.current[idx] as any)[field] && !(emp as any)[field]) {
                                    (merged as any)[field] = (currentEmployeesRef.current[idx] as any)[field];
                                }
                            });
                            currentEmployeesRef.current[idx] = merged;
                        } else {
                            currentEmployeesRef.current.push(emp);
                        }
                    });

                    setRawEmployees([...currentEmployeesRef.current]);
                    currentEmployees = [...currentEmployeesRef.current];

                    setRawBackendEdges(prev => {
                        const next = [...prev];
                        incomingNodes.forEach(emp => {
                            const myNode = currentEmployeesRef.current.find(n => 
                                String(n.id) === String(emp.id) || 
                                (n.linkedin && emp.linkedin && n.linkedin === emp.linkedin) ||
                                (n.name === emp.name && n.role === emp.role)
                            ) || emp;

                            if (myNode.manager_id && myNode.id !== "root_company") {
                                const edgeIdx = next.findIndex(e => String(e.target) === String(myNode.id));
                                const newEdge = {
                                    id: `e-${myNode.manager_id}-${myNode.id}`,
                                    source: myNode.manager_id,
                                    target: myNode.id,
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
                console.error("[WS] Erro ao processar mensagem:", (e as any).message || e);
            }
        };

        ws.onerror = () => {
            setError("Erro na conexÃ£o WebSocket com o Worker.");
            setLoading(false);
            clearTimeout(timeoutId);
        };
    }, [refineHierarchy, setLoading, setError]);

    const reconnectToActiveJob = useCallback(async (onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void) => {
        const jobDataStr = localStorage.getItem('active-discovery-job');
        if (!jobDataStr) return false;
        
        if (jobDataStr === "NaN" || jobDataStr === "undefined") {
            localStorage.removeItem('active-discovery-job');
            return false;
        }
        
        try {
            const jobData = JSON.parse(jobDataStr);
            const { job_id, brand, logo, domain } = jobData;

            // ðŸ” VALIDAR: O job ainda existe no Redis/Backend?
            try {
                await jobsApi.getJobStatus(job_id);
            } catch {
                console.warn(`[Reconnect] Job ${job_id} nÃ£o existe mais no backend. Limpando cache.`);
                localStorage.removeItem('active-discovery-job');
                return false;
            }

            console.log(`[Reconnect] ðŸ”„ Reconectando ao job: ${job_id}`);
            if (onNotification) {
                onNotification('info', `Reconectado ao mapeamento em andamento (${brand})...`);
            }

            // ðŸ’¾ ANTES DE RECONECTAR: Buscar o que JÃ FOI MAPEADO no banco!
            let existingEmployees: HierarchyEmployee[] = [];
            if (jobData.orgId) {
                try {
                    const data = await hierarchyApi.loadHierarchyByPipedrive(jobData.orgId);
                    if (data && data.nodes && data.nodes.length > 0) {
                        // Limpeza de URLs para nÃ£o duplicar proxy
                        existingEmployees = data.nodes.map((n: any) => {
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
                        console.log(`[Reconnect] Carregados ${existingEmployees.length} nÃ³s jÃ¡ existentes para ${brand}.`);
                    }
                } catch (e) {
                    console.warn('[Reconnect] Erro ao buscar hierarquia prÃ©via antes de reconectar:', e);
                }
            }

            // Reconecta ao WebSocket passando o que jÃ¡ temos
            setLoading(true);
            connectToJobWebSocket(
                job_id, 
                brand, 
                logo, 
                domain, 
                [], 
                onNotification, 
                existingEmployees.length > 0 ? existingEmployees : undefined
            );
            setActiveJobId(job_id);
            return true;
        } catch (e) {
            console.error("[Reconnect] Erro ao reconectar:", (e as any).message || e);
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
            let data: any = isPipedriveId
                ? await hierarchyApi.loadHierarchyByPipedrive(orgId)
                : await hierarchyApi.loadHierarchyByLocalId(orgId);

            // ðŸ”„ FALLBACK: Se tentou por Pipedrive e nÃ£o achou nada, tenta pelo ID local
            // Isso resolve o caso de empresas criadas manualmente ou que perderam o vÃ­nculo.
            if (isPipedriveId && (!data?.nodes || data.nodes.length === 0)) {
                console.log(`[useHierarchy] Hierarquia nÃ£o encontrada por Pipedrive ID ${orgId}. Tentando ID local...`);
                try {
                    const localData = await hierarchyApi.loadHierarchyByLocalId(orgId);
                    if (localData?.nodes && localData.nodes.length > 0) {
                        data = localData;
                    }
                } catch {
                    /* ignore fallback errors */
                }
            }
            
            if (data.nodes && data.nodes.length > 0) {
                // Limpeza de URLs para evitar Duplo Proxy (IDEMPOTÃŠNCIA)
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
                console.log(`[Database] Carregados ${data.nodes.length} nÃ³s do banco para ${data.company_name}.`);
                return data;
            }
            return null;
        } catch (e: any) {
            console.warn("[useHierarchy] Load hierarchy error:", (e as any).message || e);
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
            const data = await orgsApi.triggerSmartSync();
            if (data.status === 'success') {
                console.log('[Pipedrive] Smart Sync concluÃ­do:', data.message);
                return data;
            } else {
                setError(data.message || 'Erro no Smart Sync.');
            }
        } catch (e) {
            console.error('Smart Sync error:', (e as any).message || e);
            setError('Erro ao conectar com Pipedrive.');
        } finally {
            setLoading(false);
        }
    }, []);

    const confirmIntelligence = useCallback(async (payload: { name: string, cnpj?: string, domain?: string, address?: string, pipedrive_id?: number, linkedin_url?: string, logo_url?: string, partners?: any[] }) => {
        try {
            return await hierarchyApi.confirmIntelligence(payload as any);
        } catch (e) {
            console.error('Confirm intelligence error:', (e as any).message || e);
            return { status: 'error' };
        }
    }, []);

    const resetHierarchy = useCallback(() => {
        setRawEmployees([]);
        setRawBackendEdges([]);
        setBrandOptions([]);
        setError(null);
    }, []);

    const handleCandidateAction = async (employeeId: string, action: 'approve' | 'reject') => {
        try {
            const data = await hierarchyApi.candidateAction(employeeId, action);

            console.log(`[useHierarchy] Candidato ${action === 'approve' ? 'aprovado' : 'rejeitado'}:`, data);

            // ðŸ”„ AtualizaÃ§Ã£o de Estado Local (Usa conversÃ£o para String para evitar colisÃ£o entre id numÃ©rico e string do parÃ¢metro)
            if (action === 'approve') {
                setBrandOptions(prev => prev.filter(opt => String(opt.id) !== String(employeeId)));
                
                setRawEmployees(prev => {
                    const next = prev.map(emp => {
                        if (String(emp.id) === String(employeeId) && emp.role && emp.role.toLowerCase().includes('humana')) {
                            return { ...emp, role: 'Aprovado (Recarregue para ver cargo)' };
                        }
                        return emp;
                    });
                    currentEmployeesRef.current = next;
                    return next;
                });
            } else {
                setBrandOptions(prev => prev.filter(opt => String(opt.id) !== String(employeeId)));
                setRawEmployees(prev => {
                    const next = prev.map(emp => {
                        if (String(emp.id) === String(employeeId)) {
                            return { ...emp, role: 'Reprovado', department: 'Reprovado' };
                        }
                        return emp;
                    });
                    currentEmployeesRef.current = next;
                    return next;
                });
            }

            return data;
        } catch (e: any) {
            console.error(`[useHierarchy] Erro na aÃ§Ã£o ${action}:`, e.message);
            throw e;
        }
    };

    const approveCandidate = useCallback((id: string) => handleCandidateAction(id, 'approve'), []);
    const rejectCandidate = useCallback((id: string) => handleCandidateAction(id, 'reject'), []);

    const deleteEmployee = useCallback(async (id: string) => {
        // Se for um nÃ³ persistido no banco (ID comeÃ§a com node_), avisamos o backend
        if (String(id).startsWith('node_')) {
            try {
                await hierarchyApi.candidateAction(id, 'reject');
                console.log(`[useHierarchy] FuncionÃ¡rio ${id} removido e marcado como reprovado no banco.`);
            } catch (e) {
                console.error(`[useHierarchy] Erro ao sincronizar remoÃ§Ã£o com backend:`, e);
            }
        }

        setRawEmployees(prev => {
            const next = prev.filter(emp => String(emp.id) !== String(id));
            currentEmployeesRef.current = next;
            return next;
        });
        
        setRawBackendEdges(prev => {
            return prev.filter(edge => 
                String(edge.source) !== String(id) && 
                String(edge.target) !== String(id)
            );
        });
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
        stopHierarchyScan,
        connectToJobWebSocket,
        reconnectToActiveJob,
        loadStoredHierarchy,
        refineHierarchy,
        updateEmployee,
        smartSyncPipedrive,
        confirmIntelligence,
        setBrandOptions,
        resetHierarchy,
        approveCandidate,
        rejectCandidate,
        deleteEmployee,
        setRawEmployees,
        setRawBackendEdges
    };
};
