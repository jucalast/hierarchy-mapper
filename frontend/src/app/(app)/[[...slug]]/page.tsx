"use client";

import React from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { useBackendReady } from '@/hooks/useBackendReady';

const NetworkGraph = dynamic(() => import('@/components/network-graph/NetworkGraph'), { ssr: false });

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

  return <>{children}</>;
}

export default function DashboardPage() {
  const router = useRouter();
  
  const handleLogout = () => {
    ['token','user_id','user_name','user_email','user_role','tenant_id','tenant_name']
      .forEach((k) => localStorage.removeItem(k));
    
    // Remove token from cookie
    document.cookie = "token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    router.push('/login');
  };

  return (
    <main style={{ height: '100%', width: '100%' }}>
      <BackendGate>
        <NetworkGraph onLogout={handleLogout} />
      </BackendGate>
    </main>
  );
}
