import React from 'react';
import { Database, PanelRight, PanelRightOpen } from 'lucide-react';
import styles from './NetworkGraph.module.css';
import { TriggerNotifications } from './TriggerNotifications';
import { API_BASE_URL } from '@/services/config';

interface HeaderProps {
    confirmedBrand: string;
    showChat?: boolean;
    onToggleChat?: () => void;
    onOpenChatForOrg?: (orgId: number, orgName: string) => void;
}

export const Header: React.FC<HeaderProps> = ({ confirmedBrand, showChat, onToggleChat, onOpenChatForOrg }) => {
    return (
        <header className={styles.header}>
            <div className={styles.breadcrumbs}>
                <div className={styles.headerIconWrapper}>
                    <Database size={14} className={styles.headerIcon} />
                </div>
                <span className={styles.breadcrumbItem}>Pipedrive Workspace</span>
                <span className={styles.breadcrumbDivider}>/</span>
                <span className={styles.breadcrumbActive}>{confirmedBrand || 'OSINT Flow'}</span>
                <span className={styles.statusBadge}>DRAFT</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: 'auto' }}>
                {/* Notificações de respostas de clientes */}
                <TriggerNotifications
                    apiBase={API_BASE_URL}
                    onOpenChat={onOpenChatForOrg}
                />

                {onToggleChat && (
                    <button
                        onClick={onToggleChat}
                        className={`${styles.navIcon}`}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center', color: showChat ? 'rgba(255, 255, 255, 1)' : 'rgba(255, 255, 255, 0.6)' }}
                        title={showChat ? "Fechar Assistente" : "Abrir Assistente"}
                    >
                        {showChat ? <PanelRightOpen size={20} /> : <PanelRight size={20} />}
                    </button>
                )}
            </div>
        </header>
    );
};
