import { useChatStore } from '../store/chatStore';
import { getJobWebSocketUrl } from './api/jobs';
import { Edge } from 'reactflow';
import { hierarchy as hierarchyApi, organizations as organizationsApi } from './api';
import { clearGraphCache } from '../hooks/useGraphPersistence';

const DIACRITICS_RE = new RegExp('[\\u0300-\\u036f]', 'g');
const normalizeName = (name?: string) =>
  name ? name.normalize('NFD').replace(DIACRITICS_RE, '').toLowerCase().trim() : '';

export interface JobConnectionConfig {
  jobId: string;
  orgId: number;
  brand: string;
  logo: string;
  domain: string;
  partners: any[];
  chatPrompted?: boolean;
}

// Lotes de candidatos passam por LLM (role_engine) + validação de e-mail/SMTP + Pipedrive,
// e podem ficar minutos sem publicar nada caso o provider de LLM esteja em throttling/fallback
// (ver core/llm/quota_manager.py). Um timeout curto aqui derrubaria a conexão enquanto o job
// AINDA está rodando no backend e continuando a persistir gente aprovada no banco.
const JOB_IDLE_TIMEOUT_MS = 20 * 60 * 1000;
const MAX_RECONNECT_ATTEMPTS = 6;

class ConnectionManager {
  private connections: Record<string, WebSocket> = {};
  private timeouts: Record<string, NodeJS.Timeout> = {};
  // true quando o fechamento foi decidido por nós (done/error/timeout/cancelamento) —
  // usado pelo onclose para distinguir de uma queda inesperada (rede, hot-reload do
  // backend em dev) que deve tentar reconectar em vez de abandonar o job.
  private intentionalClose: Record<string, boolean> = {};
  private reconnectAttempts: Record<string, number> = {};

  public connectToJob(config: JobConnectionConfig, initialEmployees?: any[]) {
    const { jobId, orgId, brand, logo, domain, partners } = config;

    // Se já estiver conectado a este job, ignora
    if (this.connections[jobId]) {
      console.log(`[ConnectionManager] Já conectado ao job: ${jobId}`);
      return;
    }

    console.log(`[ConnectionManager] Estabelecendo conexão para job=${jobId}, orgId=${orgId}`);

    // Inicializa o estado na store se vazio
    const store = useChatStore.getState();
    let currentEmployees = initialEmployees && initialEmployees.length > 0
      ? [...initialEmployees]
      : [
          {
            id: 'root_company',
            name: brand || "Empresa",
            role: "Holding / Matriz",
            department: "Corporate Root",
            level: 0,
            logo: logo,
            company_logo: logo,
            domain: domain
          }
        ];

    if (!initialEmployees || initialEmployees.length === 0) {
      partners.forEach((p, idx) => {
        currentEmployees.push({
          id: `partner_${idx}`,
          name: p.name || `Sócio ${idx + 1}`,
          role: p.role || "Sócio / Administrador",
          department: "Quadro de Sócios (QSA)",
          level: 6,
          manager_id: 'root_company',
          company: brand
        });
      });
    }

    store.setRawEmployees(orgId, currentEmployees);
    store.setActiveJobId(orgId, jobId);
    store.setMappingLoading(orgId, true);
    store.setMappingError(orgId, null);

    const initialEdges: Edge[] = [];
    currentEmployees.forEach(emp => {
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
    store.setRawBackendEdges(orgId, initialEdges);

    this.reconnectAttempts[jobId] = 0;
    this.openSocket(config);
  }

  // Abre (ou reabre, numa reconexão) o WebSocket de um job já inicializado na store.
  // Não toca no baseline de funcionários — isso só acontece uma vez, em connectToJob.
  private openSocket(config: JobConnectionConfig) {
    const { jobId, orgId, brand, chatPrompted } = config;

    const wsUrl = getJobWebSocketUrl(jobId);
    const ws = new WebSocket(wsUrl);
    this.connections[jobId] = ws;
    this.intentionalClose[jobId] = false;

    const resetTimeout = () => {
      if (this.timeouts[jobId]) clearTimeout(this.timeouts[jobId]);
      this.timeouts[jobId] = setTimeout(() => {
        console.log(`[ConnectionManager] ⏱️ Timeout: Nenhuma mensagem para o job ${jobId}`);
        this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
      }, JOB_IDLE_TIMEOUT_MS);
    };

    resetTimeout();

    ws.onmessage = (event) => {
      resetTimeout();
      this.reconnectAttempts[jobId] = 0; // qualquer mensagem confirma que a conexão está saudável
      // Tem que buscar o estado FRESCO a cada mensagem — uma referência capturada uma única vez
      // na abertura do socket fica congelada, e a próxima mensagem mescla a partir de um
      // baseline desatualizado, sobrescrevendo (e perdendo) o que a mensagem anterior já tinha
      // adicionado. Era exatamente isso que fazia funcionários "somerem" no meio do scan.
      const store = useChatStore.getState();
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'error') {
          store.setMappingError(orgId, data.message);
          this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
          return;
        }

        if (data.type === 'done') {
          console.log(`[ConnectionManager] Job ${jobId} finalizado.`);
          
          // Marca que o scan terminou
          window.dispatchEvent(new CustomEvent(`hierarchy_scan_finished_${orgId}`, {
            detail: {
              orgId,
              brand,
              chatPrompted,
              contacts: store.mappings[orgId]?.rawEmployees || []
            }
          }));

          this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
          return;
        }

        if (data.type === 'clear_nodes') {
          console.log(`[ConnectionManager] Comando de limpeza para orgId=${orgId}`);

          // Alinhado com a lógica de delete do b2b_scanner.py: preserva
          // root, sócios/QSA, decisões humanas explícitas (Aprovado/Reprovado)
          // e contatos vindos do Pipedrive (CRM — não são "descobertos" pelo
          // scan, então não devem sumir; se o scan os reencontrar, o merge por
          // linkedin/nome/pipedrive_id atualiza o registro em vez de duplicar).
          // Funcionários com cargos identificados do mapeamento ANTERIOR são descartados
          // para que o re-scan comece do zero — evita que nós antigos persistam na tela.
          const currentNodes = store.mappings[orgId]?.rawEmployees || [];
          const keepers = currentNodes.filter(emp => {
            const isRoot = emp.id === 'root_company' || emp.level === 0;
            const isPartner = emp.level === 6 || String(emp.id).startsWith('partner_');
            const isPartnerDept = emp.department && (
              emp.department.includes('QSA') ||
              emp.department.includes('Sócio') ||
              emp.department.includes('Societário') ||
              emp.department.includes('Conselho')
            );
            const isHumanDecision = emp.role?.startsWith('Aprovado') || emp.role === 'Reprovado';
            const isPipedrive = emp.source === 'pipedrive' || !!emp.pipedrive_id;
            return isRoot || isPartner || isPartnerDept || isHumanDecision || isPipedrive;
          });

          store.setRawEmployees(orgId, keepers);
          
          const newEdges: Edge[] = [];
          keepers.forEach(emp => {
            if (emp.manager_id && emp.id !== "root_company") {
              newEdges.push({
                id: `e-${emp.manager_id}-${emp.id}`,
                source: emp.manager_id,
                target: emp.id,
                animated: false,
                style: { stroke: '#6e7681', strokeWidth: 3.0 }
              });
            }
          });
          store.setRawBackendEdges(orgId, newEdges);
          return;
        }

        if (data.type === 'batch' || data.type === 'initial') {
          const incomingNodes = (data.nodes || []).map((emp: any) => {
            // Garante que todo nó sem manager_id explícito conecte-se ao root.
            // Sem isso, o fallback de calculateEdges pode escolher um sócio (level 6)
            // como pai em vez de root_company, causando nós "soltos" no grafo.
            if (!emp.manager_id && emp.id !== 'root_company' && emp.level !== 0) {
              return { ...emp, manager_id: 'root_company' };
            }
            return emp;
          }) as any[];
          const currentNodes = [...(store.mappings[orgId]?.rawEmployees || [])];
          const currentEdges = [...(store.mappings[orgId]?.rawBackendEdges || [])];

          incomingNodes.forEach(emp => {
            const idx = currentNodes.findIndex(n =>
              String(n.id) === String(emp.id) ||
              (n.linkedin && emp.linkedin && n.linkedin === emp.linkedin) ||
              (normalizeName(n.name) === normalizeName(emp.name) && n.role === emp.role)
            );
            
            if (idx > -1) {
              if (currentNodes[idx].role?.startsWith('Aprovado') || currentNodes[idx].role === 'Reprovado') {
                return;
              }

              const oldId = currentNodes[idx].id;
              const merged = { ...emp, ...currentNodes[idx] };
              merged.role = emp.role || merged.role;
              merged.department = emp.department || merged.department;
              merged.level = emp.level || merged.level;
              merged.manager_id = emp.manager_id || merged.manager_id;

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
                console.log(`[ConnectionManager] Atualizando ID provisório: ${oldId} -> ${newId}`);
                // Atualiza manager_id de outros nós
                for (let k = 0; k < currentNodes.length; k++) {
                  if (String(currentNodes[k].manager_id) === String(oldId)) {
                    currentNodes[k].manager_id = newId;
                  }
                }
                // Atualiza as arestas
                for (let k = 0; k < currentEdges.length; k++) {
                  let updated = false;
                  if (String(currentEdges[k].source) === String(oldId)) {
                    currentEdges[k].source = newId;
                    updated = true;
                  }
                  if (String(currentEdges[k].target) === String(oldId)) {
                    currentEdges[k].target = newId;
                    updated = true;
                  }
                  if (updated) {
                    currentEdges[k].id = `e-${currentEdges[k].source}-${currentEdges[k].target}`;
                  }
                }
              }
              
              const imgFields = ['logo', 'image', 'url', 'company_logo', 'logo_url', 'brand_logo', 'avatar', 'profile_pic', 'photo'];
              imgFields.forEach(field => {
                if (currentNodes[idx][field] && !emp[field]) {
                  merged[field] = currentNodes[idx][field];
                }
              });
              currentNodes[idx] = merged;
            } else {
              currentNodes.push(emp);
            }
          });

          // Atualiza as arestas
          incomingNodes.forEach(emp => {
            const myNode = currentNodes.find(n =>
              String(n.id) === String(emp.id) ||
              (n.linkedin && emp.linkedin && n.linkedin === emp.linkedin) ||
              (normalizeName(n.name) === normalizeName(emp.name) && n.role === emp.role)
            ) || emp;

            if (myNode.manager_id && myNode.id !== "root_company") {
              const edgeIdx = currentEdges.findIndex(e => String(e.target) === String(myNode.id));
              const newEdge = {
                id: `e-${myNode.manager_id}-${myNode.id}`,
                source: myNode.manager_id,
                target: myNode.id,
                animated: false
              };
              if (edgeIdx > -1) currentEdges[edgeIdx] = newEdge;
              else currentEdges.push(newEdge);
            }
          });

          store.setRawEmployees(orgId, currentNodes);
          store.setRawBackendEdges(orgId, currentEdges);
        }
      } catch (e) {
        console.error("[ConnectionManager] Erro ao processar mensagem WS:", e);
      }
    };

    ws.onerror = () => {
      // O onclose dispara imediatamente depois e decide se reconecta — aqui só logamos.
      console.warn(`[ConnectionManager] Erro de conexão WS para job ${jobId}.`);
    };

    ws.onclose = () => {
      console.log(`[ConnectionManager] Conexão encerrada para job=${jobId}`);
      delete this.connections[jobId];

      if (this.intentionalClose[jobId]) {
        // closeAndCleanup já tratou tudo (done/error/timeout/cancelamento manual)
        delete this.intentionalClose[jobId];
        return;
      }

      // Queda inesperada (rede, hot-reload do backend em dev/uvicorn --reload, etc).
      // O job ARQ é um processo separado do servidor web e pode continuar rodando e
      // persistindo gente aprovada no banco — abandonar o tracking aqui faria essas
      // pessoas só aparecerem num refresh manual da página. Tenta reconectar antes de desistir.
      const attempts = (this.reconnectAttempts[jobId] || 0) + 1;
      this.reconnectAttempts[jobId] = attempts;

      if (attempts > MAX_RECONNECT_ATTEMPTS) {
        console.warn(`[ConnectionManager] Job ${jobId}: limite de tentativas de reconexão atingido.`);
        useChatStore.getState().setMappingError(orgId, "Conexão com o mapeamento foi perdida. Recarregue a página para ver o progresso mais recente.");
        this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
        return;
      }

      const delay = Math.min(2000 * attempts, 10000);
      console.log(`[ConnectionManager] Tentando reconectar ao job ${jobId} em ${delay}ms (tentativa ${attempts}/${MAX_RECONNECT_ATTEMPTS})...`);
      setTimeout(() => {
        if (this.connections[jobId]) return; // já reconectado por outro caminho
        // Enquanto ficamos desconectados, o worker pode ter publicado e persistido
        // candidatos aprovados que ninguém ouviu (Redis pub/sub não tem replay).
        // Busca o estado atual no banco antes de reabrir o socket, pra não perder essa gente.
        this.reconcileFromDatabase(orgId).finally(() => this.openSocket(config));
      }, delay);
    };
  }

  // Recupera nós que foram persistidos no banco enquanto o WebSocket estava caído
  // (ex: hot-reload do backend em dev) e que por isso nunca chegaram via streaming.
  private async reconcileFromDatabase(orgId: number) {
    try {
      const data = await hierarchyApi.loadHierarchyByPipedrive(orgId);
      if (!data?.nodes?.length) return;

      const store = useChatStore.getState();
      const currentNodes = [...(store.mappings[orgId]?.rawEmployees || [])];
      const currentEdges = [...(store.mappings[orgId]?.rawBackendEdges || [])];
      let added = false;

      data.nodes.forEach((dbNode: any) => {
        const exists = currentNodes.some(n =>
          String(n.id) === String(dbNode.id) ||
          (n.linkedin && dbNode.linkedin && n.linkedin === dbNode.linkedin) ||
          (normalizeName(n.name) === normalizeName(dbNode.name) && n.role === dbNode.role)
        );
        if (!exists) {
          currentNodes.push(dbNode);
          added = true;
          if (dbNode.manager_id && dbNode.id !== "root_company") {
            currentEdges.push({
              id: `e-${dbNode.manager_id}-${dbNode.id}`,
              source: dbNode.manager_id,
              target: dbNode.id,
              animated: false
            });
          }
        }
      });

      if (added) {
        console.log(`[ConnectionManager] Recuperados nós do banco que não chegaram via WS (orgId=${orgId}).`);
        store.setRawEmployees(orgId, currentNodes);
        store.setRawBackendEdges(orgId, currentEdges);
      }
    } catch (e) {
      console.warn('[ConnectionManager] Falha ao reconciliar com o banco após reconexão:', e);
    }
  }

  public disconnectFromJob(jobId: string) {
    this.intentionalClose[jobId] = true;
    const ws = this.connections[jobId];
    if (ws) {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      delete this.connections[jobId];
    }
    if (this.timeouts[jobId]) {
      clearTimeout(this.timeouts[jobId]);
      delete this.timeouts[jobId];
    }
  }

  private closeAndCleanup(jobId: string, orgId: number, chatPrompted?: boolean, brand?: string) {
    this.disconnectFromJob(jobId);
    delete this.reconnectAttempts[jobId];

    const store = useChatStore.getState();
    store.setMappingLoading(orgId, false);
    store.setActiveJobId(orgId, null);
    
    localStorage.removeItem(`active-discovery-job-${orgId}`);

    // 🔔 Notifica o Drawer para remover o badge imediatamente
    window.dispatchEvent(new CustomEvent('hierarchy_job_finished', { detail: { orgId, brand } }));

    // Aciona refinamento final de IA
    const currentNodes = store.mappings[orgId]?.rawEmployees || [];
    if (currentNodes.length > 0) {
      this.refineHierarchyAfterMapping(orgId, currentNodes, chatPrompted, brand);
    }
  }

  private async refineHierarchyAfterMapping(orgId: number, nodes: any[], chatPrompted?: boolean, brand?: string) {
    console.log(`[ConnectionManager] Executando refinamento final IA para orgId=${orgId}`);
    try {
      // Reconcilia com o banco ANTES de refinar: o worker persiste cada candidato aprovado
      // incrementalmente, mas nem tudo chega via streaming (WS pode ter caído, ou o conjunto
      // final vem num evento 'result' que o grafo não consome — o segundo socket do scan).
      // Sem isto, o refino rodaria sobre um conjunto incompleto e "perderia" gente que já
      // está no banco, só reaparecendo num reload manual.
      await this.reconcileFromDatabase(orgId);
      const freshNodes = useChatStore.getState().mappings[orgId]?.rawEmployees || nodes;

      const data = await hierarchyApi.refineHierarchy(freshNodes);
      if (data && data.nodes) {
        const refreshedNodes = data.nodes.map((emp: any) => {
          if (!emp.manager_id && emp.id !== "root_company") {
            return { ...emp, manager_id: "root_company" };
          }
          return emp;
        });

        const store = useChatStore.getState();
        store.setRawEmployees(orgId, refreshedNodes);

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
        store.setRawBackendEdges(orgId, newEdges);

        // Limpa o cache de layout APENAS desta empresa (o refino reordenou a hierarquia).
        // Escopado por orgId e pela marca (empresas ainda não integradas são cacheadas por nome).
        clearGraphCache(orgId, brand);

        console.log(`[ConnectionManager] Refinamento concluído para orgId=${orgId}. Notificando listeners.`);

        window.dispatchEvent(new CustomEvent(`hierarchy_refinement_done_${orgId}`, {
          detail: {
            orgId,
            brand,
            chatPrompted,
            contacts: refreshedNodes
          }
        }));
      }
    } catch (e) {
      console.error("[ConnectionManager] Erro no refinamento automático:", e);
    } finally {
      // Dispara validação em lote de e-mails (canais de comunicação) para todos os
      // funcionários mapeados — roda como BackgroundTask no backend, não bloqueia.
      // Executado no finally para garantir que ocorra mesmo se o refinamento falhar.
      void this.triggerBatchEmailValidation(orgId);
    }
  }

  private async triggerBatchEmailValidation(orgId: number) {
    try {
      await organizationsApi.batchValidateEmails(orgId);
      console.log(`[ConnectionManager] ✅ Validação em lote de canais iniciada para org ${orgId}`);
    } catch (e) {
      console.warn(`[ConnectionManager] ⚠️ Falha ao iniciar validação em lote para org ${orgId}:`, e);
    }
  }
}

export const connectionManager = new ConnectionManager();
