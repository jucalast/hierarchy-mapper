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
    Globe
} from 'lucide-react';
import { API_V1_URL } from '@/services/config';
import type { ScanEmployeeProfile } from '@/hooks/useHierarchyScan';

interface HierarchyScanViewProps {
    onBack: () => void;
    // Contexto da empresa atual (pré-preenche a URL)
    defaultCompanyUrl?: string;
    // Estado do scan vindo do hook pai (useHierarchyScan no NetworkGraph)
    isScanning: boolean;
    scanProgress: number;
    consoleLogs: string[];
    hasPreview: boolean;
    previewUrl: string;
    scanResults: ScanEmployeeProfile[];
    scanError: string | null;
    // Callbacks para o hook pai
    onStartScan: (url: string, cookie: string) => void;
    onStopScan: () => void;
    onImageClick: (e: React.MouseEvent<HTMLImageElement>) => void;
    onSendText: (text: string) => void;
    onPressEnter: () => void;
    onPressBackspace: () => void;
}

export const HierarchyScanView: React.FC<HierarchyScanViewProps> = ({
    onBack,
    defaultCompanyUrl = '',
    isScanning,
    scanProgress,
    consoleLogs,
    hasPreview,
    previewUrl,
    scanResults,
    scanError,
    onStartScan,
    onStopScan,
    onImageClick,
    onSendText,
    onPressEnter,
    onPressBackspace,
}) => {
    // Estado de UI local — não tem nada a ver com o scan em si
    const [companyUrl, setCompanyUrl] = useState(defaultCompanyUrl);
    const [cookie, setCookie] = useState('');
    const [showBrowser, setShowBrowser] = useState(false);
    const [showCookie, setShowCookie] = useState(false);
    const [inputText, setInputText] = useState('');

    const consoleEndRef = useRef<HTMLDivElement>(null);

    // Sincroniza URL da empresa se a prop mudar (ex: troca de empresa no drawer)
    useEffect(() => {
        if (defaultCompanyUrl && !isScanning) {
            setCompanyUrl(defaultCompanyUrl);
        }
    }, [defaultCompanyUrl, isScanning]);

    // Carrega cookie salvo no localStorage ao montar
    useEffect(() => {
        const savedCookie = localStorage.getItem('linkedin_li_at_cookie');
        if (savedCookie) {
            setCookie(savedCookie);
        }
    }, []);

    // Rola o terminal para o final automaticamente quando chegam novos logs
    useEffect(() => {
        if (consoleEndRef.current) {
            consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [consoleLogs]);

    const handleCookieChange = (val: string) => {
        setCookie(val);
        localStorage.setItem('linkedin_li_at_cookie', val);
    };

    const handleStart = () => {
        onStartScan(companyUrl, cookie);
    };

    const handleSendText = () => {
        if (!inputText.trim()) return;
        onSendText(inputText);
        setInputText('');
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
            {/* Header */}
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
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
                            <rect x="2" y="9" width="4" height="12" />
                            <circle cx="4" cy="4" r="2" />
                        </svg>
                    </div>
                    <div>
                        <h1 style={{ fontSize: '20px', fontWeight: 600, margin: 0 }}>LinkedIn Scraper</h1>
                        <p style={{ fontSize: '13px', color: 'var(--sw-text-subtle)', margin: '2px 0 0 0' }}>
                            {isScanning
                                ? '🟢 Varredura em execução — você pode navegar livremente, o scan continua em background.'
                                : 'Mapeador e raspador integrado em tempo real. O scan continua mesmo ao navegar para outras telas.'}
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
                    ← Voltar para o Grafo
                </button>
            </div>

            {/* Layout em Duas Colunas */}
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
                        Configurações
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
                            disabled={isScanning}
                            placeholder="https://www.linkedin.com/company/empresa/people/"
                            style={{
                                background: 'rgba(0, 0, 0, 0.25)',
                                border: '1px solid var(--sw-border)',
                                borderRadius: '10px',
                                padding: '12px',
                                color: 'var(--sw-text-base)',
                                fontSize: '13px',
                                outline: 'none',
                                transition: 'border-color 0.2s',
                                opacity: isScanning ? 0.6 : 1,
                            }}
                            onFocus={e => e.currentTarget.style.borderColor = 'var(--sw-primary)'}
                            onBlur={e => e.currentTarget.style.borderColor = 'var(--sw-border)'}
                        />
                    </div>

                    {/* Cookie li_at */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <label style={{ fontSize: '13px', fontWeight: 500, color: 'var(--sw-text-subtle)' }}>
                                Cookie de Sessão 'li_at'
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
                            type={showCookie ? 'text' : 'password'}
                            value={cookie}
                            onChange={e => handleCookieChange(e.target.value)}
                            disabled={isScanning}
                            placeholder="Insira seu cookie li_at para rodar headless..."
                            style={{
                                background: 'rgba(0, 0, 0, 0.25)',
                                border: '1px solid var(--sw-border)',
                                borderRadius: '10px',
                                padding: '12px',
                                color: 'var(--font-mono)',
                                fontSize: '13px',
                                outline: 'none',
                                opacity: isScanning ? 0.6 : 1,
                            }}
                        />
                        <span style={{ fontSize: '11px', color: 'var(--sw-text-muted)', lineHeight: '1.4' }}>
                            {!cookie ? (
                                <span style={{ color: 'var(--sw-status-warning)' }}>
                                    ⚠️ Sem cookie — o login pode ser feito pelo Live Preview ao lado.
                                </span>
                            ) : (
                                'Cookie injetado! O script iniciará logado automaticamente.'
                            )}
                        </span>
                    </div>

                    {/* Modo Headful */}
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
                            disabled={isScanning}
                            style={{ width: '38px', height: '20px', cursor: 'pointer', accentColor: 'var(--sw-primary)' }}
                        />
                    </div>

                    {/* Botão de Ação */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {!isScanning ? (
                            <button
                                onClick={handleStart}
                                disabled={!companyUrl}
                                style={{
                                    background: 'var(--sw-primary)',
                                    color: '#ffffff',
                                    border: 'none',
                                    borderRadius: '12px',
                                    padding: '14px',
                                    fontSize: '14px',
                                    fontWeight: 600,
                                    cursor: companyUrl ? 'pointer' : 'not-allowed',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: '8px',
                                    transition: 'all 0.2s',
                                    boxShadow: '0 4px 12px rgba(129, 140, 248, 0.25)',
                                    opacity: companyUrl ? 1 : 0.6,
                                }}
                                onMouseEnter={e => { if (companyUrl) e.currentTarget.style.background = 'var(--sw-primary-hover)'; }}
                                onMouseLeave={e => e.currentTarget.style.background = 'var(--sw-primary)'}
                            >
                                <Play size={16} />
                                Iniciar Varredura
                            </button>
                        ) : (
                            <button
                                onClick={onStopScan}
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
                                    boxShadow: '0 4px 12px rgba(239, 68, 68, 0.25)'
                                }}
                            >
                                <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                                Parar Varredura
                            </button>
                        )}
                    </div>

                    {/* Barra de Progresso */}
                    {isScanning && (
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
                                <strong>{scanProgress}%</strong>
                            </div>
                            <div style={{ width: '100%', height: '6px', background: 'rgba(0,0,0,0.3)', borderRadius: '3px', overflow: 'hidden' }}>
                                <div style={{
                                    height: '100%',
                                    width: `${scanProgress}%`,
                                    background: 'var(--sw-primary)',
                                    borderRadius: '3px',
                                    transition: 'width 0.4s ease'
                                }} />
                            </div>
                        </div>
                    )}
                </div>

                {/* Painel Direito: Live Preview + Terminal */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', width: '100%' }}>

                    {/* Browser Preview */}
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
                        {/* Browser Header */}
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
                                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', width: '100%' }}>
                                    {companyUrl || 'linkedin.com'}
                                </span>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                {isScanning && (
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
                                    src={previewUrl}
                                    alt="Live Browser View"
                                    onClick={onImageClick}
                                    style={{
                                        width: '100%',
                                        height: '100%',
                                        objectFit: 'contain',
                                        cursor: isScanning ? 'pointer' : 'default',
                                        transition: 'all 0.3s var(--transition-smooth)'
                                    }}
                                    title={isScanning ? 'Clique na tela para interagir com o browser!' : ''}
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
                                    {isScanning ? (
                                        <>
                                            <Loader2 size={32} style={{ animation: 'spin 1s linear infinite', color: 'var(--sw-primary)' }} />
                                            <span style={{ fontSize: '13px' }}>Aguardando primeira captura do navegador...</span>
                                        </>
                                    ) : (
                                        <>
                                            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3 }}>
                                                <rect width="18" height="18" x="3" y="3" rx="2" />
                                                <path d="M3 9h18" />
                                                <path d="M9 21V9" />
                                            </svg>
                                            <span style={{ fontSize: '13px' }}>Inicie a varredura para ver o navegador em tempo real.</span>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Painel de Interação Remota */}
                        {isScanning && (
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
                                        placeholder="Digite texto para o campo focado (ex: e-mail, senha)..."
                                        onKeyDown={e => { if (e.key === 'Enter') handleSendText(); }}
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
                                    <button onClick={handleSendText} disabled={!inputText.trim()} style={{ background: 'var(--sw-primary)', color: '#fff', border: 'none', borderRadius: '8px', padding: '8px 16px', fontSize: '12px', fontWeight: 600, cursor: 'pointer', opacity: inputText.trim() ? 1 : 0.6 }}>
                                        Enviar
                                    </button>
                                    <button onClick={onPressEnter} style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid var(--sw-border)', color: '#fff', borderRadius: '8px', padding: '8px 16px', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}>
                                        Enter ↵
                                    </button>
                                    <button onClick={onPressBackspace} style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', borderRadius: '8px', padding: '8px 16px', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}>
                                        Apagar ⌫
                                    </button>
                                </div>
                                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.45)' }}>
                                    💡 Clique na tela acima → depois use os botões para digitar e submeter o login.
                                </span>
                            </div>
                        )}
                    </div>

                    {/* Terminal de Logs */}
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
                            <span>terminal — agent@linkb2b:~ (live_logs)</span>
                            {isScanning && (
                                <div style={{
                                    marginLeft: 'auto',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '5px',
                                    color: '#4ade80',
                                    fontSize: '10px',
                                    fontWeight: 600,
                                }}>
                                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#4ade80', animation: 'pulse 1.5s infinite ease-in-out' }} />
                                    SCANNING
                                </div>
                            )}
                        </div>

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
                                    if (log.startsWith('[System]')) textColor = 'var(--sw-primary)';
                                    else if (log.includes('✅') || log.startsWith('🎉') || log.includes('Login detectado')) textColor = '#4ade80';
                                    else if (log.startsWith('👤') || log.startsWith('[Operator]')) textColor = '#38bdf8';
                                    else if (log.includes('⚠️') || log.includes('Warning')) textColor = '#fbbf24';
                                    else if (log.startsWith('❌') || log.startsWith('[Erro') || log.startsWith('[Error]')) textColor = '#f87171';
                                    else if (log.includes('📊')) textColor = 'rgba(255,255,255,0.5)';
                                    return (
                                        <div key={index} style={{ color: textColor, whiteSpace: 'pre-wrap' }}>
                                            {log}
                                        </div>
                                    );
                                })
                            ) : (
                                <div style={{ color: 'rgba(255, 255, 255, 0.3)', fontStyle: 'italic' }}>
                                    Aguardando tarefas... Terminal inativo.
                                </div>
                            )}
                            <div ref={consoleEndRef} />
                        </div>
                    </div>
                </div>
            </div>

            {/* Erro */}
            {scanError && !isScanning && (
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
                        <strong style={{ fontSize: '14px', color: 'var(--sw-status-danger)' }}>Falha na Automação</strong>
                        <p style={{ fontSize: '13px', color: 'var(--sw-text-subtle)', margin: 0, lineHeight: '1.5' }}>
                            {scanError}
                        </p>
                    </div>
                </div>
            )}

            {/* Resultados */}
            {scanResults.length > 0 && !isScanning && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', animation: 'fadeIn 0.4s' }}>
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
                                Extração concluída: <strong>{scanResults.length}</strong> pessoas importadas.
                            </span>
                        </div>
                        <button
                            onClick={() => {
                                const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(scanResults, null, 4));
                                const a = document.createElement('a');
                                a.setAttribute('href', dataStr);
                                a.setAttribute('download', `linkedin_colaboradores_${Date.now()}.json`);
                                document.body.appendChild(a);
                                a.click();
                                a.remove();
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

                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fill, minmax(285px, 1fr))',
                        gap: '16px',
                        maxHeight: 'calc(100vh - 200px)',
                        overflowY: 'auto',
                        paddingRight: '4px'
                    }}>
                        {scanResults.map((profile, idx) => (
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
                                <div style={{
                                    width: '48px', height: '48px', borderRadius: '50%',
                                    background: 'rgba(255,255,255,0.05)',
                                    border: '1px solid var(--sw-border)',
                                    overflow: 'hidden', display: 'flex',
                                    alignItems: 'center', justifyContent: 'center', flexShrink: 0
                                }}>
                                    {profile.avatar ? (
                                        <img src={profile.avatar} alt={profile.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                            onError={e => {
                                                e.currentTarget.style.display = 'none';
                                                e.currentTarget.parentElement?.insertAdjacentHTML('beforeend', '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--sw-text-muted)" stroke-width="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>');
                                            }}
                                        />
                                    ) : (
                                        <User size={20} style={{ color: 'var(--sw-text-muted)' }} />
                                    )}
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', overflow: 'hidden', width: '100%' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: '4px' }}>
                                        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--sw-text-base)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={profile.name}>
                                            {profile.name}
                                        </span>
                                        <a href={profile.linkedin_url} target="_blank" rel="noreferrer"
                                            style={{ color: 'var(--sw-text-muted)', display: 'flex', flexShrink: 0, transition: 'color 0.2s' }}
                                            onMouseEnter={e => e.currentTarget.style.color = 'var(--sw-primary)'}
                                            onMouseLeave={e => e.currentTarget.style.color = 'var(--sw-text-muted)'}
                                        >
                                            <ExternalLink size={12} />
                                        </a>
                                    </div>
                                    <span style={{ fontSize: '12px', color: 'var(--sw-text-subtle)', lineHeight: '1.3', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', minHeight: '32px' }} title={profile.role}>
                                        {profile.role}
                                    </span>
                                    {profile.location && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--sw-text-muted)' }}>
                                            <MapPin size={10} style={{ flexShrink: 0 }} />
                                            <span style={{ fontSize: '11px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={profile.location}>
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
