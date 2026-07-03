import React, { useState, useRef } from 'react';
import {
    Loader2, CheckCircle2, XCircle, Check, X,
    Paperclip, FileText, Wand2, ChevronDown, Building2, RotateCcw,
} from 'lucide-react';
import styles from '../../styles/ChatPanel.module.css';
import { refineMessage } from '../../../../services/api/ai';
import { parseMarkdownToHTML } from '../markdown';
import { AgentEvent } from '../types';
import { getAvatarUrl, getProxiedUrl } from '@/utils/avatarUtils';

/**
 * Procura, nos detalhes de org cacheados (`org-*-details`), a pessoa dona deste e-mail.
 * É a MESMA fonte que o Card Node usa — assim a foto resolvida por `getAvatarUrl` é
 * idêntica à exibida no grafo. Retorna o objeto da pessoa ou null.
 */
function findRecipientData(email: string): any | null {
    if (typeof window === 'undefined' || !email) return null;
    const target = email.trim().toLowerCase();
    try {
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (!key || !key.startsWith('org-') || !key.endsWith('-details')) continue;
            const raw = localStorage.getItem(key);
            if (!raw) continue;
            const persons = (JSON.parse(raw)?.persons) || [];
            for (const p of persons) {
                const emails: string[] = Array.isArray(p.email)
                    ? p.email.map((e: any) => (typeof e === 'string' ? e : e?.value) || '')
                    : (typeof p.email === 'string' ? [p.email] : []);
                if (emails.some(e => e.trim().toLowerCase() === target)) return p;
            }
        }
    } catch { /* cache ausente/corrompido — ignora e cai no fallback */ }
    return null;
}

/**
 * Avatar do destinatário com cascata de fontes encadeada (sem iniciais):
 *   1. Foto da pessoa no cache (getAvatarUrl — idêntica ao Card Node)
 *   2. Gravatar/LinkedIn por e-mail (unavatar)
 *   3. Logo da EMPRESA pelo domínio do e-mail (fallback solicitado)
 *   4. Ícone de prédio (último recurso)
 * A imagem é sempre recortada (`cover`) num círculo fixo — fica perfeitamente
 * enquadrada no card independente da proporção original.
 */
const RecipientAvatar: React.FC<{ email: string; person: any; size?: number }> = ({ email, person, size = 22 }) => {
    const domain = email.includes('@') ? email.split('@')[1].trim() : '';
    const candidates = React.useMemo(() => {
        const list: { url: string; fit: 'cover' | 'contain' }[] = [];
        const pPhoto = person ? getAvatarUrl(person) : null;
        if (pPhoto) list.push({ url: pPhoto, fit: 'cover' });                                              // foto da pessoa (Card Node)
        if (email) list.push({ url: `https://unavatar.io/${encodeURIComponent(email)}?fallback=false`, fit: 'cover' }); // gravatar/linkedin
        if (domain) list.push({ url: `https://unavatar.io/${encodeURIComponent(domain)}`, fit: 'contain' }); // logo da empresa (não cortar)
        return list.map(c => ({ url: getProxiedUrl(c.url) || c.url, fit: c.fit }));
    }, [email, person, domain]);
    const [idx, setIdx] = React.useState(0);
    const exhausted = idx >= candidates.length;
    return (
        <span style={{
            width: size,
            height: size,
            flexShrink: 0,
            borderRadius: 5,
            overflow: 'hidden',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            // Fundo branco para que logos com transparência fiquem visíveis no dark-mode.
            background: '#ffffff',
        }}>
            {exhausted ? (
                <Building2 size={Math.round(size * 0.55)} style={{ color: '#868686' }} />
            ) : (
                <img
                    src={candidates[idx].url}
                    alt={person?.name || email}
                    width={size}
                    height={size}
                    loading="lazy"
                    decoding="async"
                    style={{ width: '100%', height: '100%', objectFit: candidates[idx].fit, display: 'block' }}
                    onError={() => setIdx(i => i + 1)}
                />
            )}
        </span>
    );
};

/**
 * Chip de destinatário: avatar (foto da pessoa → logo da empresa) + endereço.
 */
const RecipientChip: React.FC<{ email: string }> = ({ email }) => {
    const person = React.useMemo(() => findRecipientData(email), [email]);
    return (
        <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 7,
            padding: '3px 11px 3px 4px',
            background: 'var(--sw-hover)',
            border: 'var(--sw-border-width) solid var(--sw-border)',
            borderRadius: 10,
            fontSize: 14,
            color: 'var(--sw-text-base)',
            maxWidth: '100%',
        }}>
            <RecipientAvatar email={email} person={person} size={22} />
            <span style={{ wordBreak: 'break-all' }}>{email}</span>
        </span>
    );
};

export const ConfirmationCard: React.FC<{
    event: AgentEvent;
    onConfirm: (action_id: string, approved: boolean, file?: File) => void;
    decided?: boolean;
    approvedResult?: boolean;
}> = ({ event, onConfirm, decided, approvedResult }) => {
    const [previewText, setPreviewText] = useState(event.preview ?? '');
    const [refineText, setRefineText] = useState('');
    const [isRefining, setIsRefining] = useState(false);
    const [attachedFile, setAttachedFile] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleRefine = async () => {
        if (!refineText.trim() || isRefining || !event.action_id) return;
        setIsRefining(true);
        try {
            const res = await refineMessage({ action_id: event.action_id, feedback: refineText });
            if (res.ok && res.refined_message) {
                setPreviewText(res.refined_message);
                setRefineText('');
            }
        } catch (e: any) {
            console.error('Refine message failed:', e);
            alert(`Erro ao refinar mensagem: ${e.message || 'Erro desconhecido'}`);
        } finally {
            setIsRefining(false);
        }
    };

    const tool = event.tool || '';
    const isEmail = tool === 'email_send' || tool === 'email_reply';
    const isPipedrive = tool.startsWith('pipedrive_') || tool === 'evaluate_prospects';
    const isCall = tool === 'open_ligacao_view';

    // Configurações visuais por canal
    const channelConfig = {
        bg: 'transparent',
        border: 'var(--sw-border)',
        headerBg: 'var(--sw-hover)',
        icon: isEmail ? '/outlook.png' : isPipedrive ? '/pipedrive.png' : isCall ? '/telefone.png' : '/wppicon.png',
        iconSize: isEmail ? 16 : isPipedrive ? 16 : 14,
        accentColor: isEmail ? '#0078d4' : isPipedrive ? '#f36e21' : isCall ? '#10b981' : '#22c55e',
        labelColor: 'var(--sw-text-muted)',
    };

    if (decided) {
        return (
            <div className={styles.logLine} style={{ marginBottom: 8 }}>
                {approvedResult
                    ? <CheckCircle2 size={12} style={{ color: channelConfig.accentColor, flexShrink: 0 }} />
                    : <XCircle size={12} style={{ color: 'var(--sw-text-muted)', opacity: 0.5, flexShrink: 0 }} />
                }
                <span>{approvedResult ? 'Ação aprovada' : 'Ação cancelada'}</span>
                <span style={{ opacity: 0.4 }}>· {event.label}</span>
            </div>
        );
    }

    const labelStr = event.label || '';
    const hasAttachment = labelStr.includes('+ anexo:') || labelStr.includes('attachment');
    const attachmentName = hasAttachment
        ? (labelStr.match(/\+\s*anexo:\s*([^)]+)\)/i)?.[1]?.trim() || 'Arquivo')
        : null;

    const options = event.options || [];
    const hasOptions = options.length > 0;
    const failed = !!event.send_failed;

    // Hierarquia do título: para e-mails, o destinatário já aparece na caixa
    // "Para/Cc" abaixo — então exibimos apenas o assunto (parte após o "—"),
    // evitando redundância e dando peso tipográfico correto ao subject.
    const baseTitle = hasOptions
        ? (event.label || 'O que deseja fazer?')
        : hasAttachment
            ? labelStr.replace(/\s*\(.*?anexo.*?\)/i, '')
            : labelStr;
    const displayTitle = (isEmail && !hasOptions)
        ? (baseTitle.match(/—\s*([\s\S]+)$/)?.[1]?.trim() || baseTitle)
        : baseTitle;

    // Rótulo de linha do cabeçalho "compose" (Para / Cc / Assunto / Anexos).
    const metaLabel: React.CSSProperties = {
        color: 'var(--sw-text-muted)',
        fontWeight: 600,
        letterSpacing: '0.03em',
        fontSize: 13,
    };

    // Separa a imagem de assinatura do corpo do e-mail: dentro do bloco itálico/recuado
    // ela fica torta, então a renderizamos num bloco próprio, perfeitamente emoldurado.
    const sigMatch = previewText.match(/<img[^>]*signature\/image[^>]*>/i);
    const signatureSrc = sigMatch?.[0].match(/src=["']([^"']+)["']/i)?.[1] || null;
    const previewBody = sigMatch
        ? previewText.replace(sigMatch[0], '').replace(/(?:\s*<br\s*\/?>\s*)+$/i, '').trimEnd()
        : previewText;

    return (
        <div style={{
            borderRadius: 10,
            border: `var(--sw-border-width) solid var(--sw-border)`,
            background: 'var(--chat-console-bg)',
            overflow: 'hidden',
            marginBottom: 12,
            transition: 'all 0.3s ease'
        }}>
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                borderBottom: 'var(--sw-border-width) solid var(--sw-border)',
                background: 'var(--chat-console-bg)'
            }}>
                {isCall
                    ? <img src="/telefone.png" alt="Ligação" style={{ width: 20, height: 20, objectFit: 'contain' }} />
                    : <img src={channelConfig.icon!} alt="Channel" style={{ width: channelConfig.iconSize, height: channelConfig.iconSize, borderRadius: 3 }} />
                }
                <span style={{ fontSize: 'var(--font-xs)', color: 'var(--sw-text-muted)', letterSpacing: '0.06em', fontWeight: 700, textTransform: 'uppercase' }}>
                    {hasOptions ? 'DECISÃO NECESSÁRIA' : isEmail ? 'CONFIRMAR E-MAIL' : isPipedrive ? 'CONFIRMAR PIPEDRIVE' : isCall ? 'INICIAR LIGAÇÃO' : 'CONFIRMAR WHATSAPP'}
                </span>
                {failed && (
                    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, fontSize: 'var(--font-xs)', color: '#ef4444' }}>
                        <XCircle size={10} />
                        <span style={{ fontWeight: 700 }}>Falhou</span>
                    </div>
                )}
            </div>
            <div style={{ padding: '12px' }}>
                {!(isEmail && !hasOptions) && (
                    <div style={{ fontSize: 'var(--font-sm)', color: 'var(--sw-text-base)', marginBottom: 10, fontWeight: 700, lineHeight: '1.4' }}>
                        {displayTitle}
                    </div>
                )}
                {isEmail && !hasOptions && (event.to || (event.cc && event.cc.length > 0)) && (
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'max-content 1fr',
                        columnGap: 12,
                        rowGap: 8,
                        alignItems: 'center',
                        marginBottom: 12,
                    }}>
                        {event.to && (
                            <>
                                <span style={metaLabel}>Para</span>
                                <span style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                                    <RecipientChip email={event.to} />
                                </span>
                            </>
                        )}
                        {event.cc && event.cc.length > 0 && (
                            <>
                                <span style={metaLabel}>Cc</span>
                                <span style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                                    {event.cc.map((addr, idx) => (
                                        <RecipientChip key={idx} email={addr} />
                                    ))}
                                </span>
                            </>
                        )}
                    </div>
                )}
                {isEmail && !hasOptions && displayTitle && (
                    <div style={{ marginBottom: 12 }}>
                        <div style={{ color: 'var(--sw-text-base)', fontWeight: 700, fontSize: 20, lineHeight: 1.3 }}>{displayTitle}</div>
                    </div>
                )}

                {hasAttachment && (
                    <div style={{ ...metaLabel, marginBottom: 6 }}>Anexos</div>
                )}
                {hasAttachment && (
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                        background: 'transparent',
                        border: 'var(--sw-border-width) solid var(--sw-border)',
                        borderRadius: 6,
                        marginBottom: 12,
                    }}>
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: 32,
                            height: 32,
                            borderRadius: 4,
                            background: 'rgba(239, 68, 68, 0.1)',
                            color: '#ef4444',
                        }}>
                            <FileText size={18} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--sw-text-base)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {attachmentName?.endsWith('.pdf') ? attachmentName : `${attachmentName}.pdf`}
                            </span>
                            <span style={{ fontSize: 11, color: 'var(--sw-text-muted)', marginTop: 2 }}>
                                7 MB
                            </span>
                        </div>
                        <ChevronDown size={16} style={{ color: 'var(--sw-text-muted)', cursor: 'pointer' }} />
                    </div>
                )}
                {previewBody && (
                    <div
                        style={{
                            fontSize: 'var(--font-sm)',
                            color: 'var(--sw-text-base)',
                            opacity: 0.85,
                            padding: '2px 0 2px 12px',
                            borderLeft: `var(--sw-border-width) solid ${channelConfig.accentColor}40`,
                            borderRadius: 6,
                            fontStyle: 'italic',
                            marginBottom: 12,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            lineHeight: '1.6'
                        }}
                        dangerouslySetInnerHTML={{ __html: parseMarkdownToHTML(previewBody) }}
                    />
                )}
                {signatureSrc && (
                    <div style={{
                        marginBottom: 12,
                        borderRadius: 4,
                        overflow: 'hidden',
                        border: 'var(--sw-border-width) solid var(--sw-border)',
                        background: '#ffffff',
                        padding: 8,
                        display: 'flex',
                    }}>
                        <img
                            src={signatureSrc}
                            alt="Assinatura"
                            style={{ width: '100%', height: 'auto', objectFit: 'contain', display: 'block', borderRadius: 2 }}
                        />
                    </div>
                )}

                {event.action_id && !isCall && !hasOptions && (
                    <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                        <input
                            value={refineText}
                            onChange={e => setRefineText(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter' && refineText.trim() && !isRefining) handleRefine(); }}
                            placeholder="O que você quer mudar na mensagem?"
                            disabled={isRefining}
                            style={{
                                flex: 1,
                                background: 'var(--sw-hover)',
                                border: 'var(--sw-border-width) solid var(--sw-border)',
                                borderRadius: 8,
                                padding: '7px 10px',
                                fontSize: 12,
                                color: 'var(--sw-text-base)',
                                outline: 'none',
                                minWidth: 0,
                                opacity: isRefining ? 0.4 : 1,
                            }}
                            />
                            {(isEmail || !isPipedrive) && (
                                <>
                                    <input
                                        type="file"
                                        accept="image/*,.pdf"
                                        ref={fileInputRef}
                                        style={{ display: 'none' }}
                                        onChange={e => {
                                            if (e.target.files && e.target.files.length > 0) {
                                                setAttachedFile(e.target.files[0]);
                                            }
                                        }}
                                    />
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        title="Anexar arquivo (PDF ou Imagem)"
                                        style={{
                                            flexShrink: 0,
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            padding: '7px 10px',
                                            background: attachedFile ? 'var(--sw-hover)' : 'transparent',
                                            border: 'var(--sw-border-width) solid var(--sw-border)',
                                            borderRadius: 8,
                                            color: attachedFile ? channelConfig.accentColor : 'var(--sw-text-subtle)',
                                            cursor: 'pointer',
                                            transition: 'all 0.18s ease',
                                        }}
                                        onMouseEnter={e => { if (!attachedFile) e.currentTarget.style.color = 'var(--sw-text-base)'; }}
                                        onMouseLeave={e => { if (!attachedFile) e.currentTarget.style.color = 'var(--sw-text-subtle)'; }}
                                    >
                                        <Paperclip size={14} />
                                    </button>
                                </>
                            )}
                        <button
                            onClick={handleRefine}
                            disabled={isRefining || !refineText.trim()}
                            style={{
                                flexShrink: 0,
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                                padding: '7px 12px',
                                background: 'var(--sw-hover)',
                                border: 'var(--sw-border-width) solid var(--sw-border)',
                                borderRadius: 8,
                                color: 'var(--sw-text-subtle)',
                                fontSize: 12,
                                cursor: isRefining || !refineText.trim() ? 'not-allowed' : 'pointer',
                                opacity: isRefining || !refineText.trim() ? 0.4 : 1,
                                whiteSpace: 'nowrap',
                                transition: 'all 0.18s ease',
                            }}
                            onMouseEnter={e => { if (!refineText.trim()) return; e.currentTarget.style.color = 'var(--sw-text-base)'; }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--sw-text-subtle)'; }}
                        >
                            {isRefining ? <Loader2 size={12} className={styles.spinner} /> : <Wand2 size={12} />}
                            <span>{isRefining ? 'Refinando...' : 'Refinar'}</span>
                        </button>
                    </div>
                )}

                {attachedFile && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, padding: '6px 10px', background: 'var(--sw-hover)', borderRadius: 6, border: 'var(--sw-border-width) solid var(--sw-border)' }}>
                        <Paperclip size={12} style={{ color: channelConfig.accentColor }} />
                        <span style={{ fontSize: 11, color: 'var(--sw-text-base)', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {attachedFile.name}
                        </span>
                        <button
                            onClick={() => { setAttachedFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                            style={{ background: 'transparent', border: 'none', color: 'var(--sw-text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                        >
                            <X size={12} />
                        </button>
                    </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                    {hasOptions ? (
                        options.map((opt: any, idx: number) => (
                            <button
                                key={idx}
                                onClick={() => onConfirm(event.action_id!, idx === 0)}
                                style={{
                                    flex: 1,
                                    padding: '8px 12px',
                                    borderRadius: 7,
                                    border: idx === 0 ? 'none' : 'var(--sw-border-width) solid var(--sw-border)',
                                    background: idx === 0 ? channelConfig.accentColor : 'transparent',
                                    color: idx === 0 ? '#fff' : 'var(--sw-text-base)',
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: 5,
                                    transition: 'all 0.15s ease'
                                }}
                                onMouseEnter={e => { if (idx !== 0) e.currentTarget.style.background = 'var(--sw-hover)'; }}
                                onMouseLeave={e => { if (idx !== 0) e.currentTarget.style.background = 'transparent'; }}
                            >
                                {idx === 0 ? <Check size={13} strokeWidth={2.5} /> : <X size={13} />}
                                {opt.label}
                            </button>
                        ))
                    ) : (
                        <>
                            <button
                                onClick={() => onConfirm(event.action_id!, true, attachedFile || undefined)}
                                style={{
                                    flex: 1,
                                    padding: '8px 12px',
                                    borderRadius: 7,
                                    border: 'none',
                                    background: isCall ? `${channelConfig.accentColor}18` : 'transparent',
                                    color: failed && !isCall ? '#ef4444' : channelConfig.accentColor,
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: 5,
                                    transition: 'all 0.15s ease'
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = failed && !isCall ? '#ef444414' : `${channelConfig.accentColor}22`; }}
                                onMouseLeave={e => { e.currentTarget.style.background = isCall ? `${channelConfig.accentColor}18` : 'transparent'; }}
                            >
                                {failed && !isCall ? <RotateCcw size={13} strokeWidth={2.5} /> : <Check size={13} strokeWidth={2.5} />}
                                {isCall ? 'Ligar agora' : failed ? 'Tentar novamente' : 'Confirmar'}
                            </button>
                            <button
                                onClick={() => onConfirm(event.action_id!, false)}
                                style={{
                                    flex: 1,
                                    padding: '8px 12px',
                                    borderRadius: 7,
                                    border: 'var(--sw-border-width) solid var(--sw-border)',
                                    background: 'transparent',
                                    color: 'var(--sw-text-subtle)',
                                    fontSize: 12,
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: 5,
                                    transition: 'all 0.15s ease'
                                }}
                                onMouseEnter={e => { e.currentTarget.style.color = 'var(--sw-text-base)'; e.currentTarget.style.background = 'var(--sw-hover)'; }}
                                onMouseLeave={e => { e.currentTarget.style.color = 'var(--sw-text-subtle)'; e.currentTarget.style.background = 'transparent'; }}
                            >
                                <X size={13} /> Cancelar
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};
