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
    const [isSmartSyncLoading, setIsSmartSyncLoading] = useState(false);

    // Contexto para despacho do evento de conclusão ao chat
    const chatContextRef = useRef({ chatPrompted: false, orgId: null as number | null, orgName: '' });
    const scanFinishedRef = useRef(false);
    const chatDoneDispatchedRef = useRef(false);

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
        // Reconecta sem initialEmployees — o WebSocket vai repassar os dados
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

    /**
     * Centraliza o despacho do evento 'hierarchy_scan_done'.
     * Só dispara se:
     * 1. O scan foi solicitado pelo chat (chatPrompted).
     * 2. O worker do backend já terminou (scanFinishedRef).
     * 3. Não há mais nenhum candidato com cargo "Análise Humana" pendente.
     */
    const checkAndDispatchChatEvent = useCallback((fromFallback = false) => {
        const { chatPrompted, orgId, orgName } = chatContextRef.current;
        if (!chatPrompted || chatDoneDispatchedRef.current) return;

        // Se o scan ainda não terminou, não podemos concluir (a menos que seja fallback de erro/timeout)
        if (!scanFinishedRef.current && !fromFallback) return;

        // Verifica se ainda há algum funcionário pendente de análise humana
        const hasPending = currentEmployeesRef.current.some(e => {
            const role = (e.role || '').toLowerCase();
            return role.includes('análise humana') || role.includes('analise humana');
        });

        // Se ainda há pendências e não é fallback, aguardamos o usuário terminar de clicar
        if (hasPending && !fromFallback) {
            console.log('[useHierarchy] Scan terminou, mas há Análise Humana pendente. Aguardando usuário...');
            return;
        }

        chatDoneDispatchedRef.current = true;

        // Filtra e formata os contatos finais para o agente
        const contacts = currentEmployeesRef.current
            .filter(e => {
                if (e.id === 'root_company' || !e.name) return false;
                const r = (e.role || '').toLowerCase();
                const d = (e.department || '').toLowerCase();
                // SEGURANÇA: Filtro case-insensitive para reprovados
                if (r.includes('reprovado') || d.includes('reprovado')) return false;
                return true;
            })
            .map(e => ({
                name: e.name,
                role: (e as any).role || '',
                email: (e as any).email || undefined,
                department: (e as any).department || undefined,
                temperature: (e as any).temperature || undefined,
                level: (e as any).level,
                decision_maker: [
                    'compras', 'procurement', 'suprimentos', 'logística', 'logistica',
                    'supply chain', 'supply', 'materiais', 'aquisição', 'aquisicao',
                    'estoque', 'sourcing'
                ].some(k => ((e as any).role || '').toLowerCase().includes(k) || ((e as any).department || '').toLowerCase().includes(k)),
            }));

        console.log(`[useHierarchy] ✅ Disparando hierarchy_scan_done. ${contacts.length} contatos aprovados.`);
        window.dispatchEvent(new CustomEvent('hierarchy_scan_done', {
            detail: {
                orgId,
                orgName,
                chatPrompted,
                contacts,
            },
        }));
    }, []);

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
                console.warn('BrasilAPI Rate Limit - Operando em modo de resiliência.');
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

        // 🛑 Cria novo AbortController para este stream
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
            console.error(err.message || err);
            setError("Falha na conexão com o servidor (streaming).");
            return null;
        } finally {
            setDiscovering(false);
            setStreamAbortController(null);
        }
    };


    const refineHierarchy = useCallback(async (employees: HierarchyEmployee[]) => {
        if (!employees || employees.length === 0) return;
        
        // 🚫 Proteção: Não permite rodar a inteligência enquanto um Discovery/Scanner Job estiver rodando em background
        if (localStorage.getItem('active-discovery-job')) {
            console.warn("[useHierarchy] O Analista de IA focou ignorado pois um mapeamento já está em andamento.");
            // Agora o toast é chamado no frontend, então apenas ignoramos a execução
            return;
        }

        setLoading(true);
        setError("");
        console.log("[useHierarchy] Iniciando refinamento automático com Groq IA...");
        try {
            const data = await hierarchyApi.refineHierarchy(employees);
            if (data.nodes) {
                const refreshedNodes = data.nodes.map((emp: any) => {
                    // Fallback de segurança: Se a IA desconectar alguém, reconecta na raiz
                    if (!emp.manager_id && emp.id !== "root_company") {
                        return { ...emp, manager_id: "root_company" };
                    }
                    return emp;
                });

                setRawEmployees(refreshedNodes);
                currentEmployeesRef.current = refreshedNodes; // ✅ Mantém o Ref sincronizado para o despacho do chat
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
                
                // 🧹 LIMPA o cache de layouts e arestas anteriores
                // Quando a hierarquia é refinada, todas as posições e conexões antigas ficam inválidas
                // Por isso, removemos TODOS os caches para forçar o recalcul do layout no próximo render
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
                onNotification('error', 'Mapeamento cancelado pelo usuário.');
            }
            setError(''); // Opcionalmente limpar erro se não quiser display duplicado
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

        // 🚀 INICIALIZAÇÃO IMEDIATA: Mantém apenas Root e Sócios se fornecidos ou já presentes.
        // Isso atende ao requisito: "os employees devem sumir do front, menos root e sócios".
        let keepers: HierarchyEmployee[] = [];
        
        if (initialEmployees && initialEmployees.length > 0) {
            // Se já temos os nós, garantimos que o Root reflita a marca confirmada agora
            keepers = initialEmployees.map(emp => {
                if (emp.id === 'root_company' || emp.level === 0) {
                    return {
                        ...emp,
                        name: confirmedBrand || emp.name,
                        logo: confirmedLogo || emp.logo,
                        company_logo: confirmedLogo || emp.company_logo,
                        domain: explicitDomain || emp.domain
                    };
                }
                return emp;
            });
        } else {
            // Se não temos initialEmployees (ex: nova empresa), criamos o root e partners básicos
            keepers.push({
                id: 'root_company',
                name: confirmedBrand || "Empresa",
                role: "Holding / Matriz",
                department: "Corporate Root",
                level: 0,
                logo: confirmedLogo,
                company_logo: confirmedLogo,
                domain: explicitDomain
            });

            partners.forEach((p, idx) => {
                keepers.push({
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

        setRawEmployees(keepers);
        currentEmployeesRef.current = [...keepers];
        
        // Gera arestas iniciais para os keepers
        const initialEdges: Edge[] = [];
        keepers.forEach(emp => {
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
        
        // Reseta estados de controle de chat
        scanFinishedRef.current = false;
        chatDoneDispatchedRef.current = false;
        
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
                setError("Não foi possível iniciar o scan.");
                setLoading(false);
                return;
            }

            console.log(`[Job API] Scan iniciado! ID: ${job_id}`);
            
            // 🚀 Identifica se foi originado pelo Chat Panel
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

            // 💾 Salvar job em localStorage para persistência
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

            // Inicializa contexto de conclusão
            chatContextRef.current = { chatPrompted, orgId: orgId || null, orgName: confirmedBrand };
            scanFinishedRef.current = false;
            chatDoneDispatchedRef.current = false;

            // Notifica o chat que o scan iniciou (para o HierarchyMappingCard atualizar status)
            window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));

            // Conectar ao WebSocket e monitorar
            connectToJobWebSocket(job_id, confirmedBrand, confirmedLogo, explicitDomain, partners, onNotification, initialEmployees, orgId, chatPrompted);

        } catch (err: any) {
            console.error("[Job API] Erro ao disparar scan:", err.message || err);
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
            // Usa o que já foi mapeado (útil para reconexão)
            currentEmployees = [...initialEmployees];
            console.log(`[WS] Inicializando com ${currentEmployees.length} funcionários pré-existentes.`);
        } else {
            // 🏢 INICIALIZAÇÃO IMEDIATA: Root Company + Sócios (QSA)
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
        }

        // Sincroniza estado inicial para renderização instantânea
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

        // ⏱️ WATCHDOG TIMEOUT: Se não receber NENHUMA mensagem (nem ping/batch) em 5 minutos, fecha a conexão
        let timeoutId: NodeJS.Timeout;
        
        const resetTimeout = () => {
            if (timeoutId) clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                console.log("[WebSocket] ⏱️ Timeout: Nenhuma mensagem recebida há 5 minutos");
                if (ws.readyState === WebSocket.OPEN) {
                    ws.close();
                }
                // Despacha evento mesmo no timeout para não travar o HierarchyMappingCard
                checkAndDispatchChatEvent(true);
                setLoading(false);
                localStorage.removeItem('active-discovery-job');
                setActiveJobId(null);
            }, 5 * 60 * 1000); // 5 minutos sem atividade
        };
        resetTimeout();

        ws.onclose = () => {
            console.log("[WebSocket] Conexão encerrada pelo servidor.");
            clearTimeout(timeoutId);
            // Se o scan não terminou normalmente (chatPrompted e sem done), tenta despachar via fallback
            if (chatContextRef.current.chatPrompted && !chatDoneDispatchedRef.current) {
                checkAndDispatchChatEvent(true);
            }
            setLoading(false);
            localStorage.removeItem('active-discovery-job');
            setActiveJobId(null);
            
            // Dispara refinamento final como medida de segurança se a conexão caiu
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
                    if (onNotification) onNotification('success', "Mapeamento concluído com sucesso!");
                    
                    // ✅ Marca que o scan terminou no backend
                    scanFinishedRef.current = true;
                    // ✅ Tenta despachar para o chat (só vai se não houver Análise Humana pendente)
                    checkAndDispatchChatEvent();

                    ws.close(); // Isso vai disparar o ws.onclose, que faz a limpeza e o refineHierarchy.
                    return;
                }

                if (data.type === 'clear_nodes') {
                    console.log("[WS] 🧹 Comando de limpeza recebido. Mantendo apenas Root e Sócios.");
                    
                    const keepers = currentEmployeesRef.current.filter(emp => {
                        const isRoot = emp.id === 'root_company' || emp.level === 0;
                        const isPartner = emp.level === 6 || String(emp.id).startsWith('partner_');
                        const isPartnerDept = emp.department && (
                            emp.department.includes('QSA') ||
                            emp.department.includes('Sócio') ||
                            emp.department.includes('Societário') ||
                            emp.department.includes('Conselho')
                        );
                        return isRoot || isPartner || isPartnerDept;
                    });
                    
                    currentEmployeesRef.current = keepers;
                    setRawEmployees(keepers);
                    
                    const newEdges: Edge[] = [];
                    keepers.forEach(emp => {
                        if (emp.manager_id && emp.id !== "root_company") {
                            newEdges.push({
                                id: `e-${emp.manager_id}-${emp.id}`,
                                source: emp.manager_id,
                                target: emp.id,
                                animated: false,
                                style: { stroke: '#6e7681', strokeWidth: 1.5 }
                            });
                        }
                    });
                    setRawBackendEdges(newEdges);
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

                            // Garante que o ID do backend prevalece se o local for provisório (ex: partner_0)
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
                                console.log(`[useHierarchy] Atualizando ID provisório: ${oldId} -> ${newId}`);
                                // Atualiza manager_id de outros nós que apontavam para o ID antigo
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
            setError("Erro na conexão WebSocket com o Worker.");
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

            // 🔍 VALIDAR: O job ainda existe no Redis/Backend?
            try {
                await jobsApi.getJobStatus(job_id);
            } catch {
                console.warn(`[Reconnect] Job ${job_id} não existe mais no backend. Limpando cache.`);
                localStorage.removeItem('active-discovery-job');
                return false;
            }

            console.log(`[Reconnect] 🔄 Reconectando ao job: ${job_id}`);
            if (onNotification) {
                onNotification('info', `Reconectado ao mapeamento em andamento (${brand})...`);
            }

            // 💾 ANTES DE RECONECTAR: Buscar o que JÁ FOI MAPEADO no banco!
            let existingEmployees: HierarchyEmployee[] = [];
            if (jobData.orgId) {
                try {
                    const data = await hierarchyApi.loadHierarchyByPipedrive(jobData.orgId);
                    if (data && data.nodes && data.nodes.length > 0) {
                        // Limpeza de URLs para não duplicar proxy
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
                        console.log(`[Reconnect] Carregados ${existingEmployees.length} nós já existentes para ${brand}.`);
                    }
                } catch (e) {
                    console.warn('[Reconnect] Erro ao buscar hierarquia prévia antes de reconectar:', e);
                }
            }

            // Reconecta ao WebSocket passando o que já temos
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

            // 🔄 FALLBACK: Se tentou por Pipedrive e não achou nada, tenta pelo ID local
            // Isso resolve o caso de empresas criadas manualmente ou que perderam o vínculo.
            if (isPipedriveId && (!data?.nodes || data.nodes.length === 0)) {
                console.log(`[useHierarchy] Hierarquia não encontrada por Pipedrive ID ${orgId}. Tentando ID local...`);
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
        } catch (e: any) {
            console.warn("[useHierarchy] Load hierarchy error:", (e as any).message || e);
            setError("Erro ao carregar dados do banco.");
            return null;
        } finally {
            setLoading(false);
        }
    }, []);

    const updateEmployee = useCallback(async (id: string, updates: Partial<HierarchyEmployee>) => {
        // Atualiza estado local imediatamente
        setRawEmployees(prev => {
            const index = prev.findIndex(e => e.id === id);
            if (index === -1) return prev;
            const updated = [...prev];
            updated[index] = { ...updated[index], ...updates };
            return updated;
        });

        // Persiste no backend se for um ID estável (node_...)
        if (id.startsWith('node_')) {
            try {
                await hierarchyApi.updateEmployeeDetails(id, updates);
                console.log(`[useHierarchy] Funcionário ${id} atualizado no banco.`);
            } catch (e) {
                console.error(`[useHierarchy] Erro ao salvar atualização no banco:`, e);
            }
        }
    }, []);

    const smartSyncPipedrive = useCallback(async (onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void) => {
        setIsSmartSyncLoading(true);
        setError("");
        try {
            const data = await orgsApi.triggerSmartSync();
            if (data.status === 'queued' && data.job_id) {
                console.log('[Pipedrive] Smart Sync iniciado em background:', data.message);
                
                const wsUrl = jobsApi.getJobWebSocketUrl(data.job_id);
                const ws = new WebSocket(wsUrl);
                
                ws.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        if (msg.type === 'job_done') {
                            setIsSmartSyncLoading(false);
                            ws.close();
                            if (onNotification) onNotification('success', msg.message || "Sincronização com Pipedrive concluída!");
                        } else if (msg.type === 'error') {
                            setIsSmartSyncLoading(false);
                            ws.close();
                            if (onNotification) onNotification('error', msg.message || "Erro durante o Smart Sync.");
                        }
                    } catch (e) {
                        console.error('Erro no WebSocket do Smart Sync:', e);
                    }
                };
                
                ws.onclose = () => {
                    setIsSmartSyncLoading(false);
                };
                
                return data;
            } else if (data.status === 'success') {
                setIsSmartSyncLoading(false);
                if (onNotification) onNotification('success', data.message || "Sincronização com Pipedrive concluída!");
                return data;
            } else {
                setError(data.message || 'Erro no Smart Sync.');
                setIsSmartSyncLoading(false);
                if (onNotification) onNotification('error', data.message || "Erro no Smart Sync.");
            }
        } catch (e) {
            console.error('Smart Sync error:', (e as any).message || e);
            setError('Erro ao conectar com Pipedrive.');
            setIsSmartSyncLoading(false);
            if (onNotification) onNotification('error', "Erro ao conectar com Pipedrive.");
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

            // 🔄 Atualização de Estado Local (Usa conversão para String para evitar colisão entre id numérico e string do parâmetro)
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

            // ✅ Verifica se esta ação completou o mapeamento para o chat
            checkAndDispatchChatEvent();

            return data;
        } catch (e: any) {
            console.error(`[useHierarchy] Erro na ação ${action}:`, e.message);
            throw e;
        }
    };

    const approveCandidate = useCallback((id: string) => handleCandidateAction(id, 'approve'), []);
    const rejectCandidate = useCallback((id: string) => handleCandidateAction(id, 'reject'), []);

    const deleteEmployee = useCallback(async (id: string) => {
        // Se for um nó persistido no banco (ID começa com node_), avisamos o backend
        if (String(id).startsWith('node_')) {
            try {
                await hierarchyApi.candidateAction(id, 'reject');
                console.log(`[useHierarchy] Funcionário ${id} removido e marcado como reprovado no banco.`);
            } catch (e) {
                console.error(`[useHierarchy] Erro ao sincronizar remoção com backend:`, e);
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

        // ✅ Verifica se esta remoção completou o mapeamento para o chat
        checkAndDispatchChatEvent();
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
        isSmartSyncLoading,
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
