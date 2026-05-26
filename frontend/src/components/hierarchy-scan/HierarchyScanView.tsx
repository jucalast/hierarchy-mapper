"use client";

import React, { useState, useEffect, useRef } from 'react';
import { 
    Play, 
    Loader2, 
    User, 
    MapPin, 
    ExternalLink, 
    FileJson, 
    CheckCircle2, 
    AlertTriangle,
    Eye,
    EyeOff,
    Terminal,
    RefreshCw,
    Globe
} from 'lucide-react';
import { apiPost, API_V1_URL } from '@/services/config';

interface EmployeeProfile {
    name: string;
    role: string;
    linkedin_url: string;
    avatar: string;
    location?: string;
}

interface HierarchyScanViewProps {
    onBack: () => void;
}

export const HierarchyScanView: React.FC<HierarchyScanViewProps> = ({ onBack }) => {
    const [companyUrl, setCompanyUrl] = useState("https://www.linkedin.com/company/grupobrasa/people/");
    const [cookie, setCookie] = useState("");
    // Iniciamos como FALSE por padrão para que o navegador NÃO abra fisicamente na tela do usuário,
    // permitindo que ele faça todo o login diretamente pelo preview da interface web!
    const [showBrowser, setShowBrowser] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [results, setResults] = useState<EmployeeProfile[]>([]);
    const [showCookie, setShowCookie] = useState(false);
    const [progressPercent, setProgressPercent] = useState(0);

    // Estados do painel de agentes e preview em tempo real
    const [consoleLogs, setConsoleLogs] = useState<string[]>([]);
    const [previewTimestamp, setPreviewTimestamp] = useState<number>(Date.now());
    const [hasPreview, setHasPreview] = useState(false);
    const [sseActive, setSseActive] = useState(false);
    const [inputText, setInputText] = useState("");

    const consoleEndRef = useRef<HTMLDivElement>(null);
    const eventSourceRef = useRef<EventSource | null>(null);

    // Carrega o cookie salvo no localStorage ao montar
    useEffect(() => {
        const savedCookie = localStorage.getItem('linkedin_li_at_cookie');
        if (savedCookie) {
            setCookie(savedCookie);
        }
        return () => {
            // Garante o fechamento da conexão se desmontar
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
        };
    }, []);

    // Rola o terminal console para baixo automaticamente
    useEffect(() => {
        if (consoleEndRef.current) {
            consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [consoleLogs]);

    // Salva o cookie no localStorage ao digitar
    const handleCookieChange = (val: string) => {
        setCookie(val);
        localStorage.setItem('linkedin_li_at_cookie', val);
    };

    const stopScraping = () => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
        setLoading(false);
        setSseActive(false);
        setConsoleLogs(prev => [...prev, "[System] Extração interrompida manualmente pelo operador."]);
    };

    const startScraping = async () => {
        setLoading(true);
        setError(null);
        setResults([]);
        setProgressPercent(0);
        setHasPreview(false);
        setConsoleLogs([
            "[System] Inicializando módulo de extração modular...",
            "[System] Tentando abrir conexão SSE para transmissão em tempo real..."
        ]);

        // Fecha qualquer conexão anterior ativa
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
        }

        const encodedUrl = encodeURIComponent(companyUrl);
        const encodedCookie = cookie ? encodeURIComponent(cookie) : "";
        const sseUrl = `${API_V1_URL}/hierarchy/linkedin-scrape/stream?company_url=${encodedUrl}&session_cookie=${encodedCookie}&headless=${!showBrowser}`;

        setSseActive(true);
        const es = new EventSource(sseUrl);
        eventSourceRef.current = es;

        es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'log') {
                    // Adiciona a linha de log do terminal vinda do backend
                    setConsoleLogs(prev => [...prev, data.message]);
                    
                    // Incrementa a barra de progresso com base na contagem de perfis seletivamente
                    if (data.message.includes("Colaboradores na página:")) {
                        const countMatch = data.message.match(/Colaboradores na página:\s*(\d+)/i);
                        if (countMatch) {
                            const count = parseInt(countMatch[1], 10);
                            // Simulação aproximada de progresso com limite de 98% antes do final
                            setProgressPercent(Math.min(98, Math.floor((count / 140) * 100)));
                        }
                    }
                } else if (data.type === 'screenshot') {
                    // Força a atualização da imagem do preview mudando a chave do cache-busting
                    setPreviewTimestamp(Date.now());
                    setHasPreview(true);
                } else if (data.type === 'result') {
                    const employees = data.data || [];
                    setResults(employees);
                    setProgressPercent(100);
                    setConsoleLogs(prev => [
                        ...prev, 
                        `[System] Processamento final concluído! ${employees.length} perfis importados com sucesso.`,
                        "[System] Conexão encerrada com sucesso."
                    ]);
                    es.close();
                    setLoading(false);
                    setSseActive(false);
                } else if (data.type === 'error') {
                    setError(data.message);
                    setConsoleLogs(prev => [...prev, `❌ [Erro do Agente] ${data.message}`]);
                    es.close();
                    setLoading(false);
                    setSseActive(false);
                }
            } catch (err) {
                console.error("Erro no processamento SSE:", err);
            }
        };

        es.onerror = (err) => {
            console.error("Erro de conexão com EventSource:", err);
            setError("Erro na conexão em tempo real com o servidor do Scraper. Verifique se o backend está ativo.");
            setConsoleLogs(prev => [...prev, "❌ [Erro de Rede] Conexão SSE falhou inesperadamente."]);
            es.close();
            setLoading(false);
            setSseActive(false);
        };
    };

    // --- MÉTODOS DE INTERAÇÃO E CONTROLE REMOTO EM TEMPO REAL ---

    const handleImageClick = async (e: React.MouseEvent<HTMLImageElement>) => {
        if (!loading) return; // Só permite interagir se o scraper estiver ativamente em execução

        const img = e.currentTarget;
        const rect = img.getBoundingClientRect();
        
        // Calcula coordenadas relativas do clique no tamanho exibido da imagem
        const x_client = e.clientX - rect.left;
        const y_client = e.clientY - rect.top;
        
        // Projeta as coordenadas no tamanho real do viewport padrão do Playwright (1280x800)
        const x_absolute = Math.round((x_client / rect.width) * 1280);
        const y_absolute = Math.round((y_client / rect.height) * 800);
        
        try {
            setConsoleLogs(prev => [...prev, `[Operator] Focando/Clicando em coordenada: (${x_absolute}, ${y_absolute})...`]);
            await apiPost(`/hierarchy/linkedin-scrape/interact?action=click&x=${x_absolute}&y=${y_absolute}`);
        } catch (err: any) {
            console.error("Erro ao enviar clique remoto:", err);
            setConsoleLogs(prev => [...prev, `❌ [System Error] Falha ao enviar clique: ${err.message}`]);
        }
    };

    const handleSendText = async () => {
        if (!inputText) return;
        try {
            setConsoleLogs(prev => [...prev, `[Operator] Inserindo texto: "${inputText}"...`]);
            await apiPost(`/hierarchy/linkedin-scrape/interact?action=type&text=${encodeURIComponent(inputText)}`);
            setInputText("");
        } catch (err: any) {
            console.error("Erro ao enviar texto remoto:", err);
            setConsoleLogs(prev => [...prev, `❌ [System Error] Falha ao enviar escrita: ${err.message}`]);
        }
    };

    const handlePressEnter = async () => {
        try {
            setConsoleLogs(prev => [...prev, `[Operator] Pressionando tecla ENTER...`]);
            await apiPost(`/hierarchy/linkedin-scrape/interact?action=press&key=Enter`);
        } catch (err: any) {
            console.error("Erro ao enviar tecla Enter:", err);
            setConsoleLogs(prev => [...prev, `❌ [System Error] Falha ao pressionar Enter: ${err.message}`]);
        }
    };

    const handlePressBackspace = async () => {
        try {
            setConsoleLogs(prev => [...prev, `[Operator] Pressionando tecla BACKSPACE...`]);
            await apiPost(`/hierarchy/linkedin-scrape/interact?action=press&key=Backspace`);
        } catch (err: any) {
            console.error("Erro ao enviar tecla Backspace:", err);
            setConsoleLogs(prev => [...prev, `❌ [System Error] Falha ao pressionar Backspace: ${err.message}`]);
        }
    };

    return (
        <div style={{
            height: '100%',
            width: '100%',
            overflowY: 'auto',
            background: 'var(--sw-bg)',
            padding: '24px',
            color: 'var(--sw-text-base)',
            fontFamily: 'var(--font-primary)',
            animation: 'fadeIn 0.4s var(--transition-smooth)'
        }}>
            {/* Header do Scraper */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '24px',
                borderBottom: '1px solid var(--sw-border)',
                paddingBottom: '16px'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                        background: 'rgba(129, 140, 248, 0.15)',
                        color: 'var(--sw-primary)',
                        padding: '10px',
                        borderRadius: '12px',
                        display: 'flex',
                        alignItems: 'center'
                    }}>
                        <svg 
                            xmlns="http://www.w3.org/2000/svg" 
                            width="24" 
                            height="24" 
                            viewBox="0 0 24 24" 
                            fill="none" 
                            stroke="currentColor" 
                            strokeWidth="2" 
                            strokeLinecap="round" 
                            strokeLinejoin="round"
                        >
                            <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
                            <rect x="2" y="9" width="4" height="12" />
                            <circle cx="4" cy="4" r="2" />
                        </svg>
                    </div>
                    <div>
                        <h1 style={{ fontSize: '20px', fontWeight: 600, margin: 0 }}>Módulo Core LinkedIn Scraper</h1>
                        <p style={{ fontSize: '13px', color: 'var(--sw-text-subtle)', margin: '2px 0 0 0' }}>
                            Mapeador e Raspador integrado em tempo real. Veja o progresso e o preview do navegador live.
                        </p>
                    </div>
                </div>

                <button 
                    onClick={onBack}
                    style={{
                        background: 'transparent',
                        border: '1px solid var(--sw-border)',
                        color: 'var(--sw-text-base)',
                        padding: '8px 16px',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        fontSize: '13px',
                        fontWeight: 500,
                        transition: 'all 0.2s',
                        letterSpacing: '0.02em'
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--sw-hover)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                    Voltar para o Grafo
                </button>
            </div>

            {/* Layout em Duas Colunas (Opções / Visualização em Tempo Real) */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: '380px 1fr',
                gap: '24px',
                alignItems: 'start',
                marginBottom: '24px'
            }}>
                
                {/* Painel Esquerdo: Configurações */}
                <div style={{
                    background: 'var(--sw-surface-base)',
                    border: '1px solid var(--sw-border)',
                    borderRadius: '16px',
                    padding: '24px',
                    boxShadow: 'var(--sw-shadow)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '20px'
                }}>
                    <h2 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--sw-primary)', margin: 0, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                        Configurações da Automação
                    </h2>

                    {/* URL da Empresa */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--sw-text-subtle)' }}>
                            URL da Empresa no LinkedIn (/people)
                        </label>
                        <input 
                            type="text" 
                            value={companyUrl}
                            onChange={e => setCompanyUrl(e.target.value)}
                            disabled={loading}
                            placeholder="https://www.linkedin.com/company/nome-da-empresa/people/"
                            style={{
                                background: 'rgba(0, 0, 0, 0.25)',
                                border: '1px solid var(--sw-border)',
                                borderRadius: '10px',
                                padding: '12px',
                                color: 'var(--sw-text-base)',
                                fontSize: '13px',
                                outline: 'none',
                                transition: 'border-color 0.2s'
                            }}
                            onFocus={e => e.currentTarget.style.borderColor = 'var(--sw-primary)'}
                            onBlur={e => e.currentTarget.style.borderColor = 'var(--sw-border)'}
                        />
                    </div>

                    {/* Cookie li_at */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--sw-text-subtle)' }}>
                                Cookie de Sessão 'li_at' (Recomendado)
                            </label>
                            <button 
                                type="button"
                                onClick={() => setShowCookie(!showCookie)}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: 'var(--sw-primary)',
                                    cursor: 'pointer',
                                    fontSize: '11px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px'
                                }}
                            >
                                {showCookie ? <EyeOff size={12} /> : <Eye size={12} />}
                                {showCookie ? 'Ocultar' : 'Mostrar'}
                            </button>
                        </div>
                        <input 
                            type={showCookie ? "text" : "password"} 
                            value={cookie}
                            onChange={e => handleCookieChange(e.target.value)}
                            disabled={loading}
                            placeholder="Insira seu cookie li_at para rodar headless..."
                            style={{
                                background: 'rgba(0, 0, 0, 0.25)',
                                border: '1px solid var(--sw-border)',
                                borderRadius: '10px',
                                padding: '12px',
                                color: 'var(--font-mono)',
                                fontSize: '13px',
                                outline: 'none'
                            }}
                        />
                        <span style={{ fontSize: '11px', color: 'var(--sw-text-muted)', lineHeight: '1.4' }}>
                            {!cookie ? (
                                <span style={{ color: 'var(--sw-status-warning)' }}>
                                    ⚠️ Sem cookie. O script rodará 100% oculto e você poderá interagir e fazer o login direto pela janela do Live Preview ao lado!
                                </span>
                            ) : (
                                "Cookie injetado! O script iniciará logado em segundo plano automaticamente."
                            )}
                        </span>
                    </div>

                    {/* Mostrar Navegador */}
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: 'rgba(0,0,0,0.2)',
                        padding: '12px 16px',
                        borderRadius: '10px',
                        border: '1px solid var(--sw-border)'
                    }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                            <span style={{ fontSize: '13px', fontWeight: 500 }}>Live GUI (Modo Headful)</span>
                            <span style={{ fontSize: '11px', color: 'var(--sw-text-muted)' }}>Exibe a janela física externa do Playwright</span>
                        </div>
                        <input 
                            type="checkbox"
                            checked={showBrowser}
                            onChange={e => setShowBrowser(e.target.checked)}
                            disabled={loading} 
                            style={{
                                width: '38px',
                                height: '20px',
                                cursor: 'pointer',
                                accentColor: 'var(--sw-primary)'
                            }}
                        />
                    </div>

                    {/* Botões de Ação */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {!loading ? (
                            <button
                                onClick={startScraping}
                                disabled={!companyUrl}
                                style={{
                                    background: 'var(--sw-primary)',
                                    color: '#ffffff',
                                    border: 'none',
                                    borderRadius: '12px',
                                    padding: '14px',
                                    fontSize: '14px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: '8px',
                                    transition: 'all 0.2s',
                                    boxShadow: '0 4px 12px rgba(129, 140, 248, 0.25)'
                                }}
                                onMouseEnter={e => e.currentTarget.style.background = 'var(--sw-primary-hover)'}
                                onMouseLeave={e => e.currentTarget.style.background = 'var(--sw-primary)'}
                            >
                                <Play size={16} />
                                Iniciar Extração Incansável
                            </button>
                        ) : (
                            <button
                                onClick={stopScraping}
                                style={{
                                    background: 'var(--sw-status-danger)',
                                    color: '#ffffff',
                                    border: 'none',
                                    borderRadius: '12px',
                                    padding: '14px',
                                    fontSize: '14px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: '8px',
                                    transition: 'all 0.2s',
                                    boxShadow: '0 4px 12px rgba(239, 68, 68, 0.25)'
                                }}
                                onMouseEnter={e => e.currentTarget.style.opacity = '0.9'}
                                onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                            >
                                <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                                Parar Agente / Interromper
                            </button>
                        )}
                    </div>

                    {/* Informações Auxiliares */}
                    {loading && (
                        <div style={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '6px',
                            background: 'rgba(255,255,255,0.03)',
                            padding: '12px',
                            borderRadius: '10px',
                            border: '1px solid var(--sw-border)'
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                                <span>Progresso da varredura</span>
                                <strong>{progressPercent}%</strong>
                            </div>
                            <div style={{
                                width: '100%',
                                height: '6px',
                                background: 'rgba(0,0,0,0.3)',
                                borderRadius: '3px',
                                overflow: 'hidden'
                            }}>
                                <div style={{
                                    height: '100%',
                                    width: `${progressPercent}%`,
                                    background: 'var(--sw-primary)',
                                    borderRadius: '3px',
                                    transition: 'width 0.4s ease'
                                }} />
                            </div>
                        </div>
                    )}
                </div>

                {/* Painel Direito: Live Agent Dashboard (Terminal e Preview) */}
                <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '20px',
                    width: '100%'
                }}>
                    
                    {/* Linha de Cima: Browser Preview Mockup */}
                    <div style={{
                        background: 'var(--sw-surface-base)',
                        border: '1px solid var(--sw-border)',
                        borderRadius: '16px',
                        overflow: 'hidden',
                        boxShadow: 'var(--sw-shadow)',
                        display: 'flex',
                        flexDirection: 'column',
                        minHeight: '460px'
                    }}>
                        {/* Browser Window Header */}
                        <div style={{
                            background: 'rgba(255,255,255,0.03)',
                            borderBottom: '1px solid var(--sw-border)',
                            padding: '10px 16px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between'
                        }}>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#ff5f56' }} />
                                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#ffbd2e' }} />
                                <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: '#27c93f' }} />
                            </div>
                            
                            {/* Browser Search Bar Mock */}
                            <div style={{
                                background: 'rgba(0,0,0,0.25)',
                                borderRadius: '6px',
                                padding: '4px 16px',
                                width: '50%',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                color: 'var(--sw-text-muted)',
                                fontSize: '11px',
                                border: '1px solid var(--sw-border)'
                            }}>
                                <Globe size={12} />
                                <span style={{
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                    width: '100%'
                                }}>
                                    {companyUrl}
                                </span>
                            </div>

                            {/* Live Badge */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                {loading && (
                                    <div style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '6px',
                                        background: 'rgba(239, 68, 68, 0.15)',
                                        color: '#ef4444',
                                        fontSize: '10px',
                                        fontWeight: 600,
                                        padding: '2px 8px',
                                        borderRadius: '12px',
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.04em',
                                        animation: 'pulse 1.5s infinite ease-in-out'
                                    }}>
                                        <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#ef4444' }} />
                                        PLAYWRIGHT LIVE
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Browser Visual Area */}
                        <div style={{
                            flex: 1,
                            background: '#121214',
                            position: 'relative',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            overflow: 'hidden',
                            height: '320px'
                        }}>
                            {hasPreview ? (
                                <img 
                                    src={`${API_V1_URL}/hierarchy/linkedin-scrape/preview?t=${previewTimestamp}`}
                                    alt="Live Browser View" 
                                    onClick={handleImageClick}
                                    style={{
                                        width: '100%',
                                        height: '100%',
                                        objectFit: 'contain',
                                        cursor: loading ? 'pointer' : 'default',
                                        transition: 'all 0.3s var(--transition-smooth)'
                                    }}
                                    title={loading ? "Clique na tela para focar em campos ou clicar em botões!" : ""}
                                />
                            ) : (
                                <div style={{
                                    display: 'flex',
                                    flexDirection: 'column',
                                    alignItems: 'center',
                                    gap: '12px',
                                    color: 'var(--sw-text-muted)',
                                    textAlign: 'center',
                                    padding: '20px'
                                }}>
                                    {loading ? (
                                        <>
                                            <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', color: 'var(--sw-primary)' }} />
                                            <span style={{ fontSize: '13px' }}>Aguardando primeira captura do navegador...</span>
                                        </>
                                    ) : (
                                        <>
                                            <svg 
                                                xmlns="http://www.w3.org/2000/svg" 
                                                width="48" 
                                                height="48" 
                                                viewBox="0 0 24 24" 
                                                fill="none" 
                                                stroke="currentColor" 
                                                strokeWidth="1.5" 
                                                strokeLinecap="round" 
                                                strokeLinejoin="round"
                                                style={{ opacity: 0.3 }}
                                            >
                                                <rect width="18" height="18" x="3" y="3" rx="2" />
                                                <path d="M3 9h18" />
                                                <path d="M9 21V9" />
                                            </svg>
                                            <span style={{ fontSize: '13px' }}>
                                                Inicie a extração para visualizar a tela do navegador Playwright em tempo real.
                                            </span>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Interactive Remote Input Panel */}
                        {loading && (
                            <div style={{
                                background: 'rgba(0, 0, 0, 0.4)',
                                borderTop: '1px solid var(--sw-border)',
                                padding: '12px 16px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '8px'
                            }}>
                                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                    <input 
                                        type="text"
                                        value={inputText}
                                        onChange={e => setInputText(e.target.value)}
                                        placeholder="Digite texto para preencher o campo focado (ex: e-mail, senha)..."
                                        onKeyDown={e => {
                                            if (e.key === 'Enter') {
                                                handleSendText();
                                            }
                                        }}
                                        style={{
                                            flex: 1,
                                            background: 'rgba(0, 0, 0, 0.4)',
                                            border: '1px solid var(--sw-border)',
                                            borderRadius: '8px',
                                            padding: '8px 12px',
                                            color: '#ffffff',
                                            fontSize: '12px',
                                            outline: 'none'
                                        }}
                                    />
                                    <button
                                        onClick={handleSendText}
                                        disabled={!inputText.trim()}
                                        style={{
                                            background: 'var(--sw-primary)',
                                            color: '#ffffff',
                                            border: 'none',
                                            borderRadius: '8px',
                                            padding: '8px 16px',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            cursor: 'pointer',
                                            opacity: inputText.trim() ? 1 : 0.6
                                        }}
                                    >
                                        Enviar Escrita
                                    </button>
                                    <button
                                        onClick={handlePressEnter}
                                        style={{
                                            background: 'rgba(255, 255, 255, 0.08)',
                                            border: '1px solid var(--sw-border)',
                                            color: '#ffffff',
                                            borderRadius: '8px',
                                            padding: '8px 16px',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            cursor: 'pointer'
                                        }}
                                    >
                                        Pressionar Enter ↵
                                    </button>
                                    <button
                                        onClick={handlePressBackspace}
                                        style={{
                                            background: 'rgba(239, 68, 68, 0.1)',
                                            border: '1px solid rgba(239, 68, 68, 0.3)',
                                            color: '#ef4444',
                                            borderRadius: '8px',
                                            padding: '8px 16px',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            cursor: 'pointer'
                                        }}
                                    >
                                        Apagar ⌫
                                    </button>
                                </div>
                                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.45)', display: 'flex', gap: '4px' }}>
                                    <span>💡</span>
                                    <span>
                                        <strong>Instruções de Login:</strong> 1. Clique na tela do navegador acima sobre o campo de login ou senha. 2. Digite seus dados no campo de texto acima e clique em <strong>"Enviar Escrita"</strong>. 3. Clique em <strong>"Pressionar Enter ↵"</strong> para submeter o formulário.
                                    </span>
                                </span>
                            </div>
                        )}
                    </div>

                    {/* Linha de Baixo: Sleek Agent Terminal Logs */}
                    <div style={{
                        background: 'rgba(10, 10, 12, 0.85)',
                        border: '1px solid var(--sw-border)',
                        borderRadius: '16px',
                        boxShadow: 'var(--sw-shadow)',
                        display: 'flex',
                        flexDirection: 'column',
                        height: '240px',
                        overflow: 'hidden',
                        backdropFilter: 'blur(12px)'
                    }}>
                        {/* Terminal Header */}
                        <div style={{
                            background: 'rgba(0,0,0,0.4)',
                            borderBottom: '1px solid rgba(255,255,255,0.06)',
                            padding: '8px 16px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            color: 'rgba(255,255,255,0.4)',
                            fontSize: '11px',
                            fontFamily: 'var(--font-mono)'
                        }}>
                            <Terminal size={12} style={{ color: 'var(--sw-primary)' }} />
                            <span>terminal - agent@linkb2b:~ (live_logs)</span>
                        </div>

                        {/* Terminal Console Logs Area */}
                        <div style={{
                            flex: 1,
                            padding: '16px',
                            overflowY: 'auto',
                            fontFamily: 'var(--font-mono)',
                            fontSize: '12px',
                            lineHeight: '1.6',
                            color: 'rgba(255, 255, 255, 0.85)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px'
                        }}>
                            {consoleLogs.length > 0 ? (
                                consoleLogs.map((log, index) => {
                                    let textColor = 'rgba(255, 255, 255, 0.8)';
                                    if (log.startsWith('[System]')) {
                                        textColor = 'var(--sw-primary)';
                                    } else if (log.includes('✅') || log.startsWith('🎉') || log.includes('Login detectado')) {
                                        textColor = '#4ade80'; // Bright Green
                                    } else if (log.startsWith('👤') || log.startsWith('[Operator]')) {
                                        textColor = '#38bdf8'; // Sky Blue
                                    } else if (log.includes('⚠️') || log.includes('Warning')) {
                                        textColor = '#fbbf24'; // Amber Yellow
                                    } else if (log.startsWith('❌') || log.startsWith('[Erro')) {
                                        textColor = '#f87171'; // Coral Red
                                    } else if (log.includes('📊')) {
                                        textColor = 'rgba(255,255,255,0.5)';
                                    }

                                    return (
                                        <div key={index} style={{ color: textColor, whiteSpace: 'pre-wrap' }}>
                                            {log}
                                        </div>
                                    );
                                })
                            ) : (
                                <div style={{ color: 'rgba(255, 255, 255, 0.3)', fontStyle: 'italic' }}>
                                    Aguardando tarefas da CPU... Terminal inativo.
                                </div>
                            )}
                            <div ref={consoleEndRef} />
                        </div>
                    </div>
                </div>
            </div>

            {/* Mensagem de Erro Geral */}
            {error && !loading && (
                <div style={{
                    background: 'rgba(239, 68, 68, 0.08)',
                    border: '1px solid rgba(239, 68, 68, 0.2)',
                    borderRadius: '16px',
                    padding: '20px',
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'start',
                    boxShadow: 'var(--sw-shadow)',
                    marginBottom: '24px',
                    animation: 'fadeIn 0.3s'
                }}>
                    <AlertTriangle size={20} style={{ color: 'var(--sw-status-danger)', flexShrink: 0, marginTop: '2px' }} />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <strong style={{ fontSize: '14px', color: 'var(--sw-status-danger)' }}>Falha na Automação do Agente</strong>
                        <p style={{ fontSize: '13px', color: 'var(--sw-text-subtle)', margin: 0, lineHeight: '1.5' }}>
                            {error}
                        </p>
                    </div>
                </div>
            )}

            {/* Resultados da Extração */}
            {results.length > 0 && !loading && (
                <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '16px',
                    animation: 'fadeIn 0.4s'
                }}>
                    {/* Estatísticas e Ações */}
                    <div style={{
                        background: 'var(--sw-surface-base)',
                        border: '1px solid var(--sw-border)',
                        borderRadius: '12px',
                        padding: '16px 20px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        boxShadow: 'var(--sw-shadow)'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#4ade80' }}>
                            <CheckCircle2 size={18} />
                            <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--sw-text-base)' }}>
                                Extração concluída com sucesso: <strong>{results.length}</strong> pessoas importadas para análise.
                            </span>
                        </div>

                        <button
                            onClick={() => {
                                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(results, null, 4));
                                const downloadAnchor = document.createElement('a');
                                downloadAnchor.setAttribute("href", dataStr);
                                downloadAnchor.setAttribute("download", `linkedin_colaboradores_${Date.now()}.json`);
                                document.body.appendChild(downloadAnchor);
                                downloadAnchor.click();
                                downloadAnchor.remove();
                            }}
                            style={{
                                background: 'rgba(255,255,255,0.04)',
                                border: '1px solid var(--sw-border)',
                                borderRadius: '8px',
                                padding: '8px 12px',
                                color: 'var(--sw-text-base)',
                                fontSize: '12px',
                                fontWeight: 500,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                transition: 'all 0.2s'
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = 'var(--sw-hover)'}
                            onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.04)'}
                        >
                            <FileJson size={14} />
                            Exportar JSON
                        </button>
                    </div>

                    {/* Grid de Perfis */}
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(285px, 1fr))',
                        gap: '16px',
                        maxHeight: 'calc(100vh - 200px)',
                        overflowY: 'auto',
                        paddingRight: '4px'
                    }}>
                        {results.map((profile, idx) => (
                            <div 
                                key={idx}
                                style={{
                                    background: 'var(--sw-surface-base)',
                                    border: '1px solid var(--sw-border)',
                                    borderRadius: '12px',
                                    padding: '16px',
                                    display: 'flex',
                                    gap: '12px',
                                    transition: 'transform 0.2s, border-color 0.2s',
                                    boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
                                }}
                                onMouseEnter={e => {
                                    e.currentTarget.style.borderColor = 'var(--sw-primary-border)';
                                    e.currentTarget.style.transform = 'translateY(-2px)';
                                }}
                                onMouseLeave={e => {
                                    e.currentTarget.style.borderColor = 'var(--sw-border)';
                                    e.currentTarget.style.transform = 'none';
                                }}
                            >
                                {/* Foto Perfil */}
                                <div style={{
                                    width: '48px',
                                    height: '48px',
                                    borderRadius: '50%',
                                    background: 'rgba(255,255,255,0.05)',
                                    border: '1px solid var(--sw-border)',
                                    overflow: 'hidden',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    flexShrink: 0
                                }}>
                                    {profile.avatar ? (
                                        <img 
                                            src={profile.avatar} 
                                            alt={profile.name} 
                                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                            onError={e => {
                                                e.currentTarget.style.display = 'none';
                                                e.currentTarget.parentElement?.insertAdjacentHTML('beforeend', '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--sw-text-muted)" stroke-width="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>');
                                            }}
                                        />
                                    ) : (
                                        <User size={20} style={{ color: 'var(--sw-text-muted)' }} />
                                    )}
                                </div>

                                {/* Dados */}
                                <div style={{ 
                                    display: 'flex', 
                                    flexDirection: 'column', 
                                    gap: '4px',
                                    overflow: 'hidden',
                                    width: '100%'
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: '4px' }}>
                                        <span style={{ 
                                            fontSize: '14px', 
                                            fontWeight: 600, 
                                            color: 'var(--sw-text-base)',
                                            whiteSpace: 'nowrap',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis'
                                        }} title={profile.name}>
                                            {profile.name}
                                        </span>
                                        <a 
                                            href={profile.linkedin_url} 
                                            target="_blank" 
                                            rel="noreferrer"
                                            style={{ 
                                                color: 'var(--sw-text-muted)', 
                                                display: 'flex',
                                                flexShrink: 0,
                                                transition: 'color 0.2s'
                                            }}
                                            onMouseEnter={e => e.currentTarget.style.color = 'var(--sw-primary)'}
                                            onMouseLeave={e => e.currentTarget.style.color = 'var(--sw-text-muted)'}
                                            title="Abrir perfil no LinkedIn"
                                        >
                                            <ExternalLink size={12} />
                                        </a>
                                    </div>

                                    <span style={{ 
                                        fontSize: '12px', 
                                        color: 'var(--sw-text-subtle)',
                                        lineHeight: '1.3',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical',
                                        minHeight: '32px'
                                    }} title={profile.role}>
                                        {profile.role}
                                    </span>

                                    {profile.location && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--sw-text-muted)' }}>
                                            <MapPin size={10} style={{ flexShrink: 0 }} />
                                            <span style={{ 
                                                fontSize: '11px', 
                                                whiteSpace: 'nowrap', 
                                                overflow: 'hidden', 
                                                textOverflow: 'ellipsis' 
                                            }} title={profile.location}>
                                                {profile.location}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
