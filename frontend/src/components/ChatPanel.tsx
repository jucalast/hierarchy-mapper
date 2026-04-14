import React, { useState, useRef, useEffect } from 'react';
import {
    ArrowUp,
    X,
    Lightbulb,
    ChevronRight,
    Copy,
    Wand2,
    ThumbsDown,
    RotateCcw,
    Library,
    Plus,
    Loader2,
    Sun,
    Moon,
    Search
} from 'lucide-react';
import styles from './ChatPanel.module.css';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    sources?: number;
    thinkingTime?: string;
    selectedCompanies?: CompanyResult[];
}

interface CompanyResult {
    id: number;
    name: string;
    domain?: string;
    logo_url?: string;
}

interface ChatPanelProps {
    showChat: boolean;
    setShowChat: (show: boolean) => void;
    selectedOrgId?: number | null;
    selectedOrgName?: string;
    theme?: string;
    onToggleTheme?: () => void;
}

// Ícone do asterisco da IA
const AIAsterisk = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4b5563" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5">
        <line x1="12" y1="4" x2="12" y2="20"></line>
        <line x1="4" y1="12" x2="20" y2="12"></line>
        <line x1="6.34" y1="6.34" x2="17.66" y2="17.66"></line>
        <line x1="17.66" y1="6.34" x2="6.34" y2="17.66"></line>
    </svg>
);

// Ícone para as fontes (pequenos quadrados azuis)
const SourceIcon = () => (
    <div className="w-[18px] h-[18px] bg-[#5E6AD2] rounded-[4px] border border-white flex items-center justify-center shadow-sm relative -ml-1.5 first:ml-0">
        <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="w-2.5 h-2.5">
            <line x1="8" y1="6" x2="21" y2="6"></line>
            <line x1="8" y1="12" x2="21" y2="12"></line>
            <line x1="8" y1="18" x2="21" y2="18"></line>
            <line x1="3" y1="6" x2="3.01" y2="6"></line>
            <line x1="3" y1="12" x2="3.01" y2="12"></line>
            <line x1="3" y1="18" x2="3.01" y2="18"></line>
        </svg>
    </div>
);

// Ícone do modelo Opus
const OpusIcon = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ea580c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
        <path d="M12 2v4"></path>
        <path d="M12 18v4"></path>
        <path d="M4.93 4.93l2.83 2.83"></path>
        <path d="M16.24 16.24l2.83 2.83"></path>
        <path d="M2 12h4"></path>
        <path d="M18 12h4"></path>
        <path d="M4.93 19.07l2.83-2.83"></path>
        <path d="M16.24 7.76l2.83-2.83"></path>
    </svg>
);

// Ícone da organização
const OrgIcon = () => (
    <div className="w-5 h-5 bg-[#5E6AD2] rounded-md flex items-center justify-center shadow-inner shrink-0">
        <svg viewBox="0 0 100 100" className="w-3 h-3 text-white fill-current">
            <path d="M15,85 L85,15" stroke="white" strokeWidth="12" strokeLinecap="round" />
            <path d="M35,95 L95,35" stroke="rgba(255,255,255,0.6)" strokeWidth="8" strokeLinecap="round" />
        </svg>
    </div>
);

export const ChatPanel: React.FC<ChatPanelProps> = ({
    showChat,
    setShowChat,
    selectedOrgId,
    selectedOrgName = 'Organização',
    theme = 'light',
    onToggleTheme
}) => {
    const [messages, setMessages] = useState<Message[]>([
        {
            id: '1',
            role: 'assistant',
            content: 'Olá! Sou seu assistente de IA. Como posso ajudá-lo sem a análise da hierarquia?',
            timestamp: new Date(),
            thinkingTime: '2'
        }
    ]);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showAutocomplete, setShowAutocomplete] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [companies, setCompanies] = useState<CompanyResult[]>([]);
    const [selectedCompanies, setSelectedCompanies] = useState<CompanyResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [hasAtSymbol, setHasAtSymbol] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const autocompleteRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSendMessage = async () => {
        if (!inputValue.trim()) return;

        // Adicionar mensagem do usuário
        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: inputValue,
            timestamp: new Date(),
            selectedCompanies: selectedCompanies.length > 0 ? selectedCompanies : undefined
        };

        setMessages(prev => [...prev, userMessage]);
        setInputValue('');
        setIsLoading(true);

        try {
            // Chamar a API de chat
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            const response = await fetch(`${API_BASE}/api/v1/ai/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMessage.content,
                    orgId: selectedOrgId,
                    selectedCompanies: selectedCompanies.map(c => ({ id: c.id, name: c.name })),
                    context: 'hierarchy_analysis'
                })
            });

            if (response.ok) {
                const data = await response.json();
                const assistantMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: data.response || 'Desculpe, não consegui processar sua mensagem.',
                    timestamp: new Date(),
                    sources: Math.floor(Math.random() * 8),
                    thinkingTime: (Math.floor(Math.random() * 8) + 1).toString()
                };
                setMessages(prev => [...prev, assistantMessage]);
            } else {
                const errorMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: 'Desculpe, houve um erro ao processar sua mensagem. Tente novamente.',
                    timestamp: new Date()
                };
                setMessages(prev => [...prev, errorMessage]);
            }
        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: 'Erro de conexão. Por favor, verifique sua conexão e tente novamente.',
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
            // Limpar empresas selecionadas após enviar
            setSelectedCompanies([]);
            setHasAtSymbol(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    };

    const searchCompanies = async (query: string) => {
        if (query.length < 2) {
            setCompanies([]);
            return;
        }

        setIsSearching(true);
        try {
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            const response = await fetch(`${API_BASE}/api/v1/organizations/search?q=${encodeURIComponent(query)}`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (response.ok) {
                const data = await response.json();
                setCompanies(data.results || []);
            } else {
                setCompanies([]);
            }
        } catch (error) {
            console.error('Erro ao buscar empresas:', error);
            setCompanies([]);
        } finally {
            setIsSearching(false);
        }
    };

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = e.target.value;
        setInputValue(value);

        // Roxo apenas enquanto está digitando após @ sem espaço
        const lastAtIndex = value.lastIndexOf('@');
        if (lastAtIndex !== -1) {
            const textAfterAt = value.substring(lastAtIndex + 1);
            // Se tem @ e está digitando depois dele (sem espaço) - mostrar roxo
            if (!textAfterAt.includes(' ') && textAfterAt.length > 0) {
                setHasAtSymbol(true);
                setSearchTerm(textAfterAt);
                setShowAutocomplete(true);
                searchCompanies(textAfterAt);
            } else {
                // Se completou com espaço ou só tem @, remove roxo
                setHasAtSymbol(false);
                setShowAutocomplete(false);
            }
        } else {
            setShowAutocomplete(false);
            setHasAtSymbol(false);
        }
    };

    const selectCompany = (company: CompanyResult) => {
        // Adicionar empresa aos selecionados
        if (!selectedCompanies.find(c => c.id === company.id)) {
            setSelectedCompanies([...selectedCompanies, company]);
        }

        // Completar o texto do input com o nome da empresa
        const lastAtIndex = inputValue.lastIndexOf('@');
        let newValue = inputValue;
        if (lastAtIndex !== -1) {
            const beforeAt = inputValue.substring(0, lastAtIndex);
            // Completa o nome da empresa e adiciona um espaço para continuar digitando
            newValue = beforeAt + '@' + company.name + ' ';
            setInputValue(newValue);
            // Remover roxo após seleção
            setHasAtSymbol(false);
        }

        setShowAutocomplete(false);
        setSearchTerm('');
        setCompanies([]);

        // Focus input after React processes the state update
        setTimeout(() => {
            if (inputRef.current) {
                inputRef.current.focus();
                // Move o cursor exatamente para o final, depois do espaço
                const length = inputRef.current.value.length;
                inputRef.current.setSelectionRange(length, length);
            }
        }, 10);
    };

    if (!showChat) {
        return null;
    }

    return (
        <div className={`${styles.chatPanel} ${styles[theme]}`}>
            
            {/* Cabeçalho */}
            <div className={styles.chatHeader}>
                <h2 className={styles.chatTitle}>Novo Chat</h2>
            </div>

            {/* Área de Chat com Scroll */}
            <div className={styles.messagesContainer}>
                
                {messages.map((message) => (
                    <div key={message.id}>
                        {/* Mensagens do Utilizador */}
                        {message.role === 'user' && (
                            <div className={styles.userMessageWrapper}>
                                {/* Pílulas de Empresas da Mensagem */}
                                {message.selectedCompanies && message.selectedCompanies.length > 0 && (
                                    <div className={styles.userCompaniesContainer}>
                                        {message.selectedCompanies.map((company) => (
                                            <div key={company.id} className={styles.inputContextPill}>
                                                {company.logo_url ? (
                                                    <img 
                                                        src={company.logo_url} 
                                                        alt={company.name}
                                                        className={styles.companyLogo}
                                                    />
                                                ) : (
                                                    <OrgIcon />
                                                )}
                                                <div className={styles.contextText}>
                                                    <span className={styles.contextTitle}>{company.name}</span>
                                                    <span className={styles.contextSubtitle}>Análise em progresso</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                <div className={styles.userMessage}>
                                    {message.content}
                                </div>
                            </div>
                        )}

                        {/* Mensagens do Assistente */}
                        {message.role === 'assistant' && (
                            <>
                                {message.thinkingTime && (
                                    <div className={styles.aiMetadata}>
                                        <button className={styles.thinkingBtn}>
                                            <Lightbulb size={16} className={styles.thinkingIcon} />
                                            <span>Pensou durante {message.thinkingTime} segundos</span>
                                            <ChevronRight size={14} className={styles.chevron} />
                                        </button>
                                        
                                        {message.sources && message.sources > 0 && (
                                            <div className={styles.sourcesBox}>
                                                <div className={styles.sourceIcons}>
                                                    {Array(Math.min(message.sources, 3)).fill(0).map((_, i) => (
                                                        <SourceIcon key={i} />
                                                    ))}
                                                </div>
                                                <span className={styles.sourceCount}>{message.sources} fontes</span>
                                            </div>
                                        )}
                                    </div>
                                )}

                                <div className={styles.aiMessageWrapper}>
                                    <AIAsterisk />
                                    <div className={styles.aiMessage}>
                                        {message.content}
                                    </div>
                                </div>

                                {/* Barra de Ações da IA */}
                                <div className={styles.aiActions}>
                                    <button className={styles.actionBtn} title="Copiar">
                                        <Copy size={16} strokeWidth={2} />
                                    </button>
                                    <button className={styles.actionBtn} title="Reescrever">
                                        <Wand2 size={16} strokeWidth={2} />
                                    </button>
                                    <button className={styles.actionBtn} title="Avaliar negativamente">
                                        <ThumbsDown size={16} strokeWidth={2} />
                                    </button>
                                    <button className={styles.actionBtn} title="Atualizar">
                                        <RotateCcw size={16} strokeWidth={2} />
                                    </button>
                                    
                                    <div className={styles.divider}></div>
                                    
                                    <button className={styles.customizeBtn}>
                                        <Library size={15} strokeWidth={2}/>
                                        Personalizar
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                ))}

                {isLoading && (
                    <div className={styles.aiMessageWrapper}>
                        <AIAsterisk />
                        <div className={styles.aiMessage}>
                            <Loader2 size={16} className={styles.spinner} />
                            <span>Pensando...</span>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Caixa de Entrada Fixa no Fundo */}
            <div className={styles.inputContainer}>
                <div className={styles.inputBox}>
                    
                    {/* Container relativo para autocomplete */}
                    <div className={styles.inputFieldWrapper}>
                        {/* Pílulas de Empresas Selecionadas */}
                        {selectedCompanies.length > 0 && (
                            <div className={styles.inputCompaniesContainer}>
                                {selectedCompanies.map((company) => (
                                    <div key={company.id} className={styles.inputCompanyPill}>
                                        {company.logo_url ? (
                                            <img 
                                                src={company.logo_url} 
                                                alt={company.name}
                                                className={styles.pillCompanyLogo}
                                            />
                                        ) : (
                                            <OrgIcon />
                                        )}
                                        <span className={styles.pillCompanyName}>{company.name}</span>
                                        <button
                                            className={styles.removePillBtn}
                                            onClick={() => {
                                                setSelectedCompanies(selectedCompanies.filter(c => c.id !== company.id));
                                                setTimeout(() => {
                                                    if (inputRef.current) {
                                                        inputRef.current.focus();
                                                    }
                                                }, 10);
                                            }}
                                            type="button"
                                        >
                                            <X size={14} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                        {/* Campo de Texto */}
                        <input 
                            ref={inputRef}
                            type="text" 
                            value={inputValue}
                            onChange={handleInputChange}
                            onKeyPress={handleKeyPress}
                            placeholder="Digite @ para buscar uma empresa... ou pergunte sobre sua hierarquia" 
                            className={`${styles.inputField} ${hasAtSymbol ? styles.inputFieldActive : ''}`}
                            disabled={isLoading}
                            spellCheck="false"
                            autoCorrect="off"
                            autoCapitalize="off"
                        />

                        {/* Autocomplete Dropdown */}
                        {showAutocomplete && (
                            <div 
                                ref={autocompleteRef}
                                className={styles.autocompleteDropdown}
                            >
                                {isSearching && (
                                    <div className={styles.autocompleteLoading}>
                                        <Loader2 size={16} className={styles.spinner} />
                                        Buscando empresas...
                                    </div>
                                )}
                                {!isSearching && companies.length === 0 && searchTerm.length > 0 && (
                                    <div className={styles.autocompleteEmpty}>
                                        Nenhuma empresa encontrada
                                    </div>
                                )}
                                {!isSearching && companies.length > 0 && (
                                    <div className={styles.autocompleteList}>
                                        {companies.map((company) => (
                                            <button
                                                key={company.id}
                                                className={styles.autocompleteItem}
                                                onClick={() => selectCompany(company)}
                                            >
                                                {company.logo_url ? (
                                                    <img 
                                                        src={company.logo_url} 
                                                        alt={company.name}
                                                        className={styles.autocompleteItemLogo}
                                                    />
                                                ) : (
                                                    <OrgIcon />
                                                )}
                                                <div className={styles.autocompleteItemText}>
                                                    <span className={styles.autocompleteItemName}>
                                                        {company.name}
                                                    </span>
                                                    {company.domain && (
                                                        <span className={styles.autocompleteItemDomain}>
                                                            {company.domain}
                                                        </span>
                                                    )}
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Barra Inferior da Entrada */}
                    <div className={styles.inputBottom}>
                        <div className={styles.inputLeftButtons}>
                            <button className={styles.modelBtn}>
                                <OpusIcon />
                                Opus 4.5
                            </button>
                            <span className={styles.dividerSmall}>|</span>
                            <button className={styles.addBtn} title="Adicionar">
                                <Plus size={18} strokeWidth={2.5}/>
                            </button>
                        </div>
                        <button 
                            onClick={handleSendMessage}
                            disabled={isLoading || !inputValue.trim()}
                            className={styles.sendBtn}
                            title="Enviar"
                        >
                            <ArrowUp size={16} strokeWidth={2.5}/>
                        </button>
                    </div>
                </div>
            </div>
            
        </div>
    );
};
