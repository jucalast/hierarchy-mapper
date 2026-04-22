"use client";

import React, { useState, useEffect } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { Header } from '@/components/Header';
import { RotateCcw, Send, Mail, Eye, Calendar, User, Activity, AlertCircle } from 'lucide-react';
import { communication } from '@/services/api';
import { Button, EmptyState } from '@/components/ui';

export default function EmailDashboard() {
  const [showChat, setShowChat] = useState(false);
  const [metrics, setMetrics] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [composer, setComposer] = useState({ to: '', subject: '', body: '' });
  const [sending, setSending] = useState(false);
  const [tab, setTab] = useState<'metrics' | 'compose'>('compose'); // 'compose' or 'metrics'

  const fetchMetrics = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await communication.getMetrics();
      setMetrics(data.data || []);
    } catch (err: any) {
      console.error('Erro ao buscar métricas:', err);
      setError(`⚠️ Backend indisponível: ${err?.message || err}. Verifique se o serviço está rodando.`);
      setMetrics([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!composer.to || !composer.subject || !composer.body) return;
    setSending(true);
    setError(null);

    try {
      await communication.sendEmail({
        to_email: composer.to,
        subject: composer.subject,
        body: composer.body,
      });
      setComposer({ to: '', subject: '', body: '' });
      setTab('metrics');
      fetchMetrics();
    } catch (error: any) {
      console.error('Erro ao enviar email', error);
      setError(`Erro ao enviar: ${error?.message || error}`);
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', background: 'var(--bg-color)' }}>
      {/* Menu Lateral (Igual ao do sistema central) */}
      <Sidebar 
        showDrawer={false} 
        setShowDrawer={() => {}} 
        theme="dark" 
        onToggleTheme={() => {}} 
        onReset={() => {}} 
        onCopyData={() => {}} 
      />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Header confirmedBrand="E-mail Outbound (Tracking)" />

        {error && (
          <div style={{
            background: 'rgba(255, 107, 107, 0.1)',
            borderBottom: '1px solid rgba(255, 107, 107, 0.3)',
            padding: '16px 24px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '12px',
            color: '#ff6b6b'
          }}>
            <AlertCircle size={18} style={{ marginTop: '2px', flexShrink: 0 }} />
            <div style={{ fontSize: '0.9rem' }}>
              {error}
            </div>
          </div>
        )}

        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          
          {/* Painel Esquerdo (Navegação Interna do Módulo) */}
          <div style={{ 
            width: '280px', 
            background: '#131313', 
            borderRight: '1px solid rgba(255, 255, 255, 0.05)',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <div style={{ padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <h2 style={{ color: 'rgba(255, 255, 255, 0.4)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '8px' }}>
                ESTRATÉGIA B2B
              </h2>
              <button 
                onClick={() => setTab('compose')}
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px',
                  background: tab === 'compose' ? 'rgba(255, 255, 255, 0.05)' : 'transparent',
                  color: tab === 'compose' ? '#fff' : 'rgba(255, 255, 255, 0.6)',
                  border: 'none', borderRadius: '8px', cursor: 'pointer', textAlign: 'left',
                  transition: 'background 0.2s', fontSize: '0.9rem', fontWeight: 500
                }}
              >
                <Mail size={18} /> Novo Disparo
              </button>

              <button 
                onClick={() => { setTab('metrics'); fetchMetrics(); }}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px',
                  background: tab === 'metrics' ? 'rgba(255, 255, 255, 0.05)' : 'transparent',
                  color: tab === 'metrics' ? '#fff' : 'rgba(255, 255, 255, 0.6)',
                  border: 'none', borderRadius: '8px', cursor: 'pointer', textAlign: 'left',
                  transition: 'background 0.2s', fontSize: '0.9rem', fontWeight: 500
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <Activity size={18} /> Tracking & Métricas
                </div>
                {loading && <RotateCcw size={14} style={{ animation: 'spin 1s linear infinite' }} />}
              </button>
            </div>
          </div>

          {/* Área Principal */}
          <div style={{ flex: 1, background: '#1d1d1d', overflowY: 'auto' }}>
            
            {tab === 'compose' ? (
              <div style={{ maxWidth: '800px', margin: '40px auto', padding: '0 24px' }}>
                <div style={{ background: '#131313', borderRadius: '16px', border: '1px solid rgba(255, 255, 255, 0.05)', padding: '32px', boxShadow: '0 12px 30px rgba(0,0,0,0.3)' }}>
                  <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '8px', color: '#fff' }}>Compor Cadência</h1>
                  <p style={{ color: 'rgba(255, 255, 255, 0.5)', marginBottom: '32px', fontSize: '0.9rem' }}>
                    O e-mail será enviado com o sistema de tracking autônomo. O atraso humano de (2 a 5s) será aplicado nativamente antes do despacho final para preservar a reputação do IP.
                  </p>

                  <form onSubmit={handleSend} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.6)', marginBottom: '8px', fontWeight: 600 }}>Destinatário B2B</label>
                      <input 
                        type="email" 
                        required
                        value={composer.to}
                        onChange={e => setComposer({ ...composer, to: e.target.value })}
                        placeholder="lead.compras@empresa.com"
                        style={{
                          width: '100%', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)',
                          padding: '12px 16px', borderRadius: '8px', color: '#fff', outline: 'none', transition: 'border-color 0.2s', fontSize: '0.95rem'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.6)', marginBottom: '8px', fontWeight: 600 }}>Linha de Assunto</label>
                      <input 
                        type="text" 
                        required
                        value={composer.subject}
                        onChange={e => setComposer({ ...composer, subject: e.target.value })}
                        placeholder="Solução para Gargalo Opex - Dúvida rápida"
                        style={{
                          width: '100%', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)',
                          padding: '12px 16px', borderRadius: '8px', color: '#fff', outline: 'none', transition: 'border-color 0.2s', fontSize: '0.95rem'
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.6)', marginBottom: '8px', fontWeight: 600 }}>Corpo do e-mail (HTML permitido)</label>
                      <textarea 
                        required
                        value={composer.body}
                        onChange={e => setComposer({ ...composer, body: e.target.value })}
                        placeholder="Olá, percebi que você está na cadeira de Suprimentos...\n\nO tracking do pixel (gif transparente) será injetado automaticamente no rodapé..."
                        style={{
                          width: '100%', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)',
                          padding: '16px', borderRadius: '8px', color: '#fff', outline: 'none', transition: 'border-color 0.2s', fontSize: '0.95rem',
                          minHeight: '200px', resize: 'vertical'
                        }}
                      />
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '12px' }}>
                      <Button
                        type="submit"
                        size="lg"
                        variant="primary"
                        loading={sending}
                        leftIcon={!sending ? <Send size={16} /> : undefined}
                      >
                        {sending ? 'Enviando... Aguardando Delay Humano' : 'Disparar Outbound'}
                      </Button>
                    </div>
                  </form>
                </div>
              </div>
            ) : (
              <div style={{ maxWidth: '900px', margin: '40px auto', padding: '0 24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                  <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#fff' }}>Performance de Disparos</h1>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={fetchMetrics}
                    loading={loading}
                    leftIcon={!loading ? <RotateCcw size={14} /> : undefined}
                  >
                    Sincronizar Logs
                  </Button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {metrics.length === 0 ? (
                    <div style={{ background: '#131313', borderRadius: '16px', border: '1px solid rgba(255, 255, 255, 0.05)', padding: '32px' }}>
                      <EmptyState
                        icon={<Activity size={40} />}
                        title="Nenhum e-mail disparado ainda"
                        description="Use o Composer para enviar seu primeiro tiro B2B frio."
                        action={
                          <Button
                            variant="primary"
                            size="sm"
                            leftIcon={<Mail size={14} />}
                            onClick={() => setTab('compose')}
                          >
                            Ir para o Composer
                          </Button>
                        }
                      />
                    </div>
                  ) : (
                    metrics.map((m) => (
                      <div key={m.tracking_id} style={{ 
                        background: '#131313', borderRadius: '12px', border: '1px solid rgba(255, 255, 255, 0.05)', 
                        padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px', position: 'relative', overflow: 'hidden'
                      }}>
                        {m.open_count > 0 && (
                          <div style={{ position: 'absolute', top: 0, left: 0, bottom: 0, width: '4px', background: '#2ea043' }} />
                        )}

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fff', fontWeight: 600, fontSize: '1.05rem', marginBottom: '4px' }}>
                              {m.subject}
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: 'rgba(255, 255, 255, 0.5)', fontSize: '0.85rem' }}>
                              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><User size={12} /> {m.to}</span>
                              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Calendar size={12} /> {new Date(m.date).toLocaleString('pt-BR')}</span>
                            </div>
                          </div>
                          
                          <div style={{ 
                            background: m.open_count > 0 ? 'rgba(46, 160, 67, 0.1)' : 'rgba(255, 255, 255, 0.05)',
                            color: m.open_count > 0 ? '#2ea043' : 'rgba(255, 255, 255, 0.5)',
                            padding: '6px 12px', borderRadius: '100px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 700
                          }}>
                            <Eye size={14} /> 
                            {m.open_count > 0 ? `${m.open_count} Abertura(s)` : 'Não lido (Ainda)'}
                          </div>
                        </div>

                        {/* Firewalls costumam pré-carregar. Então aberturas > 2 indicam lead quente! */}
                        {m.open_count > 0 && (
                          <div style={{ borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '12px', marginTop: '4px' }}>
                            <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'rgba(255, 255, 255, 0.4)', textTransform: 'uppercase', marginBottom: '8px' }}>Log de Tracking do Pixel HTTP</div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                              {m.opens.map((hit: any, i: number) => (
                                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', background: 'rgba(255, 255, 255, 0.02)', padding: '8px 12px', borderRadius: '6px', fontSize: '0.8rem' }}>
                                  <span style={{ color: 'rgba(255, 255, 255, 0.7)', fontFamily: 'monospace', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: '350px' }}>
                                    {hit.ip_agent}
                                  </span>
                                  <span style={{ color: 'rgba(255, 255, 255, 0.5)' }}>{new Date(hit.date).toLocaleTimeString('pt-BR')}</span>
                                </div>
                              ))}
                            </div>
                            
                            {m.open_count > 2 && (
                                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '6px', color: '#ffb000', fontSize: '0.85rem' }}>
                                    <Activity size={14} /> {m.open_count} interações! Esse lead tem alta probabilidade de ter encaminhado seu material ou estar avaliando agora.
                                </div>
                            )}
                          </div>
                        )}

                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
