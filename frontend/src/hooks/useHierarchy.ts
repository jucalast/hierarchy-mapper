import { useCallback, useRef, useEffect } from 'react';
import { Edge } from 'reactflow';
import type { HierarchyEmployee } from '@/types';
import {
    hierarchy as hierarchyApi,
    jobs as jobsApi,
    organizations as orgsApi,
} from '@/services/api';
import { useChatStore } from '@/store/chatStore';
import { connectionManager } from '@/services/connectionManager';

const EMPTY_ARRAY: any[] = [];
const EMPTY_EDGES: Edge[] = [];

export const useHierarchy = () => {
  const currentOrgId = useChatStore((state) => state.currentOrgId);
  const mappingSession = useChatStore(
    useCallback(
      (state) => state.mappings[currentOrgId || 0],
      [currentOrgId]
    )
  );

  // Mapeia o estado global para variáveis locais consumidas externamente
  const rawEmployees = mappingSession?.rawEmployees || EMPTY_ARRAY;
  const rawBackendEdges = mappingSession?.rawBackendEdges || EMPTY_EDGES;
  const loading = mappingSession?.loading || false;
  const discovering = mappingSession?.discovering || false;
  const brandOptions = mappingSession?.brandOptions || EMPTY_ARRAY;
  const error = mappingSession?.error || null;
  const activeJobId = mappingSession?.activeJobId || null;
  const isSmartSyncLoading = useChatStore(state => state.globalSmartSyncLoading);

  // Setters do Zustand mapeados
  const setRawEmployees = useCallback((employees: any[] | ((prev: any[]) => any[])) => {
    useChatStore.getState().setRawEmployees(currentOrgId || 0, employees);
  }, [currentOrgId]);

  const setRawBackendEdges = useCallback((edges: Edge[] | ((prev: Edge[]) => Edge[])) => {
    useChatStore.getState().setRawBackendEdges(currentOrgId || 0, edges);
  }, [currentOrgId]);

  const setBrandOptions = useCallback((options: any[] | ((prev: any[]) => any[])) => {
    useChatStore.getState().setBrandOptions(currentOrgId || 0, options);
  }, [currentOrgId]);

  const setError = useCallback((err: string | null) => {
    useChatStore.getState().setMappingError(currentOrgId || 0, err);
  }, [currentOrgId]);

  const setLoading = useCallback((val: boolean) => {
    useChatStore.getState().setMappingLoading(currentOrgId || 0, val);
  }, [currentOrgId]);

  // Contexto para despacho do evento de conclusão ao chat
  const chatContextRef = useRef({ chatPrompted: false, orgId: null as number | null, orgName: '' });
  const scanFinishedRef = useRef(false);
  const chatDoneDispatchedRef = useRef(false);
  const brandDiscoveryAbortControllerRef = useRef<AbortController | null>(null);

  // Recupera contexto de chat pendente
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const pending = localStorage.getItem('pending-hierarchy-continuation');
    if (pending) {
      try {
        const parsed = JSON.parse(pending);
        if (parsed && parsed.org_id) {
          console.log('[useHierarchy] Chat aguardando mapeamento para org:', parsed.org_id);
          chatContextRef.current = {
            chatPrompted: true,
            orgId: Number(parsed.org_id),
            orgName: parsed.org_name || ''
          };
        }
      } catch (e) { /* ignore */ }
    }
  }, []);

  const cleanName = (name: string) => {
    if (!name) return "";
    return name
      .replace(/\|?\s*Linked\s*In/gi, '')
      .replace(/\(\s*LinkedIn\s*\)/gi, '')
      .trim();
  };

  /**
   * Centraliza o despacho do evento 'hierarchy_scan_done'.
   */
  const checkAndDispatchChatEvent = useCallback((fromFallback = false) => {
    const { chatPrompted, orgId, orgName } = chatContextRef.current;
    if (!chatPrompted || chatDoneDispatchedRef.current) return;

    // Se o scan ainda não terminou, não podemos concluir (a menos que seja fallback)
    if (!scanFinishedRef.current && !fromFallback) return;

    // Busca funcionários da organização correspondente
    const currentNodes = orgId ? (useChatStore.getState().mappings[orgId]?.rawEmployees || []) : [];

    // Verifica se ainda há algum funcionário pendente de análise humana
    const hasPending = currentNodes.some(e => {
      const role = (e.role || '').toLowerCase();
      return role.includes('análise humana') || role.includes('analise humana');
    });

    if (hasPending && !fromFallback) {
      console.log('[useHierarchy] Scan terminou, mas há Análise Humana pendente. Aguardando usuário...');
      return;
    }

    chatDoneDispatchedRef.current = true;

    // Filtra e formata os contatos finais para o agente
    const contacts = currentNodes
      .filter(e => {
        if (e.id === 'root_company' || !e.name) return false;
        const r = (e.role || '').toLowerCase();
        const d = (e.department || '').toLowerCase();
        if (r.includes('reprovado') || d.includes('reprovado')) return false;
        return true;
      })
      .map(e => ({
        name: e.name,
        role: e.role || '',
        email: e.email || undefined,
        department: e.department || undefined,
        temperature: e.temperature || undefined,
        level: e.level,
        decision_maker: [
          'compras', 'procurement', 'suprimentos', 'logística', 'logistica',
          'supply chain', 'supply', 'materiais', 'aquisição', 'aquisicao',
          'estoque', 'sourcing'
        ].some(k => (e.role || '').toLowerCase().includes(k) || (e.department || '').toLowerCase().includes(k)),
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

  // Escuta os eventos do ConnectionManager em background
  useEffect(() => {
    if (!currentOrgId) return;

    const handleRefinementDone = (e: Event) => {
      const detail = (e as CustomEvent).detail || {};
      if (detail.chatPrompted) {
        chatContextRef.current = {
          chatPrompted: true,
          orgId: detail.orgId,
          orgName: detail.brand || ''
        };
        scanFinishedRef.current = true;
        checkAndDispatchChatEvent();
      }
    };

    const handleScanFinished = (e: Event) => {
      const detail = (e as CustomEvent).detail || {};
      if (detail.chatPrompted) {
        chatContextRef.current = {
          chatPrompted: true,
          orgId: detail.orgId,
          orgName: detail.brand || ''
        };
        scanFinishedRef.current = true;
        checkAndDispatchChatEvent();
      }
    };

    const refinementEventName = `hierarchy_refinement_done_${currentOrgId}`;
    const scanFinishedEventName = `hierarchy_scan_finished_${currentOrgId}`;

    window.addEventListener(refinementEventName, handleRefinementDone);
    window.addEventListener(scanFinishedEventName, handleScanFinished);

    return () => {
      window.removeEventListener(refinementEventName, handleRefinementDone);
      window.removeEventListener(scanFinishedEventName, handleScanFinished);
    };
  }, [currentOrgId, checkAndDispatchChatEvent]);

  // Função para descobrir marca (CNPJ) via API
  const discoverBrand = useCallback(async (searchCnpj: string, explicitDomain: string = "", force: boolean = true) => {
    const targetOrgId = currentOrgId || 0;
    const store = useChatStore.getState();
    store.setDiscovering(targetOrgId, true);
    store.setMappingError(targetOrgId, null);
    store.setBrandOptions(targetOrgId, []);
    const rawCnpj = (searchCnpj || "").replace(/\D/g, "");
    if (!rawCnpj && !explicitDomain) {
      store.setDiscovering(targetOrgId, false);
      return null;
    }

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
      store.setBrandOptions(targetOrgId, cleaned);
      return data;
    } catch (err: any) {
      const msg = err?.message || String(err);
      if (msg.includes('429')) {
        console.warn('BrasilAPI Rate Limit - Operando em modo de resiliência.');
        return null;
      }
      console.error(msg);
      store.setMappingError(targetOrgId, err?.detail || 'Erro ao buscar marcas da empresa.');
      return null;
    } finally {
      store.setDiscovering(targetOrgId, false);
    }
  }, [currentOrgId]);

  // Streaming de marcas
  const discoverBrandStream = useCallback(async (
    searchCnpj: string, 
    explicitDomain: string = "", 
    force: boolean = true, 
    onCandidateFound?: (candidate: any) => void
  ) => {
    const targetOrgId = currentOrgId || 0;
    const store = useChatStore.getState();
    store.setDiscovering(targetOrgId, true);
    store.setMappingError(targetOrgId, null);
    store.setBrandOptions(targetOrgId, []);
    const rawCnpj = (searchCnpj || "").replace(/\D/g, "");
    
    if (!rawCnpj && !explicitDomain) {
      store.setDiscovering(targetOrgId, false);
      return null;
    }

    // Cria AbortController
    const controller = new AbortController();
    brandDiscoveryAbortControllerRef.current = controller;

    try {
      const streamUrl = hierarchyApi.getDiscoverBrandStreamUrl({
        cnpj: rawCnpj,
        domain: explicitDomain || undefined,
        force,
      });

      const response = await fetch(streamUrl, {
        signal: controller.signal
      });
      
      if (!response.ok) {
        store.setMappingError(targetOrgId, "Erro ao iniciar streaming de marcas.");
        store.setDiscovering(targetOrgId, false);
        return null;
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const streamedCandidates: any[] = [];

      if (!reader) {
        store.setMappingError(targetOrgId, "Não foi possível ler o stream.");
        store.setDiscovering(targetOrgId, false);
        return null;
      }

      while (true) {
        if (controller.signal.aborted) {
          console.log("[Stream] Stream cancelado pelo usuário.");
          break;
        }

        try {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");

          for (let i = 0; i < lines.length - 1; i++) {
            const line = lines[i].trim();
            if (line.startsWith("data: ")) {
              try {
                const jsonStr = line.substring(6);
                const event = JSON.parse(jsonStr);

                if (event.type === "candidate") {
                  streamedCandidates.push(event);
                  
                  const uniqueCandidates = new Map();
                  streamedCandidates.forEach((opt: any) => {
                    const cleanedName = cleanName(opt.name);
                    const key = opt.url || cleanedName.toLowerCase();
                    if (!uniqueCandidates.has(key)) {
                      uniqueCandidates.set(key, { ...opt, name: cleanedName });
                    } else {
                      const existing = uniqueCandidates.get(key);
                      if ((opt.score || 0) > (existing.score || 0)) {
                        uniqueCandidates.set(key, { ...opt, name: cleanedName });
                      }
                    }
                  });
                  
                  const cleaned = Array.from(uniqueCandidates.values())
                    .sort((a: any, b: any) => (b.score || 0) - (a.score || 0));
                  
                  store.setBrandOptions(targetOrgId, cleaned);

                  if (onCandidateFound) {
                    onCandidateFound({
                      ...event,
                      name: cleanName(event.name)
                    });
                  }
                } else if (event.type === "complete") {
                  if (event.top_alternatives && event.top_alternatives.length > 0) {
                    const uniqueFinal = new Map();
                    event.top_alternatives.forEach((opt: any) => {
                      const cleanedName = cleanName(opt.name);
                      const key = opt.url || cleanedName.toLowerCase();
                      if (!uniqueFinal.has(key)) {
                        uniqueFinal.set(key, { ...opt, name: cleanedName });
                      } else {
                        const existing = uniqueFinal.get(key);
                        if ((opt.score || 0) > (existing.score || 0)) {
                          uniqueFinal.set(key, { ...opt, name: cleanedName });
                        }
                      }
                    });
                    const finalCandidates = Array.from(uniqueFinal.values());
                    store.setBrandOptions(targetOrgId, finalCandidates);
                  }
                } else if (event.error) {
                  store.setMappingError(targetOrgId, event.error);
                }
              } catch (e) {
                console.warn("Erro ao parsear evento SSE:", e);
              }
            }
          }
          buffer = lines[lines.length - 1];
        } catch (readErr: any) {
          if (readErr.name === "AbortError" || controller.signal.aborted) {
            break;
          }
          throw readErr;
        }
      }

      return { alternatives: streamedCandidates };
    } catch (err: any) {
      if (err.name === "AbortError" || controller.signal.aborted) {
        console.log("[Stream] Stream cancelado por AbortController.");
        return null;
      }
      console.error(err.message || err);
      store.setMappingError(targetOrgId, "Falha na conexão com o servidor (streaming).");
      return null;
    } finally {
      if (brandDiscoveryAbortControllerRef.current === controller) {
        brandDiscoveryAbortControllerRef.current = null;
      }
      store.setDiscovering(targetOrgId, false);
    }
  }, [currentOrgId]);

  const cancelDiscovery = useCallback(() => {
    if (brandDiscoveryAbortControllerRef.current) {
      brandDiscoveryAbortControllerRef.current.abort();
      brandDiscoveryAbortControllerRef.current = null;
    }
  }, []);

  const refineHierarchy = useCallback(async (employees: any[]) => {
    const store = useChatStore.getState();
    const targetOrgId = currentOrgId;
    if (!targetOrgId) return;

    store.setMappingLoading(targetOrgId, true);
    store.setMappingError(targetOrgId, "");
    try {
      const data = await hierarchyApi.refineHierarchy(employees);
      if (data && data.nodes) {
        const refreshedNodes = data.nodes.map((emp: any) => {
          if (!emp.manager_id && emp.id !== "root_company") {
            return { ...emp, manager_id: "root_company" };
          }
          return emp;
        });

        store.setRawEmployees(targetOrgId, refreshedNodes);
        
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
        store.setRawBackendEdges(targetOrgId, newEdges);
        
        const keysToDelete: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key && (key.startsWith('layout-cache-') || key.startsWith('edges-cache-'))) {
            keysToDelete.push(key);
          }
        }
        keysToDelete.forEach(key => localStorage.removeItem(key));

        if (chatContextRef.current.chatPrompted && !chatDoneDispatchedRef.current) {
          scanFinishedRef.current = true;
          checkAndDispatchChatEvent();
        }
      }
    } catch (err: any) {
      console.error(err.message || err);
      store.setMappingError(targetOrgId, "Erro ao refinar hierarquia com IA.");
    } finally {
      store.setMappingLoading(targetOrgId, false);
    }
  }, [currentOrgId, checkAndDispatchChatEvent]);

  const stopHierarchyScan = useCallback(async (onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void) => {
    const store = useChatStore.getState();
    const targetOrgId = currentOrgId;
    if (!targetOrgId) return;

    const session = store.mappings[targetOrgId];
    const jobId = session?.activeJobId;
    if (!jobId) return;

    try {
      await jobsApi.cancelJob(jobId);
      if (onNotification) onNotification('error', 'Mapeamento cancelado pelo usuário.');
    } catch (e) {
      console.warn('[Job API] Erro ao abortar job:', e);
      // O backend pode não ter recebido o pedido de cancelamento (falha de rede) —
      // avisa o usuário em vez de silenciosamente fingir que parou.
      if (onNotification) onNotification('error', 'Não foi possível confirmar o cancelamento no servidor; o mapeamento pode continuar em segundo plano.');
    } finally {
      connectionManager.disconnectFromJob(jobId);
      store.setMappingLoading(targetOrgId, false);
      store.setActiveJobId(targetOrgId, null);
      localStorage.removeItem(`active-discovery-job-${targetOrgId}`);

      // 🧹 Mantém apenas root_company + sócios — descarta nós incompletos do scan cancelado
      const currentNodes = store.mappings[targetOrgId]?.rawEmployees || [];
      const keepers = currentNodes.filter(emp => {
        const isRoot = emp.id === 'root_company' || emp.level === 0;
        const isPartner = String(emp.id).startsWith('partner_') || emp.level === 6;
        const isPartnerDept = emp.department && (
          emp.department.includes('QSA') ||
          emp.department.includes('Sócio') ||
          emp.department.includes('Societário') ||
          emp.department.includes('Conselho')
        );
        return isRoot || isPartner || isPartnerDept;
      });
      store.setRawEmployees(targetOrgId, keepers);
      store.setRawBackendEdges(targetOrgId, []);

      // 🔔 Notifica o Drawer para remover o badge imediatamente
      window.dispatchEvent(new CustomEvent('hierarchy_scan_cancelled', { detail: { orgId: targetOrgId } }));
    }
  }, [currentOrgId]);

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
    initialEmployees?: any[],
    model?: string,
    strictMode?: boolean
  ) => {
    const store = useChatStore.getState();
    const targetOrgId = orgId || currentOrgId;
    if (!targetOrgId) return;

    store.setMappingLoading(targetOrgId, true);
    store.setMappingError(targetOrgId, "");
    store.setRawBackendEdges(targetOrgId, []);

    let keepers: any[] = [];
    if (initialEmployees && initialEmployees.length > 0) {
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

    store.setRawEmployees(targetOrgId, keepers);

    const initialEdges: Edge[] = [];
    keepers.forEach(emp => {
      if (emp.manager_id && emp.id !== "root_company") {
        initialEdges.push({
          id: `e-${emp.manager_id}-${emp.id}`,
          source: emp.manager_id,
          target: emp.id,
          animated: false,
          style: { stroke: '#6e7681', strokeWidth: 3.0 }
        });
      }
    });
    store.setRawBackendEdges(targetOrgId, initialEdges);

    scanFinishedRef.current = false;
    chatDoneDispatchedRef.current = false;

    const rawCnpj = (searchCnpj || "").replace(/\D/g, "");

    try {
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
        store.setMappingError(targetOrgId, "Não foi possível iniciar o scan.");
        store.setMappingLoading(targetOrgId, false);
        return;
      }

      console.log(`[useHierarchy] Scan iniciado via Job=${job_id} para org=${targetOrgId}`);

      const pending = localStorage.getItem('pending-hierarchy-continuation');
      let chatPrompted = false;
      if (pending) {
        try {
          const parsed = JSON.parse(pending);
          if (parsed && Number(parsed.org_id) === Number(targetOrgId)) {
            chatPrompted = true;
          }
        } catch {}
      }

      // Salva no localStorage
      const jobData = {
        job_id,
        cnpj: rawCnpj,
        domain: explicitDomain,
        brand: confirmedBrand,
        logo: confirmedLogo,
        startTime: Date.now(),
        orgId: targetOrgId,
        chatPrompted
      };
      localStorage.setItem(`active-discovery-job-${targetOrgId}`, JSON.stringify(jobData));
      
      chatContextRef.current = { chatPrompted, orgId: targetOrgId, orgName: confirmedBrand };
      
      window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));

      // Conecta ao connectionManager
      connectionManager.connectToJob({
        jobId: job_id,
        orgId: targetOrgId,
        brand: confirmedBrand,
        logo: confirmedLogo,
        domain: explicitDomain,
        partners,
        chatPrompted
      }, initialEmployees);

    } catch (err: any) {
      console.error("[useHierarchy] Erro ao disparar scan:", err);
      store.setMappingError(targetOrgId, "Falha ao comunicar com o motor de tarefas.");
      if (onNotification) onNotification('error', "Não foi possível iniciar o scan.");
      store.setMappingLoading(targetOrgId, false);
    }
  }, [currentOrgId]);

  // Função para conectar no WebSocket (usada para compatibilidade ou reconexão local se necessário)
  const connectToJobWebSocket = useCallback((
    job_id: string,
    confirmedBrand: string,
    confirmedLogo: string,
    explicitDomain: string,
    partners: any[],
    onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void,
    initialEmployees?: any[],
    orgId?: number | null,
    chatPrompted?: boolean
  ) => {
    const targetOrgId = orgId || currentOrgId;
    if (!targetOrgId) return;

    connectionManager.connectToJob({
      jobId: job_id,
      orgId: targetOrgId,
      brand: confirmedBrand,
      logo: confirmedLogo,
      domain: explicitDomain,
      partners,
      chatPrompted
    }, initialEmployees);
  }, [currentOrgId]);

  const reconnectToActiveJob = useCallback(async (onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void) => {
    const jobDataStr = localStorage.getItem(`active-discovery-job-${currentOrgId}`);
    if (!jobDataStr) return false;
    if (jobDataStr === "NaN" || jobDataStr === "undefined") {
      localStorage.removeItem(`active-discovery-job-${currentOrgId}`);
      return false;
    }

    try {
      const jobData = JSON.parse(jobDataStr);
      const { job_id, brand, logo, domain, orgId } = jobData;

      try {
        await jobsApi.getJobStatus(job_id);
      } catch {
        console.warn(`[useHierarchy] Job ${job_id} expirou no backend.`);
        localStorage.removeItem(`active-discovery-job-${orgId || currentOrgId}`);
        return false;
      }

      console.log(`[useHierarchy] Re-estabelecendo conexão para job=${job_id}`);
      if (onNotification) {
        onNotification('info', `Reconectado ao mapeamento em andamento (${brand})...`);
      }

      let existingEmployees: any[] = [];
      if (orgId) {
        try {
          const data = await hierarchyApi.loadHierarchyByPipedrive(orgId);
          if (data && data.nodes && data.nodes.length > 0) {
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
          }
        } catch (e) {
          console.warn('[useHierarchy] Erro ao buscar hierarquia prévia:', e);
        }
      }

      const targetOrgId = orgId || currentOrgId;
      if (targetOrgId) {
        connectionManager.connectToJob({
          jobId: job_id,
          orgId: targetOrgId,
          brand,
          logo,
          domain,
          partners: [],
          chatPrompted: jobData.chatPrompted
        }, existingEmployees);
      }
      return true;
    } catch (e) {
      console.error("[useHierarchy] Erro ao reconectar:", e);
      localStorage.removeItem(`active-discovery-job-${currentOrgId}`);
      return false;
    }
  }, [currentOrgId]);

  const loadStoredHierarchy = useCallback(async (orgId: number, isPipedriveId: boolean = true) => {
    const store = useChatStore.getState();
    if (!orgId) return null;
    const existingActiveJobId = store.mappings[orgId]?.activeJobId;
    store.setMappingLoading(orgId, true);
    store.setMappingError(orgId, "");
    if (!existingActiveJobId) {
      store.setRawEmployees(orgId, []);
      store.setRawBackendEdges(orgId, []);
    }

    try {
      let data: any = isPipedriveId
        ? await hierarchyApi.loadHierarchyByPipedrive(orgId)
        : await hierarchyApi.loadHierarchyByLocalId(orgId);

      if (isPipedriveId && (!data?.nodes || data.nodes.length === 0)) {
        try {
          const localData = await hierarchyApi.loadHierarchyByLocalId(orgId);
          if (localData?.nodes && localData.nodes.length > 0) {
            data = localData;
          }
        } catch {}
      }
      
      if (data && data.nodes && data.nodes.length > 0) {
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
        
        store.setRawEmployees(orgId, cleanedNodes);
        
        const pendingAnalysis = cleanedNodes.filter((n: any) => 
          n.role && (n.role.toLowerCase().includes('análise humana') || n.role.toLowerCase().includes('analise humana'))
        );
        if (pendingAnalysis.length > 0) {
          store.setBrandOptions(orgId, pendingAnalysis.map((p: any) => ({
            ...p,
            type: 'person',
            url: p.linkedin || p.linkedin_url,
            originalEmployee: p,
            score: p.matching_score || 0
          })));
        }
        
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
        store.setRawBackendEdges(orgId, newEdges);
        return data;
      }
      return null;
    } catch (e: any) {
      console.warn("[useHierarchy] Load hierarchy error:", e);
      store.setMappingError(orgId, "Erro ao carregar dados do banco.");
      return null;
    } finally {
      if (!useChatStore.getState().mappings[orgId]?.activeJobId) {
        store.setMappingLoading(orgId, false);
      }
    }
  }, []);

  const updateEmployee = useCallback(async (id: string, updates: Partial<HierarchyEmployee>) => {
    const store = useChatStore.getState();
    if (!currentOrgId) return;
    const safeId = String(id);
    
    store.setRawEmployees(currentOrgId, (prev) => {
      const index = prev.findIndex(e => String(e.id) === safeId);
      if (index === -1) return prev;
      const updated = [...prev];
      updated[index] = { ...updated[index], ...updates };
      return updated;
    });

    if (safeId.startsWith('node_')) {
      try {
        await hierarchyApi.updateEmployeeDetails(safeId, updates);
      } catch (e) {
        console.error(`[useHierarchy] Erro ao salvar atualização:`, e);
      }
    }
  }, [currentOrgId]);

  const smartSyncPipedrive = useCallback(async (onNotification?: (type: 'success' | 'error' | 'info', msg: string) => void) => {
    const store = useChatStore.getState();
    store.setGlobalSmartSyncLoading(true);
    store.setMappingError(currentOrgId || 0, "");
    try {
      const data = await orgsApi.triggerSmartSync();
      if (data.status === 'queued' && data.job_id) {
        const wsUrl = jobsApi.getJobWebSocketUrl(data.job_id);
        const ws = new WebSocket(wsUrl);
        
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'job_done') {
              store.setGlobalSmartSyncLoading(false);
              ws.close();
              if (onNotification) onNotification('success', msg.message || "Smart Sync concluído!");
            } else if (msg.type === 'error') {
              store.setGlobalSmartSyncLoading(false);
              ws.close();
              if (onNotification) onNotification('error', msg.message || "Erro durante o Smart Sync.");
            }
          } catch (e) {
            console.error(e);
          }
        };
        
        ws.onclose = () => {
          store.setGlobalSmartSyncLoading(false);
        };
        return data;
      } else if (data.status === 'success') {
        store.setGlobalSmartSyncLoading(false);
        if (onNotification) onNotification('success', data.message || "Smart Sync concluído!");
        return data;
      } else {
        store.setMappingError(currentOrgId || 0, data.message || 'Erro no Smart Sync.');
        store.setGlobalSmartSyncLoading(false);
        if (onNotification) onNotification('error', data.message || "Erro no Smart Sync.");
      }
    } catch (e) {
      store.setMappingError(currentOrgId || 0, 'Erro inesperado ao sincronizar.');
      store.setGlobalSmartSyncLoading(false);
      if (onNotification) onNotification('error', "Erro inesperado ao sincronizar.");
    }
  }, [currentOrgId]);

  const confirmIntelligence = useCallback(async (payload: any) => {
    try {
      return await hierarchyApi.confirmIntelligence(payload);
    } catch (e) {
      console.error(e);
      return { status: 'error' };
    }
  }, []);

  const resetHierarchy = useCallback(() => {
    const store = useChatStore.getState();
    if (currentOrgId) {
      store.setRawEmployees(currentOrgId, []);
      store.setRawBackendEdges(currentOrgId, []);
      store.setBrandOptions(currentOrgId, []);
      store.setMappingError(currentOrgId, null);
    }
  }, [currentOrgId]);

  const handleCandidateAction = useCallback(async (employeeId: string, action: 'approve' | 'reject') => {
    const store = useChatStore.getState();
    if (!currentOrgId) throw new Error("No active org selected");
    try {
      const data = await hierarchyApi.candidateAction(employeeId, action);
      if (action === 'approve') {
        store.setBrandOptions(currentOrgId, prev => prev.filter(opt => String(opt.id) !== String(employeeId)));
        store.setRawEmployees(currentOrgId, prev => {
          return prev.map(emp => {
            if (String(emp.id) === String(employeeId) && emp.role?.toLowerCase().includes('humana')) {
              return { ...emp, role: 'Aprovado (Recarregue para ver cargo)' };
            }
            return emp;
          });
        });
      } else {
        store.setBrandOptions(currentOrgId, prev => prev.filter(opt => String(opt.id) !== String(employeeId)));
        store.setRawEmployees(currentOrgId, prev => {
          return prev.map(emp => {
            if (String(emp.id) === String(employeeId)) {
              return { ...emp, role: 'Reprovado', department: 'Reprovado' };
            }
            return emp;
          });
        });
      }

      checkAndDispatchChatEvent();
      return data;
    } catch (e) {
      console.error(e);
      throw e;
    }
  }, [currentOrgId, checkAndDispatchChatEvent]);

  const approveCandidate = useCallback((id: string) => handleCandidateAction(id, 'approve'), [handleCandidateAction]);
  const rejectCandidate = useCallback((id: string) => handleCandidateAction(id, 'reject'), [handleCandidateAction]);

  const deleteEmployee = useCallback(async (id: string) => {
    const store = useChatStore.getState();
    if (!currentOrgId) return;
    const safeId = String(id);

    if (safeId.startsWith('node_')) {
      try {
        await hierarchyApi.candidateAction(safeId, 'reject');
      } catch (e) {
        console.error(e);
      }
    }

    store.setRawEmployees(currentOrgId, prev => {
      return prev.filter(emp => String(emp.id) !== safeId);
    });
    
    store.setRawBackendEdges(currentOrgId, prev => {
      return prev.filter(edge => 
        String(edge.source) !== safeId && 
        String(edge.target) !== safeId
      );
    });

    checkAndDispatchChatEvent();
  }, [currentOrgId, checkAndDispatchChatEvent]);

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
