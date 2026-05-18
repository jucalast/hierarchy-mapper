import React, { useState } from 'react';
import { Plus, MessageSquare, Loader2, Clock, Trash2, PanelRightClose, CheckSquare, Square } from 'lucide-react';
import { Avatar } from '../ui';
import type { ThreadOut } from '@/services/api/conversations';
import styles from './ChatPanel.module.css';

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
    onDeleteThreadsBulk?: (threads: ThreadOut[]) => void;
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
    onDeleteThreadsBulk,
    onBackToChat,
}) => {
    const [selectedThreads, setSelectedThreads] = useState<Set<string>>(new Set());

    const isAllSelected = threads.length > 0 && selectedThreads.size === threads.length;

    const toggleSelectAll = () => {
        if (isAllSelected) {
            setSelectedThreads(new Set());
        } else {
            setSelectedThreads(new Set(threads.map(t => t.id)));
        }
    };

    const toggleSelectThread = (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        const next = new Set(selectedThreads);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        setSelectedThreads(next);
    };

    const handleDeleteSelected = () => {
        if (!onDeleteThreadsBulk || selectedThreads.size === 0) return;
        const selected = threads.filter(t => selectedThreads.has(t.id));
        onDeleteThreadsBulk(selected);
        setSelectedThreads(new Set());
    };

    return (
        <div className={styles.threadListPanel}>
            {/* Header */}
            <div className={styles.tlHeader} style={{ paddingLeft: '16px', gap: '12px' }}>
                {selectedThreads.size > 0 ? (
                    <>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }} onClick={toggleSelectAll}>
                            <CheckSquare size={18} color="var(--sw-primary, #000)" />
                            <span style={{ color: 'var(--sw-text-base)', fontWeight: 600, fontSize: '0.88rem' }}>
                                {selectedThreads.size} {selectedThreads.size === 1 ? 'selecionada' : 'selecionadas'}
                            </span>
                        </div>
                        <div style={{ flex: 1 }} />
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginRight: '12px' }}>
                            <button
                                className={styles.tlItemDelete}
                                onClick={handleDeleteSelected}
                                title="Excluir selecionadas"
                                style={{ width: 'auto', padding: '0 12px', height: '32px', display: 'flex', gap: '6px', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', borderRadius: '6px' }}
                            >
                                <Trash2 size={14} />
                                <span style={{ fontSize: '13px', fontWeight: 500 }}>Excluir</span>
                            </button>
                            <button
                                className={`${styles.chatHeaderIconBtn}`}
                                onClick={() => setSelectedThreads(new Set())}
                                title="Cancelar"
                                style={{ width: 'auto', padding: '0 12px', height: '32px', fontSize: '13px', fontWeight: 500, color: 'var(--sw-text-muted)' }}
                            >
                                Cancelar
                            </button>
                        </div>
                    </>
                ) : (
                    <>
                        <Avatar 
                            kind="company"
                            src={selectedOrgLogo}
                            name={orgName}
                            size={32}
                            noInitialFallback={true}
                            style={{ border: selectedOrgLogo ? '1.5px solid var(--sw-border-strong)' : 'none' }}
                        />
                        <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '8px', flex: '0 1 auto', minWidth: 0 }}>
                            <span style={{ color: 'var(--sw-text-muted)', fontWeight: 600, fontSize: '0.88rem', flexShrink: 0 }}>
                                Histórico
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
                                title={orgName || 'Geral'}
                            >
                                {orgName || 'Geral'}
                            </span>
                        </div>
                        <div style={{ flex: 1 }} />
                        {threads.length > 0 && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginRight: '12px' }}>
                                <button
                                    className={`${styles.chatHeaderIconBtn}`}
                                    onClick={toggleSelectAll}
                                    title="Selecionar várias conversas"
                                >
                                    <CheckSquare size={16} />
                                </button>
                                <button
                                    className={styles.tlNewBtn}
                                    onClick={onNewThread}
                                    disabled={isCreating}
                                    title="Nova conversa"
                                    style={{ height: '32px', padding: '0 12px', fontSize: '12px' }}
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
                    </>
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
                            {isCreating ? <Loader2 size={15} className={styles.spinner} /> : <Plus size={16} strokeWidth={2.5} />}
                            <span style={{ lineHeight: 1 }}>Iniciar conversa</span>
                        </button>
                    </div>
                )}

                {!isLoading && threads.map((thread) => (
                    <div
                        key={thread.id}
                        className={`${styles.tlItem} ${selectedThreads.has(thread.id) ? styles.tlItemSelected : ''}`}
                        onClick={() => onSelectThread(thread)}
                    >
                        <div 
                            className={styles.tlItemCheckbox} 
                            onClick={(e) => toggleSelectThread(thread.id, e)}
                        >
                            {selectedThreads.has(thread.id) 
                                ? <CheckSquare size={16} color="var(--sw-primary, #000)" /> 
                                : <Square size={16} color="var(--sw-text-muted)" />
                            }
                        </div>
                        
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
