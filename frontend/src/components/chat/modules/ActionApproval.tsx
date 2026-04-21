import React from 'react';
import { 
    MessageSquare, Mail, Send, XCircle, Loader2, ShieldCheck 
} from 'lucide-react';
import { ApprovalAction } from '../ChatInterfaces';
import styles from '../../ChatPanel.module.css';

interface ActionApprovalProps {
    action: ApprovalAction;
    onApprove: (actionId: string) => void;
    onReject: (actionId: string) => void;
    status?: 'pending' | 'approving' | 'approved' | 'rejected';
}

export const ActionApproval: React.FC<ActionApprovalProps> = ({ 
    action, onApprove, onReject, status = 'pending' 
}) => {
    const isWhatsApp = action.action_type === 'send_whatsapp';
    const channelIcon = isWhatsApp ? <MessageSquare size={16} /> : <Mail size={16} />;
    const channelColor = isWhatsApp ? '#25D366' : '#0078D4';
    const channelLabel = isWhatsApp ? 'WhatsApp' : 'Email';
    const contactDetail = isWhatsApp ? action.contact_phone : action.contact_email;
    
    return (
        <div className={styles.approvalCard} style={{ borderLeftColor: channelColor }}>
            <div className={styles.approvalHeader}>
                <div className={styles.approvalChannel} style={{ color: channelColor }}>
                    {channelIcon}
                    <span>{channelLabel} para {action.contact_name}</span>
                </div>
                {contactDetail && (
                    <span className={styles.approvalContact}>{contactDetail}</span>
                )}
            </div>
            
            {action.subject && (
                <div className={styles.approvalSubject}>
                    <strong>Assunto:</strong> {action.subject}
                </div>
            )}
            
            <div className={styles.approvalPreview}>
                {action.message_preview}
            </div>
            
            <div className={styles.approvalReason}>
                {action.description}
            </div>
            
            <div className={styles.approvalActions}>
                {status === 'pending' && (
                    <>
                        <button
                            className={styles.approvalBtnApprove}
                            onClick={() => onApprove(action.action_id)}
                        >
                            <Send size={14} />
                            <span>Enviar</span>
                        </button>
                        <button
                            className={styles.approvalBtnReject}
                            onClick={() => onReject(action.action_id)}
                        >
                            <XCircle size={14} />
                            <span>Cancelar</span>
                        </button>
                    </>
                )}
                {status === 'approving' && (
                    <div className={styles.approvalStatus}>
                        <Loader2 size={14} className={styles.spinner} />
                        <span>Enviando...</span>
                    </div>
                )}
                {status === 'approved' && (
                    <div className={styles.approvalStatusSuccess}>
                        <ShieldCheck size={14} />
                        <span>Enviado com sucesso!</span>
                    </div>
                )}
                {status === 'rejected' && (
                    <div className={styles.approvalStatusRejected}>
                        <XCircle size={14} />
                        <span>Cancelado pelo usuário</span>
                    </div>
                )}
            </div>
        </div>
    );
};
