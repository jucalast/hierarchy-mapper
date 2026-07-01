import React, { useRef, useEffect, useState } from 'react';
import {
    X, Loader2, Building2, Mic, ArrowUp, Zap, AlertTriangle, CheckCircle2, XCircle, Maximize2, Minimize2, Terminal, Play, Check, ChevronDown, ChevronUp
} from 'lucide-react';
import { CompanyResult } from '../ChatInterfaces';
import { getAvatarUrl, getProxiedUrl, getCompanyLogoUrl } from '../../../utils/avatarUtils';
import styles from '../styles/ChatPanel.module.css';
import { ModelSelector, AIModel } from './ModelSelector';
import { ModelActivityBar, ModelActivityEvent, getNoticeStyle } from './ModelActivityBar';
import { AudioWaveform } from './AudioWaveform';
import { InlineEventStream, MappedContact } from '../AgentV2Message';
// AgentEvent re-exported for consumers
export type { AgentEvent } from '../AgentV2Message';
import { ActiveTaskConsole } from './ActiveTaskConsole';
import type { BatchQueueItem } from '../../../store/chatStore';

interface ChatInputProps {
    inputValue: string;
    setInputValue: (val: string) => void;
    isLoading: boolean;
    onSend: (text: string, companies: CompanyResult[]) => void;
    selectedCompanies: CompanyResult[];
    setSelectedCompanies: (companies: CompanyResult[]) => void;
    // Autocomplete props
    showAutocomplete: boolean;
    isSearching: boolean;
    searchingCategory: string | null;
    searchTerm: string;
    companies: CompanyResult[];
    selectSearchResult: (company: CompanyResult) => void;
    // Speech props
    isListening: boolean;
    isTranscribing?: boolean;
    startListening: () => void;
    stopListening: () => void;
    voiceError?: string | null;
    voiceSupported?: boolean;
    analyserNode?: React.MutableRefObject<AnalyserNode | null>;
    // Model props
    model: AIModel;
    setModel: (model: AIModel) => void;
    strictMode?: boolean;
    setStrictMode?: (strict: boolean) => void;
    liveModel?: AIModel | null;
    modelActivity?: ModelActivityEvent[];
    isStreamingActivity?: boolean;
    // Cooldown props
    pipedriveCooldown?: number;
    // Styling
    theme: string;
    onStop?: () => void;
    // Task console props
    activeRunningTask?: any;
    setActiveRunningTask?: (val: any) => void;
    taskInlineConfirmed?: Record<string, boolean>;
    onTaskInlineConfirm?: (action_id: string, approved: boolean) => Promise<void>;
    onTaskMappingComplete?: (contacts: MappedContact[]) => Promise<void>;
    onCancelActiveTask?: () => void;
    // Batch queue props
    batchQueue?: BatchQueueItem[];
    isBatchRunning?: boolean;
    batchRunningSnapshot?: BatchQueueItem[];
    batchCurrentIndex?: number;
    onExecuteBatch?: () => void;
    onClearBatch?: () => void;
    onRemoveBatchItem?: (messageId: string, actionIndex: number, action: BatchQueueItem['action']) => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({
    inputValue, setInputValue, isLoading, onSend,
    selectedCompanies, setSelectedCompanies,
    showAutocomplete, isSearching, searchingCategory, searchTerm, companies, selectSearchResult,
    isListening, isTranscribing = false, startListening, stopListening, voiceError, voiceSupported = true, analyserNode,
    model, setModel,
    strictMode = false,
    setStrictMode,
    liveModel,
    modelActivity = [],
    isStreamingActivity = false,
    pipedriveCooldown = 0,
    theme, onStop, activeRunningTask, setActiveRunningTask,
    taskInlineConfirmed, onTaskInlineConfirm, onTaskMappingComplete, onCancelActiveTask,
    batchQueue = [], isBatchRunning = false, batchRunningSnapshot = [], batchCurrentIndex = -1,
    onExecuteBatch, onClearBatch, onRemoveBatchItem,
}) => {
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const highlighterRef = useRef<HTMLDivElement>(null);
    const autocompleteRef = useRef<HTMLDivElement>(null);
    const taskConsoleLogsBottomRef = useRef<HTMLDivElement>(null);
    const [isStopHovered, setIsStopHovered] = useState(false);
    const [batchConsoleOpen, setBatchConsoleOpen] = useState(false);

    const isExpandedRunningTask = activeRunningTask && activeRunningTask.isExpanded;

    useEffect(() => {
        if (isBatchRunning) setBatchConsoleOpen(true);
    }, [isBatchRunning]);

    useEffect(() => {
        if (isExpandedRunningTask) {
            taskConsoleLogsBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [activeRunningTask?.logs, isExpandedRunningTask]);

    // Sincronizar scroll do highlighter com o textarea
    const handleScroll = () => {
        if (inputRef.current && highlighterRef.current) {
            highlighterRef.current.scrollTop = inputRef.current.scrollTop;
        }
    };

    // Auto-ajuste de altura e scroll
    useEffect(() => {
        if (inputRef.current) {
            const currentScrollTop = inputRef.current.scrollTop;
            const isAtBottom = inputRef.current.scrollHeight - inputRef.current.scrollTop <= inputRef.current.clientHeight + 10;
            const isCursorAtEnd = inputRef.current.selectionStart === inputValue.length;

            inputRef.current.style.height = 'auto';
            const newHeight = Math.min(inputRef.current.scrollHeight, 100);
            inputRef.current.style.height = `${newHeight}px`;

            if (highlighterRef.current) {
                highlighterRef.current.style.height = 'auto';
                highlighterRef.current.style.height = `${newHeight}px`;
            }

            if (isAtBottom || isCursorAtEnd) {
                inputRef.current.scrollTop = inputRef.current.scrollHeight;
            } else {
                inputRef.current.scrollTop = currentScrollTop;
            }
            
            if (highlighterRef.current) {
                highlighterRef.current.scrollTop = inputRef.current.scrollTop;
            }
        }
    }, [inputValue]);

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey && !showAutocomplete && !isLoading) {
            e.preventDefault();
            if (inputValue.trim() || selectedCompanies.length > 0) {
                onSend(inputValue, selectedCompanies);
            }
        }
    };

    const renderHighlightedText = (text: string) => {
        if (!text) return text;

        // Criar um regex dinâmico com os nomes das empresas selecionadas (se houver)
        let entityRegexPart = "";
        if (selectedCompanies.length > 0) {
            const escapedNames = selectedCompanies
                .map(c => c.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
                .join('|');
            entityRegexPart = `@(?:${escapedNames})|`;
        }

        // Regex final: busca nomes selecionados OU @ seguido de caracteres compostos
        // Usamos [A-Za-z\u00C0-\u017F\s\-&] para suportar espaços, acentos, hífens e ampersands
        const finalRegex = new RegExp(`(${entityRegexPart}@[A-Za-z\\u00C0-\\u017F0-9\\s\\-&]+?)(?=\\s*[.,;!?(){}\\[\\]<>]|\\s+@|$)`, 'g');
        const parts = text.split(finalRegex);

        return parts.map((part, i) => {
            if (part && part.startsWith('@')) {
                return <span key={i} className={styles.highlightPurple}>{part}</span>;
            }
            return part;
        });
    };

    const getInitials = (name: string) => name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
    const OrgIcon = () => <Building2 size={16} className="shrink-0 opacity-40" />;

    const notice = getNoticeStyle(modelActivity || [], undefined, theme);
    const hasRunningTask = !!activeRunningTask;
    const hasBatchBar = batchQueue.length > 0 || isBatchRunning;
    const isExpandedBatchConsole = isBatchRunning && batchConsoleOpen && !!activeRunningTask;

    const consoleBg = 'var(--chat-console-bg)';

    const taskStyle = ((hasRunningTask || hasBatchBar) && !isExpandedRunningTask && !isExpandedBatchConsole) ? {
        border: 'var(--sw-border-width) solid var(--chat-border-weak)',
        background: consoleBg,
        borderRadius: 'var(--radius-lg)',
        pointerEvents: 'auto' as const,
        overflow: 'hidden',
    } : null;

    const inputContainerStyle = (isExpandedRunningTask || isExpandedBatchConsole) ? {
        position: 'absolute' as const,
        top: isExpandedBatchConsole ? '18%' : '30%',
        bottom: 0,
        left: 0,
        width: '100%',
        padding: '0 20px 20px',
        pointerEvents: 'none' as const,
        display: 'flex',
        flexDirection: 'column' as const,
    } : {};

    const expandedTaskStyle = (isExpandedRunningTask || isExpandedBatchConsole) ? {
        border: 'var(--sw-border-width) solid var(--chat-border-weak)',
        background: consoleBg,
        borderRadius: 'var(--radius-lg)',
        pointerEvents: 'auto' as const,
        display: 'flex',
        flexDirection: 'column' as const,
        overflow: 'hidden',
        flex: 1,
        height: '100%',
    } : null;

    const containerStyle = expandedTaskStyle || taskStyle || (notice ? {
        border: 'var(--sw-border-width) solid var(--chat-border-weak)',
        background: notice.bg,
        borderRadius: 'var(--radius-lg)',
        pointerEvents: 'auto' as const,
        overflow: 'hidden' as const,
    } : {});

    const renderTaskMinimizedBar = () => {
        if (!activeRunningTask) return null;

        const isStreaming = activeRunningTask.status === 'streaming';
        const isAwaiting = activeRunningTask.status === 'awaiting_mapping' || activeRunningTask.status === 'awaiting_confirm';
        const isDone = activeRunningTask.status === 'done';
        const isCancelled = activeRunningTask.status === 'cancelled';
        const isErr = activeRunningTask.status === 'error';

        // Cores correspondentes ao componente de notificação de LLM
        const statusColor = isStreaming ? 'var(--sw-primary)' : isAwaiting ? 'var(--sw-status-warning)' : isDone ? 'var(--sw-status-success)' : isCancelled ? 'var(--sw-text-muted)' : 'var(--sw-status-danger)';
        const statusLabel = isStreaming ? 'Executando tarefa' : isAwaiting ? 'Ação requerida' : isDone ? 'Tarefa concluída' : isCancelled ? 'Tarefa cancelada' : 'Falha na tarefa';

        return (
            <div
                onClick={() => setActiveRunningTask?.({ ...activeRunningTask, isExpanded: !activeRunningTask.isExpanded })}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '8px 16px',
                    fontSize: 'var(--font-sm)',
                    fontWeight: 500,
                    color: 'var(--sw-text-subtle)',
                    letterSpacing: '0.01em',
                    cursor: 'pointer',
                    userSelect: 'none',
                    transition: 'opacity 0.2s',
                    background: consoleBg,
                    borderTopLeftRadius: 'var(--radius-lg)',
                    borderTopRightRadius: 'var(--radius-lg)',
                }}
            >
                <span style={{ color: statusColor, fontWeight: 600 }}>{statusLabel}</span>
                <span style={{ opacity: 0.25, color: 'var(--sw-text-base)' }}>·</span>
                <span style={{
                    flex: 1,
                    minWidth: 0,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    color: 'var(--sw-text-base)',
                }}>
                    {activeRunningTask.label}
                </span>

                <span style={{
                    fontSize: 'var(--font-xs)',
                    color: 'var(--sw-text-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    fontWeight: 600,
                    marginRight: 4
                }}>
                    Console
                </span>

                <span style={{
                    width: 5,
                    height: 5,
                    borderRadius: '50%',
                    background: statusColor,
                    flexShrink: 0,
                    animation: (isStreaming || isAwaiting) ? 'modelLivePulse 1.4s ease-in-out infinite' : 'none',
                }} />

                <div
                    onClick={(e) => {
                        e.stopPropagation();
                        if (onCancelActiveTask) onCancelActiveTask();
                        else setActiveRunningTask?.(null);
                    }}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 24,
                        height: 24,
                        borderRadius: '50%',
                        marginLeft: 8,
                        color: 'var(--sw-text-muted)',
                        transition: 'all 0.2s',
                    }}
                    onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'var(--sw-hover)';
                        e.currentTarget.style.color = 'var(--sw-text-base)';
                    }}
                    onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'transparent';
                        e.currentTarget.style.color = 'var(--sw-text-muted)';
                    }}
                    title="Fechar console"
                >
                    <X size={14} />
                </div>
            </div>
        );
    };

    const renderBatchQueueBar = () => {
        if (!hasBatchBar) return null;

        const accentColor = '#6366f1';
        const count = batchQueue.length;
        const statusLabel = isBatchRunning
            ? 'Executando em lote'
            : `${count} ${count === 1 ? 'ação na fila' : 'ações na fila'}`;

        const iconBtn = (onClick: React.MouseEventHandler, title: string, children: React.ReactNode) => (
            <div
                onClick={onClick}
                title={title}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    color: 'var(--sw-text-muted)',
                    cursor: 'pointer',
                    flexShrink: 0,
                    transition: 'all 0.2s',
                }}
                onMouseEnter={e => {
                    e.currentTarget.style.background = 'var(--sw-hover)';
                    e.currentTarget.style.color = 'var(--sw-text-base)';
                }}
                onMouseLeave={e => {
                    e.currentTarget.style.background = 'transparent';
                    e.currentTarget.style.color = 'var(--sw-text-muted)';
                }}
            >
                {children}
            </div>
        );

        return (
            <div style={{
                background: consoleBg,
                borderTopLeftRadius: 'var(--radius-lg)',
                borderTopRightRadius: 'var(--radius-lg)',
                userSelect: 'none',
                ...(isExpandedBatchConsole ? {
                    display: 'flex',
                    flexDirection: 'column' as const,
                    flex: 1,
                    minHeight: 0,
                    overflow: 'hidden',
                } : {}),
            }}>
                {/* Header row — clicável para abrir/fechar console quando executando em lote */}
                <div
                    onClick={isBatchRunning ? () => setBatchConsoleOpen(prev => !prev) : undefined}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '8px 16px',
                        fontSize: 'var(--font-sm)',
                        fontWeight: 500,
                        letterSpacing: '0.01em',
                        cursor: isBatchRunning ? 'pointer' : 'default',
                    }}
                >
                    <span style={{ color: accentColor, fontWeight: 600, flex: 1 }}>{statusLabel}</span>

                    {isBatchRunning && (
                        <span style={{ color: 'var(--sw-text-muted)', display: 'flex', alignItems: 'center' }}>
                            {batchConsoleOpen
                                ? <ChevronDown size={14} />
                                : <ChevronUp size={14} />}
                        </span>
                    )}

                    {!isBatchRunning && (
                        <button
                            onClick={(e) => { e.stopPropagation(); onExecuteBatch?.(); }}
                            title={`Executar ${count} ${count === 1 ? 'ação' : 'ações'}`}
                            style={{
                                width: 26,
                                height: 26,
                                borderRadius: 7,
                                background: theme === 'light' ? '#000000' : '#ffffff',
                                color: theme === 'light' ? '#ffffff' : '#000000',
                                border: theme === 'light' ? '1px solid rgba(0,0,0,0.45)' : '1px solid var(--sw-border-strong)',
                                boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexShrink: 0,
                                transition: 'all 0.2s ease',
                                transform: 'translateY(-1px)',
                            }}
                            onMouseEnter={e => {
                                e.currentTarget.style.transform = 'translateY(-2px)';
                                e.currentTarget.style.boxShadow = '0 4px 10px rgba(0,0,0,0.2)';
                            }}
                            onMouseLeave={e => {
                                e.currentTarget.style.transform = 'translateY(-1px)';
                                e.currentTarget.style.boxShadow = '0 2px 6px rgba(0,0,0,0.15)';
                            }}
                            onMouseDown={e => (e.currentTarget.style.transform = 'translateY(0)')}
                            onMouseUp={e => (e.currentTarget.style.transform = 'translateY(-1px)')}
                        >
                            <Play size={11} strokeWidth={2.5} />
                        </button>
                    )}

                </div>

                {/* Item list — idle: batchQueue com botão remover; running: snapshot com status */}
                {(() => {
                    const listItems = isBatchRunning ? batchRunningSnapshot : batchQueue;
                    if (listItems.length === 0) return null;
                    return (
                        <>
                            {listItems.map((item, idx) => {
                                const isDone = isBatchRunning && idx < batchCurrentIndex;
                                const isActive = isBatchRunning && idx === batchCurrentIndex;
                                return (
                                    <div
                                        key={`${item.messageId}-${item.actionIndex}`}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 8,
                                            padding: '5px 16px 5px 20px',
                                            fontSize: 'var(--font-sm)',
                                            borderTop: idx === 0 ? 'var(--sw-border-width) solid var(--sw-border)' : 'none',
                                            opacity: isBatchRunning && !isDone && !isActive ? 0.45 : 1,
                                            transition: 'opacity 0.2s',
                                        }}
                                    >
                                        {/* Status icon */}
                                        <span style={{ flexShrink: 0, width: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                            {isDone && <Check size={13} strokeWidth={2.5} color="#22c55e" />}
                                            {isActive && <Loader2 size={13} strokeWidth={2.5} color={accentColor} style={{ animation: 'spin 1s linear infinite' }} />}
                                            {!isDone && !isActive && (
                                                <span style={{ fontSize: 'var(--font-xs)', color: accentColor, fontWeight: 700 }}>
                                                    {idx + 1}.
                                                </span>
                                            )}
                                        </span>
                                        <span style={{
                                            flex: 1,
                                            minWidth: 0,
                                            whiteSpace: 'nowrap',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            color: isActive ? 'var(--sw-text-base)' : 'var(--sw-text-subtle)',
                                            fontWeight: isActive ? 500 : 400,
                                        }}>
                                            {item.action.label}
                                        </span>
                                        {!isBatchRunning && iconBtn(
                                            (e) => { e.stopPropagation(); onRemoveBatchItem?.(item.messageId, item.actionIndex, item.action); },
                                            'Remover da fila',
                                            <X size={12} />
                                        )}
                                    </div>
                                );
                            })}
                            <div style={{ height: 6 }} />
                        </>
                    );
                })()}

                {/* Console de execução em lote — só aparece quando executando e header está aberto */}
                {isExpandedBatchConsole && activeRunningTask && (
                    <ActiveTaskConsole
                        activeRunningTask={activeRunningTask}
                        isExpanded={true}
                        inlineConfirmed={taskInlineConfirmed || {}}
                        onInlineConfirm={onTaskInlineConfirm || (async () => { })}
                        onMappingComplete={onTaskMappingComplete}
                        model={model}
                        theme={theme}
                    />
                )}
            </div>
        );
    };


    return (
        <div className={styles.inputContainer} style={inputContainerStyle}>
            <div style={containerStyle}>
                {notice && <ModelActivityBar events={modelActivity || []} theme={theme} />}
                {renderBatchQueueBar()}
                {hasRunningTask && !isBatchRunning && renderTaskMinimizedBar()}
                {isExpandedRunningTask && !isExpandedBatchConsole && (
                    <ActiveTaskConsole
                        activeRunningTask={activeRunningTask}
                        isExpanded={isExpandedRunningTask}
                        inlineConfirmed={taskInlineConfirmed || {}}
                        onInlineConfirm={onTaskInlineConfirm || (async () => { })}
                        onMappingComplete={onTaskMappingComplete}
                        model={model}
                        theme={theme}
                    />
                )}
                <div
                    className={styles.inputBox}
                    style={(isExpandedRunningTask || isExpandedBatchConsole) ? {
                        padding: '8px',
                    } : {}}
                >
                    <div className={styles.inputFieldWrapper}>
                        {selectedCompanies.length > 0 && (
                            <div className={styles.inputCompaniesContainer}>
                                {selectedCompanies.map((company) => (
                                    <div key={company.id} className={styles.inputCompanyPill}>
                                        <div className={styles.pillIconArea}>
                                            {company.type === 'organization' ? (
                                                getCompanyLogoUrl(company) ? (
                                                    <img
                                                        src={getProxiedUrl(getCompanyLogoUrl(company))}
                                                        className={styles.pillCompanyLogo}
                                                        onError={(e) => { e.currentTarget.style.display = 'none'; }}
                                                    />
                                                ) : <OrgIcon />
                                            ) : (
                                                getAvatarUrl(company) ? (
                                                    <img
                                                        src={getProxiedUrl(getAvatarUrl(company))}
                                                        className={styles.pillCompanyLogo}
                                                        style={{ borderRadius: '50%' }}
                                                        onError={(e) => {
                                                            e.currentTarget.src = company.type === 'whatsapp' ? '/wppicon.png' : '/outlook.png';
                                                            e.currentTarget.style.objectFit = 'contain';
                                                            e.currentTarget.style.padding = '2px';
                                                        }}
                                                    />
                                                ) : (
                                                    company.type === 'whatsapp' ? <img src="/wppicon.png" alt="W" style={{ width: 18, height: 18, objectFit: 'contain' }} /> : <img src="/outlook.png" alt="E" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                                                )
                                            )}
                                        </div>
                                        <div className={styles.pillInfo}>
                                            <span className={styles.pillName}>{company.name}</span>
                                            <span className={styles.pillSubtext}>
                                                {(() => {
                                                    if (company.type === 'organization') return 'empresa';
                                                    if (company.type === 'email') return company.email;
                                                    if (company.type === 'whatsapp') return (company as any).number || company.phone;
                                                    return company.type;
                                                })()}
                                            </span>
                                        </div>
                                        <button
                                            className={styles.removePillBtn}
                                            onClick={() => setSelectedCompanies(selectedCompanies.filter(c => c.id !== company.id))}
                                            type="button"
                                        >
                                            <X size={14} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className={styles.inputBoxInterior}>
                            <div className={styles.inputHighlighter} ref={highlighterRef}>
                                {renderHighlightedText(inputValue)}
                                {inputValue.endsWith(' ') && <span style={{ visibility: 'hidden' }}>&nbsp;</span>}
                            </div>

                            <textarea
                                ref={inputRef}
                                value={inputValue}
                                onChange={(e) => setInputValue(e.target.value)}
                                onScroll={handleScroll}
                                onKeyDown={handleKeyPress}
                                placeholder="Digite @ para buscar uma empresa..."
                                className={styles.inputField}
                                rows={1}
                                spellCheck={false}
                                autoCorrect="off"
                                autoCapitalize="sentences"
                            />
                        </div>

                        {showAutocomplete && (
                            <div ref={autocompleteRef} className={styles.autocompleteDropdown}>
                                {isSearching && (
                                    <div className={styles.autocompleteLoading}>
                                        <Loader2 size={16} className={styles.spinner} />
                                        Buscando {searchingCategory || 'empresas'}...
                                    </div>
                                )}
                                {!isSearching && companies.length === 0 && searchTerm.trim().length > 0 && (
                                    <div className={styles.autocompleteEmpty}>Nenhum resultado encontrado</div>
                                )}
                                {!isSearching && companies.length > 0 && (
                                    <div className={styles.autocompleteList}>
                                        {companies.map((item, index) => (
                                            <button
                                                key={`${item.type}-${item.id}-${index}`}
                                                className={styles.autocompleteItem}
                                                onClick={() => {
                                                    selectSearchResult(item);
                                                    setTimeout(() => {
                                                        // Se o que vem após o @ já é exatamente um dos nomes selecionados, 
                                                        // paramos de pesquisar para este @ específico.
                                                        const query = searchTerm;
                                                        const matchedSelection = selectedCompanies.find(c => query.toLowerCase().startsWith(c.name.toLowerCase()));
                                                        if (matchedSelection) {
                                                            const afterName = query.substring(matchedSelection.name.length);
                                                            if (afterName.length > 0) {
                                                                return;
                                                            }
                                                        }
                                                        if (inputRef.current) {
                                                            inputRef.current.focus();
                                                            const length = inputRef.current.value.length;
                                                            inputRef.current.setSelectionRange(length, length);
                                                        }
                                                    }, 50); // Um tempo levemente maior para garantir o render do texto novo
                                                }}
                                            >
                                                <div className={styles.itemIcon} style={{ background: 'transparent' }}>
                                                    {item.type === 'organization' ? (
                                                        <div className={`${styles.initialsAvatar} ${styles.square}`} style={{ borderRadius: '4px' }}>
                                                            {getInitials(item.name)}
                                                        </div>
                                                    ) : (
                                                        getAvatarUrl(item) ? (
                                                            <img
                                                                src={getProxiedUrl(getAvatarUrl(item))}
                                                                alt={item.name}
                                                                style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }}
                                                                onError={(e) => {
                                                                    e.currentTarget.src = item.type === 'whatsapp' ? '/wppicon.png' : '/outlook.png';
                                                                    e.currentTarget.style.objectFit = 'contain';
                                                                    e.currentTarget.style.padding = '4px';
                                                                }}
                                                            />
                                                        ) : (
                                                            item.type === 'whatsapp' ?
                                                                <img src="/wppicon.png" alt="W" style={{ width: 22, height: 22, objectFit: 'contain' }} /> :
                                                                <img src="/outlook.png" alt="E" style={{ width: 22, height: 22, objectFit: 'contain' }} />
                                                        )
                                                    )}
                                                </div>
                                                <div className={styles.itemInfo}>
                                                    <div className={styles.itemName}>{item.name}</div>
                                                    <div className={styles.itemType}>
                                                        {(() => {
                                                            if (item.type === 'organization') return item.domain || 'empresa';
                                                            if (item.type === 'email') return (item.email && item.email !== item.name) ? item.email : 'email';
                                                            if (item.type === 'whatsapp') {
                                                                const contact = (item as any).number || item.phone;
                                                                return (contact && contact !== item.name) ? contact : 'whatsapp';
                                                            }
                                                            return item.type;
                                                        })()}
                                                    </div>
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}

                        <div className={styles.inputBottom}>
                            {isListening ? (
                                /* ── Modo gravação: ondas + botão stop ── */
                                <div className={styles.recordingBar}>
                                    <span className={styles.recordingDot} />
                                    {analyserNode && (
                                        <AudioWaveform analyserNode={analyserNode} isActive={isListening} />
                                    )}
                                    <button
                                        className={styles.stopRecordingBtn}
                                        onClick={stopListening}
                                        title="Parar gravação"
                                    >
                                        <Loader2 size={18} className={styles.spinner} />
                                        Parar
                                    </button>
                                </div>
                            ) : (
                                /* ── Modo normal ── */
                                <div className={styles.inputLeftControls}>
                                    <ModelSelector
                                        model={model}
                                        setModel={setModel}
                                        strictMode={strictMode}
                                        setStrictMode={setStrictMode}
                                        theme={theme}
                                        liveModel={liveModel}
                                    />
                                    {pipedriveCooldown > 0 && (
                                        <>
                                            <div className={styles.dividerSmall}>|</div>
                                            <div className={styles.cooldownBadge} title="Pipedrive em Cooldown (Aguardando reset de cota)">
                                                <Zap size={12} className={styles.cooldownIcon} />
                                                <span>
                                                    {Math.floor(pipedriveCooldown / 60)}:{String(pipedriveCooldown % 60).padStart(2, '0')}
                                                </span>
                                            </div>
                                        </>
                                    )}
                                    <div className={styles.dividerSmall}>|</div>
                                    <button
                                        className={styles.voiceBtn}
                                        onClick={startListening}
                                        disabled={!voiceSupported || isTranscribing}
                                        title={
                                            !voiceSupported
                                                ? 'Captura de áudio não suportada neste navegador'
                                                : isTranscribing
                                                    ? 'Transcrevendo...'
                                                    : 'Enviar por voz'
                                        }
                                    >
                                        {isTranscribing
                                            ? <Loader2 size={16} className={styles.spinner} />
                                            : <Mic size={16} />
                                        }
                                        <span className={styles.voiceBtnLabel}>
                                            {isTranscribing ? 'Transcrevendo' : 'Voz'}
                                        </span>
                                    </button>
                                </div>
                            )}

                            <button
                                className={`${styles.sendBtn} ${(!isLoading && (inputValue.trim() || selectedCompanies.length > 0)) ? styles.active : ''}`}
                                onMouseEnter={() => { if (isLoading) setIsStopHovered(true); }}
                                onMouseLeave={() => { setIsStopHovered(false); }}
                                style={isLoading ? {
                                    background: isStopHovered ? 'rgba(239, 68, 68, 0.3)' : 'rgba(239, 68, 68, 0.2)',
                                    color: '#ef4444',
                                    opacity: 1,
                                    cursor: 'pointer',
                                    transition: 'all 0.2s',
                                    transform: isStopHovered ? 'scale(1.08)' : 'scale(1.05)',
                                    border: 'none',
                                    boxShadow: 'none'
                                } : {}}
                                disabled={!isLoading && !inputValue.trim() && selectedCompanies.length === 0}
                                onClick={() => {
                                    if (isLoading) {
                                        if (onStop) onStop();
                                    } else {
                                        onSend(inputValue, selectedCompanies);
                                    }
                                }}
                                title={isLoading ? "Parar resposta da IA" : "Enviar mensagem"}
                                type="button"
                            >
                                {isLoading ? (
                                    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18 }}>
                                        {/* Um ícone de Stop Quadrado clássico preenchido (tamanho aumentado para 18) */}
                                        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                                            <rect x="4" y="4" width="16" height="16" rx="2.5" />
                                        </svg>
                                    </span>
                                ) : (
                                    <ArrowUp size={18} />
                                )}
                            </button>
                        </div>
                        {voiceError && (
                            voiceError === 'blocked' ? (
                                <div className={styles.voiceErrorHint}>
                                    <span>
                                        Microfone bloqueado.{' '}
                                        <strong>Clique no cadeado</strong> na barra de endereço
                                        → Microfone → <strong>Permitir</strong> → recarregue.
                                    </span>
                                    <button
                                        className={styles.voiceRetryBtn}
                                        onClick={startListening}
                                    >
                                        Tentar novamente
                                    </button>
                                </div>
                            ) : (
                                <div className={styles.voiceErrorHint}>{voiceError}</div>
                            )
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
