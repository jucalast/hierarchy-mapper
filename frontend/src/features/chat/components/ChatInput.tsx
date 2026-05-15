import React, { useRef, useEffect, useState } from 'react';
import {
    X, Loader2, Building2, Mic, ArrowUp, Zap
} from 'lucide-react';
import { CompanyResult } from '../types';
import { getAvatarUrl, getProxiedUrl, getCompanyLogoUrl } from '@/utils/avatarUtils';
import styles from '../styles/components/ChatInput.module.css';
import { ModelSelector, AIModel } from './ui/ModelSelector';
import { ModelActivityBar, ModelActivityEvent, getNoticeStyle } from './ui/ModelActivityBar';
import { AudioWaveform } from './ui/AudioWaveform';

interface ChatInputProps {
    inputValue: string;
    setInputValue: (val: string) => void;
    isLoading: boolean;
    onSend: (text: string, companies: CompanyResult[]) => void;
    selectedCompanies: CompanyResult[];
    setSelectedCompanies: (companies: CompanyResult[]) => void;
    // Autocomplete props
    showAutocomplete: boolean;
    isSearching: boolean;
    searchingCategory: string | null;
    searchTerm: string;
    companies: CompanyResult[];
    selectSearchResult: (company: CompanyResult) => void;
    // Speech props
    isListening: boolean;
    isTranscribing?: boolean;
    startListening: () => void;
    stopListening: () => void;
    voiceError?: string | null;
    voiceSupported?: boolean;
    analyserNode?: React.MutableRefObject<AnalyserNode | null>;
    // Model props
    model: AIModel;
    setModel: (model: AIModel) => void;
    strictMode?: boolean;
    setStrictMode?: (strict: boolean) => void;
    liveModel?: AIModel | null;
    modelActivity?: ModelActivityEvent[];
    // Cooldown props
    pipedriveCooldown?: number;
    // Styling
    theme: string;
    onStop?: () => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({
    inputValue, setInputValue, isLoading, onSend,
    selectedCompanies, setSelectedCompanies,
    showAutocomplete, isSearching, searchingCategory, searchTerm, companies, selectSearchResult,
    isListening, isTranscribing = false, startListening, stopListening, voiceError, voiceSupported = true, analyserNode,
    model, setModel,
    strictMode = false,
    setStrictMode,
    liveModel,
    modelActivity = [],
    pipedriveCooldown = 0,
    theme,
    onStop
}) => {
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const highlighterRef = useRef<HTMLDivElement>(null);
    const autocompleteRef = useRef<HTMLDivElement>(null);
    const [isStopHovered, setIsStopHovered] = useState(false);

    // Sincronizar scroll do highlighter com o textarea
    const handleScroll = () => {
        if (inputRef.current && highlighterRef.current) {
            highlighterRef.current.scrollTop = inputRef.current.scrollTop;
        }
    };

    // Auto-ajuste de altura
    useEffect(() => {
        if (inputRef.current) {
            inputRef.current.style.height = 'auto';
            inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 76)}px`;
        }
    }, [inputValue]);

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey && !showAutocomplete && !isLoading) {
            e.preventDefault();
            if (inputValue.trim() || selectedCompanies.length > 0) {
                onSend(inputValue, selectedCompanies);
            }
        }
    };

    const renderHighlightedText = (text: string) => {
        if (!text) return text;

        let entityRegexPart = "";
        if (selectedCompanies.length > 0) {
            const escapedNames = selectedCompanies
                .map(c => c.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
                .join('|');
            entityRegexPart = `@(?:${escapedNames})|`;
        }

        const finalRegex = new RegExp(`(${entityRegexPart}@[A-Za-z\\u00C0-\\u017F0-9\\s\\-&]+?)(?=\\s*[.,;!?(){}\\[\\]<>]|\\s+@|$)`, 'g');
        const parts = text.split(finalRegex);

        return parts.map((part, i) => {
            if (part && part.startsWith('@')) {
                return <span key={i} className={styles.highlightPurple}>{part}</span>;
            }
            return part;
        });
    };

    const getInitials = (name: string) => name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
    const OrgIcon = () => <Building2 size={16} className="shrink-0 opacity-40" />;

    const notice = getNoticeStyle(modelActivity || []);

    const containerStyle = notice ? {
        border: `1px solid ${notice.border}`,
        background: notice.bg,
        borderRadius: 16,
    } : {};

    return (
        <div className={styles.inputContainer}>
            <div style={containerStyle}>
                {notice && <ModelActivityBar events={modelActivity || []} />}
                
                <div className={styles.inputBox}>
                    <div className={styles.inputFieldWrapper}>
                        {selectedCompanies.length > 0 && (
                            <div className={styles.inputCompaniesContainer}>
                                {selectedCompanies.map((company) => (
                                    <div key={company.id} className={styles.inputCompanyPill}>
                                        <div className={styles.pillIconArea}>
                                            {company.type === 'organization' ? (
                                                getCompanyLogoUrl(company) ? (
                                                    <img
                                                        src={getProxiedUrl(getCompanyLogoUrl(company))}
                                                        className={styles.pillCompanyLogo}
                                                        onError={(e) => { e.currentTarget.style.display = 'none'; }}
                                                    />
                                                ) : <OrgIcon />
                                            ) : (
                                                getAvatarUrl(company) ? (
                                                    <img
                                                        src={getProxiedUrl(getAvatarUrl(company))}
                                                        className={styles.pillCompanyLogo}
                                                        style={{ borderRadius: '50%' }}
                                                        onError={(e) => {
                                                            e.currentTarget.src = company.type === 'whatsapp' ? '/wppicon.png' : '/outlook.png';
                                                            e.currentTarget.style.objectFit = 'contain';
                                                            e.currentTarget.style.padding = '2px';
                                                        }}
                                                    />
                                                ) : (
                                                    company.type === 'whatsapp' ? <img src="/wppicon.png" alt="W" style={{ width: 18, height: 18, objectFit: 'contain' }} /> : <img src="/outlook.png" alt="E" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                                                )
                                            )}
                                        </div>
                                        <div className={styles.pillInfo}>
                                            <span className={styles.pillName}>{company.name}</span>
                                            <span className={styles.pillSubtext}>
                                                {company.type === 'organization' ? 'empresa' : (company.email || (company as any).number || company.phone)}
                                            </span>
                                        </div>
                                        <button
                                            className={styles.removePillBtn}
                                            onClick={() => setSelectedCompanies(selectedCompanies.filter(c => c.id !== company.id))}
                                            type="button"
                                        >
                                            <X size={14} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className={styles.inputBoxInterior}>
                            <div className={styles.inputHighlighter} ref={highlighterRef}>
                                {renderHighlightedText(inputValue)}
                                {inputValue.endsWith(' ') && <span style={{ visibility: 'hidden' }}>&nbsp;</span>}
                            </div>

                            <textarea
                                ref={inputRef}
                                value={inputValue}
                                onChange={(e) => setInputValue(e.target.value)}
                                onScroll={handleScroll}
                                onKeyDown={handleKeyPress}
                                placeholder="Digite @ para buscar uma empresa..."
                                className={styles.inputField}
                                rows={1}
                                spellCheck={false}
                                autoCorrect="off"
                                autoCapitalize="sentences"
                            />
                        </div>

                        {showAutocomplete && (
                            <div ref={autocompleteRef} className={styles.autocompleteDropdown}>
                                {isSearching && (
                                    <div className={styles.autocompleteLoading}>
                                        <Loader2 size={16} className={styles.spinner} />
                                        Buscando {searchingCategory || 'empresas'}...
                                    </div>
                                )}
                                {!isSearching && companies.length === 0 && searchTerm.trim().length > 0 && (
                                    <div className={styles.autocompleteEmpty}>Nenhum resultado encontrado</div>
                                )}
                                {!isSearching && companies.length > 0 && (
                                    <div className={styles.autocompleteList}>
                                        {companies.map((item, index) => (
                                            <button
                                                key={`${item.type}-${item.id}-${index}`}
                                                className={styles.autocompleteItem}
                                                onClick={() => {
                                                    selectSearchResult(item);
                                                    if (inputRef.current) {
                                                        inputRef.current.focus();
                                                        const length = inputRef.current.value.length;
                                                        inputRef.current.setSelectionRange(length, length);
                                                    }
                                                }}
                                            >
                                                <div className={styles.itemIcon}>
                                                    {item.type === 'organization' ? (
                                                        <div className={`${styles.initialsAvatar} ${styles.square}`} style={{ borderRadius: '4px' }}>
                                                            {getInitials(item.name)}
                                                        </div>
                                                    ) : (
                                                        getAvatarUrl(item) ? (
                                                            <img
                                                                src={getProxiedUrl(getAvatarUrl(item))}
                                                                alt={item.name}
                                                                style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }}
                                                                onError={(e) => {
                                                                    e.currentTarget.src = item.type === 'whatsapp' ? '/wppicon.png' : '/outlook.png';
                                                                    e.currentTarget.style.objectFit = 'contain';
                                                                    e.currentTarget.style.padding = '4px';
                                                                }}
                                                            />
                                                        ) : (
                                                            item.type === 'whatsapp' ?
                                                                <img src="/wppicon.png" alt="W" style={{ width: 22, height: 22, objectFit: 'contain' }} /> :
                                                                <img src="/outlook.png" alt="E" style={{ width: 22, height: 22, objectFit: 'contain' }} />
                                                        )
                                                    )}
                                                </div>
                                                <div className={styles.itemInfo}>
                                                    <div className={styles.itemName}>{item.name}</div>
                                                    <div className={styles.itemType}>
                                                        {item.type === 'organization' ? (item.domain || 'empresa') : (item.email || (item as any).number || item.phone || item.type)}
                                                    </div>
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}

                        <div className={styles.inputBottom}>
                            {isListening ? (
                                <div className={styles.recordingBar}>
                                    <span className={styles.recordingDot} />
                                    {analyserNode && (
                                        <AudioWaveform analyserNode={analyserNode} isActive={isListening} />
                                    )}
                                    <button
                                        className={styles.stopRecordingBtn}
                                        onClick={stopListening}
                                        title="Parar gravação"
                                    />
                                </div>
                            ) : (
                                <div className={styles.inputLeftControls}>
                                    <ModelSelector
                                        model={model}
                                        setModel={setModel}
                                        strictMode={strictMode}
                                        setStrictMode={setStrictMode}
                                        theme={theme}
                                        liveModel={liveModel}
                                    />
                                    {pipedriveCooldown > 0 && (
                                        <>
                                            <div className={styles.dividerSmall}>|</div>
                                            <div className={styles.cooldownBadge} title="Pipedrive em Cooldown">
                                                <Zap size={12} className={styles.cooldownIcon} />
                                                <span>
                                                    {Math.floor(pipedriveCooldown / 60)}:{String(pipedriveCooldown % 60).padStart(2, '0')}
                                                </span>
                                            </div>
                                        </>
                                    )}
                                    <div className={styles.dividerSmall}>|</div>
                                    <button
                                        className={styles.voiceBtn}
                                        onClick={startListening}
                                        disabled={!voiceSupported || isTranscribing}
                                        title={!voiceSupported ? 'Não suportado' : isTranscribing ? 'Transcrevendo...' : 'Voz'}
                                    >
                                        {isTranscribing ? <Loader2 size={16} className={styles.spinner} /> : <Mic size={16} />}
                                        <span className={styles.voiceBtnLabel}>
                                            {isTranscribing ? 'Transcrevendo' : 'Voz'}
                                        </span>
                                    </button>
                                </div>
                            )}

                            <button
                                className={`${styles.sendBtn} ${(!isLoading && (inputValue.trim() || selectedCompanies.length > 0)) ? styles.active : ''}`}
                                onMouseEnter={() => { if (isLoading) setIsStopHovered(true); }}
                                onMouseLeave={() => { setIsStopHovered(false); }}
                                style={isLoading ? {
                                    background: isStopHovered ? 'rgba(239, 68, 68, 0.3)' : 'rgba(239, 68, 68, 0.2)',
                                    color: '#ef4444',
                                    opacity: 1,
                                    transform: isStopHovered ? 'scale(1.08)' : 'scale(1.05)',
                                } : {}}
                                disabled={!isLoading && !inputValue.trim() && selectedCompanies.length === 0}
                                onClick={() => {
                                    if (isLoading) {
                                        if (onStop) onStop();
                                    } else {
                                        onSend(inputValue, selectedCompanies);
                                    }
                                }}
                                type="button"
                            >
                                {isLoading ? (
                                    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                                        <rect x="4" y="4" width="16" height="16" rx="2.5" />
                                    </svg>
                                ) : (
                                    <ArrowUp size={18} />
                                )}
                            </button>
                        </div>
                        {voiceError && <div className={styles.voiceErrorHint}>{voiceError}</div>}
                    </div>
                </div>
            </div>
        </div>
    );
};
