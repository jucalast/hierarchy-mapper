import { useState, useCallback, useEffect, useMemo } from 'react';
import { organizations, api } from '@/services/api';

const TASK_SUMMARY_CACHE_KEY = 'pipedrive-task-summary-cache';
const ACTIVE_STAGE_FILTER_KEY = 'drawer-active-stage-filter';

export function usePipedriveSync() {
    const [pipedriveOrgs, setPipedriveOrgs] = useState<any[]>([]);
    const [searchTerm, setSearchTerm] = useState("");
    const [loadingOrgs, setLoadingOrgs] = useState(true);
    const [taskSummary, setTaskSummary] = useState<Record<number, { next_due_date: string; overdue_count: number; pending_count: number }>>({});
    const [activeStageFilter, setActiveStageFilterState] = useState<string | null>(null);

    const fetchTaskSummary = useCallback(async () => {
        try {
            const items = await api.get<Array<{
                org_id: number;
                next_due_date: string;
                overdue_count: number;
                pending_count: number;
            }>>('/pipedrive/activities/pending-summary');
            if (Array.isArray(items)) {
                const map: Record<number, typeof items[0]> = {};
                items.forEach(i => { map[i.org_id] = i; });
                setTaskSummary(map);
                try { localStorage.setItem(TASK_SUMMARY_CACHE_KEY, JSON.stringify(map)); } catch {}
            }
        } catch { /* silent */ }
    }, []);

    // Persiste a aba de stage ativa (não reordena a lista — apenas mantém a seleção entre reload/navegação)
    const setActiveStageFilter = useCallback((stage: string | null) => {
        setActiveStageFilterState(stage);
        try {
            if (stage === null) {
                localStorage.removeItem(ACTIVE_STAGE_FILTER_KEY);
            } else {
                localStorage.setItem(ACTIVE_STAGE_FILTER_KEY, stage);
            }
        } catch {}
    }, []);

    const SYNC_TTL_MS = 5 * 60 * 1000;
    
    const fetchPipedriveOrgs = useCallback(async () => {
        if (pipedriveOrgs.length === 0) setLoadingOrgs(true);
        try {
            const lastSync = Number(localStorage.getItem('pipedrive-sync-ts') || 0);
            if (Date.now() - lastSync > SYNC_TTL_MS) {
                localStorage.setItem('pipedrive-sync-ts', String(Date.now()));
                organizations.triggerPipedriveSync().catch(() => {});
            }
            const data = await organizations.listOrganizations();
            const list = Array.isArray(data) ? [...data].sort((a: any, b: any) => Number(b.id) - Number(a.id)) : [];
            setPipedriveOrgs(list);
            fetchTaskSummary();
            if (list.length > 0) localStorage.setItem('pipedrive-orgs-cache', JSON.stringify(list));
        } catch (e: any) {
            console.warn('[PipedriveSync] Sync error:', e.message || e);
        } finally {
            setLoadingOrgs(false);
        }
    }, [pipedriveOrgs.length, fetchTaskSummary]);

    const handleOrgRenamed = useCallback((orgId: number, newName: string) => {
        setPipedriveOrgs(prev => prev.map(org => Number(org.id) === orgId ? { ...org, name: newName } : org));
        const cached = localStorage.getItem("pipedrive-orgs-cache");
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                const updated = parsed.map((org: any) => Number(org.id) === orgId ? { ...org, name: newName } : org);
                localStorage.setItem("pipedrive-orgs-cache", JSON.stringify(updated));
            } catch (e) {}
        }
    }, []);

    const filteredOrgs = useMemo(() => {
        const seen = new Set<number>();
        return pipedriveOrgs
            .filter(org => {
                const id = Number(org.id);
                if (!id || seen.has(id)) return false;
                seen.add(id);
                const matchesSearch = (
                    org.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    org.domain?.toLowerCase().includes(searchTerm.toLowerCase())
                );
                const matchesStage = !activeStageFilter || org.stage_name === activeStageFilter;
                return matchesSearch && matchesStage;
            })
            .map(org => ({
                ...org,
                _taskSummary: taskSummary[Number(org.id)] || null,
            }))
            .sort((a, b) => {
                const ta = a._taskSummary;
                const tb = b._taskSummary;
                if (!ta && !tb) return 0;
                if (!ta) return 1;
                if (!tb) return -1;
                const aOverdue = ta.overdue_count > 0;
                const bOverdue = tb.overdue_count > 0;
                if (aOverdue !== bOverdue) return aOverdue ? -1 : 1;
                return ta.next_due_date.localeCompare(tb.next_due_date);
            });
    }, [pipedriveOrgs, searchTerm, taskSummary, activeStageFilter]);

    // Coleta estágios únicos das orgs carregadas e ordena pela ordem do Pipedrive (ordem fixa, nunca reordenada)
    const uniqueStages = useMemo(() => {
        const seen = new Set<string>();
        const stages: { name: string; count: number; order_nr: number }[] = [];
        for (const org of pipedriveOrgs) {
            const s = org.stage_name;
            if (s && !seen.has(s)) {
                seen.add(s);
                stages.push({ name: s, count: 0, order_nr: org.stage_order_nr || 0 });
            }
        }
        // Conta orgs por estágio
        for (const stage of stages) {
            stage.count = pipedriveOrgs.filter(o => o.stage_name === stage.name).length;
        }
        // Ordena pela ordem oficial do Pipedrive (stage_order_nr)
        stages.sort((a, b) => a.order_nr - b.order_nr);
        return stages;
    }, [pipedriveOrgs]);

    useEffect(() => {
        const cached = localStorage.getItem("pipedrive-orgs-cache");
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    setPipedriveOrgs(parsed);
                    setLoadingOrgs(false);
                }
            } catch (e) {}
        }

        try {
            const cachedSummary = localStorage.getItem(TASK_SUMMARY_CACHE_KEY);
            if (cachedSummary) {
                const parsed = JSON.parse(cachedSummary);
                if (parsed && typeof parsed === 'object') setTaskSummary(parsed);
            }
        } catch (e) {}

        try {
            const savedFilter = localStorage.getItem(ACTIVE_STAGE_FILTER_KEY);
            if (savedFilter) setActiveStageFilterState(savedFilter);
        } catch (e) {}

        fetchPipedriveOrgs();
    }, []);

    // taskSummary é a fonte única do contador "Tarefas pra hoje" (Sidebar) e do
    // badge colorido por empresa (Drawer/OrgListItem). Sem isso, completar/desfazer
    // uma tarefa só atualizava a timeline da empresa expandida no Drawer — o mapa
    // taskSummary ficava com o next_due_date antigo, deixando o badge verde mesmo
    // sem tarefa pendente pra hoje.
    useEffect(() => {
        const handleTaskChanged = () => { fetchTaskSummary(); };
        window.addEventListener('crm_timeline_changed', handleTaskChanged);
        window.addEventListener('crm_task_completed', handleTaskChanged);
        window.addEventListener('crm_task_uncompleted', handleTaskChanged);
        return () => {
            window.removeEventListener('crm_timeline_changed', handleTaskChanged);
            window.removeEventListener('crm_task_completed', handleTaskChanged);
            window.removeEventListener('crm_task_uncompleted', handleTaskChanged);
        };
    }, [fetchTaskSummary]);

    return {
        pipedriveOrgs, setPipedriveOrgs,
        searchTerm, setSearchTerm,
        loadingOrgs,
        taskSummary,
        filteredOrgs,
        fetchPipedriveOrgs,
        handleOrgRenamed,
        uniqueStages,
        activeStageFilter,
        setActiveStageFilter,
    };
}
