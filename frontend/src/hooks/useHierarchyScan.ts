'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { API_V1_URL, apiPost } from '@/services/config';

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

    const eventSourceRef = useRef<EventSource | null>(null);

    const previewUrl = `${API_V1_URL}/hierarchy/linkedin-scrape/preview?t=${previewTimestamp}`;

    const appendLog = useCallback((message: string) => {
        setConsoleLogs((prev) => [...prev, message]);
    }, []);

    const startScan = useCallback((
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
            '[System] Conectando ao agente SSE...',
        ]);

        let sseUrl = `${API_V1_URL}/hierarchy/linkedin-scrape/stream?company_url=${encodeURIComponent(companyUrl)}&headless=true`;
        if (sessionCookie) {
            sseUrl += `&session_cookie=${encodeURIComponent(sessionCookie)}`;
        }
        if (areaFocus) {
            sseUrl += `&area_focus=${encodeURIComponent(areaFocus)}`;
        }
        if (productFocus) {
            sseUrl += `&product_focus=${encodeURIComponent(productFocus)}`;
        }
        if (model) {
            sseUrl += `&model=${encodeURIComponent(model)}`;
        }

        const eventSource = new EventSource(sseUrl);

        eventSource.onmessage = (event) => {
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
                        eventSource.close();
                        setIsScanning(false);
                        break;
                    }
                    case 'error': {
                        setScanError(data.message);
                        appendLog(`[Error] ${data.message}`);
                        eventSource.close();
                        setIsScanning(false);
                        break;
                    }
                }
            } catch {
                appendLog(`[System] Mensagem não processada: ${event.data}`);
            }
        };

        eventSource.onerror = () => {
            setScanError('Erro na conexão SSE...');
            appendLog('[Error] Erro na conexão SSE...');
            eventSource.close();
            setIsScanning(false);
        };

        eventSourceRef.current = eventSource;
    }, [appendLog]);

    const stopScan = useCallback(async () => {
        appendLog('[System] Solicitando parada graciosa e extração dos dados coletados até o momento...');
        try {
            await apiPost(`${API_V1_URL}/hierarchy/linkedin-scrape/stop`, {});
        } catch {
            appendLog('[System Error] Falha ao enviar comando de parada. Fechando conexão de forma forçada.');
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }
            setIsScanning(false);
        }
    }, [appendLog]);

    const handleImageClick = useCallback(
        async (e: React.MouseEvent<HTMLImageElement>) => {
            if (!isScanning) return;

            const rect = e.currentTarget.getBoundingClientRect();
            // Calcula frações decimais (0 a 1) para total independência de resolução e proporção visual!
            const x = (e.clientX - rect.left) / rect.width;
            const y = (e.clientY - rect.top) / rect.height;

            appendLog(`[Operator] Clique em (${Math.round(x * 100)}%, ${Math.round(y * 100)}%)`);

            try {
                await apiPost(
                    `${API_V1_URL}/hierarchy/linkedin-scrape/interact?action=click&x=${x}&y=${y}`,
                    {}
                );
            } catch {
                appendLog('[System Error] Falha ao enviar clique');
            }
        },
        [isScanning, appendLog]
    );

    const sendText = useCallback(
        async (text: string) => {
            if (!text) return;

            appendLog(`[Operator] Digitando: ${text}`);

            try {
                await apiPost(
                    `${API_V1_URL}/hierarchy/linkedin-scrape/interact?action=type&text=${encodeURIComponent(text)}`,
                    {}
                );
            } catch {
                appendLog('[System Error] Falha ao enviar texto');
            }
        },
        [appendLog]
    );

    const pressEnter = useCallback(async () => {
        appendLog('[Operator] Pressionando Enter');

        try {
            await apiPost(
                `${API_V1_URL}/hierarchy/linkedin-scrape/interact?action=press&key=Enter`,
                {}
            );
        } catch {
            appendLog('[System Error] Falha ao enviar tecla Enter');
        }
    }, [appendLog]);

    const pressBackspace = useCallback(async () => {
        appendLog('[Operator] Pressionando Backspace');

        try {
            await apiPost(
                `${API_V1_URL}/hierarchy/linkedin-scrape/interact?action=press&key=Backspace`,
                {}
            );
        } catch {
            appendLog('[System Error] Falha ao enviar tecla Backspace');
        }
    }, [appendLog]);

    const resetScan = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
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
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
        };
    }, []);

    return {
        startScan,
        stopScan,
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
