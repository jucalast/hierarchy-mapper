import React, { useState } from 'react';
import { ApprovalAction } from '../ChatInterfaces';
import { WhatsAppThreadCard, EmailThreadCard } from './CommunicationModules';
import styles from '../styles/ChatPanel.module.css';
import * as ai from '../../../services/api/ai';

interface ActionApprovalProps {
    action: ApprovalAction;
    onApprove: (actionId: string) => void;
    onReject: (actionId: string) => void;
    status?: 'pending' | 'approving' | 'approved' | 'rejected';
}

export const ActionApproval: React.FC<ActionApprovalProps> = ({
    action, onApprove, onReject, status = 'pending'
}) => {
    const [currentMessage, setCurrentMessage] = useState(action.message_preview);
    const [refineText, setRefineText] = useState('');
    const [isRefining, setIsRefining] = useState(false);

    const handleRefine = async () => {
        if (!refineText.trim() || isRefining) return;
        setIsRefining(true);
        try {
            const res = await ai.refineMessage({ action_id: action.action_id, feedback: refineText });
            if (res.ok && res.refined_message) {
                setCurrentMessage(res.refined_message);
                setRefineText('');
            }
        } catch {
            // silent — mantém a mensagem atual
        } finally {
            setIsRefining(false);
        }
    };

    const isWhatsApp = action.action_type === 'send_whatsapp';

    if (isWhatsApp) {
        return (
            <div className={styles.moduleContainer}>
                <WhatsAppThreadCard
                    type="whatsapp"
                    contact={{ name: action.contact_name, phone: action.contact_phone }}
                    sentMessage={currentMessage}
                    status={status}
                    onApprove={() => onApprove(action.action_id)}
                    onReject={() => onReject(action.action_id)}
                    refineText={refineText}
                    onRefineChange={setRefineText}
                    onRefine={handleRefine}
                    isRefining={isRefining}
                />
            </div>
        );
    }

    return (
        <div className={styles.moduleContainer}>
            <EmailThreadCard
                type="email"
                contact={{ name: action.contact_name, email: action.contact_email }}
                sentMessage={currentMessage}
                subject={action.subject}
                isReply={action.is_reply}
                originalSubject={action.original_subject}
                status={status}
                onApprove={() => onApprove(action.action_id)}
                onReject={() => onReject(action.action_id)}
                refineText={refineText}
                onRefineChange={setRefineText}
                onRefine={handleRefine}
                isRefining={isRefining}
            />
        </div>
    );
};
