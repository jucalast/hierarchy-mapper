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
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  } as React.CSSProperties,
  
  card: {
    background: 'white',
    borderRadius: '12px',
    padding: '40px',
    textAlign: 'center' as const,
    boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
    minWidth: '300px',
  },
  
  spinner: {
    width: '50px',
    height: '50px',
    margin: '0 auto 20px',
    border: 'var(--sw-border-width) solid var(--sw-border)',
    borderTop: '4px solid #667eea',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  } as React.CSSProperties,
  
  errorIcon: {
    fontSize: '48px',
    marginBottom: '20px',
  },
  
  title: {
    margin: '0 0 10px',
    fontSize: '24px',
    color: '#333',
  },
  
  subtitle: {
    margin: '0',
    color: '#666',
    fontSize: '14px',
  },
  
  error: {
    margin: '10px 0',
    color: '#dc3545',
    fontSize: '14px',
  },
  
  button: {
    marginTop: '20px',
    padding: '10px 20px',
    background: '#667eea',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '14px',
    fontWeight: '600',
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
