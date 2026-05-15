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
import styles from './FloatingToolbar.module.css';
import { Avatar } from '@/components/ui';

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
}) => {
    const [isClosing, setIsClosing] = React.useState(false);
    const [displayOptions, setDisplayOptions] = React.useState<any[]>([]);
    const [isFocused, setIsFocused] = React.useState(false);
    const [localSelected, setLocalSelected] = React.useState<string | null>(null);

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

    const isSearching = discovering || loading || enrichingIds.has(999);
    const isNewCompanyMode = confirmedBrand === ' ';
    const needsAttention = (!!confirmedBrand || isNewCompanyMode) && !cnpj && !isFocused && !isSearching;

    const handleLocalSelect = (opt: any) => {
        const key = opt.name || opt.url;
        console.log('[Toolbar] Local Click Handled:', key);
        setLocalSelected(key);
        onBrandSelect(opt);
    };

    return (
        <div
            className={styles.toolbarUnifiedWrapper}
            data-sidebar-open={isSidebarOpen}
            data-chat-open={isChatOpen}
        >
            {error && <div className={styles.error}><AlertCircle size={18} /> {error}</div>}

            {displayOptions.length > 0 && (
                <div className={`${styles.optionsContainer} ${isClosing ? styles.optionsContainerClosing : ''}`}>
                    {displayOptions.map((opt: any, idx: number) => (
                        <div
                            key={`brand-opt-${idx}-${opt.url || opt.name}`}
                            className={`${styles.brandCard} ${(confirmedBrand === (opt.name || opt.url) || localSelected === (opt.name || opt.url)) ? styles.brandCardActive : ''}`}
                            onClick={() => handleLocalSelect(opt)}
                        >
                            <div className={styles.brandAvatarWrapper}>
                                <Avatar
                                    kind={opt.type === 'person' ? 'person' : 'company'}
                                    data={opt}
                                    size={36}
                                    className={styles.brandAvatar}
                                />
                            </div>
                            <div className={styles.brandInfo}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <div className={styles.brandNameLine}>{opt.name}</div>
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
                                </div>
                                {opt.followers && (
                                    <div className={styles.brandFollowers}>{opt.followers} seguidores</div>
                                )}
                            </div>

                            {opt.type === 'person' && (
                                <div className={styles.cardQuickActions}>
                                    <button
                                        type="button"
                                        className={styles.rejectBtn}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            if (onRejectCandidate) onRejectCandidate(opt.id);
                                        }}
                                        title="Reprovar e Descartar"
                                    >
                                        <X size={14} />
                                    </button>
                                    <button
                                        type="button"
                                        className={styles.approveBtn}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            if (onApproveCandidate) onApproveCandidate(opt.id);
                                        }}
                                        title="Aprovar Perfil"
                                    >
                                        <Check size={14} />
                                    </button>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            <div
                className={`${styles.refineTab} ${isSearching ? styles.searching : ''} ${enrichingIds.has(999) ? styles.refineTabEnriching : ''}`}
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
                                            size={32}
                                            className={styles.brandAvatar}
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
                                    !discovering && !loading ? (
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
                                            onClick={stopHierarchyScan}
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
            {children}
        </div>
    );
};
