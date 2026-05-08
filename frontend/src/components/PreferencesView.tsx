import React, { useEffect, useState, useRef } from 'react';

import { 

    ChevronLeft,

    ChevronDown, 

    Save, 

    RefreshCw, 

    Cpu, 

    Settings2, 

    Database, 

    Activity, 

    AlertTriangle, 

    CheckCircle2, 

    Zap,

    Sparkles

} from 'lucide-react';

import { ai } from '@/services/api';

import styles from './PreferencesView.module.css';

interface PreferencesViewProps {

    onBack: () => void;

}

interface QuotaModelDetail {

    limit: number;

    remaining: number;

    used: number;

    pct: number; // percentage of remaining

    tokens_limit?: number;

    tokens_remaining?: number;

    tokens_pct?: number;

    status: string;

    updated_at: number;

}

type QuotasResponse = Record<string, Record<string, QuotaModelDetail>>;

const HUMAN_PROVIDERS: Record<string, { label: string; logo: string; image?: string; color: string }> = {

    gemini: { label: "Google Gemini", logo: "♊", image: "/gemini.png", color: "#8E75C8" },

    groq: { label: "Groq Speed API", logo: "⚡", image: "/groq llama.svg", color: "#F59E0B" },

    claude: { label: "Anthropic Claude", logo: "🍁", image: "/claude.png", color: "#D97706" },

    sambanova: { label: "SambaNova Systems", logo: "🌐", image: "/sambanova.png", color: "#2563EB" },

    deepseek: { label: "DeepSeek API", logo: "🐋", image: "/deepseek.png", color: "#0D9488" },

    cerebras: { label: "Cerebras Systems", logo: "🎛️", image: "/cerebras.png", color: "#EF4444" },

    ollama: { label: "Ollama (Local)", logo: "🐑", image: "/groq llama.svg", color: "#10B981" },

};

const HUMAN_MODELS = [
    { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash Lite (Rápido & Econômico)", description: "Otimizado para latência ultra-baixa em tarefas simples." },
    { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash (Padrão)", description: "Equilíbrio ideal entre velocidade e raciocínio contextual." },
    { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro (Alta Fidelidade)", description: "Raciocínio complexo e janela de contexto de 1M+ tokens." },
    { value: "gemini-flash-latest", label: "Gemini Flash Latest", description: "Última versão de produção do modelo de alta velocidade do Google Gemini." },
    { value: "gemini-2.0-flash-exp", label: "Gemini 2.0 Flash Exp (Experimental)", description: "Versão experimental de próxima geração para testes do Gemini Flash." },
    { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash (Multimodal)", description: "Modelo multimídia eficiente e altamente estável do Google." },
    { value: "llama-3.3-70b-versatile", label: "Llama 3.3 70B Versatile (Meta / Groq)", description: "Poder analítico de 70B com a velocidade absurda do hardware LPU." },
    { value: "llama-3.1-8b-instant", label: "Llama 3.1 8B Instant (Rápido / Groq)", description: "Espinha dorsal para interações de alta frequência e baixa latência." },
    { value: "meta-llama/llama-4-scout-17b-16e-instruct", label: "Llama 4 Scout 17B (Groq / SambaNova)", description: "Nova geração Llama 4 otimizada para eficiência e precisão." },
    { value: "qwen/qwen3-32b", label: "Qwen 3 32B (Groq / Alibaba)", description: "Excelente performance em lógica, matemática e codificação." },
    { value: "llama-3.2-11b-vision-preview", label: "Llama 3.2 11B Vision (Groq)", description: "Análise visual, OCR e interpretação de imagens em tempo real." },
    { value: "groq/compound", label: "Groq Compound System", description: "Sistema autônomo com busca web e execução de código nativa." },
    { value: "mixtral-8x7b-32768", label: "Mixtral 8x7B MoE (Groq)", description: "Arquitetura Mixture-of-Experts para respostas versáteis." },
    { value: "claude-3-5-sonnet-latest", label: "Claude 3.5 Sonnet (Anthropic)", description: "O 'cérebro' para análise estratégica e escrita refinada." },
    { value: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku (Anthropic)", description: "Rápido e preciso para extração de dados estruturados." },
    { value: "Llama-4-Scout-17B-16E-Instruct", label: "Llama 4 Scout 17B (SambaNova)", description: "Performance Llama 4 em infraestrutura RDU de alta densidade." },
    { value: "Meta-Llama-3.3-70B-Instruct", label: "Llama 3.3 70B (SambaNova)", description: "Modelo 70B completo rodando em hardware SambaNova." },
    { value: "deepseek-chat", label: "DeepSeek Chat V3", description: "Modelo versátil com excelente custo-benefício e lógica." },
    { value: "llama3.1-8b", label: "Llama 3.1 8B (Cerebras)", description: "Velocidade supersônica via hardware CS-3." },
    { value: "llama-3.3-70b", label: "Llama 3.3 70B (Cerebras)", description: "70B com latência mínima recorde na indústria." },
    { value: "qwen-3-235b-a22b-instruct-2507", label: "Qwen 3 235B Instruct (Alibaba / Cerebras)", description: "Modelo gigante executado em velocidade inacreditável via hardware Cerebras CS-3." },
    { value: "qwen-3-235b-instruct", label: "Qwen 3 235B Instruct (Cerebras)", description: "Modelo de 235 bilhões de parâmetros com extrema profundidade cognitiva." },
    { value: "gpt-oss-120b", label: "GPT OSS 120B (Cerebras)", description: "Modelo open-source de grande porte para orquestração avançada." },
    { value: "zai-glm-4.7", label: "GLM 4.7 (Cerebras)", description: "Modelo de raciocínio lógico claro com suporte nativo a thinking." },
    { value: "qwen2.5:3b", label: "Qwen 2.5 3B (Ollama Local)", description: "Privacidade total rodando localmente na sua máquina (3B)." },
    { value: "qwen2.5:1.5b", label: "Qwen 2.5 1.5B (Ollama Local)", description: "Modelo leve rodando em hardware local para máxima eficiência e privacidade (1.5B)." },
];


export const PreferencesView: React.FC<PreferencesViewProps> = ({ onBack }) => {

    const [preferredModel, setPreferredModel] = useState('gemini-2.5-flash');

    const [strictMode, setStrictMode] = useState(false);

    const [quotas, setQuotas] = useState<QuotasResponse>({});

    const [loadingQuotas, setLoadingQuotas] = useState(true);

    const [saving, setSaving] = useState(false);

    const [isRefreshing, setIsRefreshing] = useState(false);

    const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

    const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({

        gemini: true, // Google Gemini vem aberto por padrão para mostrar interatividade

    });

    const toggleProvider = (provKey: string) => {

        setExpandedProviders(prev => ({

            ...prev,

            [provKey]: !prev[provKey]

        }));

    };

    const pollingInterval = useRef<NodeJS.Timeout | null>(null);

    const showToast = (type: 'success' | 'error', message: string) => {

        setToast({ type, message });

        setTimeout(() => setToast(null), 4000);

    };

    const loadPreferences = async () => {

        try {

            const res = await ai.getPreference();

            if (res) {

                setPreferredModel(res.preferred_model || 'gemini-2.5-flash');

                setStrictMode(res.strict_mode || false);

            }

        } catch (e: any) {

            console.error("Erro ao carregar preferências:", e);

        }

    };

    const fetchQuotas = async (silent = false) => {

        if (!silent) setLoadingQuotas(true);

        else setIsRefreshing(true);

        try {

            const res = await ai.getQuotas();

            if (res) {

                setQuotas(res);

            }

        } catch (e: any) {

            console.error("Erro ao buscar cotas:", e);

        } finally {

            setLoadingQuotas(false);

            setIsRefreshing(false);

        }

    };

    const handleSave = async () => {

        setSaving(true);

        try {

            const res = await ai.updatePreference(preferredModel, strictMode);

            if (res && res.status === 'ok') {

                showToast('success', `Modelo preferido atualizado para ${preferredModel}!`);

            } else {

                showToast('error', "Erro ao salvar preferências.");

            }

        } catch (e: any) {

            showToast('error', e.message || "Erro de rede ao salvar preferências.");

        } finally {

            setSaving(false);

        }

    };

    useEffect(() => {

        loadPreferences();

        fetchQuotas();

        // Configura polling a cada 5 segundos para tempo real realístico

        pollingInterval.current = setInterval(() => {

            fetchQuotas(true);

        }, 5000);

        return () => {

            if (pollingInterval.current) {

                clearInterval(pollingInterval.current);

            }

        };

    }, []);

    const getProgressColorClass = (pct: number) => {

        if (pct >= 50) return styles.progressGreen;

        if (pct >= 20) return styles.progressOrange;

        return styles.progressRed;

    };

    return (

        <div className={styles.container}>

            {/* Header */}

            <header className={styles.header}>

                <div className={styles.titleArea}>

                    <h1 className={styles.title}>

                        <Settings2 size={24} /> Configurações do Sistema

                    </h1>

                    <span className={styles.subtitle}>

                        Gerencie suas chaves, preferências de IA, limites de quotas e parametrizações globais.

                    </span>

                </div>

                <button className={styles.backBtn} onClick={onBack}>

                    <ChevronLeft size={16} /> Voltar

                </button>

            </header>

            {/* Dashboard Layout */}

            <div className={styles.settingsLayout}>
                {/* Sidebar Esquerda de Configurações */}
                <aside className={styles.settingsSidebar}>
                    <div className={styles.sidebarSectionTitle}>Configurações</div>
                    <nav className={styles.sidebarMenu}>
                        <div className={`${styles.sidebarItem} ${styles.sidebarItemActive}`}>
                            <Sparkles size={16} />
                            <span>Preferências & Limites LLM</span>
                        </div>
                    </nav>
                </aside>

                {/* Conteúdo Principal Direito */}
                <div className={styles.settingsContent}>
                    <div className={styles.dashboardContainer}>

                {/* Preferências Globais */}
                <div className={styles.card}>
                    <h2 className={styles.cardTitle}>
                        <span className={styles.cardTitleText}>
                            <Cpu size={18} /> Preferências Globais
                        </span>
                    </h2>

                    <div className={styles.formGroup}>
                        <label className={styles.label}>Modelo Preferido (Padrão do Sistema)</label>
                        <select 
                            className={styles.select}
                            value={preferredModel}
                            onChange={(e) => setPreferredModel(e.target.value)}
                        >
                            {HUMAN_MODELS.map(m => (
                                <option key={m.value} value={m.value}>{m.label}</option>
                            ))}
                        </select>
                    </div>

                    <div 
                        className={styles.checkboxContainer}
                        onClick={() => setStrictMode(!strictMode)}
                    >
                        <div className={styles.checkbox}>
                            {strictMode && <CheckCircle2 size={12} color="#3b82f6" />}
                        </div>
                        <div className={styles.checkboxText}>
                            <span className={styles.checkboxLabel}>Strict Mode (Forçar Modelo)</span>
                            <span className={styles.checkboxSub}>
                                Se ativado, o sistema sempre tentará usar o modelo acima com retries agressivos, 
                                desativando o fallback automático para outros provedores em caso de falha.
                            </span>
                        </div>
                    </div>

                    <button 
                        className={styles.saveBtn}
                        onClick={handleSave}
                        disabled={saving}
                    >
                        {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                        {saving ? "Salvando..." : "Salvar Preferências"}
                    </button>
                </div>

                <div style={{ height: '32px' }} />

                {/* Dashboard de Cotas em Tempo Real */}
                <div className={styles.card}>

                    <h2 className={styles.cardTitle}>

                        <span className={styles.cardTitleText}>

                            <Activity size={18} /> Limites de Cotas em Tempo Real (0-100%)

                        </span>

                        {isRefreshing && (

                            <div className={styles.refreshingIndicator}>

                                <RefreshCw size={14} className={styles.spin} />

                                <span style={{ fontSize: '11px' }}>atualizando...</span>

                            </div>

                        )}

                    </h2>

                    {loadingQuotas ? (

                        <div className={styles.noDataText} style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>

                            <RefreshCw size={24} className={styles.spin} />

                            <span>Carregando saldos reais dos provedores...</span>

                        </div>

                    ) : (

                        <div className={styles.providersList}>

                            {Object.entries(quotas).map(([provKey, modelsMap]) => {

                                const meta = HUMAN_PROVIDERS[provKey] || { label: provKey, logo: "🤖", color: "#3b82f6" };

                                // Determina se algum modelo desse provedor está rate limited

                                const isRateLimited = Object.values(modelsMap).some(m => m.status === 'rate_limited');

                                const isAnyNoCredits = Object.values(modelsMap).some(m => m.status === 'no_credits');

                                const isExpanded = expandedProviders[provKey] ?? false;

                                return (

                                    <div key={provKey} className={styles.providerCard}>

                                        {/* Header do Provedor */}

                                        <div 

                                            className={styles.providerHeader}

                                            onClick={() => toggleProvider(provKey)}

                                            style={{ cursor: 'pointer', userSelect: 'none' }}

                                        >

                                            <div className={styles.providerBrand}>

                                                {meta.image ? (

                                                    <img 

                                                        src={meta.image} 

                                                        alt={meta.label} 

                                                        className={styles.providerLogoImage} 

                                                    />

                                                ) : (

                                                    <span className={styles.providerLogoEmoji}>{meta.logo}</span>

                                                )}

                                                <span className={styles.providerName}>{meta.label}</span>

                                            </div>

                                            <div className={styles.providerHeaderRight}>

                                                <div className={`${styles.providerBadge} ${(isRateLimited || isAnyNoCredits) ? styles.badgeCritical : styles.badgeHealthy}`}>

                                                    {isRateLimited ? (

                                                        <>

                                                            <AlertTriangle size={12} />

                                                            <span>RATE LIMITED / COOLDOWN</span>

                                                        </>

                                                    ) : isAnyNoCredits ? (

                                                        <>

                                                            <AlertTriangle size={12} />

                                                            <span>SEM SALDO / SEM CRÉDITOS</span>

                                                        </>

                                                    ) : (

                                                        <>

                                                            <CheckCircle2 size={12} />

                                                            <span>ATIVO E SAUDÁVEL</span>

                                                        </>

                                                    )}

                                                </div>

                                                <ChevronDown 

                                                    size={16} 

                                                    className={`${styles.chevron} ${isExpanded ? styles.chevronExpanded : ''}`}

                                                />

                                            </div>

                                        </div>

                                        {/* Detalhes por Modelo */}

                                        {isExpanded && (

                                            <div className={styles.providerContent}>

                                            {Object.entries(modelsMap).length === 0 ? (

                                                <div className={styles.noDataText}>Nenhum modelo registrado ainda.</div>

                                            ) : (

                                                Object.entries(modelsMap).map(([modelName, detail]) => {

                                                    const isModelRateLimited = detail.status === 'rate_limited' || detail.status === 'cooldown';
                                                    const isNoCredits = detail.status === 'no_credits';
                                                    const pct = (isModelRateLimited || isNoCredits) ? 0 : detail.pct;

                                                    return (

                                                        <div key={modelName} className={styles.modelRow}>

                                                            <div className={styles.modelInfo}>

                                                                <span className={styles.modelName}>{modelName}</span>

                                                                <span className={styles.modelStats}>

                                                                    {isModelRateLimited ? (
                                                                        <span className={styles.modelStatsCritical}>INDISPONÍVEL (RATE LIMITED / COOLDOWN)</span>
                                                                    ) : isNoCredits ? (
                                                                        <span className={styles.modelStatsCritical}>INDISPONÍVEL (SEM CRÉDITOS / SALDO INSUFICIENTE)</span>
                                                                    ) : (
                                                                        <>
                                                                            Disponível: <span className={styles.modelStatsHighlight}>{pct}%</span> ({detail.remaining} / {detail.limit} reqs)
                                                                        </>
                                                                    )}

                                                                </span>

                                                            </div>

                                                            {/* Barra de Progresso Real-Time */}

                                                            <div className={styles.progressContainer}>

                                                                <div 

                                                                    className={`${styles.progressBar} ${(isModelRateLimited || isNoCredits) ? styles.progressRed : getProgressColorClass(pct)}`}

                                                                    style={{ width: `${pct}%` }}

                                                                />

                                                            </div>

                                                            {/* Tokens status if present (Groq/SambaNova) */}

                                                            {detail.tokens_limit ? (

                                                                <div className={styles.tokenStats}>

                                                                    <Database size={10} />

                                                                    <span>Tokens: {detail.tokens_pct}% ({Math.round((detail.tokens_remaining || 0) / 1000)}k / {Math.round(detail.tokens_limit / 1000)}k restantes)</span>

                                                                </div>

                                                            ) : null}

                                                        </div>

                                                    );

                                                })

                                            )}

                                        </div>

                                        )}

                                    </div>

                                );

                            })}

                        </div>

                    )}

                </div>

                <div style={{ height: '32px' }} />

                {/* Catálogo de Modelos */}
                <div className={styles.card}>
                    <h2 className={styles.cardTitle}>
                        <span className={styles.cardTitleText}>
                            <Sparkles size={18} /> Catálogo de Modelos & Capacidades
                        </span>
                    </h2>

                    <div className={styles.providersList}>
                        {HUMAN_MODELS.map(m => (
                            <div key={m.value} className={styles.providerCard} style={{ padding: '16px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                    <span className={styles.modelName}>{m.label}</span>
                                    <code style={{ fontSize: '10px', opacity: 0.5 }}>{m.value}</code>
                                </div>
                                <p style={{ fontSize: '12px', opacity: 0.7, lineHeight: '1.5', fontWeight: 300 }}>
                                    {m.description}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>

                <div style={{ height: '40px' }} />

                </div>
            </div>
        </div>
    </div>
    );
};