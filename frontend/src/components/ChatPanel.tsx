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
    Search,
    Mic,
    MicOff,
    Terminal,
    Database,
    Code2,
    CheckCircle2,
    Phone,
    Mail,
    Calendar,
    MessageSquare,
    CheckCheck,
    ChevronDown,
    Building2,
    User2,
    ExternalLink
} from 'lucide-react';
import styles from './ChatPanel.module.css';
import { TimelineEventRow, TimelineEvent } from './TimelineEventRow';
import { useSpeechToText } from '../hooks/useSpeechToText';
import { PersonaCard } from './PersonaCard';
import { CompactEmployeeCard } from './CompactEmployeeCard';
import { getAvatarUrl, getProxiedUrl, getCompanyLogoUrl } from '../utils/avatarUtils';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    sources?: number;
    thinkingTime?: string;
    selectedCompanies?: CompanyResult[];
    ui_module?: 'TaskList' | 'ContactGrid' | 'CompanyCard' | 'WhatsAppThread' | 'EmailThread' | null;
    data?: any;
    debug?: {
        intent?: any;
        data_scope?: string[];
        raw_context?: any;
        full_prompt?: string;
    };
    showDebug?: boolean;
}

interface CompanyResult {
    id: number | string;
    name: string;
    type?: 'organization' | 'whatsapp' | 'email';
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
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
}

// Ícone da IA (Gemini)
const AIAsterisk = () => (
    <img src="/gemini.png" alt="Gemini AI" width="22" height="22" className="shrink-0 mt-0.5 object-contain" />
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

// Ícone do modelo Gemini
const GeminiIcon = () => (
    <img src="/gemini.png" alt="Gemini" width="16" height="16" className="shrink-0 object-contain" />
);

const OrgIcon = () => <Building2 size={16} className="shrink-0 opacity-40" />;

// --- COMPONENTES VISUAIS PARA MÓDULOS DA IA ---

const DebugSection: React.FC<{ title: string; icon: React.ReactNode; content: string | object }> = ({ title, icon, content }) => {
    const [isOpen, setIsOpen] = useState(false);
    const contentStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);

    return (
        <div className={styles.debugSection}>
            <div className={styles.debugHeader} onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer', userSelect: 'none' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {icon}
                    <span>{title}</span>
                </div>
                <ChevronDown size={14} className={isOpen ? styles.rotated : ''} style={{ transition: 'transform 0.2s ease' }} />
            </div>
            {isOpen && (
                <pre className={styles.debugPre}>{contentStr}</pre>
            )}
        </div>
    );
};

const DebugPanel: React.FC<{ debug: any; isOpen: boolean }> = ({ debug, isOpen }) => {
    if (!isOpen || !debug) return null;
    return (
        <div className={styles.debugPanel}>
            <DebugSection
                title="Prompt Enviado"
                icon={<Terminal size={14} />}
                content={debug.full_prompt || "Nenhum prompt disponível"}
            />
            <DebugSection
                title="Dados Consultados"
                icon={<Database size={14} />}
                content={debug.raw_context}
            />
            <DebugSection
                title="Intenção Classificada"
                icon={<Code2 size={14} />}
                content={debug.intent}
            />
        </div>
    );
};

const TaskList: React.FC<{ data: any }> = ({ data }) => {
    const tasks = data?.today_tasks || data?.activities || [];
    if (!tasks.length) return <div className={styles.emptyModule}>Nenhuma tarefa encontrada.</div>;

    const getIcon = (type: string) => {
        switch (type) {
            case 'call': return <Phone size={14} />;
            case 'meeting': return <Calendar size={14} />;
            case 'email': return <Mail size={14} />;
            default: return <CheckCircle2 size={14} />;
        }
    };

    return (
        <div className={styles.moduleContainer}>

            <div className={styles.taskList} style={{ marginTop: '16px' }}>
                {tasks.map((task: any, i: number) => {
                    const event: TimelineEvent = {
                        id: task.id || i,
                        type: 'activity',
                        timestamp: task.due_date || task.add_time || '',
                        title: task.subject || 'Tarefa',
                        user: task.owner_name,
                        contact: task.person_name,
                        company: task.org_name,
                        content: task.note,
                        done: task.done === true || task.done === 1,
                        activityType: task.type,
                        icon: getIcon(task.type)
                    };
                    return (
                        <TimelineEventRow
                            key={event.id}
                            event={event}
                            isLast={true}
                            hasBackground={true}
                        />
                    );
                })}
            </div>
        </div>
    );
};

const ContactGrid: React.FC<{ data: any }> = ({ data }) => {
    const contacts = data?.decision_makers || data?.persons || [];

    if (!contacts.length) {
        // Fallback for isolated single OSINT lead
        const osint = data?.osint_result;
        if (osint && osint.lead) {
            const singlePersona = {
                name: osint.lead,
                company: osint.empresa,
                phone: osint.whatsapp?.numero || osint.pabx || osint.contatosSede,
                email: osint.emailProvavel,
                location: osint.notas || "Lead Enriquecido",
                department: "Enriquecimento OSINT"
            };
            return (
                <div className={styles.moduleContainer}>
                    <div className={styles.moduleHeader}><User2 size={16} /> <span>Contato Enriquecido</span></div>
                    <div className={styles.contactGrid} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <PersonaCard data={singlePersona} />
                    </div>
                </div>
            );
        }
        return <div className={styles.emptyModule}>Nenhum contato encontrado.</div>;
    }

    return (
        <div className={styles.moduleContainer}>
            <div className={styles.contactGrid} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {contacts.map((c: any, i: number) => (
                    <CompactEmployeeCard key={i} data={c} />
                ))}
            </div>
        </div>
    );
};


const CompanyCard: React.FC<{ data: any }> = ({ data }) => {
    const org = data?.organization;
    if (!org) return null;
    return (
        <div className={styles.moduleContainer}>
            <div className={styles.moduleHeader}><Building2 size={16} /> <span>Dados Corporativos</span></div>
            <div className={styles.companyCard}>
                <div className={styles.companyInfoRow}><strong>CNPJ:</strong> <span>{org.cnpj || 'Não informado'}</span></div>
                <div className={styles.companyInfoRow}><strong>Site:</strong> <a href={org.domain} target="_blank" rel="noreferrer">{org.domain}</a></div>
                <div className={styles.companyInfoRow}><strong>Indústria:</strong> <span>{org.industry || 'N/A'}</span></div>
            </div>
        </div>
    );
};

const WhatsAppThread: React.FC<{ data: any, onOpenWhatsApp?: (info: { name: string, id?: string }) => void }> = ({ data, onOpenWhatsApp }) => {
    const waResult = data?.whatsapp_result || {};
    const action = waResult.whatsapp_action;
    const contact = waResult.contact || waResult.resolved_contact;
    const sentMessage = waResult.sent_message;

    // Se for uma confirmação de mensagem enviada, mostra o preview (miniatura)
    if (action === 'send_message' || action === 'send') {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return (
            <div className={styles.moduleContainer}>
                <div className={styles.waPreviewCard}>
                    <div className={styles.waPreviewHeader}>
                        <div className={styles.waAvatarSmall}>
                            {waResult.contact_picture ? (
                                <img src={waResult.contact_picture} alt="Avatar" className={styles.waAvatarImg} />
                            ) : contact?.profilePicture ? (
                                <img src={contact.profilePicture} alt="Avatar" className={styles.waAvatarImg} />
                            ) : (
                                <User2 size={20} color="#adb5bd" />
                            )}
                        </div>
                        <div className={styles.waPreviewInfo}>
                            <div className={styles.waPreviewName}>{contact?.name || 'Contato'}</div>
                            <div className={styles.waPreviewStatus}>visto por último hoje às {time}</div>
                        </div>
                        <div className={styles.waLinkIcon} onClick={() => {
                            if (onOpenWhatsApp) {
                                onOpenWhatsApp({ name: contact?.name || 'WhatsApp', id: contact?.id });
                            } else {
                                window.open(`/whatsapp?chatId=${contact?.id || ''}`, '_blank');
                            }
                        }}>
                            <ExternalLink size={14} />
                        </div>
                    </div>
                    <div className={styles.waPreviewBubble}>
                        <div className={styles.waPreviewText}>{sentMessage}</div>
                        <div className={styles.waPreviewTime}>
                            {time}
                            <div className={styles.waChecks}>
                                <CheckCheck size={14} />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    const result = waResult.resultado || {};
    const messages = result.messages || [];
    if (!messages.length) return <div className={styles.emptyModule}>Sem histórico de mensagens.</div>;
    return (
        <div className={styles.moduleContainer}>
            <div className={styles.moduleHeader}><MessageSquare size={16} /> <span>Conversa WhatsApp</span></div>
            <div className={styles.waThread}>
                {messages.slice(-5).map((m: any, i: number) => (
                    <div key={i} className={`${styles.waBubble} ${m.fromMe ? styles.me : styles.them}`}>
                        <div className={styles.waText}>{m.body}</div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const EmailThread: React.FC<{ data: any }> = ({ data }) => {
    const emailResult = data?.email_result || {};
    const action = emailResult.email_action || data?.email_action;
    const contact = emailResult.contact || emailResult.resolved_contact || {};
    const sentMessage = emailResult.sent_message || emailResult.body_preview || "";
    const subject = emailResult.subject || "Sem Assunto";
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Se for uma confirmação de email enviado, mostra o preview (miniatura)
    return (
        <div className={styles.moduleContainer}>
            <div className={styles.emailPreviewCard}>
                <div className={styles.emailPreviewHeader}>
                    <div className={styles.emailAvatarSmall}>
                        {contact.profilePicture || contact.avatar_url ? (
                            <img src={getProxiedUrl(contact.profilePicture || contact.avatar_url)} alt="Avatar" className={styles.waAvatarImg} />
                        ) : (
                            <div className={styles.emailInitials}>
                                {(contact.name || 'D').charAt(0).toUpperCase()}
                            </div>
                        )}
                        <div className={styles.outlookBadge}>
                            <Mail size={10} color="white" fill="white" />
                        </div>
                    </div>
                    <div className={styles.emailPreviewInfo}>
                        <div className={styles.emailPreviewRecipient}>{contact.name || contact.email || 'Destinatário'}</div>
                        <div className={styles.emailPreviewSnippet}>{subject}</div>
                    </div>
                    <div className={styles.emailExternalIcon}>
                         <ExternalLink size={14} />
                    </div>
                </div>
                <div className={styles.emailPreviewBody}>
                    <div className={styles.emailBodyText}>{sentMessage}</div>
                    <div className={styles.emailPreviewMeta}>
                        <div className={styles.emailSentStatus}>
                            <CheckCheck size={14} />
                            <span>Enviado via Outlook</span>
                        </div>
                        <div className={styles.emailTime}>{time}</div>
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- FIM DOS COMPONENTES VISUAIS ---

export const ChatPanel: React.FC<ChatPanelProps> = ({
    showChat,
    setShowChat,
    selectedOrgId,
    selectedOrgName = 'Organização',
    theme = 'light',
    onToggleTheme,
    onOpenWhatsApp
}) => {
    const { isListening, transcript, startListening, stopListening } = useSpeechToText();
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

    useEffect(() => {
        if (transcript) {
            setInputValue(prev => prev + (prev ? ' ' : '') + transcript);
        }
    }, [transcript]);

    const handleMicClick = () => {
        if (isListening) {
            stopListening();
        } else {
            startListening();
        }
    };
    const [isLoading, setIsLoading] = useState(false);
    const [showAutocomplete, setShowAutocomplete] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [companies, setCompanies] = useState<any[]>([]);
    const [selectedCompanies, setSelectedCompanies] = useState<any[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [searchingCategory, setSearchingCategory] = useState<string | null>(null);
    const lastSearchId = useRef(0);
    const [hasAtSymbol, setHasAtSymbol] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const autocompleteRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const highlighterRef = useRef<HTMLDivElement>(null);

    // Sincroniza o scroll do highlight com o input
    const handleScroll = () => {
        if (inputRef.current && highlighterRef.current) {
            highlighterRef.current.scrollTop = inputRef.current.scrollTop;
            highlighterRef.current.scrollLeft = inputRef.current.scrollLeft;
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleCopy = (content: string) => {
        navigator.clipboard.writeText(content);
        // Pode adicionar um toast de sucesso aqui se quiser
    };

    const handleReload = async (index: number) => {
        // Encontrar a última mensagem do usuário antes desta do assistente
        let lastUserMessageIndex = -1;
        for (let i = index - 1; i >= 0; i--) {
            if (messages[i].role === 'user') {
                lastUserMessageIndex = i;
                break;
            }
        }

        if (lastUserMessageIndex === -1) return;

        const userMsg = messages[lastUserMessageIndex];

        // Remove a mensagem atual do assistente (e possivelmente tudo depois dela para manter consistência)
        const updatedMessages = messages.slice(0, lastUserMessageIndex + 1);
        setMessages(updatedMessages);
        setIsLoading(true);

        try {
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            const response = await fetch(`${API_BASE}/api/v1/ai/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMsg.content,
                    orgId: selectedOrgId,
                    selectedCompanies: userMsg.selectedCompanies ? userMsg.selectedCompanies.map(c => ({ id: c.id, name: c.name })) : undefined,
                    context: 'hierarchy_analysis',
                    history: updatedMessages.slice(-6).map(m => ({ role: m.role, content: m.content }))
                })
            });

            if (response.ok) {
                const data = await response.json();
                const assistantMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: data.response,
                    timestamp: new Date()
                };
                setMessages(prev => [...prev, assistantMessage]);
            } else {
                console.error("Erro na resposta da IA:", response.status);
            }
        } catch (error) {
            console.error("Erro ao chamar API de chat:", error);
        } finally {
            setIsLoading(false);
        }
    };

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
        setSelectedCompanies([]); // Limpar as pílulas após enviar
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
                    context: 'hierarchy_analysis',
                    history: messages.slice(-6).map(m => ({ role: m.role, content: m.content }))
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
                    thinkingTime: (Math.floor(Math.random() * 8) + 1).toString(),
                    ui_module: data.ui_module,
                    data: data.data,
                    debug: data.debug
                };
                setMessages(prev => [...prev, assistantMessage]);
            }
            else {
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

    const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    };

    const searchUniversal = async (query: string) => {
        if (query.length < 1) {
            setCompanies([]);
            return;
        }

        const searchId = ++lastSearchId.current;
        setIsSearching(true);
        try {
            let searchType = undefined;
            let cleanQuery = query;

            // Identifica prefixos: @empresa, @contato, @nome, @email
            const lowerQuery = query.toLowerCase();
            
            if (lowerQuery.startsWith('empresa')) {
                searchType = 'organization';
                cleanQuery = query.substring(7).trim();
                setSearchingCategory('empresas');
            } else if (lowerQuery.startsWith('contato')) {
                searchType = 'whatsapp';
                cleanQuery = query.substring(7).trim();
                setSearchingCategory('contatos');
            } else if (lowerQuery.startsWith('nome')) {
                searchType = 'whatsapp';
                cleanQuery = query.substring(4).trim();
                setSearchingCategory('contatos');
            } else if (lowerQuery.startsWith('email')) {
                searchType = 'email';
                cleanQuery = query.substring(5).trim();
                setSearchingCategory('emails');
            } else {
                setSearchingCategory(null);
            }

            // Se o usuário digitou apenas o prefixo (ex: "@email"), não buscamos nada ainda para não poluir
            if (!cleanQuery && searchType && query.length > 2) {
                setCompanies([]);
                setIsSearching(false);
                return;
            }

            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            let url = `${API_BASE}/api/v1/search/universal?q=${encodeURIComponent(cleanQuery)}`;
            if (searchType) {
                url += `&type=${searchType}`;
            }

            const response = await fetch(url, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });

            if (searchId !== lastSearchId.current) return;

            if (response.ok) {
                const data = await response.json();
                if (data.results) {
                    setCompanies(data.results || []);
                } else {
                    setCompanies([]);
                }
            } else {
                setCompanies([]);
            }
        } catch (error) {
            console.error('Erro na busca universal:', error);
            if (searchId === lastSearchId.current) {
                setCompanies([]);
            }
        } finally {
            if (searchId === lastSearchId.current) {
                setIsSearching(false);
            }
        }
    };

    useEffect(() => {
        if (inputRef.current) {
            inputRef.current.style.height = 'auto';
            const newHeight = Math.min(inputRef.current.scrollHeight, 95); // Ajustado para ~3 linhas
            inputRef.current.style.height = `${newHeight}px`;
            
            // Sincroniza o highlighter
            if (highlighterRef.current) {
                highlighterRef.current.style.height = `${newHeight}px`;
            }
        }
    }, [inputValue]);

    const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const value = e.target.value;
        setInputValue(value);
        
        // Sincronizar pílulas: se o usuário apagou o texto "@Nome", remove a pílula correspondente
        if (selectedCompanies.length > 0) {
            const updatedCompanies = selectedCompanies.filter(company => {
                const mentionText = `@${company.name}`;
                return value.includes(mentionText);
            });
            if (updatedCompanies.length !== selectedCompanies.length) {
                setSelectedCompanies(updatedCompanies);
            }
        }

        // Encontra o último @ para decidir se mostra autocomplete
        const lastAtIndex = value.lastIndexOf('@');
        if (lastAtIndex !== -1) {
            const textSinceAt = value.substring(lastAtIndex + 1);
            const lowerText = textSinceAt.toLowerCase();
            
            // Detecta se o usuário está começando a digitar um prefixo ou se já escolheu um
            const isTypingPrefix = ['empresa', 'contato', 'email', 'nome'].some(p => p.startsWith(lowerText) && lowerText.length > 0);
            const hasChosenPrefix = lowerText.startsWith('empresa') || 
                                   lowerText.startsWith('contato') || 
                                   lowerText.startsWith('nome') || 
                                   lowerText.startsWith('email');

            if (lowerText.length === 0 || isTypingPrefix || hasChosenPrefix) {
                setHasAtSymbol(true);
                setSearchTerm(textSinceAt);
                setShowAutocomplete(true);
                searchUniversal(textSinceAt);
            } else {
                // Se começou com @, sempre mostra o autocomplete e tenta buscar, 
                // a menos que tenha espaços e NÃO seja um prefixo conhecido (fim da menção)
                const isGeneralMention = !hasChosenPrefix && textSinceAt.includes(' ');
                
                if (isGeneralMention) {
                    setShowAutocomplete(false);
                } else {
                    setHasAtSymbol(true);
                    setSearchTerm(textSinceAt);
                    setShowAutocomplete(true);
                    searchUniversal(textSinceAt);
                }
            }
        } else {
            setShowAutocomplete(false);
            setHasAtSymbol(false);
        }
    };

    const selectSearchResult = (item: any) => {
        // Adicionar à lista de contextos selecionados (pílulas)
        if (!selectedCompanies.find(c => c.id === item.id)) {
            setSelectedCompanies([...selectedCompanies, item]);
        }

        // Completar o texto do input com o nome
        const lastAtIndex = inputValue.lastIndexOf('@');
        let newValue = inputValue;
        if (lastAtIndex !== -1) {
            const beforeAt = inputValue.substring(0, lastAtIndex);
            // Mostra o nome e prepara o espaço
            newValue = beforeAt + '@' + item.name + ' ';
            setInputValue(newValue);
            setHasAtSymbol(false);
        }

        setShowAutocomplete(false);
        setSearchTerm('');
        setCompanies([]);

        setTimeout(() => {
            if (inputRef.current) {
                inputRef.current.focus();
                const length = inputRef.current.value.length;
                inputRef.current.setSelectionRange(length, length);
            }
        }, 10);
    };

    const getAvatarUrl = (item: any): string | null => {
        if (!item) return null;
        if (item.avatar_url) return item.avatar_url;
        if (item.email) return `https://unavatar.io/${item.email}`;
        return null;
    };

    const getInitials = (name: string): string => {
        if (!name) return '';
        const parts = name.trim().split(/\s+/);
        if (parts.length === 0) return '';
        if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    };

    const renderHighlightedText = (text: string) => {
        if (!text) return null;
        
        // 1. Criamos um array com os nomes das empresas/contatos selecionados para destaque total
        const selectedNames = selectedCompanies.map(c => `@${c.name}`);
        
        // 2. Regex que prioriza os nomes selecionados (com espaços) e depois os prefixos simples
        // Ordenamos por tamanho (maior primeiro) para evitar que @João pegue antes de @João Luccas
        const sortedNames = [...selectedNames].sort((a, b) => b.length - a.length);
        const escapedNames = sortedNames.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
        
        // A regex busca: nomes selecionados OU qualquer @seguido_de_letras (prefixo)
        const pattern = escapedNames.length > 0 
            ? `(^|\\s)(${escapedNames.join('|')}|@\\S+)`
            : `(^|\\s)(@\\S+)`;
            
        const parts = text.split(new RegExp(pattern, 'g'));
        
        const result: React.ReactNode[] = [];
        for (let i = 0; i < parts.length; i++) {
            // Com dois grupos de captura, partes[i] segue o padrão:
            // i % 3 == 0 -> Texto comum
            // i % 3 == 1 -> O espaço/início capturado pelo primeiro grupo (^|\s)
            // i % 3 == 2 -> O nome/tag capturado pelo segundo grupo
            
            if (i % 3 === 0) {
                if (parts[i]) result.push(<span key={i}>{parts[i]}</span>);
            } else if (i % 3 === 1) {
                if (parts[i]) result.push(<span key={i}>{parts[i]}</span>); // Adiciona o espaço preservado
            } else {
                const partWithAt = parts[i];
                if (!partWithAt) continue;
                
                const isSelected = selectedNames.includes(partWithAt);
                const isPrefix = ['@empresa', '@contato', '@email', '@nome'].some(p => partWithAt.toLowerCase().startsWith(p));
                
                result.push(
                    <span 
                        key={i} 
                        className={(isSelected || isPrefix) ? styles.highlightPurple : undefined}
                        style={(isSelected || isPrefix) ? { color: '#5E6AD2', fontWeight: 600 } : undefined}
                    >
                        {partWithAt}
                    </span>
                );
            }
        }
        return result;
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

                {messages.map((message, index) => (
                    <div key={message.id}>
                        {/* Mensagens do Utilizador */}
                        {message.role === 'user' && (
                            <div className={styles.userMessageWrapper}>
                                {/* Pílulas de Empresas da Mensagem */}
                                {message.selectedCompanies && message.selectedCompanies.length > 0 && (
                                    <div className={styles.userCompaniesContainer}>
                                        {message.selectedCompanies.map((company) => (
                                            <div key={company.id} className={styles.inputContextPill}>
                                                {company.type === 'organization' ? (
                                                    getCompanyLogoUrl(company) ? (
                                                        <img
                                                            src={getProxiedUrl(getCompanyLogoUrl(company))}
                                                            alt={company.name}
                                                            className={styles.companyLogo}
                                                            onError={(e) => {
                                                                (e.target as HTMLImageElement).src = ''; 
                                                                (e.target as HTMLImageElement).style.display = 'none';
                                                            }}
                                                        />
                                                    ) : <OrgIcon />
                                                ) : (
                                                    getAvatarUrl(company) ? (
                                                        <img
                                                            src={getProxiedUrl(getAvatarUrl(company))}
                                                            alt={company.name}
                                                            className={styles.companyLogo}
                                                            style={{ borderRadius: '50%' }}
                                                            onError={(e) => {
                                                                (e.target as HTMLImageElement).style.display = 'none';
                                                            }}
                                                        />
                                                    ) : (company.type === 'whatsapp' ? <MessageSquare size={16} color="#25D366" /> : <Mail size={16} color="#0078d4" />)
                                                )}
                                                <div className={styles.contextText}>
                                                    <span className={styles.contextTitle}>{company.name}</span>
                                                    <span className={styles.contextSubtitle}>
                                                        {company.type === 'whatsapp' ? 'Contato WhatsApp' : 
                                                         company.type === 'email' ? 'Contato Outlook' : 
                                                         'Inteligência Corporativa'}
                                                    </span>
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
                            <div className={styles.assistantMessageGroup}>
                                {message.thinkingTime && (
                                    <div className={styles.aiMetadata}>
                                        <button className={styles.thinkingBtn} onClick={() => {
                                            const newMessages = [...messages];
                                            newMessages[index].showDebug = !newMessages[index].showDebug;
                                            setMessages(newMessages);
                                        }}>
                                            <Lightbulb size={16} className={styles.thinkingIcon} />
                                            <span>Pensou durante {message.thinkingTime} segundos</span>
                                            <ChevronDown size={14} className={`${styles.chevron} ${message.showDebug ? styles.rotated : ''}`} />
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

                                <DebugPanel debug={message.debug} isOpen={!!message.showDebug} />

                                <div className={styles.aiMessageWrapper}>
                                    <AIAsterisk />
                                    <div className={styles.aiMessageContainer}>
                                        <div className={styles.aiMessage}>
                                            {message.content}
                                        </div>

                                        {/* RENDERIZAÇÃO DE MÓDULOS VISUAIS */}
                                        {message.ui_module === 'TaskList' && <TaskList data={message.data} />}
                                        {message.ui_module === 'ContactGrid' && <ContactGrid data={message.data} />}
                                        {message.ui_module === 'CompanyCard' && <CompanyCard data={message.data} />}
                                        {message.ui_module === 'WhatsAppThread' && <WhatsAppThread data={message.data} onOpenWhatsApp={onOpenWhatsApp} />}
                                        {message.ui_module === 'EmailThread' && <EmailThread data={message.data} />}
                                    </div>
                                </div>

                                {/* Barra de Ações da IA */}
                                <div className={styles.aiActions}>
                                    <button className={styles.actionBtn} title="Copiar" onClick={() => handleCopy(message.content)}>
                                        <Copy size={16} strokeWidth={2} />
                                    </button>
                                    <button className={styles.actionBtn} title="Debug/Prompt" onClick={() => {
                                        const newMessages = [...messages];
                                        newMessages[index].showDebug = !newMessages[index].showDebug;
                                        setMessages(newMessages);
                                    }}>
                                        <Terminal size={16} strokeWidth={2} />
                                    </button>
                                    <button className={styles.actionBtn} title="Avaliar negativamente">
                                        <ThumbsDown size={16} strokeWidth={2} />
                                    </button>
                                    <button className={styles.actionBtn} title="Atualizar" onClick={() => handleReload(index)}>
                                        <RotateCcw size={16} strokeWidth={2} />
                                    </button>

                                    <div className={styles.divider}></div>

                                    <button className={styles.customizeBtn}>
                                        <Library size={15} strokeWidth={2} />
                                        Personalizar
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                ))}

                {isLoading && (
                    <div className={styles.aiMessageWrapper}>
                        <AIAsterisk />
                        <div className={styles.aiMessage} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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
                                        {company.type === 'organization' ? (
                                            getCompanyLogoUrl(company) ? <img src={getProxiedUrl(getCompanyLogoUrl(company))} className={styles.pillCompanyLogo} onError={(e) => (e.target as HTMLImageElement).style.display='none'} /> : <OrgIcon />
                                        ) : (
                                            getAvatarUrl(company) ? <img src={getProxiedUrl(getAvatarUrl(company))} className={styles.pillCompanyLogo} style={{ borderRadius: '50%' }} onError={(e) => (e.target as HTMLImageElement).style.display='none'} /> : 
                                            (company.type === 'whatsapp' ? <MessageSquare size={14} color="#25D366" /> : <Mail size={14} color="#0078d4" />)
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
                        <div className={styles.inputBoxInterior}>
                            {/* Overlay de Destaque (Fica atrás do input) */}
                            <div className={styles.inputHighlighter} ref={highlighterRef}>
                                {renderHighlightedText(inputValue)}
                                {inputValue.endsWith(' ') && <span style={{ visibility: 'hidden' }}>&nbsp;</span>}
                            </div>

                            {/* Campo de Texto Real (Textarea para multiline) */}
                            <textarea
                                ref={inputRef}
                                value={inputValue}
                                onChange={handleInputChange}
                                onScroll={handleScroll}
                                onKeyDown={handleKeyPress}
                                placeholder="Digite @ para buscar uma empresa..."
                                className={styles.inputField}
                                disabled={isLoading}
                                spellCheck="false"
                                autoComplete="off"
                                autoCorrect="off"
                                autoCapitalize="off"
                                rows={1}
                            />
                        </div>

                        {/* Autocomplete Dropdown */}
                        {showAutocomplete && (
                            <div
                                ref={autocompleteRef}
                                className={styles.autocompleteDropdown}
                            >
                                {isSearching && (
                                    <div className={styles.autocompleteLoading}>
                                        <Loader2 size={16} className={styles.spinner} />
                                        Buscando {searchingCategory || 'empresas'}...
                                    </div>
                                )}
                                {!isSearching && companies.length === 0 && searchTerm.length > 0 && !(['empresa', 'contato', 'nome', 'email'].some(p => searchTerm.toLowerCase().trim() === p)) && (
                                    <div className={styles.autocompleteEmpty}>
                                        Nenhum resultado encontrado
                                    </div>
                                )}
                                {!isSearching && companies.length > 0 && (
                                    <div className={styles.autocompleteList}>
                                        {companies.map((item, index) => (
                                            <button
                                                key={`${item.type}-${item.id}-${index}`}
                                                className={styles.autocompleteItem}
                                                onClick={() => selectSearchResult(item)}
                                            >
                                                <div className={styles.itemIcon}>
                                                    {item.type === 'organization' && (
                                                        getCompanyLogoUrl(item) ? (
                                                            <div className={styles.avatarWrapper}>
                                                                <img 
                                                                    src={getProxiedUrl(getCompanyLogoUrl(item))} 
                                                                    className={styles.itemAvatar}
                                                                    style={{ borderRadius: '4px' }}
                                                                    onError={(e) => {
                                                                        (e.target as HTMLImageElement).style.display = 'none';
                                                                        const next = (e.target as HTMLElement).nextElementSibling as HTMLElement;
                                                                        if (next) next.style.display = 'flex';
                                                                    }}
                                                                />
                                                                <div className={`${styles.initialsAvatar} ${styles.square}`} style={{ display: 'none', borderRadius: '4px' }}>
                                                                    {getInitials(item.name)}
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <div className={`${styles.initialsAvatar} ${styles.square}`} style={{ borderRadius: '4px' }}>
                                                                {getInitials(item.name)}
                                                            </div>
                                                        )
                                                    )}
                                                    {item.type === 'whatsapp' && <MessageSquare size={16} color="#25D366" />}
                                                    {item.type === 'email' && (
                                                        getAvatarUrl(item) ? (
                                                            <div className={styles.avatarWrapper}>
                                                                <img 
                                                                    src={getProxiedUrl(getAvatarUrl(item))} 
                                                                    className={styles.itemAvatar}
                                                                    onError={(e) => {
                                                                        (e.target as HTMLImageElement).style.display = 'none';
                                                                        const next = (e.target as HTMLElement).nextElementSibling as HTMLElement;
                                                                        if (next) next.style.display = 'flex';
                                                                    }}
                                                                />
                                                                <div className={styles.initialsAvatar} style={{ display: 'none' }}>
                                                                    {getInitials(item.name || item.email)}
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <div className={styles.initialsAvatar}>
                                                                {getInitials(item.name || item.email)}
                                                            </div>
                                                        )
                                                    )}
                                                </div>
                                                <div className={styles.itemInfo}>
                                                    <span className={styles.itemName}>{item.name}</span>
                                                    <span className={styles.itemType}>
                                                        {item.type === 'organization' ? (item.domain || 'Empresa') : 
                                                         item.type === 'whatsapp' ? (item.number || 'WhatsApp') : 
                                                         (item.email || 'Email (Outlook)')}
                                                    </span>
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
                                <GeminiIcon />
                                Gemini 2.5 Flash
                            </button>
                            <span className={styles.dividerSmall}>|</span>
                            <button className={styles.addBtn} title="Adicionar">
                                <Plus size={18} strokeWidth={2.5} />
                            </button>
                            <button
                                className={`${styles.micBtn} ${isListening ? styles.micBtnActive : ''}`}
                                onClick={handleMicClick}
                                title={isListening ? "Parar de ouvir" : "Digitar por voz"}
                                type="button"
                            >
                                {isListening ? <MicOff size={18} /> : <Mic size={18} />}
                            </button>
                        </div>
                        <button
                            onClick={handleSendMessage}
                            disabled={isLoading || !inputValue.trim()}
                            className={styles.sendBtn}
                            title="Enviar"
                        >
                            <ArrowUp size={16} strokeWidth={2.5} />
                        </button>
                    </div>
                </div>
            </div>

        </div>
    );
};
