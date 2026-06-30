'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { API_V1_URL } from '@/services/config';
import { hierarchy as hierarchyApi, jobs as jobsApi } from '@/services/api';
import { connectionManager } from '@/services/connectionManager';

export interface ScanEmployeeProfile {
    id?: string;
    name: string;
    role: string;
    linkedin_url: string;
    avatar: string;
    location?: string;
    observations?: string;
    evidence?: string;
    email?: string;
}

export interface OrgScanState {
    isScanning: boolean;
    scanError: string | null;
    scanProgress: number;
    consoleLogs: string[];
    hasPreview: boolean;
    previewTimestamp: number;
    previewUrl: string;
    scanResults: ScanEmployeeProfile[];
}

export interface UseHierarchyScanReturn {
    getScanState: (orgId: number) => OrgScanState;
    startScan: (
        orgId: number,
        companyUrl: string,
        sessionCookie?: string,
        areaFocus?: string,
        productFocus?: string,
        model?: string
    ) => void;
    stopScan: (orgId: number) => void;
    reconnectScan: () => Promise<boolean>;
    handleImageClick: (orgId: number, e: React.MouseEvent<HTMLImageElement>) => void;
    sendText: (orgId: number, text: string) => void;
    pressEnter: (orgId: number) => void;
    pressBackspace: (orgId: number) => void;
    resetScan: (orgId: number) => void;
    isAnyScanning: boolean;
    activeScanOrgId: number | null;
    activeScanOrgIds: number[];
}

// ---------- localStorage helpers ----------

const SCANS_KEY = 'active-linkedin-scans';
const LEGACY_KEY = 'active-linkedin-scan';

type StoredEntry = {
    job_id: string;
    orgId: number;
    companyUrl: string;
    startTime: number;
    chatPrompted: boolean;
};

function _readAllStored(): Record<number, StoredEntry> {
    if (typeof window === 'undefined') return {};
    try {
        const raw = localStorage.getItem(SCANS_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<number, StoredEntry>;
        }
        // Retrocompatibilidade com o formato antigo (uma única entrada)
        const legacy = localStorage.getItem(LEGACY_KEY);
        if (legacy && legacy !== 'NaN' && legacy !== 'undefined') {
            const p = JSON.parse(legacy) as StoredEntry;
            if (p?.job_id && p?.orgId) return { [p.orgId]: p };
        }
    } catch { /* ignore */ }
    return {};
}

function _writeScanEntry(orgId: number, entry: StoredEntry | null) {
    if (typeof window === 'undefined') return;
    const all = _readAllStored();
    if (entry === null) {
        delete all[orgId];
    } else {
        all[orgId] = entry;
    }
    if (Object.keys(all).length === 0) {
        localStorage.removeItem(SCANS_KEY);
    } else {
        localStorage.setItem(SCANS_KEY, JSON.stringify(all));
    }
    localStorage.removeItem(LEGACY_KEY);
}

// ---------- hook ----------

const EMPTY_STATE: OrgScanState = {
    isScanning: false,
    scanError: null,
    scanProgress: 0,
    consoleLogs: [],
    hasPreview: false,
    previewTimestamp: Date.now(),
    previewUrl: '',
    scanResults: [],
};

type ScanRefs = { ws: WebSocket | null; jobId: string | null };

// Scans LinkedIn duram no máximo ~20 min (JOB_IDLE_TIMEOUT_MS). Qualquer entrada
// com mais de 2 horas é considerada expirada e descartada para evitar falso "Mapeando..."
// após reiniciar o sistema no dia seguinte.
const MAX_SCAN_AGE_MS = 2 * 60 * 60 * 1000;

function _buildInitialState(): Record<number, OrgScanState> {
    const stored = _readAllStored();
    const result: Record<number, OrgScanState> = {};
    const now = Date.now();
    for (const [orgIdStr, entry] of Object.entries(stored)) {
        if (entry.startTime && (now - entry.startTime) > MAX_SCAN_AGE_MS) {
            _writeScanEntry(Number(orgIdStr), null);
            continue;
        }
        result[Number(orgIdStr)] = {
            ...EMPTY_STATE,
            isScanning: true,
            consoleLogs: ['[System] Reconectando à varredura em andamento...'],
        };
    }
    return result;
}

export function useHierarchyScan(): UseHierarchyScanReturn {
    const [scanMap, setScanMap] = useState<Record<number, OrgScanState>>(_buildInitialState);
    const refsMap = useRef<Record<number, ScanRefs>>({});

    // Inicializa refs a partir do localStorage na montagem
    useEffect(() => {
        const stored = _readAllStored();
        for (const [orgIdStr, entry] of Object.entries(stored)) {
            const orgId = Number(orgIdStr);
            if (!refsMap.current[orgId]) {
                refsMap.current[orgId] = { ws: null, jobId: entry.job_id };
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const getScanState = useCallback((orgId: number): OrgScanState => {
        const state = scanMap[orgId] ?? EMPTY_STATE;
        return {
            ...state,
            previewUrl: `${API_V1_URL}/hierarchy/linkedin-scrape/preview?t=${state.previewTimestamp}`,
        };
    }, [scanMap]);

    // Cria a conexão WebSocket para um orgId/jobId. Usa setScanMap com updater
    // funcional em todos os handlers para evitar stale closure sobre scanMap.
    const attachWebSocket = useCallback((orgId: number, jobId: string) => {
        const existing = refsMap.current[orgId];
        if (existing?.ws) existing.ws.close();
        refsMap.current[orgId] = { ws: null, jobId };

        const ws = new WebSocket(jobsApi.getJobWebSocketUrl(jobId));

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case 'log': {
                        setScanMap(prev => {
                            const cur = prev[orgId] ?? EMPTY_STATE;
                            const match = (data.message as string).match(/Colaboradores na página:\s*(\d+)/);
                            const progress = match ? Math.min(parseInt(match[1], 10) * 1.5, 98) : cur.scanProgress;
                            return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, data.message], scanProgress: progress } };
                        });
                        break;
                    }
                    case 'screenshot': {
                        setScanMap(prev => {
                            const cur = prev[orgId] ?? EMPTY_STATE;
                            return { ...prev, [orgId]: { ...cur, hasPreview: true, previewTimestamp: Date.now() } };
                        });
                        break;
                    }
                    case 'cookie': {
                        localStorage.setItem('linkedin_li_at_cookie', data.cookie);
                        setScanMap(prev => {
                            const cur = prev[orgId] ?? EMPTY_STATE;
                            return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, '[System] Cookie li_at capturado e salvo!'] } };
                        });
                        break;
                    }
                    case 'clear_nodes': {
                        setScanMap(prev => {
                            const cur = prev[orgId] ?? EMPTY_STATE;
                            return { ...prev, [orgId]: { ...cur, scanResults: [], scanProgress: 0 } };
                        });
                        break;
                    }
                    case 'batch': {
                        if (data.nodes?.length > 0) {
                            setScanMap(prev => {
                                const cur = prev[orgId] ?? EMPTY_STATE;
                                const newProfiles: ScanEmployeeProfile[] = data.nodes.map((n: any) => ({
                                    id: n.id, name: n.name, role: n.role,
                                    linkedin_url: n.linkedin || n.url, avatar: n.avatar,
                                    location: n.location, observations: n.observations,
                                    evidence: n.evidence, email: n.email,
                                }));
                                const filtered = newProfiles.filter(p =>
                                    !cur.scanResults.some(e => e.linkedin_url === p.linkedin_url)
                                );
                                return { ...prev, [orgId]: { ...cur, scanResults: [...cur.scanResults, ...filtered] } };
                            });
                        }
                        break;
                    }
                    case 'result': {
                        if (data.data?.length > 0) {
                            setScanMap(prev => {
                                const cur = prev[orgId] ?? EMPTY_STATE;
                                return { ...prev, [orgId]: { ...cur, scanResults: data.data, scanProgress: 100 } };
                            });
                        }
                        break;
                    }
                    case 'done': {
                        setScanMap(prev => {
                            const cur = prev[orgId] ?? EMPTY_STATE;
                            return { ...prev, [orgId]: { ...cur, isScanning: false, scanProgress: 100, consoleLogs: [...cur.consoleLogs, '[System] Varredura e processamento concluídos com sucesso!'] } };
                        });
                        ws.close();
                        _writeScanEntry(orgId, null);
                        break;
                    }
                    case 'error': {
                        setScanMap(prev => {
                            const cur = prev[orgId] ?? EMPTY_STATE;
                            return { ...prev, [orgId]: { ...cur, isScanning: false, scanError: data.message, consoleLogs: [...cur.consoleLogs, `[Error] ${data.message}`] } };
                        });
                        ws.close();
                        _writeScanEntry(orgId, null);
                        break;
                    }
                }
            } catch {
                setScanMap(prev => {
                    const cur = prev[orgId] ?? EMPTY_STATE;
                    return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, `[System] Mensagem não processada: ${event.data}`] } };
                });
            }
        };

        ws.onerror = () => {
            setScanMap(prev => {
                const cur = prev[orgId] ?? EMPTY_STATE;
                return { ...prev, [orgId]: { ...cur, isScanning: false, consoleLogs: [...cur.consoleLogs, '[Error] Conexão com o agente perdida. O scan continua em segundo plano no servidor.'] } };
            });
        };

        refsMap.current[orgId] = { ws, jobId };
    }, []); // setScanMap é estável; orgId/jobId chegam como parâmetros

    const attachGraphConnection = useCallback(async (
        jobId: string,
        orgId: number,
        chatPrompted: boolean,
        snapshotEmployees?: any[]
    ) => {
        const { useChatStore } = await import('@/store/chatStore');
        const apiModule = await import('@/services/api');
        const hierarchyApi = apiModule.hierarchy;

        // Prioriza o snapshot capturado em startScan (antes de qualquer await),
        // depois tenta o store atual, e por último carrega do banco como fallback.
        let existingEmployees = (snapshotEmployees && snapshotEmployees.length > 0)
            ? snapshotEmployees
            : useChatStore.getState().mappings[orgId]?.rawEmployees || [];

        if (existingEmployees.length === 0 && orgId) {
            try {
                const data = await hierarchyApi.loadHierarchyByPipedrive(orgId);
                if (data?.nodes?.length) {
                    existingEmployees = data.nodes;
                }
            } catch (e) {
                console.warn('[HierarchyScan] Erro ao carregar hierarquia prévia para preservar sócios:', e);
            }
        }

        connectionManager.connectToJob({
            jobId, orgId, brand: '', logo: '', domain: '', partners: [], chatPrompted,
        }, existingEmployees);
    }, []);

    const resolveChatPrompted = (orgId: number): boolean => {
        const pending = localStorage.getItem('pending-hierarchy-continuation');
        if (!pending) return false;
        try {
            const parsed = JSON.parse(pending);
            return !!(parsed && Number(parsed.org_id) === Number(orgId));
        } catch { return false; }
    };

    const startScan = useCallback(async (
        orgId: number,
        companyUrl: string,
        sessionCookie?: string,
        areaFocus?: string,
        productFocus?: string,
        model?: string
    ) => {
        // Captura o snapshot dos employees ANTES de qualquer await para evitar
        // condição de corrida onde o store é limpo enquanto o HTTP request aguarda.
        const { useChatStore: chatStoreModule } = await import('@/store/chatStore');
        const snapshotEmployees = chatStoreModule.getState().mappings[orgId]?.rawEmployees || [];

        setScanMap(prev => ({
            ...prev,
            [orgId]: {
                ...EMPTY_STATE,
                isScanning: true,
                consoleLogs: ['[System] Inicializando HierarchyScan...', '[System] Enfileirando job de varredura...'],
            }
        }));
        window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));

        try {
            const { job_id } = await hierarchyApi.startLinkedinScrape({
                companyUrl, sessionCookie, headless: true, areaFocus, productFocus, model,
            });
            const chatPrompted = resolveChatPrompted(orgId);
            _writeScanEntry(orgId, { job_id, orgId, companyUrl, startTime: Date.now(), chatPrompted });
            setScanMap(prev => {
                const cur = prev[orgId] ?? EMPTY_STATE;
                return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, '[System] Conectando ao agente...'] } };
            });
            attachWebSocket(orgId, job_id);
            void attachGraphConnection(job_id, orgId, chatPrompted, snapshotEmployees);
        } catch {
            setScanMap(prev => ({
                ...prev,
                [orgId]: {
                    ...EMPTY_STATE,
                    isScanning: false,
                    scanError: 'Não foi possível iniciar a varredura.',
                    consoleLogs: ['[System Error] Falha ao iniciar a varredura.'],
                }
            }));
        }
    }, [attachWebSocket, attachGraphConnection]);

    const reconnectScan = useCallback(async (): Promise<boolean> => {
        const stored = _readAllStored();
        if (Object.keys(stored).length === 0) return false;

        let anyReconnected = false;
        for (const [orgIdStr, entry] of Object.entries(stored)) {
            const orgId = Number(orgIdStr);
            if (!entry.job_id) continue;
            try {
                const status = await jobsApi.getJobStatus(entry.job_id);
                if (status.status !== 'queued' && status.status !== 'in_progress') {
                    _writeScanEntry(orgId, null);
                    setScanMap(prev => {
                        const cur = prev[orgId] ?? EMPTY_STATE;
                        return { ...prev, [orgId]: { ...cur, isScanning: false } };
                    });
                    continue;
                }
            } catch {
                _writeScanEntry(orgId, null);
                setScanMap(prev => {
                    const cur = prev[orgId] ?? EMPTY_STATE;
                    return { ...prev, [orgId]: { ...cur, isScanning: false } };
                });
                continue;
            }
            setScanMap(prev => ({
                ...prev,
                [orgId]: { ...(prev[orgId] ?? EMPTY_STATE), isScanning: true }
            }));
            window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));
            attachWebSocket(orgId, entry.job_id);
            void attachGraphConnection(entry.job_id, orgId, !!entry.chatPrompted);
            anyReconnected = true;
        }
        return anyReconnected;
    }, [attachWebSocket, attachGraphConnection]);

    const stopScan = useCallback(async (orgId: number) => {
        setScanMap(prev => {
            const cur = prev[orgId] ?? EMPTY_STATE;
            return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, '[System] Solicitando parada graciosa e extração dos dados coletados até o momento...'] } };
        });
        const jobId = refsMap.current[orgId]?.jobId;
        try {
            if (!jobId) throw new Error('Nenhum job ativo');
            await hierarchyApi.stopLinkedinScrape(jobId);
        } catch {
            setScanMap(prev => {
                const cur = prev[orgId] ?? EMPTY_STATE;
                return { ...prev, [orgId]: { ...cur, isScanning: false, consoleLogs: [...cur.consoleLogs, '[System Error] Falha ao enviar comando de parada. Fechando conexão de forma forçada.'] } };
            });
            const refs = refsMap.current[orgId];
            if (refs?.ws) { refs.ws.close(); refs.ws = null; }
        }

        const { useChatStore } = await import('@/store/chatStore');
        const store = useChatStore.getState();
        const currentNodes = store.mappings[orgId]?.rawEmployees || [];
        const keepers = currentNodes.filter((emp: any) => {
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
        store.setRawEmployees(orgId, keepers);
        store.setRawBackendEdges(orgId, []);
        _writeScanEntry(orgId, null);
        window.dispatchEvent(new CustomEvent('hierarchy_scan_cancelled', { detail: { orgId } }));
    }, []);

    const handleImageClick = useCallback(async (orgId: number, e: React.MouseEvent<HTMLImageElement>) => {
        const refs = refsMap.current[orgId];
        if (!refs?.jobId) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = (e.clientY - rect.top) / rect.height;
        setScanMap(prev => {
            const cur = prev[orgId] ?? EMPTY_STATE;
            return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, `[Operator] Clique em (${Math.round(x * 100)}%, ${Math.round(y * 100)}%)`] } };
        });
        try {
            await hierarchyApi.interactLinkedinScrape(refs.jobId, 'click', { x, y });
        } catch {
            setScanMap(prev => {
                const cur = prev[orgId] ?? EMPTY_STATE;
                return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, '[System Error] Falha ao enviar clique'] } };
            });
        }
    }, []);

    const sendText = useCallback(async (orgId: number, text: string) => {
        const refs = refsMap.current[orgId];
        if (!text || !refs?.jobId) return;
        setScanMap(prev => {
            const cur = prev[orgId] ?? EMPTY_STATE;
            return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, `[Operator] Digitando: ${text}`] } };
        });
        try {
            await hierarchyApi.interactLinkedinScrape(refs.jobId, 'type', { text });
        } catch {
            setScanMap(prev => {
                const cur = prev[orgId] ?? EMPTY_STATE;
                return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, '[System Error] Falha ao enviar texto'] } };
            });
        }
    }, []);

    const pressEnter = useCallback(async (orgId: number) => {
        const refs = refsMap.current[orgId];
        if (!refs?.jobId) return;
        setScanMap(prev => {
            const cur = prev[orgId] ?? EMPTY_STATE;
            return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, '[Operator] Pressionando Enter'] } };
        });
        try { await hierarchyApi.interactLinkedinScrape(refs.jobId, 'press', { key: 'Enter' }); } catch { /* ignore */ }
    }, []);

    const pressBackspace = useCallback(async (orgId: number) => {
        const refs = refsMap.current[orgId];
        if (!refs?.jobId) return;
        setScanMap(prev => {
            const cur = prev[orgId] ?? EMPTY_STATE;
            return { ...prev, [orgId]: { ...cur, consoleLogs: [...cur.consoleLogs, '[Operator] Pressionando Backspace'] } };
        });
        try { await hierarchyApi.interactLinkedinScrape(refs.jobId, 'press', { key: 'Backspace' }); } catch { /* ignore */ }
    }, []);

    const resetScan = useCallback((orgId: number) => {
        const refs = refsMap.current[orgId];
        if (refs?.ws) refs.ws.close();
        refsMap.current[orgId] = { ws: null, jobId: null };
        setScanMap(prev => {
            const next = { ...prev };
            delete next[orgId];
            return next;
        });
    }, []);

    useEffect(() => {
        return () => {
            for (const refs of Object.values(refsMap.current)) {
                if (refs.ws) refs.ws.close();
            }
        };
    }, []);

    const isAnyScanning = Object.values(scanMap).some(s => s.isScanning);

    const activeScanOrgIds: number[] = Object.entries(scanMap)
        .filter(([, s]) => s.isScanning)
        .map(([id]) => Number(id));

    const activeScanOrgId: number | null = activeScanOrgIds[0] ?? null;

    return {
        getScanState,
        startScan,
        stopScan,
        reconnectScan,
        handleImageClick,
        sendText,
        pressEnter,
        pressBackspace,
        resetScan,
        isAnyScanning,
        activeScanOrgId,
        activeScanOrgIds,
    };
}
