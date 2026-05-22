'use client';

import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '@/services/config';

export type ReadyState = 'checking' | 'ready' | 'timeout';

const POLL_INTERVAL_MS = 1000;
const MAX_WAIT_MS = 60_000; // desiste após 60s — servidor provavelmente travado

/**
 * Aguarda o backend sinalizar readiness via GET /ready (HTTP 200).
 * Enquanto o backend retorna 503 ("starting"), mantém state = 'checking'.
 * Ideal para usar como gate antes de renderizar a aplicação principal.
 */
export function useBackendReady(): { state: ReadyState; elapsed: number } {
    const [state, setState] = useState<ReadyState>('checking');
    const [elapsed, setElapsed] = useState(0);
    const startRef = useRef(Date.now());
    const cancelRef = useRef(false);

    useEffect(() => {
        cancelRef.current = false;
        startRef.current = Date.now();

        const tick = async () => {
            while (!cancelRef.current) {
                const now = Date.now();
                const elapsedMs = now - startRef.current;
                setElapsed(Math.floor(elapsedMs / 1000));

                if (elapsedMs > MAX_WAIT_MS) {
                    setState('timeout');
                    return;
                }

                try {
                    const res = await fetch(`${API_BASE_URL}/ready`, {
                        signal: AbortSignal.timeout(3000),
                        cache: 'no-store',
                    });
                    if (res.ok) {
                        setState('ready');
                        return;
                    }
                    // 503 = ainda inicializando, continua polling
                } catch {
                    // rede indisponível, continua tentando
                }

                await new Promise<void>((resolve) => {
                    const t = setTimeout(resolve, POLL_INTERVAL_MS);
                    // Permite cancelamento imediato no unmount
                    if (cancelRef.current) {
                        clearTimeout(t);
                        resolve();
                    }
                });
            }
        };

        void tick();
        return () => { cancelRef.current = true; };
    }, []);

    return { state, elapsed };
}
