'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Send, UserCircle, MessageSquare, Plus, Smile, Mic, AlertCircle } from 'lucide-react';
import { Drawer } from '@/components/Drawer';
import { Sidebar } from '@/components/Sidebar';
import { Header } from '@/components/Header';
import styles from '@/components/NetworkGraph.module.css'; // reaproveitar grid

export default function WhatsAppClone() {
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ id: string, text: string, sender: 'me' | 'them' }[]>([]);
  const [inputText, setInputText] = useState('');

  // Estados Pipedrive para o Drawer original
  const [pipedriveOrgs, setPipedriveOrgs] = useState<any[]>([]);
  const [loadingOrgs, setLoadingOrgs] = useState(true);
  const [errorOrgs, setErrorOrgs] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [showDrawer, setShowDrawer] = useState(true);
  const [showChat, setShowChat] = useState(false);

  // Busca dos orgs Pipedrive assim como no NetworkGraph
  const fetchPipedriveOrgs = async () => {
    if (pipedriveOrgs.length === 0) setLoadingOrgs(true);
    setErrorOrgs(null);
    try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
        fetch(`${API_URL}/api/v1/pipedrive_sync`, { method: 'POST' }).catch(() => {});
        const orgsResp = await fetch(`${API_URL}/api/v1/pipedrive/organizations?_=${Date.now()}`);
        if (!orgsResp.ok) {
            if (pipedriveOrgs.length === 0) {
              setPipedriveOrgs([]);
              setErrorOrgs(`Backend respondeu com status ${orgsResp.status}`);
            }
            setLoadingOrgs(false);
            return;
        }
        
        // Proteção contra erro de parsing ou retorno HTML inesperado em erro 500 do servidor FastAPI ou Vite Proxy
        const textData = await orgsResp.text();
        try {
            const data = JSON.parse(textData);
            const list = Array.isArray(data) ? data : [];
            setPipedriveOrgs(list);
            setErrorOrgs(null);
        } catch(parseErr: any) {
            console.warn('Resposta não foi JSON válido:', textData.slice(0, 100));
            if (pipedriveOrgs.length === 0) {
              setPipedriveOrgs([]);
              setErrorOrgs('Resposta do backend inválida');
            }
        }
    } catch (e: any) {
        console.warn('Erro na requisição das empresas:', e.message || e);
        if (pipedriveOrgs.length === 0) {
          setPipedriveOrgs([]);
          setErrorOrgs(`Backend indisponível: ${e.message}. Certifique-se de que o servidor está rodando em http://127.0.0.1:8000`);
        }
    } finally {
        setLoadingOrgs(false);
    }
  };

  useEffect(() => {
    fetchPipedriveOrgs();
  }, []);

  const filteredOrgs = useMemo(() => {
    return pipedriveOrgs.filter(org =>
        org.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (org.address && org.address.toLowerCase().includes(searchTerm.toLowerCase()))
    );
  }, [pipedriveOrgs, searchTerm]);

  // Handle para quando um negócio (Org) do drawer principal for selecionado
  const handleOrgClick = (org: any) => {
    // Definimos o ID ou Número principal de ativo, podemos simular que selecionou o 'whatsapp' dele
    setActiveChat(org.name); 
    setMessages([
      { id: '1', text: `Oi, estou entrando em contato em nome da ${org.name}.`, sender: 'me' }
    ]);
  };

  const handleSendMessage = () => {
    if (!inputText.trim() || !activeChat) return;
    
    // Como os Orgs não necessariamente têm fone atrelado que pegamos (ainda),
    // apenas renderizamos visualmente o balão de fala da simulação no front
    setMessages([...messages, { id: Date.now().toString(), text: inputText, sender: 'me' }]);
    setInputText('');
  };

  // Autoscroll para a última mensagem
  const messagesEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className={styles.container}>
      <Sidebar 
          showDrawer={showDrawer} 
          setShowDrawer={setShowDrawer}
          showChat={showChat}
          setShowChat={setShowChat}
          theme="dark"
          onToggleTheme={() => {}}
          onReset={() => { window.location.href = '/'; }}
          onCopyData={() => {}}
      />

      <Drawer
          showDrawer={showDrawer}
          setShowDrawer={setShowDrawer}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          filteredOrgs={filteredOrgs}
          onOrgClick={handleOrgClick}
          isLoading={loadingOrgs}
          selectedOrgId={null}
      />

      <main className={styles.mainContent} style={{ display: 'flex', flexDirection: 'column', position: 'relative' }}>
        <Header confirmedBrand={activeChat || 'WhatsApp Messages'} />

        {errorOrgs && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            backgroundColor: '#7f1d1d',
            color: '#fca5a5',
            padding: '12px 16px',
            borderRadius: '6px',
            margin: '12px 16px 0 16px',
            zIndex: 100
          }}>
            <AlertCircle size={20} />
            <div style={{ flex: 1 }}>
              <strong>Erro ao carregar empresas:</strong> {errorOrgs}
            </div>
            <button
              onClick={() => fetchPipedriveOrgs()}
              style={{
                background: 'rgba(255, 255, 255, 0.1)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                color: '#fca5a5',
                padding: '4px 12px',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.8rem'
              }}
            >
              Tentar novamente
            </button>
          </div>
        )}

        {activeChat ? (
          <>
            {/* Viewport de Mensagens harmonizada com fundo escuro simulando o Dark Mode perfeitamente */}
            <div style={{
              flex: 1,
              position: 'relative',
              backgroundColor: '#1d1d1d', // cor solicitada pelo usuário
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden'
            }}>
              {/* Imagem de Fundo do WhatsApp (Padrão de Rabiscos) */}
              <div style={{
                position: 'absolute',
                top: 0, left: 0, right: 0, bottom: 0,
                backgroundImage: 'url("/wpp.png")',
                backgroundRepeat: 'repeat',
                backgroundSize: '600px',
                pointerEvents: 'none', // Impede que a textura interfira nos cliques e no scroll
                zIndex: 0
              }} />

              {/* Contêiner real das mensagens com Scroll */}
              <div style={{
                flex: 1,
                overflowY: 'auto',
                padding: '30px 10%',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
                zIndex: 1
              }}>
              {messages.map(msg => {
                const isMe = msg.sender === 'me';
                return (
                  <div
                    key={msg.id}
                    style={{
                      alignSelf: isMe ? 'flex-end' : 'flex-start',
                      backgroundColor: isMe ? 'var(--accent-color, #005c4b)' : 'var(--floating-bg)',
                      color: isMe ? '#fff' : 'var(--text-primary)',
                      padding: '8px 12px 24px 12px',
                      borderRadius: isMe ? '12px 0px 12px 12px' : '0px 12px 12px 12px',
                      maxWidth: '75%',
                      boxShadow: '0 1px 0.5px rgba(0,0,0,0.15)',
                      border: '1px solid var(--border-color)',
                      fontSize: '0.95rem',
                      lineHeight: '1.4',
                      position: 'relative'
                    }}
                  >
                    {msg.text}
                    {/* Timestamp simulando o WhatsApp escuro no cantinho */}
                    <span style={{ 
                      position: 'absolute', 
                      bottom: '4px', right: '8px', 
                      fontSize: '0.65rem', 
                      color: isMe ? 'rgba(255,255,255,0.7)' : 'var(--text-secondary)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      16:07
                      {isMe && <span style={{ color: '#53bdeb' }}>✓✓</span>}
                    </span>
                  </div>
                );
              })}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Input Flex Bar (Estilo Floating Toolbar Glass/Escuro) */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              padding: '6px 6px 6px 8px',
              backgroundColor: '#111111',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '14px',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
              margin: '16px 24px', // Margem para fazer flutuar
              gap: '8px',
              zIndex: 10,
              minHeight: '52px'
            }}>
              <button 
                type="button"
                style={{ 
                  background: 'transparent',
                  border: 'none', 
                  color: 'rgba(255, 255, 255, 0.4)', 
                  cursor: 'pointer', 
                  display: 'flex', 
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '40px',
                  height: '40px',
                  borderRadius: '8px',
                  transition: 'background 0.2s',
                }}
                onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'}
                onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                title="Anexar"
              >
                <Plus size={20} />
              </button>
              
              <div style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                backgroundColor: 'transparent',
                borderRadius: '8px',
                padding: '0 12px',
                height: '38px',
                transition: 'background 0.2s, box-shadow 0.2s',
              }}
              onFocus={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                e.currentTarget.style.boxShadow = 'inset 0 0 0 1px rgba(255, 255, 255, 0.05)';
              }}
              onBlur={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.boxShadow = 'none';
              }}
              >
                <Smile size={18} style={{ color: 'rgba(255, 255, 255, 0.4)', marginRight: '12px', cursor: 'pointer' }} />
                <input
                  type="text"
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                  placeholder="Digite uma mensagem"
                  style={{ 
                    flex: 1, 
                    border: 'none', 
                    background: 'transparent', 
                    outline: 'none', 
                    color: '#ffffff', 
                    fontSize: '0.85rem',
                    fontWeight: 400
                  }}
                />
              </div>

              {inputText.trim() ? (
                <button
                  onClick={handleSendMessage}
                  style={{ 
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '0 16px',
                    height: '38px',
                    background: '#ffffff',
                    border: '1px solid #ffffff',
                    borderRadius: '8px',
                    color: '#000000',
                    fontSize: '0.85rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onMouseOver={(e) => e.currentTarget.style.opacity = '0.9'}
                  onMouseOut={(e) => e.currentTarget.style.opacity = '1'}
                  title="Enviar"
                >
                  <Send size={16} />
                  Enviar
                </button>
              ) : (
                <button 
                  type="button" 
                  style={{ 
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '40px',
                    height: '40px',
                    borderRadius: '8px',
                    background: 'transparent', 
                    border: 'none', 
                    color: 'rgba(255, 255, 255, 0.4)', 
                    cursor: 'pointer', 
                    transition: 'background 0.2s'
                  }}
                  onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'}
                  onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                  title="Gravar áudio"
                >
                  <Mic size={20} />
                </button>
              )}
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)', background: 'var(--bg-color)' }}>
            <MessageSquare size={64} style={{ marginBottom: '20px', opacity: 0.2 }} />
            <h3 style={{ userSelect: 'none' }}>Selecione uma empresa do Drawer para iniciar um Contato</h3>
            <p style={{ marginTop: '10px', maxWidth: '400px', textAlign: 'center', opacity: 0.7 }}>
              Clique em um negócio na barra lateral para começar a redigir mensagens ou ver o histórico inteligente.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
