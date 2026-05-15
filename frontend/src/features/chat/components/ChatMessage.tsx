import React from 'react';
import {
    CheckCircle2, Copy, RotateCcw, ThumbsDown, ThumbsUp, Building2, MessageSquare, Mail, Zap, ClipboardCheck, RefreshCw, MessageCircle, GitBranch
} from 'lucide-react';
import { Message, CompanyResult, SuggestedAction } from '../types';
import { AIModel } from './ui/ModelSelector';
import { TaskList, ContactGrid, CompanyCard } from './modules/ContextModules';
import { WhatsAppThread, EmailThread } from './modules/CommunicationModules';
import { getAvatarUrl, getProxiedUrl, getCompanyLogoUrl } from '@/utils/avatarUtils';
import styles from '../styles/components/ChatMessage.module.css';

// ── Mapa de ícones das ações sugeridas ──────────────────────────────────────
const ACTION_ICON_MAP: Record<string, React.ReactNode> = {
    task:     <ClipboardCheck size={13} />,
    sync:     <RefreshCw size={13} />,
    whatsapp: <MessageCircle size={13} />,
    email:    <Mail size={13} />,
    pipeline: <GitBranch size={13} />,
    default:  <Zap size={13} />,
};

const SuggestedActionChips = ({
    actions,
    onAction,
}: {
    actions: SuggestedAction[];
    onAction: (prompt: string) => void;
}) => {
    if (!actions || actions.length === 0) return null;
    return (
        <div className="flex flex-wrap gap-2 px-4 pb-3" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', padding: '4px 16px 12px 16px' }}>
            {actions.map((action, i) => (
                <div
                    key={i}
                    role="button"
                    tabIndex={0}
                    onClick={() => onAction(action.prompt)}
                    className={styles.actionChip}
                    style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        fontSize: '12px',
                        fontWeight: 500,
                        color: 'var(--chat-text-secondary)',
                        background: 'var(--chat-bg-secondary)',
                        border: '1px solid var(--chat-border-color)',
                        borderRadius: '20px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        lineHeight: 1.3,
                        outline: 'none',
                    }}
                    title={action.prompt}
                >
                    <span style={{ opacity: 0.7, flexShrink: 0 }}>
                        {ACTION_ICON_MAP[action.icon || 'default']}
                    </span>
                    {action.label}
                </div>
            ))}
        </div>
    );
};

interface ChatMessageProps {
    message: Message;
    theme?: string;
    onRegenerate?: (messageId?: string) => void;
    onSuggestedAction?: (prompt: string) => void;
    model?: AIModel;
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
}

const MODEL_LOGO_MAP: Record<AIModel, string> = {
    claude: '/claude.png',
    gemini: '/gemini.png',
    groq: '/groq llama.svg',
    cerebras: '/cerebras.png',
    deepseek: '/deepseek.png',
    sambanova: '/sambanova.png',
};

const AIAsterisk = ({ model }: { model: AIModel }) => (
    <img
        src={MODEL_LOGO_MAP[model] ?? '/claude.png'}
        alt={`${model} AI`}
        width="16"
        height="16"
        className="shrink-0 object-contain"
    />
);

export const ChatMessage: React.FC<ChatMessageProps> = ({
    message, theme = 'light', onRegenerate, onSuggestedAction, model = 'claude', onOpenWhatsApp
}) => {
    const isUser = message.role === 'user';

    const renderHighlightedText = (text: string, keyPrefix: string) => {
        const parts = text.split(/(@[a-zA-Z0-9\u00C0-\u017F\s\-&]+?)(?=\s*[.,;!?(){}\[\]<>]|\s+@|$)/g);
        return parts.map((part, i) => {
            if (part.startsWith('@')) {
                return <span key={`${keyPrefix}-high-${i}`} className={styles.highlightPurple}>{part}</span>;
            }
            return part;
        });
    };

    const renderInlineMarkdown = (text: string, messageData?: any) => {
        const parts = text.split(/(\[\[(?:TASK|NEW_TASK):\d+\]\])/g);
        return parts.flatMap((part, i) => {
            if (part.startsWith('[[TASK:')) {
                const match = part.match(/\[\[TASK:(\d+)\]\]/);
                const idx = match ? parseInt(match[1]) - 1 : -1;
                const task = messageData?.past_activities?.[idx];
                return task ? [<div key={`task-${i}`} style={{ margin: '12px 0' }}><TaskList data={{ activities: [task] }} /></div>] : [];
            }
            if (part.startsWith('[[NEW_TASK:')) {
                const match = part.match(/\[\[NEW_TASK:(\d+)\]\]/);
                const idx = match ? parseInt(match[1]) - 1 : -1;
                const task = messageData?.new_activities?.[idx];
                return task ? [
                    <div key={`newtask-${i}`} style={{ margin: '12px 0' }}>
                        <div style={{ fontSize: '10px', color: task.done ? '#10B981' : '#5E6AD2', marginBottom: '4px', textTransform: 'uppercase', fontWeight: 600 }}>
                            {task.done ? 'Atividade Concluída' : 'Nova Atividade agendada'}
                        </div>
                        <TaskList data={{ activities: [task] }} />
                    </div>
                ] : [];
            }
            const boldParts = part.split(/(\*\*.*?\*\*)/g);
            return boldParts.flatMap((bPart, bi) => {
                if (bPart.startsWith('**') && bPart.endsWith('**')) {
                    return [<strong key={`bold-${i}-${bi}`} style={{ fontWeight: 700 }}>{bPart.slice(2, -2)}</strong>];
                }
                return renderHighlightedText(bPart, `${i}-${bi}`);
            });
        });
    };

    const renderMarkdown = (text: string, messageData?: any) => {
        if (!text) return null;
        const lines = text.split('\n');
        return lines.map((line, idx) => {
            if (line.includes('[[PAST_TASKS]]')) {
                return (
                    <div key={idx} style={{ margin: '8px 0' }}>
                        <div style={{ fontSize: '14px', color: '#888', marginBottom: '12px', textTransform: 'uppercase', fontWeight: 800 }}>Cenário Analisado (Pipedrive)</div>
                        <TaskList data={{ activities: messageData?.past_activities }} />
                    </div>
                );
            }
            if (line.includes('[[NEW_TASKS]]')) {
                return (
                    <div key={idx} style={{ margin: '12px 0' }}>
                        <div style={{ fontSize: '14px', color: '#5E6AD2', marginBottom: '12px', textTransform: 'uppercase', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <CheckCircle2 size={16} /> Nova Atividade Gerada
                        </div>
                        <TaskList data={{ activities: messageData?.new_activities }} />
                    </div>
                );
            }
            if (line.trim() === '---') return <hr key={idx} style={{ margin: '12px 0', border: 'none', borderTop: '1px solid rgba(255,255,255,0.1)' }} />;
            if (line.startsWith('### ')) {
                return <h3 key={idx} style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '4px', marginBottom: '8px' }}>{renderInlineMarkdown(line.replace('### ', '').replace('🎯 ', ''), messageData)}</h3>;
            }
            return <div key={idx} style={{ marginBottom: '12px', lineHeight: '1.6' }}>{renderInlineMarkdown(line, messageData)}</div>;
        });
    };

    if (isUser) {
        return (
            <div className={styles.userMessageWrapper}>
                {message.data?.selectedCompanies && message.data.selectedCompanies.length > 0 && (
                    <div className={styles.userCompaniesContainer}>
                        {message.data.selectedCompanies.map((c: CompanyResult) => (
                            <div key={c.id} className={styles.inputCompanyPill}>
                                <div className={styles.pillIconArea}>
                                    {c.type === 'organization' ? (
                                        getCompanyLogoUrl(c) ? (
                                            <img
                                                src={getProxiedUrl(getCompanyLogoUrl(c))}
                                                alt={c.name}
                                                className={styles.pillCompanyLogo}
                                                onError={(e) => { e.currentTarget.style.display = 'none'; }}
                                            />
                                        ) : (
                                            <Building2 size={16} className="shrink-0 opacity-40" />
                                        )
                                    ) : (
                                        getAvatarUrl(c) ? (
                                            <img
                                                src={getProxiedUrl(getAvatarUrl(c))}
                                                alt={c.name}
                                                className={styles.pillCompanyLogo}
                                                style={{ borderRadius: '50%' }}
                                                onError={(e) => {
                                                    e.currentTarget.src = c.type === 'whatsapp' ? '/wppicon.png' : '/outlook.png';
                                                    e.currentTarget.style.objectFit = 'contain';
                                                }}
                                            />
                                        ) : (
                                            c.type === 'whatsapp' ?
                                                <img src="/wppicon.png" alt="W" style={{ width: 18, height: 18, objectFit: 'contain' }} /> :
                                                <img src="/outlook.png" alt="E" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                                        )
                                    )}
                                </div>
                                <div className={styles.pillInfo}>
                                    <div className={styles.pillName}>{c.name}</div>
                                    <div className={styles.pillSubtext}>
                                        {c.type === 'organization' ? 'Empresa' : (c.phone || c.email || (c.type === 'whatsapp' ? 'WhatsApp' : 'E-mail'))}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
                <div className={styles.userMessage}>{message.content}</div>
            </div>
        );
    }

    return (
        <div className={styles.assistantMessageGroup}>
            <div className={styles.aiMessageWrapper}>
                <div className={styles.aiMessageIconArea}>
                    <AIAsterisk model={model} />
                </div>
                <div className={styles.aiMessage}>
                    {renderMarkdown(message.content, message.data)}
                </div>
            </div>

            {/* Módulos de Interface */}
            {message.ui_module === 'TaskList' && <TaskList data={message.data} />}
            {message.ui_module === 'ContactGrid' && <ContactGrid data={message.data} />}
            {message.ui_module === 'CompanyCard' && <CompanyCard data={message.data} />}
            {message.ui_module === 'WhatsAppThread' && <WhatsAppThread data={message.data} onOpenWhatsApp={onOpenWhatsApp} />}
            {message.ui_module === 'EmailThread' && <EmailThread data={message.data} />}

            {/* Ações Sugeridas */}
            {message.ui_module === 'DealStatus' && onSuggestedAction && (
                <SuggestedActionChips
                    actions={message.suggested_actions || message.data?.suggested_actions || []}
                    onAction={onSuggestedAction}
                />
            )}

            {/* Ações da Mensagem */}
            <div className={styles.messageActions}>
                <div className={styles.actionGroup}>
                    <button className={styles.actionBtn} title="Copiar resposta" onClick={() => navigator.clipboard.writeText(message.content)}>
                        <Copy size={14} />
                    </button>
                    <button className={styles.actionBtn} title="Gerar outra resposta" onClick={() => onRegenerate?.(message.id)}>
                        <RotateCcw size={14} />
                    </button>
                </div>
                <div className={styles.actionGroupDivider} />
                <div className={styles.actionGroup}>
                    <button className={styles.actionBtn} title="Resposta útil">
                        <ThumbsUp size={14} />
                    </button>
                    <button className={styles.actionBtn} title="Não foi útil">
                        <ThumbsDown size={14} />
                    </button>
                </div>
            </div>
        </div>
    );
};
