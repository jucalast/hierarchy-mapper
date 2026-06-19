import React from 'react';
import {
    AlertCircle,
    Fingerprint,
    Globe,
    Target,
    Loader2,
    Play,
    ArrowLeft,
    Search,
    RotateCcw,
    Check,
    X,
} from 'lucide-react';
import styles from './styles/Toolbar.module.css';
import { Avatar } from '../ui';
import { MappingModeToggle } from './components/MappingModeToggle';

export interface NormalToolbarProps {
    error: string | null;
    handleSearch: (e: React.FormEvent) => void;
    cnpj: string;
    setCnpj: (val: string) => void;
    confirmedBrand: string;
    setConfirmedBrand: (val: string) => void;
    confirmedLogo: string;
    confirmedFollowers: string;
    domainTarget: string;
    setDomainTarget: (val: string) => void;
    productFocus: string;
    setProductFocus: (val: string) => void;
    areaFocus: 'compras' | 'logistica';
    setAreaFocus: (val: 'compras' | 'logistica') => void;
    handleAutoEnrich: () => void;
    enrichingIds: Set<number>;
    discovering: boolean;
    loading: boolean;
    step: string;
    brandOptions: any[];
    onBrandSelect: (brandObj: any) => void;
    hasMapping?: boolean;
    stopHierarchyScan?: () => void;
    cancelDiscovery?: () => void;
    onApproveCandidate?: (id: string) => void;
    onRejectCandidate?: (id: string) => void;
    isSidebarOpen?: boolean;
    isChatOpen?: boolean;
    children?: React.ReactNode;
    mappingMode: 'discovery' | 'scan';
    onMappingModeChange: (mode: 'discovery' | 'scan') => void;
    scanTerminal?: React.ReactNode;
    scanPreview?: React.ReactNode;
    isScanning?: boolean;
    onStopScan?: () => void;
}

export const NormalToolbar: React.FC<NormalToolbarProps> = ({
    error,
    handleSearch,
    cnpj,
    setCnpj,
    confirmedBrand,
    setConfirmedBrand,
    confirmedLogo,
    confirmedFollowers,
    domainTarget,
    setDomainTarget,
    productFocus,
    setProductFocus,
    areaFocus,
    setAreaFocus,
    handleAutoEnrich,
    enrichingIds,
    discovering,
    loading,
    step,
    brandOptions,
    onBrandSelect,
    hasMapping,
    stopHierarchyScan,
    cancelDiscovery,
    onApproveCandidate,
    onRejectCandidate,
    isSidebarOpen = false,
    isChatOpen = false,
    children,
    mappingMode,
    onMappingModeChange,
    scanTerminal,
    scanPreview,
    isScanning = false,
    onStopScan,
}) => {
    const [isClosing, setIsClosing] = React.useState(false);
    const [displayOptions, setDisplayOptions] = React.useState<any[]>([]);
    const [isFocused, setIsFocused] = React.useState(false);
    const [localSelected, setLocalSelected] = React.useState<string | null>(null);

    React.useEffect(() => {
        if (!confirmedBrand) {
            setLocalSelected(null);
        }
    }, [confirmedBrand]);

    // Animação de entrada e saída do carrossel de opções
    React.useEffect(() => {
        if (brandOptions.length > 0) {
            setIsClosing(false);
            setDisplayOptions(brandOptions);
        } else if (displayOptions.length > 0) {
            setIsClosing(true);
            const timer = setTimeout(() => {
                setDisplayOptions([]);
                setIsClosing(false);
            }, 300); // Duração da animação swSlideDown
            return () => clearTimeout(timer);
        }
    }, [brandOptions]);

    const isScanningActive = mappingMode === 'discovery' ? (discovering || loading) : isScanning;
    const isSearching = discovering || loading || enrichingIds.has(999) || isScanning;
    const isNewCompanyMode = confirmedBrand === ' ';
    const needsAttention = (!!confirmedBrand || isNewCompanyMode) && !cnpj && !isFocused && !isSearching;

    const handleLocalSelect = (opt: any) => {
        const key = opt.name || opt.url;
        console.log('[Toolbar] Local Click Handled:', key);
        setLocalSelected(key);
        onBrandSelect(opt);
    };

    return (
        <>
        {scanPreview}
        {children}
        <div
            className={styles.toolbarUnifiedWrapper}
            data-sidebar-open={isSidebarOpen}
            data-chat-open={isChatOpen}
        >
            {error && <div className={styles.error}><AlertCircle size={18} /> {error}</div>}

            <div className={styles.purpleToolbarWrapper}>
                <div className={styles.mainToolbarSection}>
                    {displayOptions.length > 0 && (
                        <div className={`${styles.optionsContainer} ${isClosing ? styles.optionsContainerClosing : ''}`}>
                            {displayOptions.map((opt: any, idx: number) => {
                                const isPerson = opt.type === 'person';
                                const isActive = confirmedBrand === (opt.name || opt.url) || localSelected === (opt.name || opt.url);
                                const prevIsPerson = idx > 0 && displayOptions[idx - 1]?.type === 'person';
                                const nextIsPerson = idx < displayOptions.length - 1 && displayOptions[idx + 1]?.type === 'person';
                                const showDivider = idx > 0 && isPerson !== prevIsPerson;
                                return (
                                    <React.Fragment key={`brand-opt-${idx}-${opt.url || opt.name}`}>
                                        {showDivider && <div className={styles.toolbarDivider} />}
                                        <div
                                            className={`${styles.brandCard} ${isPerson ? styles.personCard : ''} ${isActive ? styles.brandCardActive : ''}`}
                                            onClick={() => {
                                                if (isPerson) {
                                                    const linkedin = opt.originalEmployee?.linkedin_url
                                                        || opt.originalEmployee?.linkedin
                                                        || opt.url
                                                        || `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(opt.name)}`;
                                                    window.open(linkedin, '_blank');
                                                } else {
                                                    handleLocalSelect(opt);
                                                }
                                            }}
                                            title={isPerson ? 'Ver perfil no LinkedIn' : undefined}
                                            style={isPerson ? { cursor: 'pointer' } : undefined}
                                        >
                                            {isPerson ? (
                                                <div className={styles.personAvatarWrapper}>
                                                    <Avatar kind="person" data={opt} size={34} style={{ borderRadius: '8px' }} />
                                                </div>
                                            ) : (
                                                <div className={styles.brandAvatarWrapper}>
                                                    <Avatar kind="company" data={opt} size={34} />
                                                </div>
                                            )}

                                            <div className={styles.brandInfo}>
                                                <div className={styles.brandNameLine}>{opt.name}</div>
                                                {opt.followers && (
                                                    <div className={styles.brandFollowers}>{opt.followers}</div>
                                                )}
                                            </div>

                                            {isPerson ? (
                                                <>
                                                    <img
                                                        src="/linkedin.png"
                                                        alt="LinkedIn"
                                                        title="Ver no LinkedIn"
                                                        style={{ width: 18, height: 18, objectFit: 'contain', borderRadius: 4, opacity: 0.55, cursor: 'pointer', flexShrink: 0, transition: 'opacity 0.2s' }}
                                                        onMouseEnter={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '0.9'; }}
                                                        onMouseLeave={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '0.55'; }}
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            const linkedin = opt.originalEmployee?.linkedin_url || opt.originalEmployee?.linkedin || opt.url || `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(opt.name)}`;
                                                            window.open(linkedin, '_blank');
                                                        }}
                                                    />
                                                    <div className={styles.cardQuickActions}>
                                                        <button
                                                            type="button"
                                                            className={styles.rejectBtn}
                                                            onClick={(e) => { e.stopPropagation(); if (onRejectCandidate) onRejectCandidate(opt.id); }}
                                                            title="Reprovar"
                                                        >
                                                            <X size={12} />
                                                        </button>
                                                        <button
                                                            type="button"
                                                            className={styles.approveBtn}
                                                            onClick={(e) => { e.stopPropagation(); if (onApproveCandidate) onApproveCandidate(opt.id); }}
                                                            title="Aprovar"
                                                        >
                                                            <Check size={12} />
                                                        </button>
                                                    </div>
                                                </>
                                            ) : (
                                                <img
                                                    src="/linkedin.png"
                                                    alt="LinkedIn"
                                                    className={styles.linkedinIcon}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        const linkedin = opt.originalEmployee?.linkedin || opt.url || `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(opt.name)}`;
                                                        window.open(linkedin, '_blank');
                                                    }}
                                                    title="Ver no LinkedIn"
                                                />
                                            )}
                                        </div>
                                    </React.Fragment>
                                );
                            })}
                        </div>
                    )}

                    <div className={`${styles.toolbarContentLayout} ${displayOptions.length > 0 ? styles.toolbarConnected : ''} ${scanTerminal ? styles.toolbarTerminalConnected : ''}`}>
                        <div
                            className={`${styles.refineTab} ${isSearching ? styles.searching : ''} ${enrichingIds.has(999) ? styles.refineTabEnriching : ''} ${displayOptions.length > 0 ? styles.refineTabConnected : ''} ${scanTerminal ? styles.refineTabTerminalConnected : ''}`}
                            title="Intelligence Controller"
                        >
                            {step === 'input' ? (
                                <div className={styles.searchBox}>
                                    <form onSubmit={handleSearch} className={styles.inputGroup}>
                                        <div className={`${styles.toolbarSegment} ${needsAttention ? styles.inputAttention : ''}`}>
                                            <Fingerprint size={14} className={styles.inputIcon} />
                                            <input
                                                placeholder="CNPJ"
                                                className={styles.input}
                                                value={cnpj}
                                                onChange={(e) => setCnpj(e.target.value)}
                                                onFocus={() => setIsFocused(true)}
                                                onBlur={() => setIsFocused(false)}
                                            />
                                        </div>

                                        {domainTarget && (
                                            <>
                                                <div className={styles.toolbarDivider} />
                                                <div className={styles.toolbarSegment}>
                                                    <Globe size={14} className={styles.inputIcon} />
                                                    <input
                                                        placeholder="Domínio"
                                                        className={styles.input}
                                                        value={domainTarget}
                                                        onChange={(e) => setDomainTarget(e.target.value)}
                                                    />
                                                    {!discovering && !loading && (
                                                        <button
                                                            type="button"
                                                            className={`${styles.cleanSearchBtn} ${enrichingIds.has(999) ? styles.cleanSearchLoading : ''}`}
                                                            onClick={(e) => { e.stopPropagation(); handleAutoEnrich(); }}
                                                            title="Refinar Metadados com IA (CNPJ/Domínio)"
                                                        >
                                                            {enrichingIds.has(999) ? <Loader2 size={16} className={styles.loadingAnim} /> : <RotateCcw size={16} />}
                                                        </button>
                                                    )}
                                                </div>
                                            </>
                                        )}

                                        {!domainTarget && !discovering && !loading && (
                                            <button
                                                type="button"
                                                className={`${styles.cleanSearchBtn} ${enrichingIds.has(999) ? styles.cleanSearchLoading : ''}`}
                                                onClick={(e) => { e.stopPropagation(); handleAutoEnrich(); }}
                                                title="Buscar Domínio e Dados"
                                            >
                                                {enrichingIds.has(999) ? <Loader2 size={18} className={styles.loadingAnim} /> : <Search size={18} />}
                                            </button>
                                        )}
                                    </form>

                                    {!enrichingIds.has(999) && domainTarget && (
                                        <div className={styles.toolbarActions}>
                                            {!discovering && !loading && (
                                                <button onClick={handleSearch} className={styles.detectBtn}>
                                                    <Search size={14} />
                                                    Detectar
                                                </button>
                                            )}
                                            {(discovering || loading) && (
                                                <button onClick={cancelDiscovery} className={`${styles.detectBtn} ${styles.stopBtn}`} title="Parar busca de empresa">
                                                    <Loader2 size={18} className={styles.loadingAnim} />
                                                    Parar
                                                </button>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className={styles.searchBoxTwoRows}>
                                    <form onSubmit={handleSearch} className={styles.inputGroupColumn}>
                                        {/* Linha 1: Brand preview + Área + botão Mapear */}
                                        <div className={styles.confirmRow1}>
                                            <button type="button" className={styles.backBtn} onClick={() => onBrandSelect(null)}>
                                                <ArrowLeft size={16} />
                                            </button>

                                            <div className={`${styles.brandCard} ${styles.selectedBrandPreview}`}>
                                                <div className={styles.brandAvatarWrapper}>
                                                    <Avatar
                                                        kind="company"
                                                        src={confirmedLogo}
                                                        name={confirmedBrand}
                                                        data={{ domain: domainTarget }}
                                                        size={34}
                                                    />
                                                </div>
                                                <div className={styles.brandInfo}>
                                                    <input
                                                        className={`${styles.input} ${styles.brandNameLine}`}
                                                        value={confirmedBrand}
                                                        onChange={(e) => setConfirmedBrand(e.target.value)}
                                                    />
                                                    {confirmedFollowers && (
                                                        <div className={styles.brandFollowers} title={`${confirmedFollowers} seguidores`}>
                                                            {confirmedFollowers} seguidores
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                            <div className={styles.toolbarDivider} />

                                            <div className={styles.areaSelectorContainer}>
                                                <button type="button" className={`${styles.areaBtn} ${areaFocus === 'compras' ? styles.areaBtnActive : ''}`} onClick={() => setAreaFocus('compras')}>Compras</button>
                                                <button type="button" className={`${styles.areaBtn} ${areaFocus === 'logistica' ? styles.areaBtnActive : ''}`} onClick={() => setAreaFocus('logistica')}>Logística</button>
                                            </div>

                                            <div className={styles.toolbarDivider} />

                                            {!enrichingIds.has(999) && (
                                                !isScanningActive ? (
                                                    <button
                                                        type="button"
                                                        onClick={handleSearch}
                                                        className={styles.detectBtn}
                                                        disabled={!cnpj}
                                                        style={{ opacity: !cnpj ? 0.5 : 1, cursor: !cnpj ? 'not-allowed' : 'pointer' }}
                                                        title={!cnpj ? 'Preencha o CNPJ para começar' : 'Iniciar mapeamento'}
                                                    >
                                                        {hasMapping ? <RotateCcw size={14} /> : <Play size={14} fill="currentColor" />}
                                                        Mapear
                                                    </button>
                                                ) : (
                                                    <button
                                                        type="button"
                                                        onClick={mappingMode === 'discovery' ? stopHierarchyScan : onStopScan}
                                                        className={`${styles.detectBtn} ${styles.stopBtn}`}
                                                        title="Cancelar mapeamento em andamento"
                                                    >
                                                        <Loader2 size={18} className={styles.loadingAnim} />
                                                        Parar
                                                    </button>
                                                )
                                            )}
                                        </div>

                                        {/* Linha 2: CNPJ + Categoria */}
                                        <div className={styles.confirmRow2}>
                                            <div className={`${styles.toolbarSegment} ${!cnpj ? styles.inputAttention : ''}`} style={{ maxWidth: 180, flexShrink: 0 }}>
                                                <Fingerprint size={14} className={styles.inputIcon} />
                                                <input
                                                    placeholder="CNPJ Obrigatório"
                                                    className={styles.input}
                                                    value={cnpj}
                                                    onChange={(e) => setCnpj(e.target.value)}
                                                    style={{ color: !cnpj ? '#ff4444' : 'inherit' }}
                                                />
                                            </div>

                                            <div className={styles.toolbarDivider} />

                                            <div className={styles.toolbarSegment}>
                                                <Target size={14} className={styles.inputIcon} />
                                                <input
                                                    placeholder="Categoria (ex: Embalagens)"
                                                    className={styles.input}
                                                    value={productFocus}
                                                    onChange={(e) => setProductFocus(e.target.value)}
                                                />
                                            </div>
                                        </div>
                                    </form>
                                </div>
                            )}
                        </div>
                    </div>
                    {scanTerminal}
                </div>

                <MappingModeToggle
                    mode={mappingMode}
                    onChange={onMappingModeChange}
                    visible={step !== 'input'}
                />
            </div>
        </div>
        </>
    );
};
