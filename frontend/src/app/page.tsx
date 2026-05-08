"use client";

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import LoginView from '@/components/LoginView';

// Carrega dinamicamente o NetworkGraph no lado do cliente para evitar problemas de SSR (ReactFlow dependente)
const NetworkGraph = dynamic(() => import('@/components/NetworkGraph'), { ssr: false });

export default function Home() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    // Verifica se o token de login está persistido no localStorage
    const token = localStorage.getItem('token');
    setIsAuthenticated(!!token);
  }, []);

  const handleLogout = () => {
    // Limpa os tokens e as informações associadas do SaaS
    localStorage.removeItem('token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_email');
    localStorage.removeItem('user_role');
    localStorage.removeItem('tenant_id');
    localStorage.removeItem('tenant_name');
    setIsAuthenticated(false);
  };

  // Carregando inicial leve
  if (isAuthenticated === null) {
    return (
      <div style={{
        height: '100vh',
        width: '100vw',
        background: '#05060b',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        color: 'rgba(255,255,255,0.4)',
        fontFamily: 'Inter, sans-serif',
        fontSize: '13px',
        letterSpacing: '0.5px'
      }}>
        Carregando Sessão...
      </div>
    );
  }

  return (
    <main>
      {isAuthenticated ? (
        <NetworkGraph onLogout={handleLogout} />
      ) : (
        <LoginView onLoginSuccess={() => setIsAuthenticated(true)} />
      )}
    </main>
  );
}
