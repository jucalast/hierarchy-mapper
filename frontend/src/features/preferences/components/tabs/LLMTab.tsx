import React from 'react';
import { Cpu, Save, RefreshCw, Activity, CheckCircle2, AlertTriangle, Database, ChevronDown } from 'lucide-react';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import { HUMAN_MODELS, HUMAN_PROVIDERS } from '../../constants';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'preferredModel' | 'setPreferredModel'
    | 'strictMode' | 'setStrictMode'
    | 'quotas' | 'loadingQuotas' | 'isRefreshing'
    | 'expandedProviders' | 'toggleProvider'
    | 'saving' | 'handleSaveLLM'
>;

const getProgressColorClass = (pct: number, s: Record<string, string>) => {
    if (pct >= 50) return s.progressGreen;
    if (pct >= 20) return s.progressOrange;
    return s.progressRed;
};

export const LLMTab: React.FC<Props> = ({
    preferredModel, setPreferredModel,
    strictMode, setStrictMode,
    quotas, loadingQuotas, isRefreshing,
    expandedProviders, toggleProvider,
    saving, handleSaveLLM,
}) => (
    <div className={styles.dashboardContainer}>
        <div className={styles.card}>
            <h2 className={styles.cardTitle}>
                <span className={styles.cardTitleText}>
                    <Cpu size={18} /> Modelos & Preferências de IA
                </span>
            </h2>

            <div className={styles.formGroup}>
                <label className={styles.label}>Modelo Preferido (Padrão do Sistema)</label>
                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                    O cérebro de IA preferido para orquestrar as cadeias de agentes, ler biografias do LinkedIn, classificar cargos, estruturar hierarquias e redigir propostas de vendas.
                </span>
                <select className={styles.select} value={preferredModel} onChange={(e) => setPreferredModel(e.target.value)}>
                    {HUMAN_MODELS.map(m => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                </select>
            </div>

            <div className={styles.checkboxContainer} onClick={() => setStrictMode(!strictMode)}>
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

            <button className={styles.saveBtn} onClick={handleSaveLLM} disabled={saving}>
                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                {saving ? "Salvando..." : "Salvar Preferências"}
            </button>
        </div>

        <div style={{ height: '32px' }} />

        <div className={styles.card}>
            <h2 className={styles.cardTitle}>
                <span className={styles.cardTitleText}>
                    <Activity size={18} /> Limites de Cotas em Tempo Real
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
                    <span>Sincronizando quotas com os provedores de IA...</span>
                </div>
            ) : (
                <div className={styles.providersList}>
                    {Object.entries(quotas).map(([provKey, modelsMap]) => {
                        const meta = HUMAN_PROVIDERS[provKey] || { label: provKey, logo: "🤖", color: "#3b82f6" };
                        const isRateLimited = Object.values(modelsMap).some(m => m.status === 'rate_limited');
                        const isAnyNoCredits = Object.values(modelsMap).some(m => m.status === 'no_credits');
                        const isExpanded = expandedProviders[provKey] ?? false;

                        return (
                            <div key={provKey} className={styles.providerCard}>
                                <div
                                    className={styles.providerHeader}
                                    onClick={() => toggleProvider(provKey)}
                                    style={{ cursor: 'pointer', userSelect: 'none' }}
                                >
                                    <div className={styles.providerBrand}>
                                        {meta.image ? (
                                            <img src={meta.image} alt={meta.label} className={styles.providerLogoImage} />
                                        ) : (
                                            <span className={styles.providerLogoEmoji}>{meta.logo}</span>
                                        )}
                                        <span className={styles.providerName}>{meta.label}</span>
                                    </div>
                                    <div className={styles.providerHeaderRight}>
                                        <div className={`${styles.providerBadge} ${(isRateLimited || isAnyNoCredits) ? styles.badgeCritical : styles.badgeHealthy}`}>
                                            {isRateLimited ? (
                                                <><AlertTriangle size={12} /><span>RATE LIMITED / COOLDOWN</span></>
                                            ) : isAnyNoCredits ? (
                                                <><AlertTriangle size={12} /><span>SEM CRÉDITOS</span></>
                                            ) : (
                                                <><CheckCircle2 size={12} /><span>ATIVO E DISPONÍVEL</span></>
                                            )}
                                        </div>
                                        <ChevronDown size={16} className={`${styles.chevron} ${isExpanded ? styles.chevronExpanded : ''}`} />
                                    </div>
                                </div>

                                {isExpanded && (
                                    <div className={styles.providerContent}>
                                        {Object.entries(modelsMap).length === 0 ? (
                                            <div className={styles.noDataText}>Nenhum modelo registrado.</div>
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
                                                                    <span className={styles.modelStatsCritical}>COOLDOWN (RATE LIMITED)</span>
                                                                ) : isNoCredits ? (
                                                                    <span className={styles.modelStatsCritical}>INDISPONÍVEL (SEM SALDO)</span>
                                                                ) : (
                                                                    <>Disponível: <span className={styles.modelStatsHighlight}>{pct}%</span> ({detail.remaining} / {detail.limit} reqs)</>
                                                                )}
                                                            </span>
                                                        </div>
                                                        <div className={styles.progressContainer}>
                                                            <div
                                                                className={`${styles.progressBar} ${(isModelRateLimited || isNoCredits) ? styles.progressRed : getProgressColorClass(pct, styles as Record<string, string>)}`}
                                                                style={{ width: `${pct}%` }}
                                                            />
                                                        </div>
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
    </div>
);
