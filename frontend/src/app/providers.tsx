"use client";

import { NotificationProvider } from '@/contexts/NotificationContext';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <NotificationProvider>
      {children}
    </NotificationProvider>
  );
}
