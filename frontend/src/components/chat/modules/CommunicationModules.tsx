import React from 'react';
import {
    MessageSquare, Mail, ExternalLink, CheckCheck, User2, Reply, Send, XCircle, Loader2, ShieldCheck, CornerDownLeft
} from 'lucide-react';
import { getAvatarUrl, getProxiedUrl } from '../../../utils/avatarUtils';
import styles from '../../ChatPanel.module.css';

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
}

export const WhatsAppThreadCard: React.FC<ThreadCardProps> = ({ 
    contact, sentMessage, status, onApprove, onReject, onOpenExternal 
}) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const isPending = status === 'pending';

    return (
        <div className={`${styles.waPreviewCard} ${styles.glassModuleCard}`} style={{ margin: status ? '8px 0' : '0' }}>
            <div className={styles.waPreviewHeader}>
                <div className={styles.waAvatarSmall}>
                    {contact?.profilePicture ? (
                        <img src={contact.profilePicture} alt="Avatar" className={styles.waAvatarImg} />
                    ) : (
                        <User2 size={20} color="#adb5bd" />
                    )}
                </div>
                <div className={styles.waPreviewInfo}>
                    <div className={styles.waPreviewName}>{contact?.name || 'Contato'}</div>
                    <div className={styles.waPreviewStatus}>
                        {status === 'approved' ? 'enviado com sucesso' : `visto por último hoje às ${time}`}
                    </div>
                </div>
                <div className={styles.waLinkIcon} onClick={onOpenExternal}>
                    <ExternalLink size={14} />
                </div>
            </div>
            <div className={styles.waPreviewBubble}>
                <div className={styles.waPreviewText} dangerouslySetInnerHTML={{ __html: sentMessage }} />
                <div className={styles.waPreviewTime}>
                    {time}
                    <div className={styles.waChecks} style={{ color: status === 'approved' ? '#34B7F1' : '#9ca3af' }}>
                        <CheckCheck size={14} />
                    </div>
                </div>
            </div>

            {/* Approval Controls */}
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
                            <span>{status === 'approving' ? 'Enviando...' : status === 'approved' ? 'Enviado' : 'Cancelado'}</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export const EmailThreadCard: React.FC<ThreadCardProps> = ({
    contact, sentMessage, subject, status, onApprove, onReject, onOpenExternal, isReply, originalSubject
}) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const isPending = status === 'pending';

    return (
        <div className={styles.emailPreviewCard} style={{ margin: status ? '8px 0' : '0' }}>
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
                    <div className={styles.emailPreviewRecipient}>{contact.name || contact.email || 'Destinatário'}</div>
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
                <div className={styles.emailBodyText} dangerouslySetInnerHTML={{ __html: sentMessage }} />
                <div className={styles.emailPreviewMeta}>
                    <div className={styles.emailSentStatus}>
                        <CheckCheck size={14} />
                        <span>{status === 'approved' ? 'Enviado via Outlook' : isReply ? 'Resposta via Outlook' : 'Rascunho via Outlook'}</span>
                    </div>
                    <div className={styles.emailTime}>{time}</div>
                </div>

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
                ) : (
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

export const WhatsAppThread: React.FC<{ data: any, onOpenWhatsApp?: (info: { name: string, id?: string }) => void }> = ({ data, onOpenWhatsApp }) => {
    const waResult = data?.whatsapp_result || {};
    const action = waResult.whatsapp_action;
    const contact = waResult.contact || waResult.resolved_contact;
    const sentMessage = waResult.sent_message;

    if (action === 'send_message' || action === 'send') {
        return (
            <div className={styles.moduleContainer}>
                <WhatsAppThreadCard 
                    type="whatsapp"
                    contact={contact}
                    sentMessage={sentMessage}
                    onOpenExternal={() => {
                        if (onOpenWhatsApp) onOpenWhatsApp({ name: contact?.name || 'WhatsApp', id: contact?.id });
                    }}
                />
            </div>
        );
    }

    const result = waResult.resultado || {};
    const messages = result.messages || [];
    if (!messages.length) return <div className={styles.emptyModule}>Sem histórico de mensagens.</div>;
    return (
        <div className={styles.moduleContainer}>
            <div className={styles.moduleHeader}><MessageSquare size={16} /> <span>Conversa WhatsApp</span></div>
            <div className={styles.waThread}>
                {messages.slice(-5).map((m: any, i: number) => (
                    <div key={i} className={`${styles.waBubble} ${m.fromMe ? styles.me : styles.them}`}>
                        <div className={styles.waText}>{m.body}</div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export const EmailThread: React.FC<{ data: any }> = ({ data }) => {
    const emailResult = data?.email_result || data || {};
    const action = emailResult.email_action;
    const contact = emailResult.contact || emailResult.resolved_contact || { email: emailResult.to };
    const sentMessage = emailResult.sent_message || emailResult.body_preview || "";
    const subject = emailResult.subject || "Sem Assunto";

    if (action === 'send_email' || action === 'send' || !action) {
        return (
            <div className={styles.moduleContainer}>
                <EmailThreadCard 
                    type="email"
                    contact={contact}
                    sentMessage={sentMessage}
                    subject={subject}
                />
            </div>
        );
    }

    const result = emailResult.resultado || {};
    const messages = result.messages || emailResult.messages || [];
    if (!messages.length) return <div className={styles.emptyModule}>Sem emails recentes na pasta.</div>;

    return (
        <div className={styles.moduleContainer}>
            <div className={styles.moduleHeader}><Mail size={16} /> <span>Conversa Outlook</span></div>
            <div className={styles.emailList}>
                {messages.slice(0, 5).map((m: any, i: number) => (
                    <div key={i} className={styles.emailListItem}>
                        <div className={styles.emailListSubject}>{m.subject}</div>
                        <div className={styles.emailListSnippet}>{m.snippet || m.body}</div>
                    </div>
                ))}
            </div>
        </div>
    );
};
