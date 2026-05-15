import React from 'react';
import { Plus, Trash2, Clock, MessageSquare } from 'lucide-react';
import { Avatar } from '@/components/ui';
import type { ThreadOut } from '@/services/api/conversations';
import styles from '../styles/components/ThreadList.module.css';

interface ThreadListViewProps {
    threads: ThreadOut[];
    isLoadingThreads: boolean;
    onNewThread: () => void;
    onOpenThread: (thread: ThreadOut) => void;
    onDeleteThread: (thread: ThreadOut) => void;
    selectedOrgName: string;
    selectedOrgLogo?: string;
    isCreatingThread: boolean;
}

export const ThreadListView: React.FC<ThreadListViewProps> = ({
    threads,
    isLoadingThreads,
    onNewThread,
    onOpenThread,
    onDeleteThread,
    selectedOrgName,
    selectedOrgLogo,
    isCreatingThread
}) => {
    return (
        <div className={styles.threadListPanel}>
            <div className={styles.tlHeader}>
                <Avatar 
                    src={selectedOrgLogo} 
                    name={selectedOrgName} 
                    size="sm" 
                    className={styles.tlHeaderAvatar}
                />
                <div className={styles.tlHeaderInfo}>
                    <span className={styles.tlOrgName}>{selectedOrgName}</span>
                    <span className={styles.tlSubtitle}>Conversas</span>
                </div>
                <button 
                    className={styles.tlNewBtn} 
                    onClick={onNewThread}
                    disabled={isCreatingThread}
                >
                    <Plus size={16} />
                    Novo Chat
                </button>
            </div>

            <div className={styles.tlList}>
                {isLoadingThreads ? (
                    <div className={styles.tlLoading}>Carregando conversas...</div>
                ) : threads.length === 0 ? (
                    <div className={styles.tlEmpty}>
                        <MessageSquare size={40} className={styles.tlEmptyIcon} />
                        <span className={styles.tlEmptyTitle}>Nenhuma conversa ainda</span>
                        <span className={styles.tlEmptyDesc}>
                            Inicie um novo chat para começar a mapear decisores e gerir oportunidades.
                        </span>
                        <button className={styles.tlEmptyNewBtn} onClick={onNewThread}>
                            <Plus size={18} /> Iniciar agora
                        </button>
                    </div>
                ) : (
                    threads.map(thread => (
                        <button 
                            key={thread.id} 
                            className={styles.tlItem}
                            onClick={() => onOpenThread(thread)}
                        >
                            <div className={styles.tlItemIcon}>
                                <Clock size={16} />
                            </div>
                            <div className={styles.tlItemContent}>
                                <div className={styles.tlItemTop}>
                                    <span className={styles.tlItemTitle}>{thread.title || 'Conversa sem título'}</span>
                                    <span className={styles.tlItemDate}>
                                        {new Date(thread.updated_at || thread.created_at).toLocaleDateString()}
                                    </span>
                                </div>
                                <div className={styles.tlItemBottom}>
                                    <span className={styles.tlItemCount}>
                                        <MessageSquare size={10} /> {thread.message_count || 0} msgs
                                    </span>
                                </div>
                            </div>
                            <div className={styles.tlItemActions}>
                                <button 
                                    className={styles.tlItemDelete}
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDeleteThread(thread);
                                    }}
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </button>
                    ))
                )}
            </div>
        </div>
    );
};
