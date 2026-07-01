import React from 'react';
import { Loader2, Target } from 'lucide-react';
import styles from '../../styles/ChatPanel.module.css';
import { renderMarkdown } from '../markdown';

export const ProspectingPlanCard = ({
    isGenerating,
    planMarkdown,
    orgName
}: {
    isGenerating: boolean;
    planMarkdown: string | null;
    orgName: string | null;
}) => {
    return (
        <div style={{
            margin: '12px 0',
            background: 'var(--chat-bg-secondary)',
            border: 'var(--sw-border-width) solid var(--sw-border)',
            borderRadius: 12,
            overflow: 'hidden',
            boxShadow: 'var(--shadow-sm)'
        }}>
            <div style={{
                padding: '12px 14px',
                borderBottom: 'var(--sw-border-width) solid var(--sw-border)',
                background: 'var(--chat-console-bg)',
                display: 'flex',
                alignItems: 'center',
                gap: 8
            }}>
                {isGenerating ? (
                    <Loader2 size={14} className={styles.spinner} style={{ color: '#a78bfa' }} />
                ) : (
                    <Target size={14} style={{ color: '#a78bfa' }} />
                )}
                <span style={{ fontSize: 'var(--font-sm)', fontWeight: 600, color: 'var(--sw-text-base)' }}>
                    Plano de Prospecção (SPIN)
                </span>
                {orgName && (
                    <span style={{ fontSize: 'var(--font-xs)', color: 'var(--sw-text-muted)', marginLeft: 'auto' }}>
                        {orgName}
                    </span>
                )}
            </div>

            <div style={{ padding: '14px', fontSize: 'var(--font-sm)', color: 'var(--sw-text-base)', maxHeight: 400, overflowY: 'auto' }}>
                {isGenerating ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '10px 4px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--sw-text-muted)' }}>
                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'pulse 1.5s infinite' }} />
                            Analisando perfil dos decisores mapeados...
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--sw-text-muted)', opacity: 0.7 }}>
                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'pulse 1.5s infinite 0.5s' }} />
                            Avaliando ICP e fit de produto...
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--sw-text-muted)', opacity: 0.4 }}>
                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'pulse 1.5s infinite 1s' }} />
                            Redigindo sequências de abordagem e hooks...
                        </div>
                    </div>
                ) : planMarkdown ? (
                    <div className={styles.aiMessage}>
                        {renderMarkdown(planMarkdown)}
                    </div>
                ) : (
                    <div style={{ color: '#ef4444' }}>Plano não disponível ou erro na geração.</div>
                )}
            </div>
        </div>
    );
};
