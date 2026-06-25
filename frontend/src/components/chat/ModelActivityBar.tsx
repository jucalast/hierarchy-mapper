import React from 'react';
import { AIModel } from './ModelSelector';

export interface ModelActivityEvent {
    id: number;
    type: 'model_active' | 'rate_wait' | 'context_overflow' | 'model_switch';
    provider?: AIModel;
    model?: string;
    wait_sec?: number;
    reason?: string;
    estimated_tokens?: number;
    limit?: number;
    timestamp: number;
}

const MODEL_LOGOS: Partial<Record<AIModel, string>> = {
    claude: '/claude.png',
    gemini: '/gemini.png',
    groq: '/groq llama.svg',
    cerebras: '/cerebras.png',
    deepseek: '/deepseek.png',
    sambanova: '/sambanova.png',
};

const MODEL_INVERT: Partial<Record<AIModel, boolean>> = { groq: true };

const MODEL_COLORS: Partial<Record<AIModel, string>> = {
    claude: '#a855f7',
    gemini: '#3b82f6',
    groq: '#ca8a04',
    cerebras: '#ea580c',
    deepseek: '#6366f1',
    sambanova: '#ef4444',
};

export type NoticeStyle = {
    bg: string;
    border: string;
    color: string;
    text: string;
    logo?: string;
    invert?: boolean;
    isLive?: boolean;
};

function formatWait(sec: number): string {
    return sec >= 60 ? `${Math.round(sec / 60)}min` : `${Math.round(sec)}s`;
}

export function getNoticeStyle(events: ModelActivityEvent[], remainingSeconds?: number, theme?: string): NoticeStyle | null {
    if (events.length === 0) return null;
    const ev = events[events.length - 1];
    const modelLabel = ev.model ?? ev.provider ?? '—';
    const providerColor = ev.provider ? (MODEL_COLORS[ev.provider] ?? '#64748b') : '#64748b';

    const GRAY_BG = 'var(--chat-console-bg)';
    const GRAY_BORDER = 'var(--sw-border)';
    const DEFAULT_COLOR = 'var(--sw-text-subtle)';

    if (ev.type === 'rate_wait') {
        const sec = remainingSeconds !== undefined ? remainingSeconds : (ev.wait_sec || 0);
        return {
            bg: GRAY_BG,
            border: GRAY_BORDER,
            color: '#ca8a04',
            text: `Aguardando cota req/min (${sec}s) · ${modelLabel}`,
            logo: undefined,
            invert: false,
        };
    }

    if (ev.type === 'context_overflow') {
        const estTokens = ev.estimated_tokens ? ev.estimated_tokens.toLocaleString('pt-BR') : '0';
        const limitTokens = ev.limit ? ev.limit.toLocaleString('pt-BR') : '0';
        return {
            bg: GRAY_BG,
            border: GRAY_BORDER,
            color: '#ef4444',
            text: `${modelLabel} não suporta ${estTokens} tokens (limite ${limitTokens}) · usando modelo maior`,
            logo: undefined,
            invert: false,
        };
    }

    if (ev.type === 'model_switch') return {
        bg: GRAY_BG,
        border: GRAY_BORDER,
        color: providerColor,
        text: `Fallback para ${ev.provider}`,
        logo: undefined,
        invert: false,
    };

    // model_active
    return {
        bg: GRAY_BG,
        border: GRAY_BORDER,
        color: DEFAULT_COLOR,
        text: `Usando ${ev.provider}${ev.model && ev.model !== ev.provider ? ` · ${modelLabel}` : ''}`,
        logo: undefined,
        invert: false,
        isLive: true,
    };
}

interface ModelActivityBarProps {
    events: ModelActivityEvent[];
    theme?: string;
}

export const ModelActivityBar: React.FC<ModelActivityBarProps> = ({ events, theme }) => {
    const ev = events[events.length - 1];
    const [remaining, setRemaining] = React.useState(ev?.wait_sec || 0);

    React.useEffect(() => {
        if (ev && ev.type === 'rate_wait') {
            setRemaining(ev.wait_sec || 0);
        }
    }, [ev?.id, ev?.wait_sec]);

    React.useEffect(() => {
        if (ev && ev.type === 'rate_wait' && remaining > 0) {
            const t = setInterval(() => {
                setRemaining(r => Math.max(0, r - 1));
            }, 1000);
            return () => clearInterval(t);
        }
    }, [ev?.id, ev?.type, remaining > 0]);

    if (!ev) return null;

    const notice = getNoticeStyle(events, remaining, theme);
    if (!notice) return null;

    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 16px',
            fontSize: 'var(--font-sm)',
            fontWeight: 500,
            color: notice.color,
            letterSpacing: '0.01em',
            background: notice.bg,
            borderTopLeftRadius: 'var(--radius-lg)',
            borderTopRightRadius: 'var(--radius-lg)',
        }}>
            <span>{notice.text}</span>
            {notice.isLive && (
                <span style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: '#22c55e', flexShrink: 0,
                    animation: 'modelLivePulse 1.4s ease-in-out infinite',
                }} />
            )}
        </div>
    );
};
