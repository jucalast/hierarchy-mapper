import React from 'react';
import { Clock, Plus, PanelRightClose } from 'lucide-react';
import { Avatar } from '../../ui';
import styles from '../ChatPanel.module.css';

interface ChatPanelHeaderProps {
    logo?: string;
    orgName: string;
    title: string;
    onNewThread: () => void;
    onBackToList: () => void;
    onCloseChat?: () => void;
}

export const ChatPanelHeader: React.FC<ChatPanelHeaderProps> = ({
    logo,
    orgName,
    title,
    onNewThread,
    onBackToList,
    onCloseChat,
}) => {
    return (
        <div className={styles.chatHeader} style={{ paddingLeft: '16px', gap: '12px' }}>
            <Avatar 
                kind="company"
                src={logo}
                name={orgName}
                size={32}
                style={{ border: logo ? '3px solid var(--sw-border-strong)' : 'none' }}
            />
            <div className={styles.chatHeaderInfo} style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '8px', flex: '0 1 auto', minWidth: 0 }}>
                <span style={{ color: 'var(--sw-text-muted)', fontWeight: 600, fontSize: '0.88rem', flexShrink: 0 }}>
                    {title}
                </span>
                <span style={{ color: 'var(--sw-border)', fontWeight: 300, fontSize: '0.88rem', flexShrink: 0 }}>/</span>
                <span 
                    style={{ 
                        color: 'var(--sw-text-base)', 
                        fontWeight: 600, 
                        fontSize: '0.88rem', 
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        maxWidth: '180px',
                        flexShrink: 1
                    }}
                    title={orgName}
                >
                    {orgName}
                </span>
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginRight: '12px' }}>
                <button
                    className={styles.tlNewBtn}
                    onClick={onNewThread}
                    title="Nova conversa"
                    style={{ height: '32px', padding: '0 12px', fontSize: '12px' }}
                >
                    <Plus size={13} />
                    <span>Nova</span>
                </button>
                <button
                    className={styles.chatHeaderIconBtn}
                    onClick={onBackToList}
                    title="Histórico de conversas"
                >
                    <Clock size={20} />
                </button>
                {onCloseChat && (
                    <button
                        className={styles.chatHeaderIconBtn}
                        onClick={onCloseChat}
                        title="Fechar Painel"
                    >
                        <PanelRightClose size={20} />
                    </button>
                )}
            </div>
        </div>
    );
};
