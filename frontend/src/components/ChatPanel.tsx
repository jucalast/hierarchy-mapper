import React, { useState, useRef, useEffect } from 'react';
import { Loader2, ChevronDown } from 'lucide-react';
import styles from './ChatPanel.module.css';

// Novas interfaces compartilhadas
import { Message, CompanyResult, ApprovalAction } from './chat/ChatInterfaces';

// Sub-componentes Modularizados
import { ChatHeader } from './chat/ChatHeader';
import { ChatInput } from './chat/ChatInput';
import { ChatMessage } from './chat/ChatMessage';
import { DebugPanel } from './chat/DebugPanel';

import { useSpeechToText } from '../hooks/useSpeechToText';

const GeminiIcon = () => (
    <img src="/gemini.png" alt="Gemini" width="16" height="16" className="shrink-0 object-contain" />
);

interface ChatPanelProps {
    showChat: boolean;
    setShowChat: (show: boolean) => void;
    selectedOrgId?: number | null;
    selectedOrgName?: string;
    theme?: string;
    onToggleTheme?: () => void;
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
}

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
    
    // Estados do Chat
    const [messages, setMessages] = useState<Message[]>([
        {
            id: '1',
            role: 'assistant',
            content: `Olá! Sou seu assistente de IA. Como posso ajudá-lo com a análise da @${selectedOrgName}?`,
            timestamp: new Date()
        }
    ]);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [selectedCompanies, setSelectedCompanies] = useState<CompanyResult[]>([]);
    const [currentLogs, setCurrentLogs] = useState<string[]>([]);
    const [approvalStatuses, setApprovalStatuses] = useState<Record<string, 'pending' | 'approving' | 'approved' | 'rejected'>>({});
    const [model, setModel] = useState<'gemini' | 'groq'>('gemini');
    const [isThinkingExpanded, setIsThinkingExpanded] = useState(true);

    // Estados de Autocomplete
    const [showAutocomplete, setShowAutocomplete] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [companies, setCompanies] = useState<CompanyResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [searchingCategory, setSearchingCategory] = useState<string | null>(null);
    const lastSearchId = useRef(0);

    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Efeitos
    useEffect(() => {
        if (transcript) {
            setInputValue(prev => prev + transcript);
        }
    }, [transcript]);

    // Função para rolar até o fim
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, currentLogs]);

    // Handlers
    const handleInputChange = (val: string) => {
        setInputValue(val);
        const lastAtIndex = val.lastIndexOf('@');
        if (lastAtIndex !== -1) {
            let query = val.substring(lastAtIndex + 1);
            
            // Se o que vem após o @ já é exatamente um dos nomes selecionados, 
            // paramos de pesquisar para este @ específico até que apareça outro @.
            const matchedSelection = selectedCompanies.find(c => query.toLowerCase().startsWith(c.name.toLowerCase()));
            if (matchedSelection) {
                const afterName = query.substring(matchedSelection.name.length);
                if (afterName.length > 0) {
                    setShowAutocomplete(false);
                    return;
                }
            }

            // Lógica para tratar categorias (@contato -> whatsapp, @email -> email)
            const categoryMatch = query.match(/^(contato|email|empresa|cnpj|lead)\s+(.*)/i);
            if (categoryMatch) {
                let category = categoryMatch[1].toLowerCase();
                const actualSearch = categoryMatch[2];
                
                if (category === 'contato') category = 'whatsapp';
                
                setSearchingCategory(category);
                setSearchTerm(actualSearch);
                setShowAutocomplete(true);
                searchUniversal(actualSearch, category);
                return;
            }

            if (query.trim().length > 0 && query.length < 30) {
                setSearchTerm(query);
                setShowAutocomplete(true);
                setSearchingCategory(null);
                searchUniversal(query);
            } else {
                setShowAutocomplete(false);
            }
            return;
        }
        setShowAutocomplete(false);
    };

    const handleSendMessage = async (text: string, companiesSelected: CompanyResult[]) => {
        if (!text.trim() && companiesSelected.length === 0) return;

        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date(),
            selectedCompanies: companiesSelected.length > 0 ? [...companiesSelected] : undefined
        };

        setMessages(prev => [...prev, userMessage]);
        setInputValue('');
        setSelectedCompanies([]);
        setIsLoading(true);
        setCurrentLogs([]);

        try {
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            const response = await fetch(`${API_BASE}/api/v1/ai/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMessage.content,
                    orgId: selectedOrgId,
                    selectedCompanies: companiesSelected,
                    context: 'hierarchy_analysis',
                    model: model,
                    history: messages.slice(-6).map(m => ({ role: m.role, content: m.content }))
                })
            });

            if (response.ok) {
                const contentType = response.headers.get('content-type');
                if (contentType?.includes('application/x-ndjson') && response.body) {
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    const sessionLogs: string[] = [];

                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop() || '';

                        for (const line of lines) {
                            if (!line.trim()) continue;
                            try {
                                const chunk = JSON.parse(line);
                                if (chunk.type === 'log') {
                                    sessionLogs.push(chunk.content);
                                    setCurrentLogs([...sessionLogs]);
                                } else if (chunk.type === 'final') {
                                    const assistantMessage: Message = {
                                        id: (Date.now() + 1).toString(),
                                        role: 'assistant',
                                        content: chunk.response || 'Finalizado.',
                                        timestamp: new Date(),
                                        ui_module: chunk.ui_module,
                                        data: chunk.data,
                                        logs: [...sessionLogs],
                                        pending_approvals: chunk.data?.pending_approvals || []
                                    };
                                    setMessages(prev => [...prev, assistantMessage]);
                                }
                            } catch (e) { console.error(e); }
                        }
                    }
                } else {
                    const data = await response.json();
                    setMessages(prev => [...prev, {
                        id: (Date.now() + 1).toString(),
                        role: 'assistant',
                        content: data.response,
                        timestamp: new Date(),
                        ui_module: data.ui_module,
                        data: data.data
                    }]);
                }
            }
        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleApproveAction = async (actionId: string) => {
        const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
        setApprovalStatuses(prev => ({ ...prev, [actionId]: 'approving' }));
        try {
            const resp = await fetch(`${API_BASE}/api/v1/ai/agent-action`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_id: actionId, approved: true })
            });
            setApprovalStatuses(prev => ({ ...prev, [actionId]: resp.ok ? 'approved' : 'pending' }));
        } catch { setApprovalStatuses(prev => ({ ...prev, [actionId]: 'pending' })); }
    };

    const handleRejectAction = async (actionId: string) => {
        const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
        setApprovalStatuses(prev => ({ ...prev, [actionId]: 'rejected' }));
        try {
            await fetch(`${API_BASE}/api/v1/ai/agent-action`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_id: actionId, approved: false })
            });
        } catch { }
    };

    const searchUniversal = async (query: string, category: string | null = null) => {
        if (query.length < 1) { setCompanies([]); return; }
        const searchId = ++lastSearchId.current;
        setIsSearching(true);
        try {
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            // Chamada para o backend com suporte a tipo específico (whatsapp, email, etc.)
            let url = `${API_BASE}/api/v1/search/universal?q=${encodeURIComponent(query)}`;
            if (category) {
                url += `&type=${category}`;
            }
            
            const response = await fetch(url);
            if (searchId === lastSearchId.current && response.ok) {
                const data = await response.json();
                let results = data.results || [];
                
                // Filtro rigoroso no frontend baseado no gatilho utilizado (@contato ou @email)
                if (category) {
                    results = results.filter((item: any) => {
                        if (category === 'whatsapp') return item.type === 'whatsapp';
                        if (category === 'email') return item.type === 'email';
                        return true;
                    });
                }
                
                setCompanies(results);
            }
        } catch { } finally { if (searchId === lastSearchId.current) setIsSearching(false); }
    };

    if (!showChat) return null;

    return (
        <div className={`${styles.chatPanel} ${styles[theme]}`} data-theme={theme}>
            <ChatHeader theme={theme} onToggleTheme={onToggleTheme} onClose={() => setShowChat(false)} />

            <div className={styles.messagesContainer}>
                {messages.map((message) => (
                    <ChatMessage 
                        key={message.id} 
                        message={message} 
                        onApprove={handleApproveAction}
                        onReject={handleRejectAction}
                        onOpenWhatsApp={onOpenWhatsApp}
                        approvalStatuses={approvalStatuses}
                    />
                ))}
                
                {/* Container de Pensamentos Ativos (Acordeon idêntico ao ChatMessage) */}
                {isLoading && (
                    <div className={styles.activeThinkingContainer} style={{ padding: '0 16px', marginBottom: '20px' }}>
                        <div className={styles.debugCard}>
                            <button 
                                className={styles.debugHeader}
                                onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
                                style={{ cursor: 'pointer', background: 'none', border: 'none', width: '100%', outline: 'none' }}
                            >
                                <div className="flex items-center gap-2">
                                    <GeminiIcon /> 
                                    <span>{isThinkingExpanded ? 'Esconder Pensamento' : 'Ver Pensamento da IA'}</span>
                                </div>
                                <ChevronDown 
                                    size={14} 
                                    style={{ 
                                        transform: isThinkingExpanded ? 'none' : 'rotate(-90deg)', 
                                        transition: 'transform 0.2s' 
                                    }} 
                                />
                            </button>
                            
                            {isThinkingExpanded && (
                                <div className={styles.streamingLogs}>
                                    {currentLogs.length === 0 ? (
                                        <div className={styles.logLine}>
                                            <Loader2 size={12} className={styles.spinner} /> <span>Iniciando pipeline...</span>
                                        </div>
                                    ) : (
                                        currentLogs.map((log, i) => (
                                            <div key={i} className={styles.logLine}>
                                                <Loader2 size={12} className={styles.spinner} /> <span>{log}</span>
                                            </div>
                                        ))
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}
                
                <div ref={messagesEndRef} />
            </div>

            <ChatInput 
                inputValue={inputValue}
                setInputValue={handleInputChange}
                isLoading={isLoading}
                onSend={handleSendMessage}
                selectedCompanies={selectedCompanies}
                setSelectedCompanies={setSelectedCompanies}
                model={model}
                setModel={setModel}
                showAutocomplete={showAutocomplete}
                isSearching={isSearching}
                searchingCategory={searchingCategory}
                searchTerm={searchTerm}
                companies={companies}
                selectSearchResult={(item) => {
                    if (!selectedCompanies.find(c => c.id === item.id)) {
                        setSelectedCompanies([...selectedCompanies, item]);
                    }
                    const lastAtIndex = inputValue.lastIndexOf('@');
                    if (lastAtIndex !== -1) {
                        setInputValue(inputValue.substring(0, lastAtIndex) + '@' + item.name + ' ');
                    }
                    setShowAutocomplete(false);
                }}
                isListening={isListening}
                startListening={startListening}
                stopListening={stopListening}
                theme={theme}
            />
        </div>
    );
};
