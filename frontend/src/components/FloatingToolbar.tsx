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
    hasMapping?: boolean;
    stopHierarchyScan?: () => void;
    cancelDiscovery?: () => void;
    activeJobId?: string | null;
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
    onBrandSelect,
    hasMapping = false,
    stopHierarchyScan,
    cancelDiscovery,
    activeJobId
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

            {/* 🔄 Mostrar carrossel durante streaming (discovering=true) se houver candidatos */}
            {step === "input" && brandOptions.length > 0 && (
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
                                        src={`http://127.0.0.1:8000/api/v1/proxy/image?url=${encodeURIComponent(opt.logo)}`}
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
                                            {/* ✨ Botão de Enriquecimento (Reload) */}
                                            {!discovering && !loading && (
                                                <button
                                                    type="button"
                                                    className={`${styles.cleanSearchBtn} ${enrichingIds.has(999) ? styles.cleanSearchLoading : ''}`}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleAutoEnrich();
                                                    }}
                                                    title="Refinar Metadados com IA (CNPJ/Domínio)"
                                                >
                                                    {enrichingIds.has(999) ? (
                                                        <Loader2 size={16} className={styles.loadingAnim} />
                                                    ) : (
                                                        <RotateCcw size={16} />
                                                    )}
                                                </button>
                                            )}
                                        </div>
                                    </>
                                )}

                                {/* Se NÃO tem domínio ainda, mostra a lupa ao lado do CNPJ para permitir o enriquecimento inicial */}
                                {!domainTarget && !discovering && !loading && (
                                    <button
                                        type="button"
                                        className={`${styles.cleanSearchBtn} ${enrichingIds.has(999) ? styles.cleanSearchLoading : ''}`}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            handleAutoEnrich();
                                        }}
                                        title="Buscar Domínio e Dados"
                                    >
                                        {enrichingIds.has(999) ? (
                                            <Loader2 size={18} className={styles.loadingAnim} />
                                        ) : (
                                            <Search size={18} />
                                        )}
                                    </button>
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
                                                src={`http://127.0.0.1:8000/api/v1/proxy/image?url=${encodeURIComponent(confirmedLogo)}`}
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
                                            <div className={styles.brandFollowers} title={`${confirmedFollowers} seguidores`}>
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
                        {/* 🚀 BOTÃO PRINCIPAL (DETECTAR OU MAPEAR) */}
                        {!enrichingIds.has(999) && (
                            <>
                                {step === "input" && domainTarget && (
                                    <>
                                        {(!discovering && !loading) && (
                                            <button
                                                onClick={handleSearch}
                                                className={`${styles.detectBtn}`}
                                            >
                                                <Search size={14} />
                                                Detectar
                                            </button>
                                        )}
                                        {(discovering || loading) && (
                                            <button
                                                onClick={cancelDiscovery}
                                                className={`${styles.detectBtn} ${styles.stopBtn}`}
                                                title="Parar busca de empresa"
                                            >
                                                <Loader2 size={18} className={styles.loadingAnim} />
                                                Parar
                                            </button>
                                        )}
                                    </>
                                )}

                                {step !== "input" && (
                                    <>
                                        {(!discovering && !loading) && (
                                            <button
                                                onClick={handleSearch}
                                                className={styles.detectBtn}
                                            >
                                                {hasMapping ? <RotateCcw size={14} /> : <Play size={14} fill="currentColor" />}
                                                Mapear
                                            </button>
                                        )}
                                        {(discovering || loading) && (
                                            <button
                                                onClick={stopHierarchyScan}
                                                className={`${styles.detectBtn} ${styles.stopBtn}`}
                                                title="Cancelar mapeamento em andamento"
                                            >
                                                <Loader2 size={18} className={styles.loadingAnim} />
                                                Parar
                                            </button>
                                        )}
                                    </>
                                )}
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
