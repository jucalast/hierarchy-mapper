'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { RefreshCw, Inbox, MessageSquare, Mail } from 'lucide-react';
import { communication } from '@/services/api';
import type {
    TrackedContact,
    CachedConversation,
    WaMessage,
    EmailMessage,
} from '@/services/api/communication';
import { buildProxyImageUrl } from '@/services/config';
import styles from './MessagesView.module.css';

const CONTACTS_POLL_MS = 30_000; // 30s

// ── Formatadores ──────────────────────────────────────────────────────────────

const formatTime = (ts?: number) => {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
};

const formatDate = (iso?: string) => {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
};

const initials = (name: string) => {
    if (!name) return '';
    return name
        .split(' ')
        .filter(Boolean)
        .slice(0, 2)
        .map((w) => w[0]?.toUpperCase() ?? '')
        .join('');
};

/** Resolve URL de foto do contato: base64 direto, URL via proxy, ou null. */
const resolveAvatar = (pic?: string): string | null => {
    if (!pic) return null;
    if (pic.startsWith('data:image/')) return pic;
    if (pic.startsWith('http')) return buildProxyImageUrl(pic) ?? null;
    return null;
};

/** Avatar com foto ou fallback de iniciais. */
function ContactAvatar({
    name,
    channel,
    profilePic,
    size = 36,
    className,
}: {
    name: string;
    channel: string;
    profilePic?: string;
    size?: number;
    className?: string;
}) {
    const src = resolveAvatar(profilePic);
    const [imgErr, setImgErr] = React.useState(false);

    if (src && !imgErr) {
        return (
            <div className={className} style={{ width: size, height: size, borderRadius: '50%', overflow: 'hidden', flexShrink: 0, border: '1.5px solid var(--sw-border-strong)' }}>
                <img
                    src={src}
                    alt={name}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={() => setImgErr(true)}
                />
            </div>
        );
    }
    return (
        <div 
            className={className} 
            style={{ 
                width: size, 
                height: size, 
                fontSize: size * 0.38, 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                borderRadius: '50%',
                flexShrink: 0
            }}
        >
            {initials(name)}
        </div>
    );
}

// ── WhatsApp Bubbles ──────────────────────────────────────────────────────────

function WaConversation({ messages }: { messages: WaMessage[] }) {
    const endRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    if (!messages.length)
        return (
            <div className={styles.noConversation}>
                <p className={styles.noConversationText}>Nenhuma mensagem encontrada.</p>
            </div>
        );

    return (
        <>
            {messages.map((m, i) => (
                <div
                    key={m.id || i}
                    className={`${styles.waBubbleRow} ${m.fromMe ? styles.waBubbleRowMe : ''}`}
                >
                    <div className={`${styles.waBubble} ${m.fromMe ? styles.waBubbleMe : styles.waBubbleThem}`}>
                        <span className={styles.waBubbleText}>{m.body}</span>
                        {m.timestamp > 0 && (
                            <span className={styles.waBubbleTime}>
                                <span>{formatTime(m.timestamp)}</span>
                                {m.fromMe && (
                                    <span style={{ marginLeft: 4, display: 'inline-flex' }} title="Entregue e lida">
                                        <svg viewBox="0 0 18 11" width="18" height="11" fill="none">
                                            <path d="M12.242 1L6.095 7.147L3.109 4.161L2.014 5.256L6.095 9.337L13.337 2.095L12.242 1Z" fill="#53bdeb"/>
                                            <path d="M16.242 1L10.095 7.147L8.98 6.032L7.885 7.127L10.095 9.337L17.337 2.095L16.242 1Z" fill="#53bdeb"/>
                                        </svg>
                                    </span>
                                )}
                            </span>
                        )}
                    </div>
                </div>
            ))}
            <div ref={endRef} />
        </>
    );
}

// ── Email Thread ──────────────────────────────────────────────────────────────

function EmailConversation({ messages }: { messages: EmailMessage[] }) {
    if (!messages.length)
        return (
            <div className={styles.noConversation}>
                <p className={styles.noConversationText}>Nenhum e-mail encontrado.</p>
            </div>
        );

    return (
        <>
            {messages.map((m, i) => (
                <div
                    key={m.entryId || i}
                    className={`${styles.emailCard} ${
                        m.direction === 'sent' ? styles.emailCardSent : styles.emailCardReceived
                    }`}
                >
                    <span
                        className={`${styles.directionTag} ${
                            m.direction === 'sent' ? styles.directionSent : styles.directionReceived
                        }`}
                    >
                        {m.direction === 'sent' ? 'Enviado' : 'Recebido'}
                    </span>
                    <div className={styles.emailHeader}>
                        <span className={styles.emailFrom}>
                            {m.direction === 'sent' ? `Para: ${m.to}` : m.from}
                        </span>
                        <span className={styles.emailDate}>{formatDate(m.date)}</span>
                    </div>
                    <div className={styles.emailSubject}>{m.subject}</div>
                    <div className={styles.emailPreview}>{m.preview}</div>
                </div>
            ))}
        </>
    );
}

// ── Componente principal ──────────────────────────────────────────────────────

interface MessagesViewProps {
    onBack?: () => void;
    orgId?: number | null;
}

export function MessagesView({ onBack, orgId }: MessagesViewProps) {
    const [contacts, setContacts] = useState<TrackedContact[]>([]);
    const [channelFilter, setChannelFilter] = useState<'all' | 'whatsapp' | 'email'>('all');
    const [selected, setSelected] = useState<TrackedContact | null>(null);
    const [conversation, setConversation] = useState<CachedConversation | null>(null);
    const [loadingContacts, setLoadingContacts] = useState(true);
    const [loadingConv, setLoadingConv] = useState(false);
    const [syncing, setSyncing] = useState(false);

    const loadContacts = useCallback(async (isSilent = false) => {
        if (!isSilent) {
            setLoadingContacts(true);
        }
        try {
            const resp = await communication.fetchTrackedContacts(
                channelFilter === 'all' ? undefined : channelFilter,
                orgId,
            );
            console.log('MessagesView fetchTrackedContacts resp:', resp);
            const newContacts = resp.contacts || [];
            
            setContacts((prev) => {
                const hasChanged = JSON.stringify(prev) !== JSON.stringify(newContacts);
                return hasChanged ? newContacts : prev;
            });
        } catch (err) {
            console.error('MessagesView fetchTrackedContacts error:', err);
            if (!isSilent) {
                setContacts([]);
            }
        } finally {
            if (!isSilent) {
                setLoadingContacts(false);
            }
        }
    }, [channelFilter, orgId]);

    useEffect(() => {
        void loadContacts(false);
        // Polling periódico para detectar novas mensagens
        const interval = window.setInterval(() => { void loadContacts(true); }, CONTACTS_POLL_MS);
        return () => window.clearInterval(interval);
    }, [loadContacts]);

    const loadConversation = useCallback(async (contact: TrackedContact, isSilent = false) => {
        setSelected(contact);
        if (!isSilent) {
            setConversation(null);
            setLoadingConv(true);
        }
        try {
            const data = await communication.fetchCachedConversation(
                contact.contact_identifier,
                contact.channel
            );
            setConversation((prev) => {
                const hasChanged = JSON.stringify(prev) !== JSON.stringify(data);
                return hasChanged ? data : prev;
            });
            // Marca como lido ao abrir a conversa
            if (contact.has_unread) {
                void communication.markConversationRead(contact.contact_identifier, contact.channel);
                setContacts((prev) =>
                    prev.map((c) =>
                        c.contact_identifier === contact.contact_identifier && c.channel === contact.channel
                            ? { ...c, has_unread: false }
                            : c
                    )
                );
            }
        } catch (err) {
            console.error('MessagesView loadConversation error:', err);
            if (!isSilent) {
                setConversation(null);
            }
        } finally {
            if (!isSilent) {
                setLoadingConv(false);
            }
        }
    }, []);

    // Polling periódico da conversa selecionada a cada 10 segundos
    useEffect(() => {
        if (!selected) return;
        const interval = window.setInterval(() => {
            void loadConversation(selected, true);
        }, 10000);
        return () => window.clearInterval(interval);
    }, [selected, loadConversation]);

    const handleSync = async () => {
        if (!selected || selected.channel !== 'whatsapp' || syncing) return;
        setSyncing(true);
        try {
            await communication.syncContact(selected.contact_identifier);
            await loadConversation(selected);
        } finally {
            setSyncing(false);
        }
    };

    const filteredContacts =
        channelFilter === 'all'
            ? contacts
            : contacts.filter((c) => c.channel === channelFilter);

    return (
        <div className={styles.container}>
            {/* ── Sidebar ── */}
            <div className={styles.sidebar}>
                <div className={styles.filterRow}>
                    {(['all', 'whatsapp', 'email'] as const).map((ch) => (
                        <button
                            key={ch}
                            className={`${styles.filterBtn} ${channelFilter === ch ? styles.filterBtnActive : ''}`}
                            onClick={() => setChannelFilter(ch)}
                        >
                            {ch === 'all' && <Inbox size={14} />}
                            {ch === 'whatsapp' && <MessageSquare size={14} />}
                            {ch === 'email' && <Mail size={14} />}
                            <span>{ch === 'all' ? 'Todos' : ch === 'whatsapp' ? 'WhatsApp' : 'E-mail'}</span>
                        </button>
                    ))}
                </div>

                <div className={styles.contactList}>
                    {loadingContacts ? (
                        <div className={styles.emptyState}>Carregando...</div>
                    ) : filteredContacts.length === 0 ? (
                        <div className={styles.emptyState}>
                            Nenhuma conversa salva ainda.
                            <br />
                            Peça ao agente para buscar mensagens de um contato.
                        </div>
                    ) : (
                        filteredContacts.map((c) => (
                            <div
                                key={`${c.contact_identifier}|${c.channel}`}
                                className={`${styles.contactItem} ${
                                    selected?.contact_identifier === c.contact_identifier &&
                                    selected?.channel === c.channel
                                        ? styles.contactItemActive
                                        : ''
                                }`}
                                onClick={() => loadConversation(c)}
                            >
                                <ContactAvatar
                                    name={c.contact_name}
                                    channel={c.channel}
                                    profilePic={c.profile_pic}
                                    size={32}
                                    className={`${styles.contactAvatar} ${
                                        c.channel === 'whatsapp'
                                            ? styles.contactAvatarWa
                                            : styles.contactAvatarEmail
                                    }`}
                                />
                                <div className={styles.contactInfo}>
                                    <div className={styles.contactName}>
                                        {c.contact_name}
                                        {c.is_key_contact && (
                                            <span className={styles.keyContactStar} title="Contato-chave / Decisor"> ★</span>
                                        )}
                                    </div>
                                    <div className={styles.contactMeta}>
                                        {c.last_message_preview || c.org_name || '—'}
                                    </div>
                                </div>
                                {c.has_unread && (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', paddingRight: 4, flexShrink: 0 }}>
                                        <span className={styles.unreadDot} title="Mensagem nova" />
                                    </div>
                                )}
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* ── Painel de conversa ── */}
            <div className={styles.conversationPanel}>
                {!selected ? (
                    <div className={styles.noConversation}>
                        <div className={styles.noConversationIcon}>
                            <Inbox size={22} />
                        </div>
                        <p className={styles.noConversationText}>
                            Selecione um contato para ver a conversa.
                        </p>
                    </div>
                ) : (
                    <>
                        <div className={styles.panelHeader}>
                            <ContactAvatar
                                name={selected.contact_name}
                                channel={selected.channel}
                                profilePic={selected.profile_pic}
                                size={36}
                                className={`${styles.contactAvatar} ${
                                    selected.channel === 'whatsapp'
                                        ? styles.contactAvatarWa
                                        : styles.contactAvatarEmail
                                }`}
                            />
                            <div className={styles.panelHeaderInfo}>
                                <div className={styles.panelHeaderName}>{selected.contact_name}</div>
                                <div className={styles.panelHeaderSub}>
                                    {selected.channel === 'whatsapp' ? (
                                        <>WhatsApp · {selected.contact_identifier}</>
                                    ) : (
                                        <>E-mail · {selected.contact_identifier}</>
                                    )}
                                    {selected.org_name && ` · ${selected.org_name}`}
                                </div>
                            </div>
                            {selected.channel === 'whatsapp' && (
                                <button
                                    className={`${styles.syncBtn} ${syncing ? styles.syncBtnLoading : ''}`}
                                    onClick={handleSync}
                                    disabled={syncing}
                                    title="Sincronizar mensagens do WhatsApp"
                                >
                                    <RefreshCw size={12} className={syncing ? styles.spin : ''} />
                                    {syncing ? 'Sincronizando...' : 'Atualizar'}
                                </button>
                            )}
                        </div>

                        <div className={`${styles.messagesArea} ${selected.channel === 'whatsapp' ? styles.messagesAreaWa : ''}`}>
                            {loadingConv ? (
                                <div className={styles.noConversation}>
                                    <p className={styles.noConversationText}>Carregando mensagens...</p>
                                </div>
                            ) : !conversation ? (
                                <div className={styles.noConversation}>
                                    <p className={styles.noConversationText}>
                                        Não foi possível carregar a conversa.
                                    </p>
                                </div>
                            ) : selected.channel === 'whatsapp' ? (
                                <WaConversation messages={conversation.messages as WaMessage[]} />
                            ) : (
                                <EmailConversation messages={conversation.messages as EmailMessage[]} />
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
