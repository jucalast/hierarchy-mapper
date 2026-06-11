/**
 * useLocalStorage — estado persistido em localStorage com SSR-safety.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export function useLocalStorage<T>(key: string, initial: T) {
  const initialRef = useRef(initial);
  const [value, setValue] = useState<T>(initial);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    setIsHydrated(true);
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null && raw !== 'undefined' && raw !== 'NaN') {
        setValue(JSON.parse(raw) as T);
      }
    } catch {
      /* ignore */
    }
  }, [key]);

  useEffect(() => {
    if (!isHydrated) return;
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* quota, serialização, etc */
    }
  }, [key, value, isHydrated]);

  const remove = useCallback(() => {
    try {
      window.localStorage.removeItem(key);
    } catch { /* no-op */ }
    setValue(initialRef.current);
  }, [key]);

  return [value, setValue, remove] as const;
}
