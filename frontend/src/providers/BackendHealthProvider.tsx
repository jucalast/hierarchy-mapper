import React, { useEffect, useState } from 'react';
import { waitForBackend, API_BASE_URL } from '@/services/config';

interface BackendHealthProviderProps {
  children: React.ReactNode;
  timeout?: number;
}

/**
 * Provider que aguarda o backend estar pronto antes de renderizar o app
 * Mostra uma tela de carregamento enquanto aguarda
 */
export default function BackendHealthProvider({ 
  children, 
  timeout = 10000 
}: BackendHealthProviderProps) {
  const [isBackendReady, setIsBackendReady] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function checkBackend() {
      try {
        console.log('🔍 Verificando se backend está pronto...');
        const isReady = await waitForBackend(timeout);
        
        if (isMounted) {
          if (isReady) {
            setIsBackendReady(true);
            setError(null);
          } else {
            setError('Backend não respondeu. Verifique se o servidor está rodando.');
          }
          setIsLoading(false);
        }
      } catch (err: any) {
        if (isMounted) {
          setError(err.message || 'Erro ao conectar com o backend');
          setIsLoading(false);
        }
      }
    }

    checkBackend();

    return () => {
      isMounted = false;
    };
  }, [timeout]);

  if (isLoading) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.spinner}></div>
          <h2 style={styles.title}>Conectando ao servidor...</h2>
          <p style={styles.subtitle}>Aguarde um momento</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.errorIcon}>⚠️</div>
          <h2 style={styles.title}>Erro de Conexão</h2>
          <p style={styles.error}>{error}</p>
          <p style={styles.subtitle}>
            Verifique se o backend está rodando em {API_BASE_URL}
          </p>
          <button
            onClick={() => window.location.reload()}
            style={styles.button}
          >
            Tentar Novamente
          </button>
        </div>
      </div>
    );
  }

  if (!isBackendReady) {
    return (
      <div style={styles.container}>
        <div style={styles.card}>
          <div style={styles.errorIcon}>✓</div>
          <h2 style={styles.title}>Carregando...</h2>
          <p style={styles.subtitle}>Backend conectado</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

const styles = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    background: 'var(--sw-sidebar)',
    fontFamily: 'var(--font-primary)',
  } as React.CSSProperties,
  
  card: {
    background: 'transparent',
    padding: '40px',
    textAlign: 'center' as const,
    minWidth: '300px',
  },
  
  spinner: {
    width: '40px',
    height: '40px',
    margin: '0 auto 24px',
    border: '2px solid var(--sw-border)',
    borderTop: '2px solid var(--sw-primary)',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  } as React.CSSProperties,
  
  errorIcon: {
    fontSize: '48px',
    marginBottom: '20px',
  },
  
  title: {
    margin: '0 0 10px',
    fontSize: 'var(--font-lg)',
    fontWeight: 600,
    color: 'var(--sw-text-base)',
  },
  
  subtitle: {
    margin: '0',
    color: 'var(--sw-text-muted)',
    fontSize: 'var(--font-sm)',
  },
  
  error: {
    margin: '10px 0',
    color: 'var(--sw-status-danger)',
    fontSize: 'var(--font-sm)',
  },
  
  button: {
    marginTop: '24px',
    padding: '12px 24px',
    background: 'var(--sw-primary)',
    color: 'white',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    fontSize: 'var(--font-sm)',
    fontWeight: '600',
    transition: 'var(--transition-fast)',
  } as React.CSSProperties,
};

// Adiciona animação CSS para o spinner
if (typeof document !== 'undefined' && !document.getElementById('backend-spinner-style')) {
  const style = document.createElement('style');
  style.id = 'backend-spinner-style';
  style.textContent = `
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
  `;
  document.head.appendChild(style);
}
