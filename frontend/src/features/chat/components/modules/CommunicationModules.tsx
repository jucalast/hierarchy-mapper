import React from 'react';
import {
    Mail, ExternalLink, CheckCheck, User2, Reply, Send, XCircle, Loader2, ShieldCheck, CornerDownLeft, Wand2
} from 'lucide-react';
import styles from '../AgentV2Message.module.css';

interface ThreadCardProps {
    type: 'whatsapp' | 'email';
    contact: any;
    sentMessage: string;
    subject?: string;
    status?: 'pending' | 'approving' | 'approved' | 'rejected';
    onApprove?: () => void;
    onReject?: () => void;
    onOpenExternal?: () => void;
    isReply?: boolean;
    originalSubject?: string;
    /** Para modo histórico: lista de mensagens {body, fromMe, timestamp} */
    historyMessages?: Array<{ body: string; fromMe: boolean; timestamp?: number }>;
    /** Props de refinamento de mensagem */
    refineText?: string;
    onRefineChange?: (v: string) => void;
    onRefine?: () => void;
    isRefining?: boolean;
}

/**
 * WhatsAppThreadCard — componente único usado em:
 *  1. Preview/aprovação de mensagem (status !== undefined, historyMessages ausente)
 *  2. Histórico de conversa (historyMessages presente)
 */
export const WhatsAppThreadCard: React.FC<ThreadCardProps> = ({
    contact,
    sentMessage,
    status,
    onApprove,
    onReject,
    onOpenExternal,
    historyMessages,
    refineText,
    onRefineChange,
    onRefine,
    isRefining,
}) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const isPending = status === 'pending';

    /** Formata timestamp Unix (segundos) → "HH:MM" */
    const fmtTime = (ts?: number) =>
        ts
            ? new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : time;

    const isHistoryMode = Array.isArray(historyMessages) && historyMessages.length > 0;

    return (
        <div
            className={`${styles.waPreviewCard} ${styles.glassModuleCard}`}
            style={{
                backgroundImage: 'url("/wpp.png")',
                backgroundSize: '600px',
                backgroundRepeat: 'repeat',
            }}
        >
            {/* ── Header ─────────────────────────────────── */}
            <div className={styles.waPreviewHeader} style={{ position: 'relative', zIndex: 1 }}>
                <div className={styles.waAvatarSmall}>
                    {contact?.profilePicture ? (
                        <img src={contact.profilePicture} alt="Avatar" className={styles.waAvatarImg} />
                    ) : (
                        <User2 size={20} color="#adb5bd" />
                    )}
                </div>
                <div className={styles.waPreviewInfo}>
                    <div className={styles.waPreviewName}>
                        {typeof contact === 'string' ? contact : (contact?.name || 'Contato')}
                    </div>
                    <div className={styles.waPreviewStatus}>
                        {status === 'approved'
                            ? 'enviado com sucesso'
                            : isHistoryMode
                            ? 'visto por último recentemente'
                            : `visto por último hoje às ${time}`}
                    </div>
                </div>
                <div className={styles.waLinkIcon} onClick={onOpenExternal}>
                    <ExternalLink size={14} />
                </div>
            </div>

            {/* ── Bubbles ────────────────────────────────── */}
            <div
                style={{
                    padding: '0 4px 12px 4px',
                    maxHeight: isHistoryMode ? '400px' : undefined,
                    overflowY: isHistoryMode ? 'auto' : undefined,
                    position: 'relative',
                    zIndex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                }}
            >
                {isHistoryMode
                    ? historyMessages!.map((m, i) => (
                          <div
                              key={i}
                              className={styles.waPreviewBubble}
                              style={{
                                  marginTop: '8px',
                                  alignSelf: m.fromMe ? 'flex-end' : 'flex-start',
                                  marginLeft: m.fromMe ? 'auto' : '12px',
                                  marginRight: m.fromMe ? '12px' : 'auto',
                                  background: m.fromMe ? 'rgb(0, 92, 75)' : 'rgb(32, 44, 51)',
                                  border: 'none',
                                  boxShadow: 'rgba(0,0,0,0.13) 0px 1px 0.5px',
                                  color: 'rgb(233, 237, 239)',
                              }}
                          >
                              <div className={styles.waPreviewText}>{m.body}</div>
                              <div
                                  className={styles.waPreviewTime}
                                  style={{ color: 'rgba(255,255,255,0.6)' }}
                              >
                                  {fmtTime(m.timestamp)}
                                  <div
                                      className={styles.waChecks}
                                      style={{
                                          color: m.fromMe
                                              ? 'rgb(83, 189, 235)'
                                              : 'rgba(255,255,255,0.6)',
                                      }}
                                  >
                                      <CheckCheck size={14} />
                                  </div>
                              </div>
                          </div>
                      ))
                    : (
                          /* Modo preview: única bolha "de envio" */
                          <div
                              className={styles.waPreviewBubble}
                              style={{
                                  marginTop: '8px',
                                  alignSelf: 'flex-end',
                                  marginLeft: 'auto',
                                  marginRight: '12px',
                                  background: 'rgb(0, 92, 75)',
                                  border: 'none',
                                  boxShadow: 'rgba(0,0,0,0.13) 0px 1px 0.5px',
                                  color: 'rgb(233, 237, 239)',
                              }}
                          >
                              <div
                                  className={styles.waPreviewText}
                                  dangerouslySetInnerHTML={{ __html: sentMessage }}
                              />
                              <div
                                  className={styles.waPreviewTime}
                                  style={{ color: 'rgba(255,255,255,0.6)' }}
                              >
                                  {time}
                                  <div
                                      className={styles.waChecks}
                                      style={{
                                          color:
                                              status === 'approved'
                                                  ? 'rgb(83, 189, 235)'
                                                  : 'rgba(255,255,255,0.6)',
                                      }}
                                  >
                                      <CheckCheck size={14} />
                                  </div>
                              </div>
                          </div>
                      )}
            </div>

            {/* ── Refine area (apenas quando pending e callback fornecido) ── */}
            {isPending && onRefine && (
                <div className={styles.refineRow}>
                    <input
                        className={styles.refineInput}
                        value={refineText ?? ''}
                        onChange={e => onRefineChange?.(e.target.value)}
                        placeholder="O que você quer mudar na mensagem?"
                        disabled={isRefining}
                        onKeyDown={e => {
                            if (e.key === 'Enter' && refineText?.trim() && !isRefining) onRefine();
                        }}
                    />
                    <button
                        className={styles.refineBtn}
                        onClick={onRefine}
                        disabled={isRefining || !refineText?.trim()}
                    >
                        {isRefining
                            ? <Loader2 size={12} className={styles.spinner} />
                            : <Wand2 size={12} />}
                        <span>{isRefining ? 'Refinando...' : 'Refinar'}</span>
                    </button>
                </div>
            )}

            {/* ── Approval Controls (apenas no modo pending/approving/etc.) ── */}
            {status && (
                <div className={styles.approvalActionsInCard}>
                    {isPending ? (
                        <>
                            <button className={styles.approvalBtnApprove} onClick={onApprove}>
                                <Send size={14} /> <span>Enviar WhatsApp</span>
                            </button>
                            <button className={styles.approvalBtnReject} onClick={onReject}>
                                <XCircle size={14} /> <span>Cancelar</span>
                            </button>
                        </>
                    ) : (
                        <div className={`${styles.approvalStatusSmall} ${styles[status]}`}>
                            {status === 'approving' && <Loader2 size={14} className={styles.spinner} />}
                            {status === 'approved' && <ShieldCheck size={14} />}
                            {status === 'rejected' && <XCircle size={14} />}
                            <span>
                                {status === 'approving'
                                    ? 'Enviando...'
                                    : status === 'approved'
                                    ? 'Enviado'
                                    : 'Cancelado'}
                            </span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export const EmailThreadCard: React.FC<ThreadCardProps> = ({
    contact, sentMessage, subject, status, onApprove, onReject, onOpenExternal, isReply, originalSubject, historyMessages,
    refineText, onRefineChange, onRefine, isRefining,
}) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const isPending = status === 'pending';
    const isHistoryMode = Array.isArray(historyMessages) && historyMessages.length > 0;

    /** Formata timestamp Unix (segundos) → "HH:MM" */
    const fmtTime = (ts?: number) =>
        ts
            ? new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            : time;

    return (
        <div className={styles.emailPreviewCard}>
            {/* Faixa de contexto — aparece apenas em replies de thread */}
            {isReply && originalSubject && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '5px 14px',
                    background: 'rgba(255,255,255,0.03)',
                    borderBottom: '1px solid rgba(255,255,255,0.05)',
                    fontSize: '10px',
                    color: 'rgba(255,255,255,0.35)',
                }}>
                    <CornerDownLeft size={10} style={{ flexShrink: 0, opacity: 0.5 }} />
                    <span style={{ fontWeight: 700, color: 'rgba(255,255,255,0.45)', marginRight: '2px' }}>thread:</span>
                    <span style={{
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        fontStyle: 'italic', maxWidth: '240px',
                    }}>{originalSubject}</span>
                </div>
            )}

            <div className={styles.emailPreviewHeader}>
                <div className={styles.emailAvatarSmall}>
                    <img src="/outlook.png" alt="E" style={{ width: 28, height: 28, objectFit: 'contain' }} />
                    <div className={styles.outlookBadge}>
                        <img src="/outlook.png" alt="Outlook" style={{ width: 24, height: 24, objectFit: 'contain' }} />
                    </div>
                </div>
                <div className={styles.emailPreviewInfo}>
                    <div className={styles.emailPreviewRecipient}>
                        {typeof contact === 'string' 
                            ? contact 
                            : (contact?.name || contact?.email || 'Destinatário')}
                    </div>
                    <div className={styles.emailPreviewSnippet}>
                        {isReply && <span className={styles.replyBadge}>RE:</span>}
                        {subject || 'Sem Assunto'}
                    </div>
                </div>
                <div className={styles.emailExternalIcon} onClick={onOpenExternal}>
                    <ExternalLink size={14} />
                </div>
            </div>

            <div className={styles.emailPreviewBody}>
                {isHistoryMode ? (
                    <div style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px',
                        padding: '4px 0 12px 0',
                        maxHeight: '400px',
                        overflowY: 'auto'
                    }}>
                        {historyMessages!.map((m, i) => (
                            <div
                                key={i}
                                className={styles.waPreviewBubble}
                                style={{
                                    alignSelf: m.fromMe ? 'flex-end' : 'flex-start',
                                    background: m.fromMe ? 'rgba(0, 120, 212, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                                    border: m.fromMe ? '1px solid rgba(0, 120, 212, 0.3)' : '1px solid rgba(255, 255, 255, 0.1)',
                                    color: 'rgba(255, 255, 255, 0.9)',
                                    marginLeft: m.fromMe ? '40px' : '0',
                                    marginRight: m.fromMe ? '0' : '40px',
                                    borderRadius: '12px',
                                    padding: '10px 14px',
                                    fontSize: '13px',
                                    lineHeight: '1.5'
                                }}
                            >
                                <div dangerouslySetInnerHTML={{ __html: m.body }} />
                                <div style={{ 
                                    fontSize: '10px', 
                                    color: 'rgba(255,255,255,0.4)', 
                                    marginTop: '4px',
                                    textAlign: 'right'
                                }}>
                                    {fmtTime(m.timestamp)}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <>
                        <div className={styles.emailBodyText} dangerouslySetInnerHTML={{ __html: sentMessage }} />
                        <div className={styles.emailPreviewMeta}>
                            <div className={styles.emailSentStatus}>
                                <CheckCheck size={14} />
                                <span>{status === 'approved' ? 'Enviado via Outlook' : isReply ? 'Resposta via Outlook' : 'Rascunho via Outlook'}</span>
                            </div>
                            <div className={styles.emailTime}>{time}</div>
                        </div>
                    </>
                )}

                {/* Refine area (email) */}
                {isPending && onRefine && (
                    <div className={styles.refineRow}>
                        <input
                            className={styles.refineInput}
                            value={refineText ?? ''}
                            onChange={e => onRefineChange?.(e.target.value)}
                            placeholder="O que você quer mudar na mensagem?"
                            disabled={isRefining}
                            onKeyDown={e => {
                                if (e.key === 'Enter' && refineText?.trim() && !isRefining) onRefine();
                            }}
                        />
                        <button
                            className={styles.refineBtn}
                            onClick={onRefine}
                            disabled={isRefining || !refineText?.trim()}
                        >
                            {isRefining
                                ? <Loader2 size={12} className={styles.spinner} />
                                : <Wand2 size={12} />}
                            <span>{isRefining ? 'Refinando...' : 'Refinar'}</span>
                        </button>
                    </div>
                )}

                {/* Approval Controls */}
                {status ? (
                    <div className={styles.approvalActionsInCard}>
                        {isPending ? (
                            <>
                                <button className={styles.approvalBtnApprove} onClick={onApprove}>
                                    {isReply
                                        ? <><CornerDownLeft size={14} /> <span>Responder Thread</span></>
                                        : <><Send size={14} /> <span>Enviar Email</span></>
                                    }
                                </button>
                                <button className={styles.approvalBtnReject} onClick={onReject}>
                                    <XCircle size={14} /> <span>Cancelar</span>
                                </button>
                            </>
                        ) : (
                            <div className={`${styles.approvalStatusSmall} ${styles[status]}`}>
                                {status === 'approving' && <Loader2 size={14} className={styles.spinner} />}
                                {status === 'approved' && <ShieldCheck size={14} />}
                                {status === 'rejected' && <XCircle size={14} />}
                                <span>{status === 'approving' ? 'Enviando...' : status === 'approved' ? 'Enviado' : 'Cancelado'}</span>
                            </div>
                        )}
                    </div>
                ) : !isHistoryMode && (
                    <div className={styles.emailPreviewActions}>
                        <button className={styles.emailActionButton}>
                            <Reply size={16} className={styles.emailActionIcon} />
                            <span>Responder</span>
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

/**
 * WhatsAppThread — renderiza o resultado de uma tool call de WhatsApp.
 * Usa sempre WhatsAppThreadCard, seja para histórico ou preview de envio.
 */
export const WhatsAppThread: React.FC<{
    data: any;
    onOpenWhatsApp?: (info: { name: string; id?: string }) => void;
}> = ({ data, onOpenWhatsApp }) => {
    const waResult = data?.whatsapp_result || {};
    const action = waResult.whatsapp_action;
    const contact = waResult.contact || waResult.resolved_contact;
    const sentMessage = waResult.sent_message || '';

    // Modo: envio/preview (sem histórico)
    if (action === 'send_message' || action === 'send') {
        return (
            <div className={styles.moduleContainer}>
                <WhatsAppThreadCard
                    type="whatsapp"
                    contact={contact}
                    sentMessage={sentMessage}
                    onOpenExternal={() =>
                        onOpenWhatsApp &&
                        onOpenWhatsApp({ name: contact?.name || 'WhatsApp', id: contact?.id })
                    }
                />
            </div>
        );
    }

    // Modo: histórico de mensagens
    const result = waResult.resultado || {};
    const messages: Array<{ body: string; fromMe: boolean; timestamp?: number }> =
        result.messages || [];

    if (!messages.length) {
        return <div className={styles.emptyModule}>Sem histórico de mensagens.</div>;
    }

    return (
        <div className={styles.moduleContainer}>
            <WhatsAppThreadCard
                type="whatsapp"
                contact={contact}
                sentMessage=""
                historyMessages={messages}
                onOpenExternal={() =>
                    onOpenWhatsApp &&
                    onOpenWhatsApp({ name: contact?.name || 'WhatsApp' })
                }
            />
        </div>
    );
};

/**
 * EmailThread — renderiza o resultado de uma tool call de Email.
 * Mapeia o payload data.email_result para EmailThreadCard.
 */
export const EmailThread: React.FC<{ data: any }> = ({ data }) => {
    const emailResult = data?.email_result || data || {};
    const action = emailResult.email_action;

    // Modo: envio/preview (sem histórico)
    if (action === 'send_email' || action === 'reply_email') {
        const contact = emailResult.contact || { 
            name: emailResult.recipient_name, 
            email: emailResult.recipient_email 
        };
        return (
            <div className={styles.moduleContainer}>
                <EmailThreadCard
                    type="email"
                    contact={contact}
                    sentMessage={emailResult.body || emailResult.sent_message || ''}
                    subject={emailResult.subject}
                    isReply={action === 'reply_email'}
                    originalSubject={emailResult.original_subject}
                />
            </div>
        );
    }

    // Modo: histórico de mensagens (Arqueologia)
    const result = emailResult.resultado || {};
    let groups: any[] = [];
    
    // 1. Prioridade: Formato rico do ContextService/ActionExecutor
    if (result.messages_by_contact) {
        groups = result.messages_by_contact;
    } else if (result.human_threads) {
        groups = [result];
    } 
    // 2. Fallback: Formato simplificado do AgentService (Arqueologia direta por contato)
    else if (emailResult.messages || emailResult.human_threads) {
        groups = [emailResult];
    }

    if (!groups || groups.length === 0) {
        return <div className={styles.emptyModule}>Sem histórico de e-mails.</div>;
    }

    // Renderiza cada grupo de thread como um card
    return (
        <div className={styles.moduleContainer} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {groups.map((group: any, idx: number) => {
                const messages = group.human_threads || group.messages || [];
                const lastMsg = messages[0] || {};
                
                const historyMessages = messages.map((m: any) => ({
                    body: m.body || m.snippet || '',
                    fromMe: (m.sender || '').toLowerCase().includes('jferres.com.br') || (m.sender || '').startsWith('/o='),
                    timestamp: m.date ? new Date(m.date).getTime() / 1000 : undefined
                }));

                const resolvedContact = typeof group.contact === 'object' && group.contact !== null
                    ? group.contact
                    : { 
                        name: group.contact || group.contact_name, 
                        email: group.email || group.contact_email 
                      };

                return (
                    <EmailThreadCard
                        key={idx}
                        type="email"
                        contact={resolvedContact}
                        sentMessage={lastMsg.body || lastMsg.snippet || ''}
                        subject={group.thread_subject || lastMsg.subject}
                        isReply={messages.length > 1}
                        originalSubject={group.thread_subject}
                        historyMessages={historyMessages}
                    />
                );
            })}
        </div>
    );
};
