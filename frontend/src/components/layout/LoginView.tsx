"use client";

import React, { useState } from 'react';
import { Mail, Lock, LogIn, AlertCircle, Info, Network, User } from 'lucide-react';
import styles from './LoginView.module.css';
import { API_BASE_URL } from '@/services/config';

interface LoginViewProps {
  onLoginSuccess: () => void;
}

export default function LoginView({ onLoginSuccess }: LoginViewProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Por favor, preencha todos os campos.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Falha na autenticação. Verifique suas credenciais.");
      }

      const data = await response.json();
      
      // Salva o Token JWT e dados do Tenant no LocalStorage
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user_id', data.user_id);
      localStorage.setItem('user_name', data.user_name);
      localStorage.setItem('user_email', data.user_email);
      localStorage.setItem('user_role', data.user_role);
      localStorage.setItem('tenant_id', data.tenant_id);
      localStorage.setItem('tenant_name', data.tenant_name);

      // Define cookie para o middleware do Next.js App Router
      document.cookie = `token=${data.access_token}; path=/;`;

      onLoginSuccess();
    } catch (err: any) {
      setError(err.message || "Erro de conexão com o servidor.");
    } finally {
      setLoading(false);
    }
  };

  const handleAutofillDemo = () => {
    setEmail('joao@jferres.com.br');
    setPassword('admin123');
    setError(null);
  };

  return (
    <div className={styles.loginPage}>
      {/* Painel de Apresentação (Apenas Imagem de Fundo) */}
      <div className={styles.brandPane} />

      {/* Painel de Formulário e Credenciais */}
      <div className={styles.formPane}>
        <div className={styles.formContainer}>
          <div className={styles.header}>
            <h1 className={styles.title}>Acessar Plataforma</h1>
            <p className={styles.subtitle}>
              Entre com suas credenciais corporativas.
            </p>
          </div>

          <form onSubmit={handleLogin} className={styles.form}>
            <div className={styles.formGroup}>
              <label className={styles.label}>E-mail de Trabalho</label>
              <div className={styles.inputWrapper}>
                <Mail size={16} className={styles.inputIcon} />
                <input
                  type="email"
                  className={styles.input}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="nome@empresa.com.br"
                  disabled={loading}
                />
              </div>
            </div>

            <div className={styles.formGroup}>
              <label className={styles.label}>Senha Corporativa</label>
              <div className={styles.inputWrapper}>
                <Lock size={16} className={styles.inputIcon} />
                <input
                  type="password"
                  className={styles.input}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  disabled={loading}
                />
              </div>
            </div>

            {error && (
              <div className={styles.errorBadge}>
                <AlertCircle size={16} style={{ flexShrink: 0 }} />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              className={styles.submitButton}
              disabled={loading}
            >
              {loading ? (
                <>
                  <LogIn size={16} className={styles.spin} />
                  Autenticando...
                </>
              ) : (
                <>
                  <LogIn size={16} />
                  Entrar no Painel
                </>
              )}
            </button>
          </form>

          <div className={styles.demoSection} onClick={handleAutofillDemo}>
            <p className={styles.demoText}>
              <Info size={14} style={{ display: 'inline-block', marginRight: '6px', verticalAlign: 'middle', opacity: 0.7 }} />
              Clique para preencher credenciais padrão:
            </p>
            <div className={styles.demoCredentialsRow}>
              <span className={styles.demoCredentialItem}>
                <User size={14} style={{ display: 'inline-block', marginRight: '6px', verticalAlign: 'middle', opacity: 0.7 }} />
                joao@jferres.com.br
              </span>
              <span className={styles.demoCredentialItem} style={{ color: 'var(--sw-primary)' }}>
                <Lock size={14} style={{ display: 'inline-block', marginRight: '6px', verticalAlign: 'middle', opacity: 0.7 }} />
                admin123
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
