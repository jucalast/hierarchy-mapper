"use client";

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import LoginView from '@/components/layout/LoginView';
import { useBackendReady } from '@/hooks/useBackendReady';

const NetworkGraph = dynamic(() => import('@/components/network-graph/NetworkGraph'), { ssr: false });

import { NotificationProvider } from '@/contexts/NotificationContext';

function BackendGate({ children }: { children: React.ReactNode }) {
  const { state, elapsed } = useBackendReady();

  if (state === 'checking') {
    return (
      <div style={{
        height: '100vh', width: '100vw', background: '#05060b',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
        alignItems: 'center', gap: '8px',
        color: 'rgba(255,255,255,0.3)', fontFamily: 'Inter, sans-serif', fontSize: '12px',
        letterSpacing: '0.08em',
      }}>
        <span>CONECTANDO AO SERVIDOR{elapsed > 2 ? ` (${elapsed}s)` : '...'}</span>
      </div>
    );
  }

  if (state === 'timeout') {
    return (
      <div style={{
        height: '100vh', width: '100vw', background: '#05060b',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
        alignItems: 'center', gap: '12px',
        color: 'rgba(255,100,100,0.7)', fontFamily: 'Inter, sans-serif', fontSize: '12px',
        letterSpacing: '0.08em',
      }}>
        <span>SERVIDOR INDISPONÍVEL</span>
        <button
          onClick={() => window.location.reload()}
          style={{
            background: 'transparent', border: '1px solid rgba(255,100,100,0.4)',
            color: 'rgba(255,100,100,0.7)', padding: '6px 16px', cursor: 'pointer',
            fontSize: '11px', letterSpacing: '0.08em', borderRadius: '4px',
          }}
        >
          TENTAR NOVAMENTE
        </button>
      </div>
    );
  }

  return children as React.ReactElement;
}

export default function Home() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    setIsAuthenticated(!!token);
  }, []);

  if (isAuthenticated === null) {
    return (
      <div style={{
        height: '100vh', width: '100vw', background: '#05060b',
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        color: 'rgba(255,255,255,0.3)', fontFamily: 'Inter, sans-serif', fontSize: '12px',
      }}>
        Carregando...
      </div>
    );
  }

  return (
    <NotificationProvider>
      <main>
        {isAuthenticated ? (
          <BackendGate>
            <NetworkGraph onLogout={() => {
              ['token','user_id','user_name','user_email','user_role','tenant_id','tenant_name']
                .forEach((k) => localStorage.removeItem(k));
              setIsAuthenticated(false);
            }} />
          </BackendGate>
        ) : (
          <LoginView onLoginSuccess={() => setIsAuthenticated(true)} />
        )}
      </main>
    </NotificationProvider>
  );
}
