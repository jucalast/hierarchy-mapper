import React from 'react';
import { 
    AlertCircle, 
    Fingerprint, 
    Globe, 
    Target, 
    Sparkles, 
    Loader2, 
    Play, 
    Building,
    ArrowLeft,
    Search,
    RotateCcw
} from 'lucide-react';


import styles from './NetworkGraph.module.css';

interface FloatingToolbarProps {
    error: string | null;
    handleSearch: (e: React.FormEvent) => void;
    cnpj: string;
    setCnpj: (val: string) => void;
    confirmedBrand: string;
    setConfirmedBrand: (val: string) => void;
    confirmedLogo: string;
    setConfirmedLogo: (val: string) => void;
    confirmedFollowers: string;
    setConfirmedFollowers: (val: string) => void;
    domainTarget: string;
    setDomainTarget: (val: string) => void;
    productFocus: string;
    setProductFocus: (val: string) => void;
    areaFocus: "compras" | "logistica";
    setAreaFocus: (val: "compras" | "logistica") => void;
    handleAutoEnrich: () => void;
    enrichingIds: Set<number>;
    discovering: boolean;
    loading: boolean;
    step: string;
    brandOptions: any[];
    onBrandSelect: (brandObj: any) => void;
}

export const FloatingToolbar: React.FC<FloatingToolbarProps> = ({
    error,
    handleSearch,
    cnpj,
    setCnpj,
    confirmedBrand,
    setConfirmedBrand,
    confirmedLogo,
    setConfirmedLogo,
    confirmedFollowers,
    setConfirmedFollowers,
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
    onBrandSelect
}) => {
    const [isFocused, setIsFocused] = React.useState(false);
    const [localSelected, setLocalSelected] = React.useState<string | null>(null);
    const isSearching = discovering || loading || enrichingIds.has(999);
    const needsAttention = !!confirmedBrand && !cnpj && !isFocused && !isSearching;

    const handleLocalSelect = (opt: any) => {
        const key = opt.name || opt.url;
        console.log("[Toolbar] Local Click Handled:", key);
        setLocalSelected(key);
        onBrandSelect(opt);
    };

    return (
        <div className={styles.toolbarUnifiedWrapper}>
            {/* 1. Header com Erro ou Brand Select Options (Progressivo) */}
            {error && <div className={styles.error}><AlertCircle size={18} /> {error}</div>}

            {step === "input" && !discovering && brandOptions.length > 0 && (
                <div className={styles.optionsContainer}>
                    {brandOptions.map((opt: any, idx: number) => (
                        <button
                            key={`brand-opt-${idx}-${opt.url || opt.name}`}
                            type="button"
                            className={`${styles.brandCard} ${(confirmedBrand === (opt.name || opt.url) || localSelected === (opt.name || opt.url)) ? styles.brandCardActive : ''}`}
                            onClick={() => handleLocalSelect(opt)}
                        >
                            <div className={styles.brandAvatarWrapper}>
                                {opt.logo ? (
                                    <img 
                                        src={`http://localhost:8000/api/v1/proxy/image?url=${encodeURIComponent(opt.logo)}`} 
                                        alt={opt.name} 
                                        className={styles.brandAvatar} 
                                    />
                                ) : (
                                    <div className={styles.brandAvatarPlaceholder}>
                                        <Building size={16} />
                                    </div>
                                )}
                            </div>
                            <div className={styles.brandInfo}>
                                <div className={styles.brandNameLine}>{opt.name}</div>
                                {opt.followers && (
                                    <div className={styles.brandFollowers}>{opt.followers} seguidores</div>
                                )}
                            </div>
                        </button>
                    ))}
                </div>
            )}

            {/* 2. Main Search Bar (Refine Tab) */}
            <div 
                className={`${styles.refineTab} ${isSearching ? styles.searching : ''} ${enrichingIds.has(999) ? styles.refineTabEnriching : ''}`}
                title="Intelligence Controller"
            >
                {/* Search Box area (Left) */}
                <div className={styles.searchBox}>
                    <form onSubmit={handleSearch} className={styles.inputGroup}>
                        {step === "input" ? (
                            <>
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
                                        </div>
                                    </>
                                )}
                            </>
                        ) : (
                            <div className={styles.confirmState}>
                                <button type="button" className={styles.backBtn} onClick={() => onBrandSelect(null)}>
                                    <ArrowLeft size={16} />
                                </button>
                                
                                <div className={`${styles.brandCard} ${styles.selectedBrandPreview}`}>
                                    <div className={styles.brandAvatarWrapper}>
                                        {confirmedLogo ? (
                                            <img 
                                                src={`http://localhost:8000/api/v1/proxy/image?url=${encodeURIComponent(confirmedLogo)}`} 
                                                className={styles.brandAvatar} 
                                                alt="Logo" 
                                            />
                                        ) : <Building size={14} className={styles.inputIcon} />}
                                    </div>
                                    <div className={styles.brandInfo}>
                                        <input 
                                            className={`${styles.input} ${styles.brandNameLine}`}
                                            value={confirmedBrand}
                                            onChange={(e) => setConfirmedBrand(e.target.value)}
                                        />
                                        {confirmedFollowers && (
                                            <div className={styles.brandFollowers}>
                                                {confirmedFollowers} seguidores
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className={styles.toolbarDivider} />
                                
                                {/* Area Selector (Compras / Logística) */}
                                <div className={styles.areaSelectorContainer}>
                                    <button 
                                        type="button" 
                                        className={`${styles.areaBtn} ${areaFocus === 'compras' ? styles.areaBtnActive : ''}`}
                                        onClick={() => setAreaFocus('compras')}
                                    >
                                        Compras
                                    </button>
                                    <button 
                                        type="button" 
                                        className={`${styles.areaBtn} ${areaFocus === 'logistica' ? styles.areaBtnActive : ''}`}
                                        onClick={() => setAreaFocus('logistica')}
                                    >
                                        Logística
                                    </button>
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
                        )}
                    </form>

                    <div className={styles.toolbarActions}>
                        {domainTarget && (
                            <button 
                                onClick={handleSearch} 
                                className={`${styles.detectBtn} ${discovering ? styles.detectBtnLoading : ''}`}
                                disabled={discovering || loading}
                            >
                                {discovering || loading ? (
                                    <Loader2 size={18} className={styles.loadingAnim} />
                                ) : (
                                    <>
                                        {step === "confirm" ? <Target size={14} /> : <Play size={14} fill="currentColor" />}
                                        {step === "confirm" ? "Mapear Hierarquia" : "Detectar"}
                                    </>
                                )}
                            </button>
                        )}
                    </div>
                </div>

                {/* Intelligence Trigger Button (Right) - Only show during SEARCH phase and if NOT detecting */}
                {step === "input" && !discovering && (
                    <div 
                        className={`${styles.refineIconWrapper} ${enrichingIds.has(999) ? styles.refineIconLoading : ''}`} 
                        onClick={handleAutoEnrich}
                        title={ (domainTarget && cnpj) ? "Refinar Enriquecimento" : "Enriquecer Inteligência" }
                    >
                        {enrichingIds.has(999) ? (
                            <Loader2 size={18} className={styles.loadingAnim} />
                        ) : (
                            (domainTarget && cnpj) ? <RotateCcw size={18} /> : <Search size={18} />
                        )}
                    </div>
                )}

            </div>
        </div>
    );
};


