import React from 'react';
import { ApprovalAction } from '../ChatInterfaces';
import { WhatsAppThreadCard, EmailThreadCard } from './CommunicationModules';
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
    
    if (isWhatsApp) {
        return (
            <div className={styles.moduleContainer}>
                <WhatsAppThreadCard
                    type="whatsapp"
                    contact={{ name: action.contact_name, phone: action.contact_phone }}
                    sentMessage={action.message_preview}
                    status={status}
                    onApprove={() => onApprove(action.action_id)}
                    onReject={() => onReject(action.action_id)}
                />
            </div>
        );
    }

    return (
        <div className={styles.moduleContainer}>
            <EmailThreadCard
                type="email"
                contact={{ name: action.contact_name, email: action.contact_email }}
                sentMessage={action.message_preview}
                subject={action.subject}
                status={status}
                onApprove={() => onApprove(action.action_id)}
                onReject={() => onReject(action.action_id)}
            />
        </div>
    );
};
