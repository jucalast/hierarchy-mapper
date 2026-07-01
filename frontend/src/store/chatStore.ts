import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { Message, CompanyResult } from '../components/chat/ChatInterfaces';
import { AgentEvent } from '../components/chat/AgentV2Message';
import { Edge } from 'reactflow';

export interface BatchQueueItem {
  messageId: string;
  actionIndex: number;
  action: { label: string; prompt: string; categoria?: string };
}

export interface ChatSession {
  messages: Message[];
  inputValue: string;
  isLoading: boolean;
  selectedCompanies: CompanyResult[];
  approvalStatuses: Record<string, 'pending' | 'approving' | 'approved' | 'rejected'>;
  liveModel: string | null;
  modelActivity: any[];
  agentEvents: any[];
  agentStreaming: boolean;
  agentConfirmedActions: Record<string, boolean>;
  activeRunningTask: {
    label: string;
    prompt: string;
    status: any;
    logs: AgentEvent[];
    isExpanded: boolean;
    orgId?: number | null;
    threadId?: string;
    actionIndex: number;
    parentMessageId?: string;
  } | null;
  approvedSuggestedActions: Record<string, any>;
  taskInlineConfirmed: Record<string, boolean>;
  batchQueue: BatchQueueItem[];
  isBatchRunning: boolean;
  batchRunningSnapshot: BatchQueueItem[];
  batchCurrentIndex: number;
}

export interface MappingSession {
  rawEmployees: any[];
  rawBackendEdges: Edge[];
  loading: boolean;
  discovering: boolean;
  brandOptions: any[];
  error: string | null;
  activeJobId: string | null;
  isSmartSyncLoading: boolean;
}

interface ChatStore {
  sessions: Record<string, ChatSession>; // chave: threadId ou orgId (se sem thread)
  mappings: Record<number, MappingSession>; // chave: orgId
  activeTabs: number[]; // Lista de orgIds abertos nas abas
  currentOrgId: number | null;
  globalSmartSyncLoading: boolean;

  // Helpers de inicialização
  getSession: (orgId: number | null | undefined, threadId: string | null | undefined) => ChatSession;
  getMapping: (orgId: number | null | undefined) => MappingSession;

  // Actions de Chat
  setInputValue: (orgId: number | null | undefined, threadId: string | null | undefined, val: string) => void;
  setMessages: (orgId: number | null | undefined, threadId: string | null | undefined, messages: Message[] | ((prev: Message[]) => Message[])) => void;
  setIsLoading: (orgId: number | null | undefined, threadId: string | null | undefined, loading: boolean) => void;
  setAgentStreaming: (orgId: number | null | undefined, threadId: string | null | undefined, streaming: boolean) => void;
  setSelectedCompanies: (orgId: number | null | undefined, threadId: string | null | undefined, companies: CompanyResult[] | ((prev: CompanyResult[]) => CompanyResult[])) => void;
  setApprovalStatuses: (orgId: number | null | undefined, threadId: string | null | undefined, statuses: Record<string, any> | ((prev: Record<string, any>) => Record<string, any>)) => void;
  setLiveModel: (orgId: number | null | undefined, threadId: string | null | undefined, model: string | null) => void;
  setModelActivity: (orgId: number | null | undefined, threadId: string | null | undefined, activity: any[] | ((prev: any[]) => any[])) => void;
  setAgentEvents: (orgId: number | null | undefined, threadId: string | null | undefined, events: any[] | ((prev: any[]) => any[])) => void;
  setAgentConfirmedActions: (orgId: number | null | undefined, threadId: string | null | undefined, confirmed: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)) => void;
  setActiveRunningTask: (orgId: number | null | undefined, threadId: string | null | undefined, task: any | ((prev: any | null) => any | null)) => void;
  setApprovedSuggestedActions: (orgId: number | null | undefined, threadId: string | null | undefined, actions: Record<string, any> | ((prev: Record<string, any>) => Record<string, any>)) => void;
  setTaskInlineConfirmed: (orgId: number | null | undefined, threadId: string | null | undefined, confirmed: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)) => void;
  setBatchQueue: (orgId: number | null | undefined, threadId: string | null | undefined, queue: BatchQueueItem[] | ((prev: BatchQueueItem[]) => BatchQueueItem[])) => void;
  setIsBatchRunning: (orgId: number | null | undefined, threadId: string | null | undefined, running: boolean) => void;
  setBatchRunningSnapshot: (orgId: number | null | undefined, threadId: string | null | undefined, snapshot: BatchQueueItem[]) => void;
  setBatchCurrentIndex: (orgId: number | null | undefined, threadId: string | null | undefined, index: number) => void;

  // Actions de Mapeamento
  setRawEmployees: (orgId: number, employees: any[] | ((prev: any[]) => any[])) => void;
  setRawBackendEdges: (orgId: number, edges: Edge[] | ((prev: Edge[]) => Edge[])) => void;
  setMappingLoading: (orgId: number, loading: boolean) => void;
  setDiscovering: (orgId: number, discovering: boolean) => void;
  setBrandOptions: (orgId: number, options: any[] | ((prev: any[]) => any[])) => void;
  setMappingError: (orgId: number, error: string | null) => void;
  setActiveJobId: (orgId: number, jobId: string | null) => void;
  setIsSmartSyncLoading: (orgId: number, loading: boolean) => void;

  // Actions Gerais/Abas
  addActiveTab: (orgId: number) => void;
  removeActiveTab: (orgId: number) => void;
  setCurrentOrgId: (orgId: number | null) => void;
  setGlobalSmartSyncLoading: (loading: boolean) => void;
}

const defaultSession = (): ChatSession => ({
  messages: [],
  inputValue: '',
  isLoading: false,
  selectedCompanies: [],
  approvalStatuses: {},
  liveModel: null,
  modelActivity: [],
  agentEvents: [],
  agentStreaming: false,
  agentConfirmedActions: {},
  activeRunningTask: null,
  approvedSuggestedActions: {},
  taskInlineConfirmed: {},
  batchQueue: [],
  isBatchRunning: false,
  batchRunningSnapshot: [],
  batchCurrentIndex: -1,
});

const defaultMapping = (): MappingSession => ({
  rawEmployees: [],
  rawBackendEdges: [],
  loading: false,
  discovering: false,
  brandOptions: [],
  error: null,
  activeJobId: null,
  isSmartSyncLoading: false,
});

export const getSessionKey = (orgId: number | null | undefined, threadId: string | null | undefined): string => {
  if (threadId) return threadId;
  if (orgId) return `org_${orgId}`;
  return 'global';
};

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: {},
      mappings: {},
      activeTabs: [],
      currentOrgId: null,
      globalSmartSyncLoading: false,

      getSession: (orgId, threadId) => {
        const key = getSessionKey(orgId, threadId);
        return get().sessions[key] || defaultSession();
      },

  getMapping: (orgId) => {
    if (!orgId) return defaultMapping();
    return get().mappings[orgId] || defaultMapping();
  },

  setInputValue: (orgId, threadId, val) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => ({
      sessions: {
        ...state.sessions,
        [key]: {
          ...(state.sessions[key] || defaultSession()),
          inputValue: val,
        },
      },
    }));
  },

  setMessages: (orgId, threadId, messages) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextMessages = typeof messages === 'function' ? messages(session.messages) : messages;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            messages: nextMessages,
          },
        },
      };
    });
  },

  setIsLoading: (orgId, threadId, loading) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => ({
      sessions: {
        ...state.sessions,
        [key]: {
          ...(state.sessions[key] || defaultSession()),
          isLoading: loading,
        },
      },
    }));
  },

  setAgentStreaming: (orgId, threadId, streaming) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => ({
      sessions: {
        ...state.sessions,
        [key]: {
          ...(state.sessions[key] || defaultSession()),
          agentStreaming: streaming,
        },
      },
    }));
  },

  setSelectedCompanies: (orgId, threadId, companies) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextCompanies = typeof companies === 'function' ? companies(session.selectedCompanies) : companies;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            selectedCompanies: nextCompanies,
          },
        },
      };
    });
  },

  setApprovalStatuses: (orgId, threadId, statuses) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextStatuses = typeof statuses === 'function' ? statuses(session.approvalStatuses) : statuses;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            approvalStatuses: nextStatuses,
          },
        },
      };
    });
  },

  setLiveModel: (orgId, threadId, model) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => ({
      sessions: {
        ...state.sessions,
        [key]: {
          ...(state.sessions[key] || defaultSession()),
          liveModel: model,
        },
      },
    }));
  },

  setModelActivity: (orgId, threadId, activity) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextActivity = typeof activity === 'function' ? activity(session.modelActivity) : activity;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            modelActivity: nextActivity,
          },
        },
      };
    });
  },

  setAgentEvents: (orgId, threadId, events) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextEvents = typeof events === 'function' ? events(session.agentEvents) : events;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            agentEvents: nextEvents,
          },
        },
      };
    });
  },

  setAgentConfirmedActions: (orgId, threadId, confirmed) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextConfirmed = typeof confirmed === 'function' ? confirmed(session.agentConfirmedActions) : confirmed;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            agentConfirmedActions: nextConfirmed,
          },
        },
      };
    });
  },

  setActiveRunningTask: (orgId, threadId, task) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextTask = typeof task === 'function' ? task(session.activeRunningTask) : task;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            activeRunningTask: nextTask,
          },
        },
      };
    });
  },

  setApprovedSuggestedActions: (orgId, threadId, actions) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextActions = typeof actions === 'function' ? actions(session.approvedSuggestedActions) : actions;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            approvedSuggestedActions: nextActions,
          },
        },
      };
    });
  },

  setTaskInlineConfirmed: (orgId, threadId, confirmed) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextConfirmed = typeof confirmed === 'function' ? confirmed(session.taskInlineConfirmed) : confirmed;
      return {
        sessions: {
          ...state.sessions,
          [key]: {
            ...session,
            taskInlineConfirmed: nextConfirmed,
          },
        },
      };
    });
  },

  setBatchQueue: (orgId, threadId, queue) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => {
      const session = state.sessions[key] || defaultSession();
      const nextQueue = typeof queue === 'function' ? queue(session.batchQueue || []) : queue;
      return {
        sessions: {
          ...state.sessions,
          [key]: { ...session, batchQueue: nextQueue },
        },
      };
    });
  },

  setIsBatchRunning: (orgId, threadId, running) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => ({
      sessions: {
        ...state.sessions,
        [key]: {
          ...(state.sessions[key] || defaultSession()),
          isBatchRunning: running,
        },
      },
    }));
  },

  setBatchRunningSnapshot: (orgId, threadId, snapshot) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => ({
      sessions: {
        ...state.sessions,
        [key]: { ...(state.sessions[key] || defaultSession()), batchRunningSnapshot: snapshot },
      },
    }));
  },

  setBatchCurrentIndex: (orgId, threadId, index) => {
    const key = getSessionKey(orgId, threadId);
    set((state) => ({
      sessions: {
        ...state.sessions,
        [key]: { ...(state.sessions[key] || defaultSession()), batchCurrentIndex: index },
      },
    }));
  },

  // Mapping state setters
  setRawEmployees: (orgId, employees) => {
    set((state) => {
      const mapping = state.mappings[orgId] || defaultMapping();
      const nextEmployees = typeof employees === 'function' ? employees(mapping.rawEmployees) : employees;
      return {
        mappings: {
          ...state.mappings,
          [orgId]: {
            ...mapping,
            rawEmployees: nextEmployees,
          },
        },
      };
    });
  },

  setRawBackendEdges: (orgId, edges) => {
    set((state) => {
      const mapping = state.mappings[orgId] || defaultMapping();
      const nextEdges = typeof edges === 'function' ? edges(mapping.rawBackendEdges) : edges;
      return {
        mappings: {
          ...state.mappings,
          [orgId]: {
            ...mapping,
            rawBackendEdges: nextEdges,
          },
        },
      };
    });
  },

  setMappingLoading: (orgId, loading) => {
    set((state) => ({
      mappings: {
        ...state.mappings,
        [orgId]: {
          ...(state.mappings[orgId] || defaultMapping()),
          loading,
        },
      },
    }));
  },

  setDiscovering: (orgId, discovering) => {
    set((state) => ({
      mappings: {
        ...state.mappings,
        [orgId]: {
          ...(state.mappings[orgId] || defaultMapping()),
          discovering,
        },
      },
    }));
  },

  setBrandOptions: (orgId, options) => {
    set((state) => {
      const mapping = state.mappings[orgId] || defaultMapping();
      const nextOptions = typeof options === 'function' ? options(mapping.brandOptions) : options;
      return {
        mappings: {
          ...state.mappings,
          [orgId]: {
            ...mapping,
            brandOptions: nextOptions,
          },
        },
      };
    });
  },

  setMappingError: (orgId, error) => {
    set((state) => ({
      mappings: {
        ...state.mappings,
        [orgId]: {
          ...(state.mappings[orgId] || defaultMapping()),
          error,
        },
      },
    }));
  },

  setActiveJobId: (orgId, jobId) => {
    set((state) => ({
      mappings: {
        ...state.mappings,
        [orgId]: {
          ...(state.mappings[orgId] || defaultMapping()),
          activeJobId: jobId,
        },
      },
    }));
  },

  setIsSmartSyncLoading: (orgId, loading) => {
    set((state) => ({
      mappings: {
        ...state.mappings,
        [orgId]: {
          ...(state.mappings[orgId] || defaultMapping()),
          isSmartSyncLoading: loading,
        },
      },
    }));
  },

  setGlobalSmartSyncLoading: (loading) => {
    set({ globalSmartSyncLoading: loading });
  },

  // Tabs management
  addActiveTab: (orgId) => {
    set((state) => {
      const nextTabs = state.activeTabs.filter((id) => id !== orgId);
      nextTabs.unshift(orgId);
      return { activeTabs: nextTabs };
    });
  },

  removeActiveTab: (orgId) => {
    set((state) => {
      const nextTabs = state.activeTabs.filter((id) => id !== orgId);
      let nextOrgId = state.currentOrgId;
      if (state.currentOrgId === orgId) {
        nextOrgId = nextTabs.length > 0 ? nextTabs[0] : null;
      }
      return {
        activeTabs: nextTabs,
        currentOrgId: nextOrgId,
      };
    });
  },

  setCurrentOrgId: (orgId) => {
    set((state) => {
      if (!orgId) return { currentOrgId: null };
      const nextTabs = state.activeTabs.filter((id) => id !== orgId);
      nextTabs.unshift(orgId);
      return {
        currentOrgId: orgId,
        activeTabs: nextTabs,
      };
    });
  },
}),
{
  name: 'linkb2b-chat-store',
  storage: createJSONStorage(() => ({
    getItem: (name) => { try { return localStorage.getItem(name); } catch { return null; } },
    setItem: (name, value) => { try { localStorage.setItem(name, value); } catch (e) { console.warn('[chatStore] localStorage quota exceeded, persist skipped:', e); } },
    removeItem: (name) => { try { localStorage.removeItem(name); } catch {} },
  })),
  partialize: (state) => ({
    sessions: Object.fromEntries(
      Object.entries(state.sessions).map(([k, s]) => [k, {
        ...s,
        modelActivity: [],
        agentEvents: [],
        activeRunningTask: null,
        isLoading: false,
        agentStreaming: false,
        batchQueue: [],
        isBatchRunning: false,
      }])
    ),
    mappings: Object.fromEntries(
      Object.entries(state.mappings).map(([k, m]) => [k, {
        loading: false,
        discovering: false,
        error: m.error,
        activeJobId: m.activeJobId,
        isSmartSyncLoading: false,
        rawEmployees: [],
        rawBackendEdges: [],
        brandOptions: [],
      }])
    ),
  }),
}
));
