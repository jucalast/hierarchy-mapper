'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { JobStreamEvent } from '@/types';

export interface UseJobStreamOptions {
  /** Reconectar automaticamente em desconexão (default: true) */
  autoReconnect?: boolean;
  /** Tentativas máximas antes de desistir (default: 5) */
  maxRetries?: number;
  /** Backoff base em ms (default: 800) */
  initialDelayMs?: number;
  /** Backoff máximo (default: 8000) */
  maxDelayMs?: number;
  /** Inclui credenciais na requisição (default: false) */
  withCredentials?: boolean;
}

export interface UseJobStreamApi {
  events: JobStreamEvent[];
  status: 'idle' | 'connecting' | 'open' | 'closed' | 'error';
  error: Error | null;
  start: (
    url: string,
    init?: RequestInit & { body?: BodyInit | null },
  ) => void;
  stop: () => void;
}

/**
 * Consome stream NDJSON (POST→stream) com reconexão exponencial.
 * Substitui usos manuais de fetch+TextDecoder espalhados por componentes.
 *
 * Uso típico:
 *   const { events, status, start, stop } = useJobStream();
 *   start('/api/v1/ai/chat', { method: 'POST', body: JSON.stringify(payload) });
 */
export function useJobStream(opts: UseJobStreamOptions = {}): UseJobStreamApi {
  const {
    autoReconnect = true,
    maxRetries = 5,
    initialDelayMs = 800,
    maxDelayMs = 8000,
  } = opts;

  const [events, setEvents] = useState<JobStreamEvent[]>([]);
  const [status, setStatus] =
    useState<UseJobStreamApi['status']>('idle');
  const [error, setError] = useState<Error | null>(null);

  const controllerRef = useRef<AbortController | null>(null);
  const retryCountRef = useRef(0);
  const lastUrlRef = useRef<string | null>(null);
  const lastInitRef = useRef<RequestInit | undefined>(undefined);
  const stoppedRef = useRef(false);

  const stop = useCallback(() => {
    stoppedRef.current = true;
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
    setStatus('closed');
  }, []);

  const connect = useCallback(
    async (url: string, init?: RequestInit) => {
      // Cancela conexão anterior, se houver
      if (controllerRef.current) controllerRef.current.abort();

      const ctrl = new AbortController();
      controllerRef.current = ctrl;
      stoppedRef.current = false;
      setStatus('connecting');
      setError(null);

      try {
        const response = await fetch(url, {
          method: init?.method || 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(init?.headers || {}),
          },
          body: init?.body,
          signal: ctrl.signal,
        });
        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        setStatus('open');
        retryCountRef.current = 0;

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // NDJSON — uma linha por evento
          let nlIdx;
          while ((nlIdx = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, nlIdx).trim();
            buffer = buffer.slice(nlIdx + 1);
            if (!line) continue;
            try {
              const evt = JSON.parse(line) as JobStreamEvent;
              setEvents((prev) => [...prev, evt]);
            } catch {
              // Linha inválida — ignora
            }
          }
        }
        // flush final
        if (buffer.trim()) {
          try {
            const evt = JSON.parse(buffer.trim()) as JobStreamEvent;
            setEvents((prev) => [...prev, evt]);
          } catch {
            /* ignore */
          }
        }
        setStatus('closed');
      } catch (e: unknown) {
        const err = e instanceof Error ? e : new Error(String(e));
        if (err.name === 'AbortError' || stoppedRef.current) {
          setStatus('closed');
          return;
        }
        setError(err);
        setStatus('error');

        // Reconexão com backoff exponencial
        if (autoReconnect && retryCountRef.current < maxRetries) {
          const delay = Math.min(
            initialDelayMs * Math.pow(2, retryCountRef.current),
            maxDelayMs,
          );
          retryCountRef.current += 1;
          setTimeout(() => {
            if (lastUrlRef.current && !stoppedRef.current) {
              connect(lastUrlRef.current, lastInitRef.current);
            }
          }, delay);
        }
      }
    },
    [autoReconnect, maxRetries, initialDelayMs, maxDelayMs],
  );

  const start = useCallback(
    (url: string, init?: RequestInit) => {
      setEvents([]);
      lastUrlRef.current = url;
      lastInitRef.current = init;
      retryCountRef.current = 0;
      void connect(url, init);
    },
    [connect],
  );

  // Cleanup ao desmontar
  useEffect(
    () => () => {
      stoppedRef.current = true;
      controllerRef.current?.abort();
    },
    [],
  );

  return { events, status, error, start, stop };
}
