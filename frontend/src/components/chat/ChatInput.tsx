import React, { useRef, useEffect, useState } from 'react';
import {
    X, Loader2, Building2, Mic, ArrowUp, Zap
} from 'lucide-react';
import { CompanyResult } from './ChatInterfaces';
import { getAvatarUrl, getProxiedUrl, getCompanyLogoUrl } from '../../utils/avatarUtils';
import styles from '../ChatPanel.module.css';
import { ModelSelector, AIModel } from './ModelSelector';
import { ModelActivityBar, ModelActivityEvent, getNoticeStyle } from './ModelActivityBar';
import { AudioWaveform } from './AudioWaveform';

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
    isStreamingActivity?: boolean;
    // Cooldown props
    pipedriveCooldown?: number;
    // Agent mode
    agentMode?: 'v1' | 'v2';
    setAgentMode?: (mode: 'v1' | 'v2') => void;
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
    isStreamingActivity = false,
    pipedriveCooldown = 0,
    agentMode = 'v1',
    setAgentMode,
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
        
        // Criar um regex dinâmico com os nomes das empresas selecionadas (se houver)
        let entityRegexPart = "";
        if (selectedCompanies.length > 0) {
            const escapedNames = selectedCompanies
                .map(c => c.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
                .join('|');
            entityRegexPart = `@(?:${escapedNames})|`;
        }

        // Regex final: busca nomes selecionados OU @ seguido de caracteres compostos
        // Usamos [A-Za-z\u00C0-\u017F\s\-&] para suportar espaços, acentos, hífens e ampersands
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

    return (
        <div className={styles.inputContainer}>
            <div style={notice ? {
                border: `1px solid ${notice.border}`,
                background: notice.bg,
                borderRadius: 16,
            } : {}}>
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
                                            {(() => {
                                                if (company.type === 'organization') return 'empresa';
                                                if (company.type === 'email') return company.email;
                                                if (company.type === 'whatsapp') return (company as any).number || company.phone;
                                                return company.type;
                                            })()}
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
                                                setTimeout(() => {
                                                    // Se o que vem após o @ já é exatamente um dos nomes selecionados, 
                                                    // paramos de pesquisar para este @ específico.
                                                    const query = searchTerm;
                                                    const matchedSelection = selectedCompanies.find(c => query.toLowerCase().startsWith(c.name.toLowerCase()));
                                                    if (matchedSelection) {
                                                        const afterName = query.substring(matchedSelection.name.length);
                                                        if (afterName.length > 0) {
                                                            return;
                                                        }
                                                    }
                                                    if (inputRef.current) {
                                                        inputRef.current.focus();
                                                        const length = inputRef.current.value.length;
                                                        inputRef.current.setSelectionRange(length, length);
                                                    }
                                                }, 50); // Um tempo levemente maior para garantir o render do texto novo
                                            }}
                                        >
                                            <div className={styles.itemIcon} style={{ background: 'transparent' }}>
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
                                                    {(() => {
                                                        if (item.type === 'organization') return item.domain || 'empresa';
                                                        if (item.type === 'email') return (item.email && item.email !== item.name) ? item.email : 'email';
                                                        if (item.type === 'whatsapp') {
                                                            const contact = (item as any).number || item.phone;
                                                            return (contact && contact !== item.name) ? contact : 'whatsapp';
                                                        }
                                                        return item.type;
                                                    })()}
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
                            /* ── Modo gravação: ondas + botão stop ── */
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
                            /* ── Modo normal ── */
                            <div className={styles.inputLeftControls}>
                                {setAgentMode && (
                                    <div className={styles.agentModeToggle}>
                                        {(['v1', 'v2'] as const).map(mode => (
                                            <button
                                                key={mode}
                                                onClick={() => setAgentMode(mode)}
                                                title={mode === 'v1' ? 'Modo padrão' : 'Agente autônomo com ferramentas'}
                                                className={`${styles.agentModeButton} ${agentMode === mode ? styles.agentModeButtonActive : ''} ${mode === 'v2' && agentMode === 'v2' ? 'agentModeV2' : ''}`}
                                            >
                                                {mode.toUpperCase()}
                                            </button>
                                        ))}
                                    </div>
                                )}
                                <div className={styles.dividerSmall}>|</div>
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
                                        <div className={styles.cooldownBadge} title="Pipedrive em Cooldown (Aguardando reset de cota)">
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
                                    title={
                                        !voiceSupported
                                            ? 'Captura de áudio não suportada neste navegador'
                                            : isTranscribing
                                            ? 'Transcrevendo...'
                                            : 'Enviar por voz'
                                    }
                                >
                                    {isTranscribing
                                        ? <Loader2 size={16} className={styles.spinner} />
                                        : <Mic size={16} />
                                    }
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
                                cursor: 'pointer',
                                transition: 'all 0.2s',
                                transform: isStopHovered ? 'scale(1.08)' : 'scale(1.05)',
                                border: 'none',
                                boxShadow: 'none'
                            } : {}}
                            disabled={!isLoading && !inputValue.trim() && selectedCompanies.length === 0}
                            onClick={() => {
                                if (isLoading) {
                                    if (onStop) onStop();
                                } else {
                                    onSend(inputValue, selectedCompanies);
                                }
                            }}
                            title={isLoading ? "Parar resposta da IA" : "Enviar mensagem"}
                            type="button"
                        >
                            {isLoading ? (
                                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18 }}>
                                    {/* Um ícone de Stop Quadrado clássico preenchido (tamanho aumentado para 18) */}
                                    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                                        <rect x="4" y="4" width="16" height="16" rx="2.5" />
                                    </svg>
                                </span>
                            ) : (
                                <ArrowUp size={18} />
                            )}
                        </button>
                    </div>
                    {voiceError && (
                        voiceError === 'blocked' ? (
                            <div className={styles.voiceErrorHint}>
                                <span>
                                    Microfone bloqueado.{' '}
                                    <strong>Clique no cadeado</strong> na barra de endereço
                                    → Microfone → <strong>Permitir</strong> → recarregue.
                                </span>
                                <button
                                    className={styles.voiceRetryBtn}
                                    onClick={startListening}
                                >
                                    Tentar novamente
                                </button>
                            </div>
                        ) : (
                            <div className={styles.voiceErrorHint}>{voiceError}</div>
                        )
                    )}
                </div>
            </div>
            </div>
        </div>
    );
};
