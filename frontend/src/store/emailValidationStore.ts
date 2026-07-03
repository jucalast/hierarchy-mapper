import { create } from 'zustand';
import toast from 'react-hot-toast';

/**
 * Store global da validação de e-mails em lote.
 *
 * O LOOP roda dentro do store (escopo de módulo), não no componente — assim o
 * processo sobrevive a troca de aba/página/desmontagem do ContactList. O estado
 * observável (progresso, e-mails validados) vive aqui, keyed por organização.
 *
 * O cancelamento usa um registro de módulo (AbortController + flag), separado do
 * estado serializável do zustand.
 */

export interface EmailUpdate {
  email?: string;
  verified?: boolean;
  deleted?: boolean;
}

export interface ValidationProgress {
  current: number;
  total: number;
  pattern?: string;
}

export interface ValidationSession {
  isRunning: boolean;
  progress: ValidationProgress | null;
  activeContactId: string | null;
  emailUpdates: Record<string, EmailUpdate>;
  loadingIds: Record<string, boolean>;
}

interface StartCtx {
  orgName: string;
  orgId?: number;
}

interface EmailValidationStore {
  sessions: Record<string, ValidationSession>;
  getSession: (key: string) => ValidationSession;
  startValidation: (key: string, queue: any[], ctx: StartCtx) => Promise<void>;
  cancelValidation: (key: string) => void;
  clearUpdates: (key: string) => void;
}

export const EMPTY_SESSION: ValidationSession = {
  isRunning: false,
  progress: null,
  activeContactId: null,
  emailUpdates: {},
  loadingIds: {},
};

export const orgKeyOf = (orgId: number | null | undefined): string =>
  orgId != null ? `org_${orgId}` : 'global';

// Registro de cancelamento por org (não serializável → fora do estado zustand).
const runControllers = new Map<string, { cancelled: boolean; controller: AbortController | null }>();

export const useEmailValidationStore = create<EmailValidationStore>()((set, get) => ({
  sessions: {},

  getSession: (key) => get().sessions[key] || EMPTY_SESSION,

  clearUpdates: (key) => {
    set((s) => ({
      sessions: {
        ...s.sessions,
        [key]: { ...(s.sessions[key] || EMPTY_SESSION), emailUpdates: {} },
      },
    }));
  },

  cancelValidation: (key) => {
    const ctl = runControllers.get(key);
    if (ctl) {
      ctl.cancelled = true;
      ctl.controller?.abort();
    }
    set((s) => ({
      sessions: {
        ...s.sessions,
        [key]: { ...(s.sessions[key] || EMPTY_SESSION), isRunning: false, progress: null, activeContactId: null },
      },
    }));
    toast.error('Validação em lote cancelada.');
  },

  startValidation: async (key, queue, ctx) => {
    // Já existe um loop rodando para esta org → não inicia outro.
    if (get().sessions[key]?.isRunning) return;
    if (!queue || queue.length === 0) return;

    const ctl = { cancelled: false, controller: null as AbortController | null };
    runControllers.set(key, ctl);

    const setSession = (fn: (sess: ValidationSession) => ValidationSession) =>
      set((s) => ({ sessions: { ...s.sessions, [key]: fn(s.sessions[key] || EMPTY_SESSION) } }));

    // Estado inicial — preserva e-mails já validados em runs anteriores.
    setSession((sess) => ({
      ...sess,
      isRunning: true,
      progress: { current: 1, total: queue.length },
      activeContactId: null,
      loadingIds: {},
    }));

    let confirmedPattern: string | undefined;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    for (let i = 0; i < queue.length; i++) {
      if (ctl.cancelled) break;
      const person = queue[i];

      setSession((sess) => ({
        ...sess,
        progress: { current: i + 1, total: queue.length, pattern: confirmedPattern },
        activeContactId: person.id,
        loadingIds: { ...sess.loadingIds, [person.id]: true },
      }));

      // Auto-scroll até a linha do contato (se a aba estiver visível).
      try {
        const row = typeof document !== 'undefined' ? document.getElementById(`contact-row-${person.id}`) : null;
        if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } catch {}

      try {
        const token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
        const personId = person.emp_id ?? (typeof person.id === 'number' ? person.id : undefined);
        ctl.controller = new AbortController();

        const response = await fetch(`${apiUrl}/api/v1/intelligence/discover-email`, {
          method: 'POST',
          signal: ctl.controller.signal,
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            contact_name: person.name,
            org_name: ctx.orgName,
            job_title: person.job_title || person.role,
            ...(personId !== undefined ? { person_id: personId } : {}),
            ...(ctx.orgId !== undefined ? { org_id: ctx.orgId } : {}),
            force: true,
          }),
        });

        if (ctl.cancelled) break;

        if (response.ok) {
          const data = await response.json();
          if (ctl.cancelled) break;
          const discoveredEmail = data.recommended || data.email;

          if (data.ok && discoveredEmail) {
            // Padrões canônicos sobrepõem web_harvested.
            if (data.pattern && (!confirmedPattern || (confirmedPattern === 'web_harvested' && data.pattern !== 'web_harvested'))) {
              confirmedPattern = data.pattern;
            }
            setSession((sess) => ({
              ...sess,
              emailUpdates: { ...sess.emailUpdates, [person.id]: { email: discoveredEmail, verified: true } },
            }));
          }
          // Falha em contato mapeado: mantém o e-mail atual (backend não sobrescreve).
        }
      } catch (error: any) {
        if (!ctl.cancelled) console.error('[validação lote] erro para', person.name, error);
      } finally {
        setSession((sess) => ({ ...sess, loadingIds: { ...sess.loadingIds, [person.id]: false } }));
      }

      if (ctl.cancelled) break;
      await new Promise((r) => setTimeout(r, 1500));
      if (ctl.cancelled) break;
    }

    const wasCancelled = ctl.cancelled;
    runControllers.delete(key);
    setSession((sess) => ({ ...sess, isRunning: false, progress: null, activeContactId: null }));

    if (!wasCancelled) {
      toast.success('Validação em lote concluída!');
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
    }
  },
}));
