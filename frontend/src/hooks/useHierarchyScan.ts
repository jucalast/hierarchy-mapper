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

export interface UseHierarchyScanReturn {
    startScan: (
        orgId: number,
        companyUrl: string,
        sessionCookie?: string,
        areaFocus?: string,
        productFocus?: string,
        model?: string
    ) => void;
    stopScan: () => void;
    reconnectScan: () => Promise<boolean>;
    isScanning: boolean;
    scanOrgId: number | null;
    scanError: string | null;
    scanProgress: number;
    consoleLogs: string[];
    hasPreview: boolean;
    previewTimestamp: number;
    previewUrl: string;
    handleImageClick: (e: React.MouseEvent<HTMLImageElement>) => void;
    sendText: (text: string) => void;
    pressEnter: () => void;
    pressBackspace: () => void;
    scanResults: ScanEmployeeProfile[];
    resetScan: () => void;
}

export function useHierarchyScan(): UseHierarchyScanReturn {
    const [isScanning, setIsScanning] = useState(false);
    const [scanOrgId, setScanOrgId] = useState<number | null>(null);
    const [scanError, setScanError] = useState<string | null>(null);
    const [scanProgress, setScanProgress] = useState(0);
    const [consoleLogs, setConsoleLogs] = useState<string[]>([]);
    const [hasPreview, setHasPreview] = useState(false);
    const [previewTimestamp, setPreviewTimestamp] = useState(Date.now());
    const [scanResults, setScanResults] = useState<ScanEmployeeProfile[]>([]);

    const wsRef = useRef<WebSocket | null>(null);
    const jobIdRef = useRef<string | null>(null);

    const previewUrl = `${API_V1_URL}/hierarchy/linkedin-scrape/preview?t=${previewTimestamp}`;

    const appendLog = useCallback((message: string) => {
        setConsoleLogs((prev) => [...prev, message]);
    }, []);

    // Mesma heurística usada pelo discovery (useHierarchy.ts) para saber se o chat
    // agent está esperando o resultado deste mapeamento (continuação de conversa).
    const resolveChatPrompted = (orgId: number): boolean => {
        const pending = localStorage.getItem('pending-hierarchy-continuation');
        if (!pending) return false;
        try {
            const parsed = JSON.parse(pending);
            return !!(parsed && Number(parsed.org_id) === Number(orgId));
        } catch {
            return false;
        }
    };

    // 🌐 Conecta o grafo (Zustand rawEmployees/rawBackendEdges) ao mesmo pipeline
    // robusto do discovery: merge/dedup, reconciliação de IDs provisórios e
    // refinamento único pós-conclusão (evita a duplicação de refino que existia
    // quando scan e discovery tinham lógicas de merge separadas).
    const attachGraphConnection = useCallback(async (jobId: string, orgId: number, chatPrompted: boolean) => {
        const { useChatStore } = await import('@/store/chatStore');
        const existingEmployees = useChatStore.getState().mappings[orgId]?.rawEmployees || [];
        connectionManager.connectToJob({
            jobId,
            orgId,
            brand: '',
            logo: '',
            domain: '',
            partners: [],
            chatPrompted,
        }, existingEmployees);
    }, []);

    // O scraping roda como background job no worker ARQ — independente da conexão
    // WS. Um reload de página só reabre o WS (via reconnectScan); não mata o scan.
    const attachWebSocket = useCallback((jobId: string) => {
        jobIdRef.current = jobId;

        const ws = new WebSocket(jobsApi.getJobWebSocketUrl(jobId));

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                switch (data.type) {
                    case 'log': {
                        appendLog(data.message);
                        const progressMatch = data.message.match(/Colaboradores na página:\s*(\d+)/);
                        if (progressMatch) {
                            const parsed = parseInt(progressMatch[1], 10);
                            setScanProgress(Math.min(parsed * 1.5, 98));
                        }
                        break;
                    }
                    case 'screenshot': {
                        setPreviewTimestamp(Date.now());
                        setHasPreview(true);
                        break;
                    }
                    case 'cookie': {
                        localStorage.setItem('linkedin_li_at_cookie', data.cookie);
                        appendLog('[System] Cookie de sessão li_at capturado e salvo localmente para futuras varreduras!');
                        break;
                    }
                    case 'clear_nodes': {
                        console.log("[Scan] 🧹 Comando de limpeza recebido do backend.");
                        setScanResults([]);
                        setScanProgress(0);
                        break;
                    }
                    case 'batch': {
                        if (data.nodes && data.nodes.length > 0) {
                            setScanResults((prev) => {
                                // Evita duplicatas pelo linkedin_url
                                const newProfiles = data.nodes.map((n: any) => ({
                                    id: n.id,
                                    name: n.name,
                                    role: n.role,
                                    linkedin_url: n.linkedin || n.url,
                                    avatar: n.avatar,
                                    location: n.location,
                                    observations: n.observations,
                                    evidence: n.evidence,
                                    email: n.email
                                }));

                                const filtered = newProfiles.filter((newP: any) =>
                                    !prev.some(oldP => oldP.linkedin_url === newP.linkedin_url)
                                );

                                return [...prev, ...filtered];
                            });
                        }
                        break;
                    }
                    case 'result': {
                        // O 'result' agora é opcional se usarmos 'batch', mas mantemos por retrocompatibilidade
                        if (data.data && data.data.length > 0) {
                            setScanResults(data.data);
                        }
                        setScanProgress(100);
                        break;
                    }
                    case 'done': {
                        appendLog('[System] Varredura e processamento concluídos com sucesso!');
                        setScanProgress(100);
                        ws.close();
                        setIsScanning(false);
                        localStorage.removeItem('active-linkedin-scan');
                        break;
                    }
                    case 'error': {
                        setScanError(data.message);
                        appendLog(`[Error] ${data.message}`);
                        ws.close();
                        setIsScanning(false);
                        localStorage.removeItem('active-linkedin-scan');
                        break;
                    }
                }
            } catch {
                appendLog(`[System] Mensagem não processada: ${event.data}`);
            }
        };

        ws.onerror = () => {
            // Falha de conexão (não confundir com o job em si): o scan continua
            // rodando no worker — não removemos o job_id, só paramos de escutar
            // localmente. Uma reconexão futura (reconnectScan) pode retomar.
            appendLog('[Error] Conexão com o agente perdida. O scan continua em segundo plano no servidor.');
            setIsScanning(false);
        };

        wsRef.current = ws;
    }, [appendLog]);

    const startScan = useCallback(async (
        orgId: number,
        companyUrl: string,
        sessionCookie?: string,
        areaFocus?: string,
        productFocus?: string,
        model?: string
    ) => {
        setIsScanning(true);
        setScanOrgId(orgId);
        // ✅ Notifica o chat panel que uma varredura iniciou (independente do modo)
        window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));
        setScanError(null);
        setScanResults([]);
        setScanProgress(0);
        setConsoleLogs([
            '[System] Inicializando HierarchyScan...',
            '[System] Enfileirando job de varredura...',
        ]);

        try {
            const { job_id } = await hierarchyApi.startLinkedinScrape({
                companyUrl,
                sessionCookie,
                headless: true,
                areaFocus,
                productFocus,
                model,
            });

            const chatPrompted = resolveChatPrompted(orgId);

            // 💾 Persiste o job_id no localStorage para sobreviver a reload de página
            localStorage.setItem('active-linkedin-scan', JSON.stringify({
                job_id,
                orgId,
                companyUrl,
                startTime: Date.now(),
                chatPrompted,
            }));

            appendLog('[System] Conectando ao agente...');
            attachWebSocket(job_id);
            void attachGraphConnection(job_id, orgId, chatPrompted);
        } catch {
            appendLog('[System Error] Falha ao iniciar a varredura.');
            setScanError('Não foi possível iniciar a varredura.');
            setIsScanning(false);
        }
    }, [appendLog, attachWebSocket, attachGraphConnection]);

    const reconnectScan = useCallback(async (): Promise<boolean> => {
        const raw = localStorage.getItem('active-linkedin-scan');
        if (!raw || raw === 'NaN' || raw === 'undefined') return false;

        let scanData: { job_id?: string; orgId?: number; chatPrompted?: boolean } | null = null;
        try {
            scanData = JSON.parse(raw);
        } catch {
            localStorage.removeItem('active-linkedin-scan');
            return false;
        }

        const jobId = scanData?.job_id;
        if (!jobId) {
            localStorage.removeItem('active-linkedin-scan');
            return false;
        }

        try {
            const status = await jobsApi.getJobStatus(jobId);
            if (status.status !== 'queued' && status.status !== 'in_progress') {
                localStorage.removeItem('active-linkedin-scan');
                return false;
            }
        } catch {
            localStorage.removeItem('active-linkedin-scan');
            return false;
        }

        setIsScanning(true);
        setScanOrgId(scanData?.orgId ?? null);
        setScanError(null);
        setConsoleLogs((prev) => [...prev, '[System] Reconectando à varredura em andamento...']);
        window.dispatchEvent(new CustomEvent('hierarchy_scan_started'));
        attachWebSocket(jobId);
        if (scanData?.orgId) {
            void attachGraphConnection(jobId, scanData.orgId, !!scanData.chatPrompted);
        }
        return true;
    }, [attachWebSocket, attachGraphConnection]);

    const stopScan = useCallback(async () => {
        appendLog('[System] Solicitando parada graciosa e extração dos dados coletados até o momento...');
        const jobId = jobIdRef.current;
        try {
            if (!jobId) throw new Error('Nenhum job ativo');
            await hierarchyApi.stopLinkedinScrape(jobId);
        } catch {
            appendLog('[System Error] Falha ao enviar comando de parada. Fechando conexão de forma forçada.');
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
            setIsScanning(false);
        }

        // 🧹 Limpa nós incompletos do Zustand — mantém apenas root + sócios
        const orgId = scanOrgId;
        if (orgId) {
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

            // Remove metadados do scan do localStorage
            localStorage.removeItem('active-linkedin-scan');

            // 🔔 Notifica o Drawer para remover o badge
            window.dispatchEvent(new CustomEvent('hierarchy_scan_cancelled', { detail: { orgId } }));
        }
    }, [appendLog, scanOrgId]);

    const handleImageClick = useCallback(
        async (e: React.MouseEvent<HTMLImageElement>) => {
            if (!isScanning || !jobIdRef.current) return;

            const rect = e.currentTarget.getBoundingClientRect();
            // Calcula frações decimais (0 a 1) para total independência de resolução e proporção visual!
            const x = (e.clientX - rect.left) / rect.width;
            const y = (e.clientY - rect.top) / rect.height;

            appendLog(`[Operator] Clique em (${Math.round(x * 100)}%, ${Math.round(y * 100)}%)`);

            try {
                await hierarchyApi.interactLinkedinScrape(jobIdRef.current, 'click', { x, y });
            } catch {
                appendLog('[System Error] Falha ao enviar clique');
            }
        },
        [isScanning, appendLog]
    );

    const sendText = useCallback(
        async (text: string) => {
            if (!text || !jobIdRef.current) return;

            appendLog(`[Operator] Digitando: ${text}`);

            try {
                await hierarchyApi.interactLinkedinScrape(jobIdRef.current, 'type', { text });
            } catch {
                appendLog('[System Error] Falha ao enviar texto');
            }
        },
        [appendLog]
    );

    const pressEnter = useCallback(async () => {
        if (!jobIdRef.current) return;
        appendLog('[Operator] Pressionando Enter');

        try {
            await hierarchyApi.interactLinkedinScrape(jobIdRef.current, 'press', { key: 'Enter' });
        } catch {
            appendLog('[System Error] Falha ao enviar tecla Enter');
        }
    }, [appendLog]);

    const pressBackspace = useCallback(async () => {
        if (!jobIdRef.current) return;
        appendLog('[Operator] Pressionando Backspace');

        try {
            await hierarchyApi.interactLinkedinScrape(jobIdRef.current, 'press', { key: 'Backspace' });
        } catch {
            appendLog('[System Error] Falha ao enviar tecla Backspace');
        }
    }, [appendLog]);

    const resetScan = useCallback(() => {
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        jobIdRef.current = null;
        setIsScanning(false);
        setScanOrgId(null);
        setScanError(null);
        setScanProgress(0);
        setConsoleLogs([]);
        setHasPreview(false);
        setPreviewTimestamp(Date.now());
        setScanResults([]);
    }, []);

    useEffect(() => {
        return () => {
            // Fecha apenas a escuta local — o job no worker continua rodando.
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, []);

    // 🌐 O refinamento pós-scan e o aviso ao chat agent agora são responsabilidade
    // única do connectionManager (mesmo pipeline do discovery) + do listener
    // centralizado em useHierarchy.ts — evita o refino duplicado/concorrente que
    // existia quando scan e discovery tinham cada um seu próprio gatilho de IA.

    return {
        startScan,
        stopScan,
        reconnectScan,
        isScanning,
        scanOrgId,
        scanError,
        scanProgress,
        consoleLogs,
        hasPreview,
        previewTimestamp,
        previewUrl,
        handleImageClick,
        sendText,
        pressEnter,
        pressBackspace,
        scanResults,
        resetScan,
    };
}
