import React, { useState, useRef, useEffect } from 'react';
import { Check, ChevronUp, Lock } from 'lucide-react';
import './ModelSelector.styles.css';

export type AIModel = 'gemini' | 'groq' | 'claude';

interface ModelOption {
    id: AIModel;
    name: string;
    description: string;
    badge: string;
    badgeColor: string;
    accentColor: string;
    logoSrc: string;
    speed: number;
}

const MODEL_OPTIONS: ModelOption[] = [
    {
        id: 'claude',
        name: 'Claude',
        description: 'Mais preciso — análise estratégica e escrita',
        badge: 'Principal',
        badgeColor: 'rgba(168,85,247,0.18)',
        accentColor: '#a855f7',
        logoSrc: '/claude.png',
        speed: 2,
    },
    {
        id: 'gemini',
        name: 'Gemini',
        description: 'Raciocínio complexo e contexto longo',
        badge: 'Rápido',
        badgeColor: 'rgba(59,130,246,0.18)',
        accentColor: '#3b82f6',
        logoSrc: '/gemini.png',
        speed: 3,
    },
    {
        id: 'groq',
        name: 'Groq',
        description: 'Ultra-rápido — respostas em menos de 1s',
        badge: 'Mais Rápido',
        badgeColor: 'rgba(234,179,8,0.18)',
        accentColor: '#eab308',
        logoSrc: '/groq llama.svg',
        speed: 3,
    },
];

interface ModelSelectorProps {
    model: AIModel;
    setModel: (model: AIModel) => void;
    strictMode?: boolean;
    setStrictMode?: (strict: boolean) => void;
    theme?: string;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({ 
    model, 
    setModel, 
    strictMode = false, 
    setStrictMode,
    theme = 'light',
}) => {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    const current = MODEL_OPTIONS.find(m => m.id === model) || MODEL_OPTIONS[0];

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        if (open) document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    const SpeedDots = ({ speed, accentColor }: { speed: number; accentColor: string }) => (
        <div style={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            {[1, 2, 3].map(i => (
                <div
                    key={i}
                    style={{
                        width: 5,
                        height: 5,
                        borderRadius: '50%',
                        background: i <= speed ? accentColor : 'var(--chat-border-color)',
                        transition: `background var(--chat-transition-fast)`,
                    }}
                />
            ))}
        </div>
    );

    const getModelLogoStyle = (modelId: AIModel, isSelected: boolean = false, isTrigger: boolean = false) => {
        if (modelId !== 'groq') return { filter: 'none' };
        
        // No trigger button (modelo atual selecionado)
        if (isTrigger) {
            return { filter: theme === 'dark' ? 'brightness(0) invert(1)' : 'brightness(0)' };
        }
        
        // No dropdown
        if (isSelected) {
            return { filter: theme === 'dark' ? 'brightness(0)' : 'brightness(0)' };
        }
        
        return { filter: 'brightness(0) invert(1)' };
    };

    return (
        <div ref={ref} className="modelSelectorWrapper">
            {/* Trigger button */}
            <button
                onClick={() => setOpen(v => !v)}
                data-open={open}
                className="modelSelectorTrigger"
            >
                <img
                    src={current.logoSrc}
                    alt={current.name}
                    className="modelIcon"
                    style={getModelLogoStyle(model, true, true)}
                />
                <span>{current.name}</span>
                {strictMode && <Lock size={10} className="strictLock" />}
                <ChevronUp
                    size={14}
                    className={`chevron ${open ? 'open' : ''}`}
                />
            </button>

            {/* Dropdown popup */}
            {open && (
                <div className="modelSelectorDropdown">
                    {/* Options */}
                    <div className="modelSelectorOptions">
                        {MODEL_OPTIONS.map(opt => {
                            const isSelected = opt.id === model;
                            return (
                                <button
                                    key={opt.id}
                                    onClick={() => { setModel(opt.id); setOpen(false); }}
                                    className={`modelOption ${isSelected ? 'selected' : ''}`}
                                >
                                    {/* Icon */}
                                    <div className="modelOptionIconWrapper">
                                        <img
                                            src={opt.logoSrc}
                                            alt={opt.name}
                                            className="modelOptionLogo"
                                            style={getModelLogoStyle(opt.id, isSelected)}
                                        />
                                    </div>

                                    {/* Text */}
                                    <div className="modelOptionInfo">
                                        <div className="modelOptionNameRow">
                                            <span className="modelOptionName">
                                                {opt.name}
                                            </span>
                                            <span
                                                className="modelOptionBadge"
                                            >
                                                {opt.badge}
                                            </span>
                                        </div>
                                        <div className="modelOptionDesc">
                                            {opt.description}
                                        </div>
                                        <div className="modelOptionSpeedRow">
                                            <span className="modelOptionSpeedLabel">
                                                Velocidade
                                            </span>
                                            <SpeedDots speed={opt.speed} accentColor="#5a5bd6" />
                                        </div>
                                    </div>

                                    {/* Check mark */}
                                    <div className="modelOptionCheck">
                                        {isSelected && (
                                            <Check size={14} style={{ color: 'var(--chat-accent-color)' }} />
                                        )}
                                    </div>
                                </button>
                            );
                        })}
                    </div>

                    {/* Strict Mode Toggle */}
                    <div className="modelSelectorStrictMode">
                        <button
                            onClick={() => setStrictMode?.(!strictMode)}
                            className={`modelSelectorStrictModeButton ${strictMode ? 'active' : ''}`}
                        >
                            <Lock size={14} className="modelSelectorStrictModeIcon" />
                            <div className="modelSelectorStrictModeInfo">
                                <div className="modelSelectorStrictModeTitle">
                                    Strict Mode
                                </div>
                                <div className="modelSelectorStrictModeDesc">
                                    {strictMode 
                                        ? 'Força este modelo com retry agressivo' 
                                        : 'Permite fallback automático se falhar'}
                                </div>
                            </div>
                            <div className="modelSelectorStrictModeToggle">
                                <div className="modelSelectorStrictModeToggleKnob" />
                            </div>
                        </button>
                    </div>
                </div>
            )}

        </div>
    );
};
