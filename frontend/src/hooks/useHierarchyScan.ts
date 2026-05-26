'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { API_V1_URL, apiPost } from '@/services/config';

export interface ScanEmployeeProfile {
    name: string;
    role: string;
    linkedin_url: string;
    avatar: string;
    location?: string;
}

interface UseHierarchyScanReturn {
    startScan: (companyUrl: string, sessionCookie?: string) => void;
    stopScan: () => void;
    isScanning: boolean;
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

    const startScan = useCallback((companyUrl: string, sessionCookie?: string) => {
        setIsScanning(true);
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
                    case 'result': {
                        setScanResults(data.data);
                        setScanProgress(100);
                        appendLog('[System] Varredura concluída com sucesso!');
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

    const stopScan = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
        setIsScanning(false);
        appendLog('[System] Varredura interrompida pelo usuário.');
    }, [appendLog]);

    const handleImageClick = useCallback(
        async (e: React.MouseEvent<HTMLImageElement>) => {
            if (!isScanning) return;

            const rect = e.currentTarget.getBoundingClientRect();
            const x = Math.round(((e.clientX - rect.left) / rect.width) * 1280);
            const y = Math.round(((e.clientY - rect.top) / rect.height) * 800);

            appendLog(`[Operator] Clique em (${x}, ${y})`);

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
