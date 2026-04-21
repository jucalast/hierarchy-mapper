import React from 'react';
import {
    MessageSquare, Mail, ExternalLink, CheckCheck, User2, Reply, Forward
} from 'lucide-react';
import { getAvatarUrl, getProxiedUrl } from '../../../utils/avatarUtils';
import styles from '../../ChatPanel.module.css'; // Temporarily reuse styles

export const WhatsAppThread: React.FC<{ data: any, onOpenWhatsApp?: (info: { name: string, id?: string }) => void }> = ({ data, onOpenWhatsApp }) => {
    const waResult = data?.whatsapp_result || {};
    const action = waResult.whatsapp_action;
    const contact = waResult.contact || waResult.resolved_contact;
    const sentMessage = waResult.sent_message;

    if (action === 'send_message' || action === 'send') {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return (
            <div className={styles.moduleContainer}>
                <div className={styles.waPreviewCard}>
                    <div className={styles.waPreviewHeader}>
                        <div className={styles.waAvatarSmall}>
                            {waResult.contact_picture ? (
                                <img src={waResult.contact_picture} alt="Avatar" className={styles.waAvatarImg} />
                            ) : contact?.profilePicture ? (
                                <img src={contact.profilePicture} alt="Avatar" className={styles.waAvatarImg} />
                            ) : (
                                <User2 size={20} color="#adb5bd" />
                            )}
                        </div>
                        <div className={styles.waPreviewInfo}>
                            <div className={styles.waPreviewName}>{contact?.name || 'Contato'}</div>
                            <div className={styles.waPreviewStatus}>visto por último hoje às {time}</div>
                        </div>
                        <div className={styles.waLinkIcon} onClick={() => {
                            if (onOpenWhatsApp) {
                                onOpenWhatsApp({ name: contact?.name || 'WhatsApp', id: contact?.id });
                            } else {
                                window.open(`/whatsapp?chatId=${contact?.id || ''}`, '_blank');
                            }
                        }}>
                            <ExternalLink size={14} />
                        </div>
                    </div>
                    <div className={styles.waPreviewBubble}>
                        <div className={styles.waPreviewText}>{sentMessage}</div>
                        <div className={styles.waPreviewTime}>
                            {time}
                            <div className={styles.waChecks}>
                                <CheckCheck size={14} />
                            </div>
                        </div>
                    </div>
                </div>
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
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (action === 'send_email' || action === 'send' || !action) {
        const initials = (contact.name || contact.email || 'D').split(' ').map((n: string) => n[0]).join('').toUpperCase().substring(0, 2);
        return (
            <div className={styles.moduleContainer}>
                <div className={styles.emailPreviewCard}>
                    <div className={styles.emailPreviewHeader}>
                        <div className={styles.emailAvatarSmall}>
                            {getAvatarUrl(contact) ? (
                                <img
                                    src={getProxiedUrl(getAvatarUrl(contact))}
                                    alt="Avatar"
                                    className={styles.waAvatarImg}
                                    style={{ borderRadius: '50%' }}
                                />
                            ) : (
                                <div className={styles.emailInitials} style={{ background: 'transparent' }}>
                                    <img src="/outlook.png" alt="E" style={{ width: 28, height: 28, objectFit: 'contain' }} />
                                </div>
                            )}
                            <div className={styles.outlookBadge}>
                                <img src="/outlook.png" alt="Outlook" style={{ width: 24, height: 24, objectFit: 'contain' }} />
                            </div>
                        </div>
                        <div className={styles.emailPreviewInfo}>
                            <div className={styles.emailPreviewRecipient}>{contact.name || contact.email || 'Destinatário'}</div>
                            <div className={styles.emailPreviewSnippet}>{subject}</div>
                        </div>
                        <div className={styles.emailExternalIcon}>
                            <ExternalLink size={14} />
                        </div>
                    </div>
                    <div className={styles.emailPreviewBody}>
                        <div className={styles.emailBodyText}>{sentMessage}</div>
                        <div className={styles.emailPreviewMeta}>
                            <div className={styles.emailSentStatus}>
                                <CheckCheck size={14} />
                                <span>Enviado via Outlook</span>
                            </div>
                            <div className={styles.emailTime}>{time}</div>
                        </div>
                        <div className={styles.emailPreviewActions}>
                            <button className={styles.emailActionButton}>
                                <Reply size={16} className={styles.emailActionIcon} />
                                <span>Responder</span>
                            </button>
                        </div>
                    </div>
                </div>
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
