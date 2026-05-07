'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
    Send,
    Smile,
    Mic,
    ArrowLeft,
    CheckCheck,
    User2,
    Plus,
    MoreVertical,
} from 'lucide-react';
import { communication } from '@/services/api';
import { Spinner } from './ui';

interface WhatsAppViewProps {
    chatName: string;
    chatId?: string;
    onBack: () => void;
}

interface Message {
    id: string;
    text: string;
    sender: 'me' | 'them';
    time: string;
    timestamp?: number;
}

const formatTime = (tsSeconds?: number) => {
    const date = tsSeconds ? new Date(tsSeconds * 1000) : new Date();
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

export const WhatsAppView: React.FC<WhatsAppViewProps> = ({ chatName, chatId, onBack }) => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [inputText, setInputText] = useState('');
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const fetchHistory = useCallback(async (isPolling = false) => {
        if (!chatId) return;
        if (!isPolling) setLoading(true);
        try {
            const data = await communication.fetchWhatsAppHistory(chatId, 100);
            const fetched: Message[] = (data.messages || []).map((m) => ({
                id: m.id,
                text: m.body,
                sender: m.fromMe ? 'me' : 'them',
                time: formatTime(m.timestamp),
                timestamp: m.timestamp,
            }));

            setMessages((prev) => {
                const lastPrevId = prev.length > 0 ? prev[prev.length - 1].id : null;
                const lastFetchedId = fetched.length > 0 ? fetched[fetched.length - 1].id : null;
                if (lastPrevId !== lastFetchedId || prev.length !== fetched.length) {
                    fetched.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
                    return fetched;
                }
                return prev;
            });
        } catch (error) {
            // Polling silencioso — só logar quando for o load inicial.
            if (!isPolling) console.error('Erro ao buscar histórico do WhatsApp:', error);
        } finally {
            if (!isPolling) setLoading(false);
        }
    }, [chatId]);

    useEffect(() => {
        void fetchHistory(false);
        const interval = window.setInterval(() => {
            void fetchHistory(true);
        }, 5000); // 5s: polling de mensagens WhatsApp
        return () => window.clearInterval(interval);
    }, [fetchHistory]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSendMessage = async () => {
        if (!inputText.trim() || !chatId) return;

        const text = inputText;
        setInputText('');

        const tempId = Date.now().toString();
        const optimistic: Message = {
            id: tempId,
            text,
            sender: 'me',
            time: formatTime(),
        };
        setMessages((prev) => [...prev, optimistic]);

        try {
            await communication.sendWhatsAppDirect(chatId, text);
        } catch (error) {
            console.error('Erro no envio de WhatsApp:', error);
        }
    };

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            position: 'relative',
            overflow: 'hidden',
        }}>
            {/* Wallpaper Padrão Pura sem cor de fundo */}
            <div style={{
                position: 'absolute',
                inset: '0px',
                backgroundImage: 'url("/wpp.png")',
                backgroundRepeat: 'repeat',
                backgroundSize: '600px',
                opacity: 1,
                zIndex: 0,
                pointerEvents: 'none'
            }} />

            {/* Header Estilo waPreviewHeader (Mapeado exatamente do Chat Panel) */}
            <div style={{
                padding: '8px 12px',
                backgroundColor: '#171616',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                zIndex: 10
            }}>
                <button onClick={onBack} style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#868686',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    padding: '4px',
                    borderRadius: '50%',
                    transition: 'background 0.2s'
                }} onMouseOver={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                   onMouseOut={e => e.currentTarget.style.background = 'transparent'}>
                    <ArrowLeft size={20} />
                </button>

                <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '50%',
                    backgroundColor: '#dfe5e7',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    overflow: 'hidden'
                }}>
                    <User2 size={22} color="#868686" />
                </div>

                <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{ color: '#e9edef', fontWeight: 600, fontSize: '14px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{chatName}</div>
                    <div style={{ color: '#868686', fontSize: '11px' }}>online</div>
                </div>

                <div style={{ color: '#868686', cursor: 'pointer', display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <MoreVertical size={18} />
                </div>
            </div>

            {/* Viewport de Mensagens Estilo Chat Thread */}
            <div style={{
                height: '100%',
                overflowY: 'auto',
                padding: '16px',
                paddingTop: '0',
                paddingBottom: '100px', // Espaço para a barra flutuante
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                zIndex: 1,
            }}>
                {loading && messages.length === 0 ? (
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#868686' }}>
                        <Spinner size={32} />
                    </div>
                ) : (
                    <>
                        {messages.map((msg) => {
                            const isMe = msg.sender === 'me';

                            return (
                                <div
                                    key={msg.id}
                                    style={{
                                        alignSelf: isMe ? 'flex-end' : 'flex-start',
                                        backgroundColor: isMe ? '#0b6a3e' : '#131313',
                                        color: '#e9edef',
                                        padding: '8px 12px 6px 14px',
                                        borderRadius: '10px',
                                        borderTopRightRadius: isMe ? '2px' : '10px',
                                        borderTopLeftRadius: isMe ? '10px' : '2px',
                                        maxWidth: '85%',
                                        fontSize: '14.5px',
                                        position: 'relative',
                                        boxShadow: '0 1px 1.5px rgba(0,0,0,0.12)',
                                        minWidth: '70px',
                                        lineHeight: '1.4'
                                    }}
                                >
                                    <div style={{ paddingRight: '45px', overflowWrap: 'break-word' }}>{msg.text}</div>
                                    <div style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'flex-end',
                                        fontSize: '11px',
                                        color: '#868686',
                                        marginTop: '-6px',
                                        gap: '3px',
                                        position: 'absolute',
                                        bottom: '4px',
                                        right: '8px'
                                    }}>
                                        {msg.time}
                                        {isMe && <div style={{ display: 'flex', color: '#53bdeb' }}><CheckCheck size={14} /></div>}
                                    </div>
                                </div>
                            );
                        })}
                    </>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Barra de Entrada Estilo Premium / Zen (Absolute para passar por cima das mensagens) */}
            <div style={{
                padding: '12px 18px 18px 18px',
                width: '100%',
                backgroundColor: 'transparent',
                zIndex: 10,
                position: 'absolute',
                bottom: 0,
                left: 0
            }}>
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    backgroundColor: '#131313e8',
                    padding: '12px',
                    borderRadius: '18px',
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
                    border: '1px solid rgba(255, 255, 255, 0.05)',
                    backdropFilter: 'blur(12px)'
                }}>
                    <div style={{ display: 'flex', gap: '8px', color: '#868686' }}>
                        <button style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: '6px', borderRadius: '6px', transition: 'all 0.2s' }}
                            onMouseOver={e => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                            onMouseOut={e => e.currentTarget.style.backgroundColor = 'transparent'}>
                            <Smile size={22} />
                        </button>
                        <button style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: '6px', borderRadius: '6px', transition: 'all 0.2s' }}
                            onMouseOver={e => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                            onMouseOut={e => e.currentTarget.style.backgroundColor = 'transparent'}>
                            <Plus size={22} />
                        </button>
                    </div>

                    <div style={{
                        flex: 1,
                        backgroundColor: 'transparent',
                        padding: '0 8px',
                        display: 'flex',
                        alignItems: 'center',
                        transition: 'all 0.3s ease',
                    }}>
                        <input
                            type="text"
                            value={inputText}
                            onChange={e => setInputText(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                            placeholder="Digite uma mensagem"
                            style={{
                                width: '100%',
                                border: 'none',
                                background: 'transparent',
                                outline: 'none',
                                color: '#e4e4e7',
                                fontSize: '15px',
                                fontFamily: 'inherit',
                                transition: 'color 0.3s'
                            }}
                        />
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center' }}>
                        {inputText.trim() ? (
                            <button
                                onClick={handleSendMessage}
                                style={{
                                    background: '#34d17c',
                                    border: 'none',
                                    color: '#fff',
                                    cursor: 'pointer',
                                    width: '40px',
                                    height: '40px',
                                    borderRadius: '50%',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    transition: 'all 0.2s ease',
                                    boxShadow: '0 4px 12px rgba(52, 209, 124, 0.3)'
                                }}
                                onMouseOver={e => e.currentTarget.style.transform = 'scale(1.05)'}
                                onMouseOut={e => e.currentTarget.style.transform = 'scale(1)'}
                            >
                                <Send size={20} />
                            </button>
                        ) : (
                            <button style={{ background: 'transparent', border: 'none', color: '#868686', cursor: 'pointer', padding: '6px', borderRadius: '6px', transition: 'all 0.2s' }}
                                onMouseOver={e => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)'}
                                onMouseOut={e => e.currentTarget.style.backgroundColor = 'transparent'}>
                                <Mic size={22} />
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
