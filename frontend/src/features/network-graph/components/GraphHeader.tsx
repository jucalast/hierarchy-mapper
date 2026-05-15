"use client";

import React from 'react';
import { PanelRight, PanelRightOpen, LogOut } from 'lucide-react';
import { TriggerNotifications } from '@/components/ui/TriggerNotifications';
import { API_BASE_URL } from '@/services/config';
import styles from '../styles/NetworkGraph.module.css';

interface GraphHeaderProps {
    showChat: boolean;
    onToggleChat: () => void;
    onOpenChat: (orgId: number, orgName: string) => void;
    showChatToggle: boolean;
    onLogout?: () => void;
}

const INTEGRATIONS = [
    { id: 'pipedrive', src: '/pipedrive.png', background: undefined },
    { id: 'whatsapp', src: '/wppicon.png', background: undefined },
    { id: 'email', src: '/outlook.png', background: '#fff' },
] as const;

export const GraphHeader: React.FC<GraphHeaderProps> = ({
    showChat,
    onToggleChat,
    onOpenChat,
    showChatToggle,
    onLogout,
}) => (
    <header className={styles.globalHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className={styles.globalHeaderTitle}>LINKB2B Hierarchy Mapper</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginLeft: 'auto' }}>
            <div className={styles.humanAnalysisAvatarStack} title="Integrações Ativas" style={{ marginRight: '16px', pointerEvents: 'auto' }}>
                {INTEGRATIONS.map((integration, idx) => (
                    <div
                        key={integration.id}
                        className={`${styles.humanAnalysisStackedAvatar} ${styles[`stackLayer${idx}`]}`}
                        style={{ background: integration.background || 'var(--sw-surface-raised)', cursor: 'pointer' }}
                    >
                        <img
                            src={integration.src}
                            alt={integration.id}
                            style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: 'inherit', padding: '2px' }}
                        />
                    </div>
                ))}
            </div>

            <TriggerNotifications
                apiBase={API_BASE_URL}
                onOpenChat={onOpenChat}
            />

            {showChatToggle && (
                <button
                    onClick={onToggleChat}
                    className={styles.navIcon}
                    style={{
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center',
                        color: showChat ? 'var(--sw-text-base)' : 'var(--sw-text-muted)',
                    }}
                    title={showChat ? "Fechar Assistente" : "Abrir Assistente"}
                >
                    {showChat ? <PanelRightOpen size={20} /> : <PanelRight size={20} />}
                </button>
            )}

            {onLogout && (
                <button
                    onClick={onLogout}
                    className={styles.navIcon}
                    style={{
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center',
                        color: 'var(--sw-text-muted)', transition: 'all 0.2s ease',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = '#f87171'; e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255, 255, 255, 0.6)'; e.currentTarget.style.background = 'transparent'; }}
                    title="Sair da Conta"
                >
                    <LogOut size={20} />
                </button>
            )}
        </div>
    </header>
);
