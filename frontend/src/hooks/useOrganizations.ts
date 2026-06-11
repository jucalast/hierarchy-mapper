/**
 * useOrganizations — lista de organizações do Pipedrive com:
 *  - cache automático em localStorage (evita flicker)
 *  - background refresh sem piscar
 *  - invalidação manual via refetch
 *  - filtro (client-side) por nome/domínio
 *
 * Substitui o bloco fetchPipedriveOrgs + cache manual espalhado em NetworkGraph/WhatsAppClone.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { OrganizationSummary } from '@/types';
import { organizations as orgsApi } from '@/services/api';

const CACHE_KEY = 'pipedrive-orgs-cache';

function readCache(): OrganizationSummary[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeCache(list: OrganizationSummary[]) {
  try {
    if (list.length > 0) {
      window.localStorage.setItem(CACHE_KEY, JSON.stringify(list));
    } else {
      window.localStorage.removeItem(CACHE_KEY);
    }
  } catch {
    /* no-op */
  }
}

export interface UseOrganizationsOptions {
  /** Disparar refetch no mount. Default true. */
  autoRefresh?: boolean;
  /** Executar também um /pipedrive_sync em background antes de listar. Default true. */
  triggerSync?: boolean;
  /** Filtro por nome/domínio (case insensitive). */
  search?: string;
}

export function useOrganizations(options: UseOrganizationsOptions = {}) {
  const { autoRefresh = true, triggerSync = true, search = '' } = options;

  const [orgs, setOrgs] = useState<OrganizationSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isHydrated, setIsHydrated] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const refetch = useCallback(async () => {
    if (orgs.length === 0) setLoading(true);
    setError(null);

    if (triggerSync) {
      // Sync em background, não bloqueia a listagem (melhor UX)
      void orgsApi.triggerPipedriveSync().catch(() => {
        /* silent */
      });
    }

    try {
      const list = await orgsApi.listOrganizations();
      if (!mountedRef.current) return;
      const next = Array.isArray(list) ? list : [];
      setOrgs(next);
      writeCache(next);
    } catch (e) {
      if (!mountedRef.current) return;
      setError(e as Error);
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [orgs.length, triggerSync]);

  useEffect(() => {
    setIsHydrated(true);
    const cached = readCache();
    if (cached.length > 0) {
      setOrgs(cached);
      setLoading(false);
    }

    if (autoRefresh) void refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return orgs;
    const q = search.toLowerCase();
    return orgs.filter((org) => {
      const name = String(org.name || '').toLowerCase();
      const domain = String(org.domain || '').toLowerCase();
      return name.includes(q) || domain.includes(q);
    });
  }, [orgs, search]);

  const updateOrg = useCallback(
    (orgId: number, patch: Partial<OrganizationSummary>) => {
      setOrgs((prev) => {
        const next = prev.map((o) => (Number(o.id) === orgId ? { ...o, ...patch } : o));
        writeCache(next);
        return next;
      });
    },
    [],
  );

  const removeOrg = useCallback((orgId: number) => {
    setOrgs((prev) => {
      const next = prev.filter(
        (o) => Number(o.id) !== orgId && Number(o.local_id) !== orgId,
      );
      writeCache(next);
      return next;
    });
  }, []);

  return {
    orgs,
    filtered,
    loading: !isHydrated || loading,
    error,
    refetch,
    updateOrg,
    removeOrg,
  };
}
