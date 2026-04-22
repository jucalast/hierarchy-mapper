/**
 * useNotifications — estado + helpers padronizados para o sistema de toasts
 * baseado em <NotificationContainer/>.
 *
 * Retorna:
 *  - notifications: lista atual
 *  - push(type, msg): enfileira
 *  - remove(id)
 *  - clear(): limpa tudo
 *  - helpers: success(msg), error(msg), info(msg), warning(msg)
 */
import { useCallback, useState } from 'react';
import type { NotificationType } from '@/components/Notification';

export interface NotificationEntry {
  id: string;
  type: NotificationType;
  message: string;
}

function genId(): string {
  return Math.random().toString(36).slice(2, 9);
}

export function useNotifications() {
  const [notifications, setNotifications] = useState<NotificationEntry[]>([]);

  const push = useCallback((type: NotificationType, message: string) => {
    const id = genId();
    setNotifications((prev) => [...prev, { id, type, message }]);
    return id;
  }, []);

  const remove = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const clear = useCallback(() => setNotifications([]), []);

  const success = useCallback((msg: string) => push('success', msg), [push]);
  const error = useCallback((msg: string) => push('error', msg), [push]);
  const info = useCallback((msg: string) => push('info', msg), [push]);
  const warning = useCallback((msg: string) => push('warning', msg), [push]);

  return { notifications, push, remove, clear, success, error, info, warning };
}
