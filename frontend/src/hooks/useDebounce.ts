import { useEffect, useState } from 'react';

/**
 * useDebounce — devolve o valor X apenas depois que ele ficar estável por `delayMs`.
 * Uso típico: debouncing de input de busca antes de disparar request.
 */
export function useDebounce<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}

/**
 * useDebouncedCallback — wrapper que coalesce múltiplas chamadas em uma única
 * após `delayMs` de silêncio.
 */
export function useDebouncedCallback<Args extends unknown[]>(
  fn: (...args: Args) => void,
  delayMs = 300,
) {
  const [timer, setTimer] = useState<number | null>(null);
  return (...args: Args) => {
    if (timer) window.clearTimeout(timer);
    const id = window.setTimeout(() => fn(...args), delayMs);
    setTimer(id);
  };
}
