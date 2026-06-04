'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { RefreshCw, Inbox, MessageSquare, Mail, ChevronDown, ChevronRight, ChevronLeft, Phone, Zap, AlertOctagon, Clock, PhoneCall } from 'lucide-react';
import { ai, communication } from '@/services/api';
import type {
    TrackedContact,
    CachedConversation,
    WaMessage,
    EmailMessage,
    SavedCallSession,
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

const isUserEmail = (str: string | undefined, userEmail: string | undefined): boolean => {
    if (!str || !userEmail) return false;
    const cleanedStr = str.toLowerCase().trim();
    const cleanedUser = userEmail.toLowerCase().trim();
    
    // Extract email from <...> or (...)
    const emailMatch = cleanedStr.match(/<([^>]+)>/) || cleanedStr.match(/\(([^)]+)\)/);
    const emailPart = emailMatch ? emailMatch[1].trim() : '';
    
    if (emailPart === cleanedUser) return true;
    if (cleanedStr.includes(cleanedUser)) return true;
    
    const userPart = cleanedUser.split('@')[0];
    if (userPart) {
        // Check if legacy Exchange DN contains user part
        const isLegacy = cleanedStr.startsWith('/') || cleanedStr.includes('o=exchangelabs') || cleanedStr.includes('cn=');
        if (isLegacy && cleanedStr.includes(userPart)) {
            return true;
        }
    }
    
    return false;
};

/**
 * Limpa e formata o remetente de e-mail, especialmente para endereços internos do Exchange (LegacyExchangeDN)
 * que começam com "/o=ExchangeLabs/ou=..."
 */
const cleanEmailSender = (fromStr: string, fallbackEmailOrName?: string, userEmail?: string): string => {
    if (!fromStr) return '';
    if (userEmail && isUserEmail(fromStr, userEmail)) {
        return '(pra mim)';
    }

    const formatName = (str: string): string => {
        return str
            .replace(/\./g, ' ')
            .split(' ')
            .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
            .join(' ');
    };

    const isRawGuid = (str: string): boolean => {
        const cleaned = str.trim().split(/[<(]/)[0].trim();
        // Um GUID / identificador hexadecimal bruto possui apenas dígitos hexadecimais, hifens ou comprimento longo sem letras além de a-f
        return /^[a-fA-F0-9\-_]+$/.test(cleaned) || (cleaned.length > 20 && !/[g-zG-Z]/.test(cleaned));
    };

    // Se contiver um e-mail padrão entre < > ou ( ), tenta extrair
    const emailMatch = fromStr.match(/<([^>]+)>/) || fromStr.match(/\(([^)]+)\)/);
    let emailPart = emailMatch ? emailMatch[1].trim() : '';
    if (!emailPart && fromStr.includes('@')) {
        emailPart = fromStr.trim();
    }

    let namePart = fromStr.split(/[<(]/)[0].trim();
    let isLegacyDN = fromStr.startsWith('/') || fromStr.toLowerCase().includes('o=exchangelabs');
    let extractedCN = '';
    let isCnUgly = false;

    if (isLegacyDN) {
        const cnParts = fromStr.split(/cn=/i);
        if (cnParts.length > 1) {
            let lastPart = cnParts[cnParts.length - 1].trim();
            lastPart = lastPart.split('/')[0].split(';')[0].trim();
            
            const hyphenParts = lastPart.split('-');
            if (hyphenParts.length > 1) {
                const possibleName = hyphenParts[hyphenParts.length - 1];
                if (possibleName && possibleName.length > 2 && !/^\d+$/.test(possibleName)) {
                    lastPart = possibleName;
                }
            }
            extractedCN = lastPart;
            isCnUgly = isRawGuid(lastPart);
        }
    }

    if (extractedCN && !isCnUgly) {
        return formatName(extractedCN);
    }

    if (isCnUgly || isRawGuid(namePart) || !namePart || namePart.includes('@') || isLegacyDN) {
        const isFromFallback = fallbackEmailOrName && (
            isLegacyDN || 
            (emailPart && fallbackEmailOrName.toLowerCase().includes(emailPart.toLowerCase())) ||
            (emailPart && emailPart.toLowerCase().includes(fallbackEmailOrName.split('@')[0].toLowerCase()))
        );

        if (isFromFallback && fallbackEmailOrName) {
            if (fallbackEmailOrName.includes('@')) {
                const username = fallbackEmailOrName.split('@')[0];
                if (!isRawGuid(username)) {
                    return formatName(username);
                }
            } else if (!isRawGuid(fallbackEmailOrName) && !fallbackEmailOrName.startsWith('/')) {
                return formatName(fallbackEmailOrName);
            }
        }

        if (emailPart) {
            const username = emailPart.split('@')[0];
            if (!isRawGuid(username)) {
                return formatName(username);
            }
            return emailPart;
        }
    }

    if (namePart && !isRawGuid(namePart) && !isLegacyDN) {
        return formatName(namePart);
    }

    return fromStr;
};

/** Avatar com foto ou fallback de iniciais. */
function ContactAvatar({
    name,
    channel,
    profilePic,
    orgLogo,
    orgDomain,
    contactIdentifier,
    size = 36,
    className,
    showChannelBadge = false,
}: {
    name: string;
    channel: string;
    profilePic?: string;
    orgLogo?: string;
    orgDomain?: string;
    contactIdentifier?: string;
    size?: number;
    className?: string;
    showChannelBadge?: boolean;
}) {
    const cleanedName = channel === 'email' ? cleanEmailSender(name) : name;
    let src = resolveAvatar(profilePic);

    if (!src) {
        if (orgLogo) {
            src = resolveAvatar(orgLogo);
        } else {
            const domain = orgDomain || (channel === 'email' && contactIdentifier?.includes('@') ? contactIdentifier.split('@').pop() : null);
            const excludedDomains = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'icloud.com'];
            if (domain && !excludedDomains.includes(domain.toLowerCase().trim())) {
                src = `https://unavatar.io/${domain.trim()}`;
            }
        }
    }
    const [imgErr, setImgErr] = React.useState(false);

    const badgeSize = Math.max(16, Math.round(size * 0.5));
    const iconSize = Math.round(size * 0.24);

    const renderBadge = () => {
        if (!showChannelBadge) return null;
        if (channel === 'ligacao') {
            return (
                <div
                    style={{
                        position: 'absolute',
                        bottom: -2,
                        right: -2,
                        width: badgeSize,
                        height: badgeSize,
                        borderRadius: '50%',
                        backgroundColor: 'var(--chat-accent-color)',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        zIndex: 2,
                        pointerEvents: 'none',
                        overflow: 'hidden',
                        boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
                    }}
                >
                    <Phone size={iconSize} style={{ strokeWidth: 2.5 }} />
                </div>
            );
        }
        const isWa = channel === 'whatsapp';
        const imgSrc = isWa ? '/wppicon.png' : '/outlook.png';

        return (
            <div
                style={{
                    position: 'absolute',
                    bottom: -2,
                    right: -2,
                    width: badgeSize,
                    height: badgeSize,
                    borderRadius: '0px',
                    backgroundColor: 'transparent',
                    border: 'none',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: 'none',
                    zIndex: 2,
                    pointerEvents: 'none',
                    overflow: 'visible',
                }}
            >
                <img
                    src={imgSrc}
                    alt={channel}
                    style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'contain',
                        borderRadius: '0px',
                        filter: 'none',
                    }}
                />
            </div>
        );
    };

    if (src && !imgErr) {
        return (
            <div 
                className={className} 
                style={{ 
                    width: size, 
                    height: size, 
                    borderRadius: '50%', 
                    overflow: 'visible', // Permite que o badge apareça fora dos limites circulares
                    flexShrink: 0, 
                    border: 'none',
                    position: 'relative',
                    boxSizing: 'border-box'
                }}
            >
                <img
                    src={src}
                    alt={cleanedName}
                    style={{ 
                        width: '100%', 
                        height: '100%', 
                        objectFit: 'cover',
                        borderRadius: '50%' // Garante o arredondamento perfeito da imagem interna
                    }}
                    onError={() => setImgErr(true)}
                />
                {renderBadge()}
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
                flexShrink: 0,
                position: 'relative',
                overflow: 'visible' // Permite que o badge apareça fora dos limites circulares
            }}
        >
            {initials(cleanedName)}
            {renderBadge()}
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

function EmailConversation({ 
    messages, 
    contactName, 
    contactIdentifier, 
    userEmail 
}: { 
    messages: EmailMessage[]; 
    contactName: string; 
    contactIdentifier: string; 
    userEmail: string; 
}) {
    const [expandedEmails, setExpandedEmails] = useState<Record<string, boolean>>({});

    const toggleEmail = (entryId: string, isLatest: boolean) => {
        setExpandedEmails(prev => ({
            ...prev,
            [entryId]: !(prev[entryId] !== undefined ? prev[entryId] : isLatest)
        }));
    };

    if (!messages.length)
        return (
            <div className={styles.noConversation}>
                <p className={styles.noConversationText}>Nenhum e-mail encontrado.</p>
            </div>
        );

    return (
        <div className={styles.emailThreadDetails}>
            {/* Lista de Mensagens da Thread */}
            <div className={styles.emailMessageList}>
                {messages.map((m, idx) => {
                    const totalMsgs = messages.length;
                    const isLatest = idx === totalMsgs - 1;
                    const expanded = expandedEmails[m.entryId] !== undefined 
                        ? expandedEmails[m.entryId] 
                        : isLatest;

                    const isSent = m.direction === 'sent' || isUserEmail(m.from, userEmail);
                    const cleanedSender = isSent 
                        ? '(pra mim)' 
                        : cleanEmailSender(m.from, contactName || contactIdentifier, userEmail);

                    return (
                        <div
                            key={m.entryId || idx}
                            className={`${styles.emailMessageItem} ${
                                m.direction === 'sent' 
                                    ? styles.emailMessageItemSent 
                                    : styles.emailMessageItemReceived
                            }`}
                        >
                            {/* Cabeçalho do E-mail (Clicável) */}
                            <div
                                className={styles.emailMessageHeader}
                                onClick={() => toggleEmail(m.entryId, isLatest)}
                            >
                                <ContactAvatar
                                    name={cleanedSender}
                                    channel="email"
                                    contactIdentifier={contactIdentifier}
                                    size={32}
                                    className={styles.emailMessageAvatar}
                                />
                                
                                <div className={styles.emailMessageSenderInfo}>
                                    <div className={styles.emailMessageRow}>
                                        <span className={styles.emailMessageSenderName} title={m.from}>
                                            {cleanedSender}
                                        </span>
                                        <span className={styles.emailMessageDate}>
                                            {formatDate(m.date)}
                                        </span>
                                    </div>
                                    <div className={styles.emailMessageRecipients}>
                                        {isSent 
                                            ? `para: ${m.to}` 
                                            : (isUserEmail(m.to, userEmail) 
                                                ? `para mim (${m.to})` 
                                                : `para: ${m.to}`)}
                                    </div>
                                    
                                    {/* Se colapsado, mostra o preview em uma linha */}
                                    {!expanded && (
                                        <div className={styles.emailMessagePreviewText}>
                                            {m.preview}
                                        </div>
                                    )}
                                </div>

                                <div className={styles.emailMessageChevron}>
                                    {expanded ? (
                                        <ChevronDown size={16} />
                                    ) : (
                                        <ChevronRight size={16} />
                                    )}
                                </div>
                            </div>

                            {/* Corpo do E-mail (Expandido) */}
                            {expanded && (
                                <div className={styles.emailMessageBody}>
                                    <div className={styles.emailMessageBodyContent}>
                                        {m.body || m.preview}
                                    </div>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ── Call Conversation ────────────────────────────────────────────────────────

function CallConversation({
    messages,
    latestInsight,
    flightPlan,
    contactName,
    createdAt,
}: {
    messages: Array<{ id?: string | number; role: string; text: string; timestamp?: number }>;
    latestInsight?: any;
    flightPlan?: any;
    contactName: string;
    createdAt?: string;
}) {
    const endRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const formatCallTime = (ts?: number) => {
        if (!ts) return '';
        const d = new Date(ts * 1000);
        return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    };

    const callDate = createdAt
        ? new Date(createdAt).toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
        : null;

    return (
        <div className={styles.callConversationContainer}>
            {/* ── Header de data da ligação ── */}
            {callDate && (
                <div className={styles.callDateHeader}>
                    <Clock size={12} />
                    <span>Ligação realizada em {callDate}</span>
                </div>
            )}

            {/* ── Resumo do Copiloto ── */}
            {latestInsight && (
                <div className={styles.callInsightSummary}>
                    <div className={styles.callInsightHeader}>
                        <Zap size={14} className={styles.callInsightZap} />
                        <span className={styles.callInsightTitle}>Resumo do Copiloto</span>
                        {latestInsight.current_step && (
                            <span className={styles.callInsightStep}>{latestInsight.current_step}</span>
                        )}
                    </div>
                    <div className={styles.callInsightContent}>
                        {latestInsight.suggestion && (
                            <div className={styles.callInsightItem}>
                                <MessageSquare size={12} className={styles.callInsightItemIcon} />
                                <div>
                                    <div className={styles.callInsightItemLabel}>Sugestão do Vendedor</div>
                                    <p className={styles.callInsightItemText}>{latestInsight.suggestion}</p>
                                </div>
                            </div>
                        )}
                        {latestInsight.objection_handling && (
                            <div className={`${styles.callInsightItem} ${styles.callInsightItemDanger}`}>
                                <AlertOctagon size={12} className={styles.callInsightItemIconDanger} />
                                <div>
                                    <div className={styles.callInsightItemLabelDanger}>Objeção Detectada</div>
                                    <p className={styles.callInsightItemText}>{latestInsight.objection_handling}</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ── Plano de Voo ── */}
            {flightPlan?.steps && Array.isArray(flightPlan.steps) && flightPlan.steps.length > 0 && (
                <div className={styles.callFlightPlan}>
                    <div className={styles.callFlightPlanHeader}>
                        <PhoneCall size={13} />
                        <span>Plano de Voo</span>
                    </div>
                    <div className={styles.callFlightPlanSteps}>
                        {flightPlan.steps.map((step: any, idx: number) => (
                            <div key={idx} className={styles.callFlightPlanStep}>
                                <div className={styles.callFlightPlanDot} />
                                <div className={styles.callFlightPlanStepText}>
                                    <strong>{step.label}</strong>
                                    {step.content && <span>{step.content}</span>}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ── Divisor ── */}
            <div className={styles.callTranscriptDivider}>
                <span>Transcrição da Ligação</span>
            </div>

            {/* ── Transcript ── */}
            {messages.length === 0 ? (
                <div className={styles.noConversation}>
                    <p className={styles.noConversationText}>Nenhuma transcrição disponível.</p>
                </div>
            ) : (
                <div className={styles.callTranscript}>
                    {messages.map((m, i) => {
                        const isMe = m.role === 'Vendedor';
                        return (
                            <div
                                key={m.id ?? i}
                                className={`${styles.callBubbleRow} ${isMe ? styles.callBubbleRowMe : styles.callBubbleRowThem}`}
                            >
                                <div className={`${styles.callBubble} ${isMe ? styles.callBubbleMe : styles.callBubbleThem}`}>
                                    <div className={styles.callBubbleMeta}>
                                        {isMe ? 'Você (Vendedor)' : contactName || 'Cliente'}
                                    </div>
                                    <div className={styles.callBubbleText}>{m.text}</div>
                                    {m.timestamp ? (
                                        <div className={styles.callBubbleTime}>{formatCallTime(m.timestamp)}</div>
                                    ) : null}
                                </div>
                            </div>
                        );
                    })}
                    <div ref={endRef} />
                </div>
            )}
        </div>
    );
}

// ── Componente principal ──────────────────────────────────────────────────────

interface MessagesViewProps {
    onBack?: () => void;
    orgId?: number | null;
}

export function MessagesView({ onBack, orgId }: MessagesViewProps) {
    const [contacts, setContacts] = useState<TrackedContact[]>([]);
    const [userEmail, setUserEmail] = useState<string>('');

    useEffect(() => {
        const fetchUserEmail = async () => {
            try {
                const ints = await ai.getIntegrations();
                const email = ints?.outlook?.credentials?.email_user;
                if (email) {
                    setUserEmail(email);
                    console.log('Successfully fetched user email from integrations:', email);
                }
            } catch (err) {
                console.error('Error fetching user email in MessagesView:', err);
            }
        };
        void fetchUserEmail();
    }, []);
    const [channelFilter, setChannelFilter] = useState<'all' | 'whatsapp' | 'email' | 'ligacao'>('all');
    const [selected, setSelected] = useState<TrackedContact | null>(null);
    const [conversation, setConversation] = useState<CachedConversation | null>(null);
    const [loadingContacts, setLoadingContacts] = useState(true);
    const [loadingConv, setLoadingConv] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [emailConversations, setEmailConversations] = useState<Record<string, CachedConversation>>({});
    const [loadingEmails, setLoadingEmails] = useState(false);
    const [calls, setCalls] = useState<SavedCallSession[]>([]);
    const [loadingCalls, setLoadingCalls] = useState(false);
    const [selectedCallSession, setSelectedCallSession] = useState<any>(null);

    const loadCallHistory = useCallback(async () => {
        setLoadingCalls(true);
        try {
            const resp = await communication.fetchCallHistory();
            if (resp && resp.ok) {
                setCalls(resp.calls || []);
            }
        } catch (err) {
            console.error("Error loading call history:", err);
        } finally {
            setLoadingCalls(false);
        }
    }, []);

    const loadContacts = useCallback(async (isSilent = false) => {
        if (!isSilent) {
            setLoadingContacts(true);
        }
        try {
            if (channelFilter === 'ligacao') {
                setContacts([]);
                setLoadingContacts(false);
                return;
            }

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
        void loadCallHistory();
        // Polling periódico para detectar novas mensagens e ligações
        const interval = window.setInterval(() => {
            void loadContacts(true);
            void loadCallHistory();
        }, CONTACTS_POLL_MS);
        return () => window.clearInterval(interval);
    }, [loadContacts, loadCallHistory]);

    // Pre-fetch e-mail conversations for all e-mail contacts to extract threads
    useEffect(() => {
        const emailContacts = contacts.filter((c) => c.channel === 'email');
        if (emailContacts.length === 0) return;

        const preFetchAll = async () => {
            setLoadingEmails(true);
            try {
                const newMap = { ...emailConversations };
                let changed = false;

                await Promise.all(
                    emailContacts.map(async (c) => {
                        try {
                            const data = await communication.fetchCachedConversation(
                                c.contact_identifier,
                                c.channel
                            );
                            if (JSON.stringify(newMap[c.contact_identifier]) !== JSON.stringify(data)) {
                                newMap[c.contact_identifier] = data;
                                changed = true;
                            }
                        } catch (err) {
                            console.error('Error pre-fetching email conversation:', err);
                        }
                    })
                );

                if (changed) {
                    setEmailConversations(newMap);
                }
            } catch (err) {
                console.error('Error pre-fetching emails:', err);
            } finally {
                setLoadingEmails(false);
            }
        };

        void preFetchAll();
    }, [contacts]);

    const loadConversation = useCallback(async (contact: TrackedContact, isSilent = false, targetThreadId?: string) => {
        setSelected(contact);
        if (contact.channel === 'email') {
            if (targetThreadId) {
                setActiveEmailThreadId(targetThreadId);
            }
        } else {
            setActiveEmailThreadId(null);
        }

        if (contact.channel === 'ligacao' as any) {
            if (!isSilent) {
                setSelectedCallSession(null);
                setConversation(null);
                setLoadingConv(true);
            }
            try {
                const resp = await communication.fetchCallSession(contact.contact_identifier);
                if (resp && resp.ok) {
                    setSelectedCallSession(resp);
                    // Also populate conversation so the panel doesn't show "no conversation"
                    const mappedConv: CachedConversation = {
                        contact_identifier: resp.id,
                        contact_name: resp.contact_name,
                        channel: 'ligacao' as any,
                        messages: [] as any,
                        message_count: resp.messages?.length ?? 0
                    };
                    setConversation(mappedConv);
                }
            } catch (err) {
                console.error("Error loading call session:", err);
            } finally {
                if (!isSilent) {
                    setLoadingConv(false);
                }
            }
            return;
        }

        const cached = contact.channel === 'email' ? emailConversations[contact.contact_identifier] : null;
        if (cached) {
            setConversation(cached);
        } else {
            if (!isSilent) {
                setConversation(null);
                setLoadingConv(true);
            }
        }

        try {
            const data = await communication.fetchCachedConversation(
                contact.contact_identifier,
                contact.channel
            );
            setConversation((prev) => {
                const hasChanged = JSON.stringify(prev) !== JSON.stringify(data);
                
                // Update cache map
                if (contact.channel === 'email') {
                    setEmailConversations((prevMap: Record<string, CachedConversation>) => {
                        if (JSON.stringify(prevMap[contact.contact_identifier]) !== JSON.stringify(data)) {
                            return {
                                ...prevMap,
                                [contact.contact_identifier]: data
                            };
                        }
                        return prevMap;
                    });
                }

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
            if (!isSilent && !cached) {
                setConversation(null);
            }
        } finally {
            if (!isSilent) {
                setLoadingConv(false);
            }
        }
    }, [emailConversations]);

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

    const [activeEmailThreadId, setActiveEmailThreadId] = useState<string | null>(null);

    const cleanSubject = (subject: string): string => {
        if (!subject) return 'sem assunto';
        let cleaned = subject;
        let prev = '';
        while (cleaned !== prev) {
            prev = cleaned;
            cleaned = cleaned.replace(/^(re|res|fwd|enc|respondo|encaminhado|reply|forward)(\[\d+\])?:\s*/i, '').trim();
        }
        return cleaned.replace(/\s+/g, ' ').toLowerCase();
    };

    const emailThreads = React.useMemo(() => {
        if (!conversation || selected?.channel !== 'email') return [];
        const emailMsgs = conversation.messages as EmailMessage[];
        const threadsMap = new Map<string, EmailMessage[]>();
        emailMsgs.forEach((m) => {
            const key = cleanSubject(m.subject);
            if (!threadsMap.has(key)) {
                threadsMap.set(key, []);
            }
            threadsMap.get(key)!.push(m);
        });

        const list = Array.from(threadsMap.entries()).map(([key, msgs]) => {
            const mostRecent = msgs[0];
            const chronologicalMsgs = [...msgs].reverse();
            return {
                id: key,
                subject: mostRecent.subject,
                messages: chronologicalMsgs,
                lastMessageDate: mostRecent.date,
            };
        });

        list.sort((a, b) => new Date(b.lastMessageDate).getTime() - new Date(a.lastMessageDate).getTime());
        return list;
    }, [conversation, selected]);

    useEffect(() => {
        if (selected?.channel === 'email' && emailThreads.length > 0) {
            if (!activeEmailThreadId || !emailThreads.some(t => t.id === activeEmailThreadId)) {
                setActiveEmailThreadId(emailThreads[0].id);
            }
        } else if (selected?.channel !== 'email') {
            setActiveEmailThreadId(null);
        }
    }, [emailThreads, selected, activeEmailThreadId]);

    const activeThread = emailThreads.find(t => t.id === activeEmailThreadId) || emailThreads[0];

    const sidebarItems = React.useMemo(() => {
        interface UnifiedSidebarItem {
            id: string;
            type: 'whatsapp' | 'email_thread' | 'call';
            contact: TrackedContact;
            threadId?: string;
            subject?: string;
            lastMessagePreview?: string;
            lastMessageDate?: string;
            messageCount?: number;
            hasUnread?: boolean;
            lastMessageFrom?: string;
        }

        const items: UnifiedSidebarItem[] = [];

        // Adiciona contatos e e-mails se o filtro não for estritamente de ligações
        if (channelFilter !== 'ligacao') {
            contacts.forEach((c) => {
                if (c.channel === 'whatsapp') {
                    items.push({
                        id: `whatsapp|${c.contact_identifier}`,
                        type: 'whatsapp',
                        contact: c,
                        subject: c.contact_name,
                        lastMessagePreview: c.last_message_preview,
                        lastMessageDate: c.fetched_at ? new Date(c.fetched_at).toISOString() : undefined,
                        hasUnread: c.has_unread,
                    });
                } else if (c.channel === 'email') {
                    const conv = emailConversations[c.contact_identifier];
                    if (!conv) {
                        // Fallback item when still loading
                        items.push({
                            id: `email_loading|${c.contact_identifier}`,
                            type: 'email_thread',
                            contact: c,
                            threadId: 'loading',
                            subject: cleanEmailSender(c.contact_name, c.contact_identifier, userEmail),
                            lastMessagePreview: c.last_message_preview || 'Carregando e-mails...',
                            hasUnread: c.has_unread,
                        });
                    } else {
                        // Group messages into threads
                        const emailMsgs = conv.messages as EmailMessage[];
                        const threadsMap = new Map<string, EmailMessage[]>();
                        emailMsgs.forEach((m) => {
                            const key = cleanSubject(m.subject);
                            if (!threadsMap.has(key)) {
                                threadsMap.set(key, []);
                            }
                            threadsMap.get(key)!.push(m);
                        });

                        threadsMap.forEach((msgs, key) => {
                            const mostRecent = msgs[0];
                            const chronologicalMsgs = [...msgs].reverse();
                            items.push({
                                id: `email_thread|${c.contact_identifier}|${key}`,
                                type: 'email_thread',
                                contact: c,
                                threadId: key,
                                subject: mostRecent.subject,
                                lastMessagePreview: mostRecent.preview || '',
                                lastMessageDate: mostRecent.date,
                                messageCount: chronologicalMsgs.length,
                                hasUnread: c.has_unread && mostRecent.direction === 'received',
                                lastMessageFrom: mostRecent.from,
                            });
                        });
                    }
                }
            });
        }

        // Adiciona sessões de ligações se o filtro for todos ou ligações
        if (channelFilter === 'all' || channelFilter === 'ligacao') {
            calls.forEach((call) => {
                items.push({
                    id: `call|${call.id}`,
                    type: 'call',
                    contact: {
                        contact_identifier: call.id,
                        contact_name: call.contact_name,
                        channel: 'ligacao' as any,
                        message_count: call.message_count,
                        org_name: '',
                        profile_pic: call.profile_pic || null,
                    } as any,
                    threadId: call.id,
                    subject: call.contact_name,
                    lastMessagePreview: call.phone || `${call.message_count} falas gravadas`,
                    lastMessageDate: call.created_at,
                    messageCount: call.message_count,
                    hasUnread: false
                });
            });
        }

        // Sort items by last message date if available
        items.sort((a, b) => {
            const dateA = a.lastMessageDate ? new Date(a.lastMessageDate).getTime() : 0;
            const dateB = b.lastMessageDate ? new Date(b.lastMessageDate).getTime() : 0;
            if (dateA && dateB) {
                return dateB - dateA; // descending chronological order (most recent first)
            }
            return 0;
        });

        return items;
    }, [contacts, emailConversations, userEmail]);

    return (
        <div className={styles.container}>
            {/* ── Sidebar ── */}
            <div className={styles.sidebar}>
                <div className={styles.filterRow}>
                    {(['all', 'whatsapp', 'email', 'ligacao'] as const).map((ch) => (
                        <button
                            key={ch}
                            className={`${styles.filterBtn} ${channelFilter === ch ? styles.filterBtnActive : ''}`}
                            onClick={() => setChannelFilter(ch)}
                            title={ch === 'all' ? 'Todos' : ch === 'whatsapp' ? 'WhatsApp' : ch === 'email' ? 'E-mail' : 'Ligações'}
                        >
                            {ch === 'all' && <Inbox size={15} />}
                            {ch === 'whatsapp' && <MessageSquare size={15} />}
                            {ch === 'email' && <Mail size={15} />}
                            {ch === 'ligacao' && <Phone size={15} />}
                        </button>
                    ))}
                </div>

                <div className={styles.contactList}>
                    {loadingContacts || loadingCalls ? (
                        <div className={styles.emptyState}>Carregando...</div>
                    ) : sidebarItems.length === 0 ? (
                        <div className={styles.emptyState}>
                            Nenhuma conversa ou ligação salva ainda.
                        </div>
                    ) : (
                        sidebarItems.map((item) => {
                            const c = item.contact;
                            
                            // Check active state
                            const isActive = item.type === 'whatsapp'
                                ? selected?.contact_identifier === c.contact_identifier && selected?.channel === 'whatsapp'
                                : item.type === 'call'
                                    ? selected?.contact_identifier === c.contact_identifier && selected?.channel === 'ligacao' as any
                                    : selected?.contact_identifier === c.contact_identifier && selected?.channel === 'email' && activeEmailThreadId === item.threadId;

                            return (
                                <div
                                    key={item.id}
                                    className={`${styles.contactItem} ${isActive ? styles.contactItemActive : ''}`}
                                    onClick={() => {
                                        if (item.type === 'whatsapp' || item.type === 'call') {
                                            void loadConversation(c);
                                        } else {
                                            if (item.threadId !== 'loading') {
                                                void loadConversation(c, false, item.threadId);
                                            }
                                        }
                                    }}
                                >
                                    {c.channel === ('ligacao' as any) ? (
                                        /* Avatar customizado para ligações: foto do contato + badge /telefone.png */
                                        <div style={{ position: 'relative', flexShrink: 0 }}>
                                            <ContactAvatar
                                                name={c.contact_name}
                                                channel={c.channel}
                                                profilePic={c.profile_pic || undefined}
                                                size={32}
                                                showChannelBadge={false}
                                                className={`${styles.contactAvatar} ${styles.contactAvatarCall}`}
                                            />
                                            {channelFilter === 'all' && (
                                                <img
                                                    src="/telefone.png"
                                                    alt="Ligação"
                                                    style={{
                                                        position: 'absolute',
                                                        bottom: -2,
                                                        right: -2,
                                                        width: 14,
                                                        height: 14,
                                                        borderRadius: '50%',
                                                        objectFit: 'cover',
                                                        background: '#0d0d0d',
                                                        border: '1.5px solid #0d0d0d',
                                                    }}
                                                />
                                            )}
                                        </div>
                                    ) : (
                                        <ContactAvatar
                                            name={c.channel === 'email' ? cleanEmailSender(c.contact_name, c.contact_identifier, userEmail) : c.contact_name}
                                            channel={c.channel}
                                            profilePic={c.profile_pic}
                                            orgLogo={c.org_logo}
                                            orgDomain={c.org_domain}
                                            contactIdentifier={c.contact_identifier}
                                            size={32}
                                            showChannelBadge={channelFilter === 'all'}
                                            className={`${styles.contactAvatar} ${
                                                c.channel === 'whatsapp'
                                                    ? styles.contactAvatarWa
                                                    : styles.contactAvatarEmail
                                            }`}
                                        />
                                    )}
                                    <div className={styles.contactInfo}>
                                        <div className={styles.contactName} title={item.subject}>
                                            {item.subject}
                                            {item.type === 'whatsapp' && c.is_key_contact && (
                                                <span className={styles.keyContactStar} title="Contato-chave / Decisor"> ★</span>
                                            )}
                                        </div>
                                        <div className={styles.contactMeta}>
                                            {item.type === 'email_thread' && item.threadId !== 'loading' ? (
                                                `${(item.lastMessageFrom && isUserEmail(item.lastMessageFrom, userEmail)) ? '(pra mim)' : cleanEmailSender(c.contact_name, c.contact_identifier, userEmail)}: ${item.lastMessagePreview}`
                                            ) : (
                                                item.lastMessagePreview || c.org_name || '—'
                                            )}
                                        </div>
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                                        {item.lastMessageDate && (
                                            <span style={{ fontSize: 10, color: 'var(--sw-text-muted)' }}>
                                                {item.type === 'email_thread' || item.type === 'call' ? formatDate(item.lastMessageDate) : formatTime(new Date(item.lastMessageDate).getTime() / 1000)}
                                            </span>
                                        )}
                                        {(item.type === 'email_thread' || item.type === 'call') && item.messageCount && item.messageCount > 1 && (
                                            <span className={styles.emailThreadItemCount}>
                                                {item.messageCount}
                                            </span>
                                        )}
                                        {item.hasUnread && (
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', paddingRight: 4, flexShrink: 0 }}>
                                                <span className={styles.unreadDot} title="Mensagem nova" />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })
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
                                name={selected.channel === 'email' ? cleanEmailSender(selected.contact_name, selected.contact_identifier, userEmail) : selected.contact_name}
                                channel={selected.channel}
                                profilePic={selected.profile_pic}
                                orgLogo={selected.org_logo}
                                orgDomain={selected.org_domain}
                                contactIdentifier={selected.contact_identifier}
                                size={36}
                                className={`${styles.contactAvatar} ${
                                    selected.channel === 'whatsapp'
                                        ? styles.contactAvatarWa
                                        : selected.channel === 'email'
                                            ? styles.contactAvatarEmail
                                            : ''
                                }`}
                            />
                            <div className={styles.panelHeaderInfo}>
                                <div className={styles.panelHeaderName}>
                                    {selected.channel === 'email' && activeThread ? activeThread.subject : (selected.channel === 'email' ? cleanEmailSender(selected.contact_name, selected.contact_identifier, userEmail) : selected.contact_name)}
                                </div>
                                <div className={styles.panelHeaderSub}>
                                    {selected.channel === 'whatsapp' ? (
                                        <>WhatsApp · {selected.contact_identifier}</>
                                    ) : selected.channel === ('ligacao' as any) ? (
                                        <><Phone size={12} style={{ display: 'inline', marginRight: 4 }} />Ligação gravada · {selectedCallSession?.phone || selected.contact_identifier}</>
                                    ) : (
                                        <>E-mail de {cleanEmailSender(selected.contact_name, selected.contact_identifier, userEmail)} ({selected.contact_identifier})</>
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

                        <div className={`${styles.messagesArea} ${selected.channel === 'whatsapp' ? styles.messagesAreaWa : selected.channel === ('ligacao' as any) ? styles.messagesAreaCall : styles.messagesAreaEmail}`}>
                            {loadingConv ? (
                                <div className={styles.noConversation}>
                                    <p className={styles.noConversationText}>Carregando ligação...</p>
                                </div>
                            ) : selected.channel === ('ligacao' as any) ? (
                                selectedCallSession ? (
                                    <CallConversation
                                        messages={selectedCallSession.messages || []}
                                        latestInsight={selectedCallSession.latest_insight}
                                        flightPlan={selectedCallSession.flight_plan}
                                        contactName={selectedCallSession.contact_name}
                                        createdAt={selectedCallSession.created_at}
                                    />
                                ) : (
                                    <div className={styles.noConversation}>
                                        <p className={styles.noConversationText}>Ligação não encontrada.</p>
                                    </div>
                                )
                            ) : !conversation ? (
                                <div className={styles.noConversation}>
                                    <p className={styles.noConversationText}>
                                        Não foi possível carregar a conversa.
                                    </p>
                                </div>
                            ) : selected.channel === 'whatsapp' ? (
                                <WaConversation messages={conversation.messages as WaMessage[]} />
                            ) : (
                                <EmailConversation key={activeEmailThreadId} messages={(activeThread?.messages || []) as EmailMessage[]} contactName={selected.contact_name} contactIdentifier={selected.contact_identifier} userEmail={userEmail} />
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
