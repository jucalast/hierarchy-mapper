import React from 'react';
import { Plus, MessageSquare, Loader2, Clock, Trash2, PanelRightClose } from 'lucide-react';
import { Avatar } from '@/components/ui';
import type { ThreadOut } from '@/services/api/conversations';
import styles from '../styles/ChatPanel.module.css';

interface ThreadListProps {
    orgName: string;
    onCloseChat?: () => void;
    threads: ThreadOut[];
    isLoading: boolean;
    onSelectThread: (thread: ThreadOut) => void;
    onNewThread: () => void;
    isCreating: boolean;
    selectedOrgLogo?: string;
    onDeleteThread?: (thread: ThreadOut) => void;
    onBackToChat?: () => void;
}

function formatDate(isoStr: string | null): string {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffH = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMin < 2) return 'agora';
    if (diffMin < 60) return `${diffMin}m`;
    if (diffH < 24 && d.getDate() === now.getDate()) {
        return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
    if (diffDays < 2) return 'ontem';
    if (diffDays < 7) return d.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '');
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '');
}

export const ThreadList: React.FC<ThreadListProps> = ({
    orgName,
    onCloseChat,
    threads,
    isLoading,
    onSelectThread,
    onNewThread,
    isCreating,
    selectedOrgLogo,
    onDeleteThread,
    onBackToChat,
}) => {
    return (
        <div className={styles.threadListPanel}>
            {/* Header */}
            <div className={styles.tlHeader}>
                <div className={styles.tlHeaderAvatar}>
                    <Avatar 
                        kind="company"
                        src={selectedOrgLogo}
                        name={orgName}
                        size={32}
                        noInitialFallback={true}
                        style={{ border: '3px solid #272727ff' }}
                    />
                </div>
                <div className={styles.tlHeaderInfo}>
                    <span className={styles.tlOrgName}>{orgName || 'Geral'}</span>
                    <span className={styles.tlSubtitle}>Workspace</span>
                </div>
                {threads.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <button
                            className={styles.tlNewBtn}
                            onClick={onNewThread}
                            disabled={isCreating}
                            title="Nova conversa"
                        >
                            {isCreating
                                ? <Loader2 size={14} className={styles.spinner} />
                                : <Plus size={14} />
                            }
                            <span>Nova</span>
                        </button>
                        <button
                            className={`${styles.chatHeaderIconBtn} ${styles.chatHeaderIconBtnActive}`}
                            onClick={onBackToChat}
                            title="Fechar histórico"
                        >
                            <Clock size={20} />
                        </button>
                    </div>
                )}
            </div>

            {/* List */}
            <div className={styles.tlList}>
                {isLoading && (
                    <div className={styles.tlLoading}>
                        <Loader2 size={16} className={styles.spinner} />
                        <span>Carregando conversas...</span>
                    </div>
                )}

                {!isLoading && threads.length === 0 && (
                    <div className={styles.tlEmpty}>
                        <div className={styles.tlEmptyIcon}>
                            <MessageSquare size={28} strokeWidth={1.2} />
                        </div>
                        <div className={styles.tlEmptyTitle}>Nenhuma conversa ainda</div>
                        <div className={styles.tlEmptyDesc}>
                            Inicie uma nova conversa com o agente sobre {orgName || 'todos os seus negócios'}.
                        </div>
                        <button className={styles.tlEmptyNewBtn} onClick={onNewThread} disabled={isCreating}>
                            {isCreating ? <Loader2 size={13} className={styles.spinner} /> : <Plus size={13} />}
                            <span>Iniciar conversa</span>
                        </button>
                    </div>
                )}

                {!isLoading && threads.map((thread) => (
                    <div
                        key={thread.id}
                        className={styles.tlItem}
                        onClick={() => onSelectThread(thread)}
                    >
                        {/* Icon */}
                        <div className={styles.tlItemIcon}>
                            <MessageSquare size={14} strokeWidth={1.5} />
                        </div>

                        {/* Content */}
                        <div className={styles.tlItemContent}>
                            <div className={styles.tlItemTop}>
                                <span className={styles.tlItemTitle}>
                                    {thread.title || 'Conversa'}
                                </span>
                                <span className={styles.tlItemDate}>
                                    {formatDate(thread.last_message_at || thread.updated_at)}
                                </span>
                            </div>
                            <div className={styles.tlItemBottom}>
                                <span className={styles.tlItemCount}>
                                    <Clock size={9} />
                                    {thread.message_count} {thread.message_count === 1 ? 'mensagem' : 'mensagens'}
                                </span>
                            </div>
                        </div>


                        <div className={styles.tlItemActions}>
                            <ChevronRight size={13} className={styles.tlItemChevron} />
                            {onDeleteThread && (
                                <button
                                    className={styles.tlItemDelete}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDeleteThread(thread);
                                    }}
                                    title="Excluir conversa"
                                >
                                    <Trash2 size={13} />
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

// Need ChevronRight imported
function ChevronRight({ size, className }: { size: number; className?: string }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
            <polyline points="9 18 15 12 9 6" />
        </svg>
    );
}
