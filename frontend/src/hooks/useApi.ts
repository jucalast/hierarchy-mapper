/**
 * useApi — hook genérico para chamadas HTTP via api client.
 * Estados: { data, error, loading, refetch, reset }.
 *
 * Cancelamento automático ao desmontar + AbortController.
 * Deduplicação leve via chave opcional (útil para evitar race).
 *
 * Para chamadas imperativas (on-click), use `useMutation`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError, type RequestOptions } from '@/services/api/client';

interface UseApiOptions<T> extends RequestOptions {
  /** Executar no mount? Default true quando `endpoint` estiver definido. */
  enabled?: boolean;
  /** Se presente, troca data em vez de perder valor anterior durante refetch */
  keepPrevious?: boolean;
  /** Transform antes de guardar em state */
  select?: (raw: unknown) => T;
  /** Callback on-success */
  onSuccess?: (data: T) => void;
  /** Callback on-error */
  onError?: (error: ApiError | Error) => void;
}

interface UseApiResult<T> {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
  refetch: () => Promise<T | null>;
  reset: () => void;
}

/**
 * Hook GET-ish. Troque `endpoint` (string) para disparar refetch automático.
 */
export function useApi<T = unknown>(
  endpoint: string | null | undefined,
  options: UseApiOptions<T> = {},
): UseApiResult<T> {
  const { enabled = true, keepPrevious = false, select, onSuccess, onError, ...requestOpts } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastRequestId = useRef(0);

  const execute = useCallback(async (): Promise<T | null> => {
    if (!endpoint) return null;
    const reqId = ++lastRequestId.current;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    if (!keepPrevious) setData(null);

    try {
      const raw = await api.get<unknown>(endpoint, { ...requestOpts, signal: ctrl.signal });
      if (reqId !== lastRequestId.current) return null; // stale
      const next = (select ? select(raw) : (raw as T));
      setData(next);
      onSuccess?.(next);
      return next;
    } catch (e) {
      if ((e as any)?.name === 'AbortError') return null;
      const err = e as ApiError | Error;
      if (reqId === lastRequestId.current) {
        setError(err);
        onError?.(err);
      }
      return null;
    } finally {
      if (reqId === lastRequestId.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint]);

  useEffect(() => {
    if (!enabled || !endpoint) return;
    void execute();
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, enabled]);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
    abortRef.current?.abort();
  }, []);

  return { data, error, loading, refetch: execute, reset };
}

/**
 * useMutation — imperativo. Ideal para ações (POST/PUT/DELETE).
 *
 * Exemplo:
 *   const { mutate, loading } = useMutation((body) => api.post('/foo', body));
 *   <Button onClick={() => mutate({ x: 1 })}>
 */
export function useMutation<Args, R>(
  fn: (args: Args, signal?: AbortSignal) => Promise<R>,
  options: {
    onSuccess?: (data: R, args: Args) => void;
    onError?: (error: ApiError | Error, args: Args) => void;
  } = {},
) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<R | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const mutate = useCallback(async (args: Args): Promise<R | null> => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const r = await fn(args, ctrl.signal);
      setData(r);
      options.onSuccess?.(r, args);
      return r;
    } catch (e) {
      if ((e as any)?.name === 'AbortError') return null;
      const err = e as ApiError | Error;
      setError(err);
      options.onError?.(err, args);
      return null;
    } finally {
      setLoading(false);
    }
  }, [fn, options]);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
    abortRef.current?.abort();
  }, []);

  return { mutate, data, error, loading, reset };
}
