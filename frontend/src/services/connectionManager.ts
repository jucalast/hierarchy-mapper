import { useChatStore } from '../store/chatStore';
import { getJobWebSocketUrl } from './api/jobs';
import { Edge } from 'reactflow';
import { hierarchy as hierarchyApi } from './api';

export interface JobConnectionConfig {
  jobId: string;
  orgId: number;
  brand: string;
  logo: string;
  domain: string;
  partners: any[];
  chatPrompted?: boolean;
}

class ConnectionManager {
  private connections: Record<string, WebSocket> = {};
  private timeouts: Record<string, NodeJS.Timeout> = {};

  public connectToJob(config: JobConnectionConfig, initialEmployees?: any[]) {
    const { jobId, orgId, brand, logo, domain, partners, chatPrompted } = config;

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
          style: { stroke: '#6e7681', strokeWidth: 1.5 }
        });
      }
    });
    store.setRawBackendEdges(orgId, initialEdges);

    // Cria o WebSocket
    const wsUrl = getJobWebSocketUrl(jobId);
    const ws = new WebSocket(wsUrl);
    this.connections[jobId] = ws;

    const resetTimeout = () => {
      if (this.timeouts[jobId]) clearTimeout(this.timeouts[jobId]);
      this.timeouts[jobId] = setTimeout(() => {
        console.log(`[ConnectionManager] ⏱️ Timeout: Nenhuma mensagem para o job ${jobId}`);
        this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
      }, 5 * 60 * 1000);
    };

    resetTimeout();

    ws.onmessage = (event) => {
      resetTimeout();
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
              contacts: store.mappings[orgId]?.rawEmployees || currentEmployees
            }
          }));

          this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
          return;
        }

        if (data.type === 'clear_nodes') {
          console.log(`[ConnectionManager] Comando de limpeza para orgId=${orgId}`);
          
          const currentNodes = store.mappings[orgId]?.rawEmployees || currentEmployees;
          const keepers = currentNodes.filter(emp => {
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
          
          store.setRawEmployees(orgId, keepers);
          
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
          store.setRawBackendEdges(orgId, newEdges);
          return;
        }

        if (data.type === 'batch' || data.type === 'initial') {
          const incomingNodes = (data.nodes || []) as any[];
          const currentNodes = [...(store.mappings[orgId]?.rawEmployees || currentEmployees)];
          const currentEdges = [...(store.mappings[orgId]?.rawBackendEdges || initialEdges)];

          incomingNodes.forEach(emp => {
            const idx = currentNodes.findIndex(n => 
              String(n.id) === String(emp.id) || 
              (n.linkedin && emp.linkedin && n.linkedin === emp.linkedin) ||
              (n.name === emp.name && n.role === emp.role)
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
              (n.name === emp.name && n.role === emp.role)
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
      store.setMappingError(orgId, "Erro na conexão WebSocket com o Worker.");
      this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
    };

    ws.onclose = () => {
      console.log(`[ConnectionManager] Conexão encerrada para job=${jobId}`);
      this.closeAndCleanup(jobId, orgId, chatPrompted, brand);
    };
  }

  public disconnectFromJob(jobId: string) {
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
    
    const store = useChatStore.getState();
    store.setMappingLoading(orgId, false);
    store.setActiveJobId(orgId, null);
    
    // Remove job do local storage se for o ativo
    const saved = localStorage.getItem('active-discovery-job');
    if (saved) {
      try {
        const jobData = JSON.parse(saved);
        if (jobData.job_id === jobId) {
          localStorage.removeItem('active-discovery-job');
        }
      } catch {}
    }

    // Aciona refinamento final de IA
    const currentNodes = store.mappings[orgId]?.rawEmployees || [];
    if (currentNodes.length > 0) {
      this.refineHierarchyAfterMapping(orgId, currentNodes, chatPrompted, brand);
    }
  }

  private async refineHierarchyAfterMapping(orgId: number, nodes: any[], chatPrompted?: boolean, brand?: string) {
    console.log(`[ConnectionManager] Executando refinamento final IA para orgId=${orgId}`);
    try {
      const data = await hierarchyApi.refineHierarchy(nodes);
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

        // Limpa caches de layout
        const keysToDelete: string[] = [];
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key && (key.startsWith('layout-cache-') || key.startsWith('edges-cache-'))) {
            keysToDelete.push(key);
          }
        }
        keysToDelete.forEach(key => localStorage.removeItem(key));
        
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
    }
  }
}

export const connectionManager = new ConnectionManager();
