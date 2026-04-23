import React from 'react';
import {
    User2, Building2, MessageSquare, ArrowUpRight, ArrowDownLeft, ArrowRight
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// ContactLogCard
// Pill de contato usada no painel de pensamento.
// Alinha visualmente com as pills de empresa do input de chat.
// ─────────────────────────────────────────────────────────────────────────────
export const ContactLogCard = ({ data, label }: { data: any; label?: string }) => {
    const isUnmapped = data.is_unmapped || data.source?.includes("Não vinculado");

    return (
        <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '8px',
            margin: '6px 0 6px 16px', padding: '8px 12px',
            borderRadius: '12px',
            border: `1px solid ${isUnmapped ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.1)'}`,
            background: isUnmapped ? 'rgba(0,0,0,0.35)' : 'rgba(255,255,255,0.05)',
            backdropFilter: 'blur(8px)',
            filter: isUnmapped ? 'grayscale(80%)' : 'none',
            opacity: isUnmapped ? 0.65 : 1,
            transition: 'all 0.2s ease',
            maxWidth: '340px',
        }}>
            {/* Avatar / ícone */}
            <div style={{
                padding: '6px', borderRadius: '8px',
                background: isUnmapped ? 'rgba(100,100,100,0.15)' : 'rgba(139,92,246,0.15)',
                flexShrink: 0,
            }}>
                <User2 size={13} style={{ color: isUnmapped ? '#6b7280' : '#a78bfa' }} />
            </div>

            {/* Nome + fonte + email */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', minWidth: 0 }}>
                <span style={{
                    fontSize: '12px', fontWeight: 600,
                    color: isUnmapped ? '#6b7280' : 'rgba(255,255,255,0.9)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>{data.name}</span>
                {data.email && (
                    <span style={{ fontSize: '10px', color: 'rgba(96,165,250,0.7)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {data.email}
                    </span>
                )}
                {data.source && !data.email && (
                    <span style={{ fontSize: '9px', color: '#6b7280', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        {data.source}
                    </span>
                )}
            </div>

            {/* Canais disponíveis */}
            {data.channels && data.channels.length > 0 && (
                <div style={{ display: 'flex', gap: '4px', marginLeft: '4px', borderLeft: '1px solid rgba(255,255,255,0.08)', paddingLeft: '8px', flexShrink: 0 }}>
                    {data.channels.includes('WhatsApp') && (
                        <img src="/wppicon.png" width="13" height="13" alt="WhatsApp"
                            style={{ filter: isUnmapped ? 'grayscale(1) opacity(0.5)' : 'none', transition: 'filter 0.2s' }} />
                    )}
                    {data.channels.includes('Email') && (
                        <img src="/outlook.png" width="13" height="13" alt="Email"
                            style={{ filter: isUnmapped ? 'grayscale(1) opacity(0.5)' : 'none', transition: 'filter 0.2s' }} />
                    )}
                </div>
            )}

            {/* Badge de prioridade */}
            {label && (
                <span style={{
                    fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em',
                    padding: '2px 6px', borderRadius: '999px',
                    background: 'rgba(16,185,129,0.15)', color: '#34d399',
                    border: '1px solid rgba(16,185,129,0.25)', flexShrink: 0,
                }}>{label}</span>
            )}
        </div>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// DealLogCard
// Card de negócio com indicador de estágio e valor.
// ─────────────────────────────────────────────────────────────────────────────
export const DealLogCard = ({ data }: { data: any }) => {
    const hasValue = data.value && data.value > 0;
    const isOpen = data.status === 'open';
    const stageName = data.stage_name || 'Sem etapa';

    return (
        <div style={{
            display: 'flex', alignItems: 'center', gap: '12px',
            margin: '8px 0 8px 16px', padding: '10px 14px',
            background: 'rgba(255,255,255,0.04)', borderRadius: '14px',
            border: '1px solid rgba(255,255,255,0.08)',
            backdropFilter: 'blur(8px)',
            width: 'fit-content', maxWidth: '340px',
            transition: 'background 0.2s',
        }}>
            {/* Ícone */}
            <div style={{ padding: '8px', borderRadius: '10px', background: 'rgba(255,255,255,0.08)', flexShrink: 0 }}>
                <Building2 size={15} style={{ color: 'rgba(255,255,255,0.6)' }} />
            </div>

            {/* Info */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: 0 }}>
                {/* Título + etapa */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{
                        fontSize: '12px', fontWeight: 700, color: 'rgba(255,255,255,0.9)',
                        textTransform: 'uppercase', letterSpacing: '0.03em',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>{data.title || data.org_name}</span>
                    <span style={{
                        fontSize: '10px', fontWeight: 700, padding: '2px 7px', borderRadius: '6px',
                        background: 'rgba(94,106,210,0.2)', color: '#818cf8',
                        border: '1px solid rgba(94,106,210,0.3)',
                        flexShrink: 0,
                    }}>{stageName}</span>
                </div>

                {/* Valor + status */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '11px', color: '#9ca3af', fontWeight: 500 }}>
                        {hasValue ? data.formatted_value : 'Sem valor definido'}
                    </span>
                    <span style={{ width: '3px', height: '3px', borderRadius: '50%', background: '#4b5563', flexShrink: 0 }} />
                    <span style={{
                        fontSize: '10px', fontWeight: 600,
                        color: isOpen ? '#34d399' : '#9ca3af',
                    }}>{isOpen ? 'Em aberto' : data.status}</span>
                </div>
            </div>
        </div>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// NoteLogCard
// Card de nota interna com destaque âmbar.
// ─────────────────────────────────────────────────────────────────────────────
export const NoteLogCard = ({ data }: { data: any }) => (
    <div style={{
        display: 'flex', flexDirection: 'column', gap: '6px',
        margin: '6px 0 6px 16px', padding: '10px 14px',
        background: 'rgba(245,158,11,0.05)', borderRadius: '12px',
        border: '1px solid rgba(245,158,11,0.12)',
        borderLeft: '3px solid rgba(245,158,11,0.4)',
        maxWidth: '320px',
    }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <MessageSquare size={11} style={{ color: 'rgba(251,191,36,0.7)' }} />
            <span style={{ fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'rgba(251,191,36,0.7)' }}>
                Nota Interna
            </span>
        </div>
        <div style={{
            fontSize: '11px', color: '#d1d5db', lineHeight: '1.5',
            display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical',
            overflow: 'hidden', fontStyle: 'italic',
        }}>
            {data.content}
        </div>
    </div>
);

// ─────────────────────────────────────────────────────────────────────────────
// Legado — ActivityLogCard mantido para retrocompatibilidade
// (RichLogRenderer agora usa TimelineEventRow diretamente)
// ─────────────────────────────────────────────────────────────────────────────
export const ActivityLogCard = ({ data }: { data: any }) => {
    // redirect para quem ainda importar diretamente
    return null;
};
