import React from 'react';
import { Loader2, Search, Navigation, RotateCcw } from 'lucide-react';
import styles from './styles/Toolbar.module.css';
import type { ProspectSession, ProspectLead } from '@/hooks/useProspecting';
import { ProspectLeadCard } from './ProspectLeadCard';

export interface ProspectingToolbarProps {
    prospectCoords?: { lat: number; lng: number } | null;
    prospectRadiusKm?: number;
    onProspectRadiusChange?: (km: number) => void;
    onProspectGeolocate?: () => void;
    prospectGeoLoading?: boolean;
    onProspectSearch?: () => void;
    onProspectStop?: () => void;
    prospectSearching?: boolean;
    prospectSession?: ProspectSession | null;
    prospectLeadsCount?: number;
    prospectTierACount?: number;
    prospectError?: string | null;
    prospectCityName?: string | null;
    onProspectCepLookup?: (cep: string) => Promise<void>;
    prospectSelectedLead?: ProspectLead | null;
    prospectPendingLeads?: ProspectLead[];
    onProspectSelectLead?: (lead: ProspectLead) => void;
    onProspectApproveLead?: (id: string) => Promise<void>;
    onProspectRejectLead?: (id: string) => Promise<void>;
    onProspectCloseLead?: () => void;
    prospectCep?: string;
    onProspectCepChange?: (cep: string) => void;
    prospectHoveredLeadId?: string | null;
    isSidebarOpen?: boolean;
    isChatOpen?: boolean;
}

export const ProspectingToolbar: React.FC<ProspectingToolbarProps> = ({
    prospectCoords,
    prospectRadiusKm = 50,
    onProspectRadiusChange,
    onProspectGeolocate,
    prospectGeoLoading,
    onProspectSearch,
    onProspectStop,
    prospectSearching,
    prospectSession,
    prospectLeadsCount = 0,
    prospectTierACount = 0,
    prospectError,
    onProspectCepLookup,
    prospectCityName,
    prospectSelectedLead,
    prospectPendingLeads = [],
    onProspectSelectLead,
    prospectHoveredLeadId,
    onProspectApproveLead,
    onProspectRejectLead,
    onProspectCloseLead,
    prospectCep = '',
    onProspectCepChange,
    isSidebarOpen = false,
    isChatOpen = false,
}) => {
    const scrollContainerRef = React.useRef<HTMLDivElement>(null);

    React.useEffect(() => {
        const targetId = prospectHoveredLeadId || prospectSelectedLead?.id;
        if (!targetId || !scrollContainerRef.current) return;

        const element = scrollContainerRef.current.querySelector(`[data-lead-id="${targetId}"]`);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        }
    }, [prospectSelectedLead?.id, prospectHoveredLeadId]);

    const isRunning = prospectSession?.status === 'running';
    const isDone = prospectSession?.status === 'completed';
    const hasCoords = !!prospectCoords;
    const hasPending = prospectPendingLeads.length > 0;

    const cepValue = prospectCep;
    const setCepValue = onProspectCepChange || (() => {});

    return (
        <div
            className={`${styles.toolbarUnifiedWrapper} ${styles.prospecting}`}
            data-sidebar-open={isSidebarOpen}
            data-chat-open={isChatOpen}
        >
            {prospectPendingLeads.length > 0 && (
                <div className={styles.optionsContainer} ref={scrollContainerRef}>
                    {prospectPendingLeads.map(lead => (
                        <ProspectLeadCard
                            key={lead.id}
                            lead={lead}
                            isSelected={lead.id === prospectSelectedLead?.id}
                            isHovered={lead.id === prospectHoveredLeadId}
                            onSelect={onProspectSelectLead || (() => {})}
                            onApprove={onProspectApproveLead || (() => Promise.resolve())}
                            onReject={onProspectRejectLead || (() => Promise.resolve())}
                        />
                    ))}
                </div>
            )}

            <div className={`${styles.refineTab} ${prospectPendingLeads.length > 0 ? styles.refineTabConnected : ''}`} style={{
                position: 'relative', overflow: 'visible', zIndex: 30,
                ...(prospectPendingLeads.length > 0 ? { borderTopLeftRadius: 0, borderTopRightRadius: 0, borderTop: 'none', boxShadow: 'none' } : {}),
            }}>
                <div className={styles.searchBox}>
                    <div className={styles.inputGroup} style={{ display: 'flex', alignItems: 'center', width: '100%', gap: 0 }}>

                        {/* CEP Group */}
                        <div className={styles.toolbarSegment} style={{ maxWidth: 170, flexShrink: 0, opacity: hasPending ? 0.35 : 1 }}>
                            <input
                                placeholder="CEP"
                                maxLength={9}
                                value={cepValue}
                                disabled={hasPending}
                                onChange={e => !hasPending && setCepValue(e.target.value.replace(/\D/g, '').replace(/^(\d{5})(\d)/, '$1-$2'))}
                                onKeyDown={async e => {
                                    if (!hasPending && e.key === 'Enter' && onProspectCepLookup) await onProspectCepLookup(cepValue);
                                }}
                                className={styles.input}
                                style={{ width: 72, letterSpacing: '0.05em', fontWeight: 600, padding: 0, cursor: hasPending ? 'not-allowed' : 'text' }}
                            />
                            <button
                                type="button"
                                className={styles.inputActionBtn}
                                disabled={hasPending}
                                onClick={async () => {
                                    if (!hasPending && onProspectCepLookup) await onProspectCepLookup(cepValue);
                                }}
                                style={{ opacity: hasPending ? 1 : cepValue.length >= 8 ? 1 : 0.3, padding: 4, cursor: hasPending ? 'not-allowed' : 'pointer' }}
                            >
                                {prospectGeoLoading
                                    ? <Loader2 size={14} className={styles.loadingAnim} />
                                    : <Search size={14} className={styles.inputActionIcon} />}
                            </button>
                              {prospectCityName && (
                                <span className={styles.toolbarText} style={{ marginLeft: 4 }}>
                                    {prospectCityName}
                                </span>
                            )}
                        </div>

                        <div className={styles.toolbarDivider} />

                        {/* Slider Group */}
                        <div className={styles.toolbarSegment} style={{ flex: 1, gap: 8, padding: '0 8px', minWidth: 80 }}>
                            <input
                                type="range" min={10} max={200} step={10}
                                value={prospectRadiusKm}
                                onChange={e => onProspectRadiusChange?.(Number(e.target.value))}
                                className={styles.rangeSlider}
                                style={{ flex: 1, cursor: 'pointer', minWidth: 60 }}
                            />
                            <span className={styles.toolbarTextBold} style={{ minWidth: 44, textAlign: 'right', flexShrink: 0 }}>
                                {prospectRadiusKm} km
                            </span>
                        </div>

                        <div className={styles.toolbarDivider} />

                        {/* Progress Group */}
                        <div className={styles.toolbarSegment} style={{ flex: '0 0 auto', justifyContent: 'center', minWidth: 100, whiteSpace: 'nowrap' }}>
                            {isRunning ? (
                                <>
                                    <Loader2 size={13} className={styles.loadingAnim} style={{ color: 'var(--sw-primary)', marginRight: 6 }} />
                                    <span className={styles.toolbarTextBold}>
                                        {prospectLeadsCount > 0 ? `${prospectLeadsCount} encontrados` : 'Buscando…'}
                                    </span>
                                </>
                            ) : isDone ? (
                                <span className={styles.toolbarTextBold}>
                                    {prospectLeadsCount} leads · {prospectTierACount} Tier A
                                </span>
                            ) : (
                                <span className={styles.toolbarText}>
                                    Pronto para buscar
                                </span>
                            )}
                        </div>
                    </div>

                    <div className={styles.toolbarActions}>
                        {isRunning || prospectSearching ? (
                            <button onClick={onProspectStop} className={`${styles.detectBtn} ${styles.stopBtn}`} title="Parar busca">
                                <Loader2 size={18} className={styles.loadingAnim} />
                                Parar
                            </button>
                        ) : (
                            <button
                                onClick={onProspectSearch}
                                className={styles.detectBtn}
                                disabled={!hasCoords}
                                title={isDone ? 'Nova busca' : 'Prospectar'}
                            >
                                {isDone ? <RotateCcw size={14} /> : <Navigation size={14} />}
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
