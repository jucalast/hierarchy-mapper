import React, { useEffect, useState, useRef } from 'react';
import { 
    ChevronLeft,
    ChevronDown, 
    Save, 
    RefreshCw, 
    Cpu, 
    Settings2, 
    Database, 
    Activity, 
    AlertTriangle, 
    CheckCircle2, 
    Zap,
    Sparkles,
    Briefcase,
    Package,
    Users,
    Flame,
    Target,
    GitFork,
    Plus,
    Trash2,
    Edit3,
    X
} from 'lucide-react';
import { ai } from '@/services/api';
import styles from './PreferencesView.module.css';

interface PreferencesViewProps {
    onBack: () => void;
}

interface QuotaModelDetail {
    limit: number;
    remaining: number;
    used: number;
    pct: number; // percentage of remaining
    tokens_limit?: number;
    tokens_remaining?: number;
    tokens_pct?: number;
    status: string;
    updated_at: number;
}

type QuotasResponse = Record<string, Record<string, QuotaModelDetail>>;

const HUMAN_PROVIDERS: Record<string, { label: string; logo: string; image?: string; color: string }> = {
    gemini: { label: "Google Gemini", logo: "♊", image: "/gemini.png", color: "#8E75C8" },
    groq: { label: "Groq Speed API", logo: "⚡", image: "/groq llama.svg", color: "#F59E0B" },
    claude: { label: "Anthropic Claude", logo: "🍁", image: "/claude.png", color: "#D97706" },
    sambanova: { label: "SambaNova Systems", logo: "🌐", image: "/sambanova.png", color: "#2563EB" },
    deepseek: { label: "DeepSeek API", logo: "🐋", image: "/deepseek.png", color: "#0D9488" },
    cerebras: { label: "Cerebras Systems", logo: "🎛️", image: "/cerebras.png", color: "#EF4444" },
    ollama: { label: "Ollama (Local)", logo: "🐑", image: "/groq llama.svg", color: "#10B981" },
};

const HUMAN_MODELS = [
    { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash Lite (Rápido & Econômico)", description: "Otimizado para latência ultra-baixa em tarefas simples." },
    { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash (Padrão)", description: "Equilíbrio ideal entre velocidade e raciocínio contextual." },
    { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro (Alta Fidelidade)", description: "Raciocínio complexo e janela de contexto de 1M+ tokens." },
    { value: "gemini-flash-latest", label: "Gemini Flash Latest", description: "Última versão de produção do modelo de alta velocidade do Google Gemini." },
    { value: "gemini-2.0-flash-exp", label: "Gemini 2.0 Flash Exp (Experimental)", description: "Versão experimental de próxima geração para testes do Gemini Flash." },
    { value: "gemini-1.5-flash", label: "Gemini 1.5 Flash (Multimodal)", description: "Modelo multimídia eficiente e altamente estável do Google." },
    { value: "llama-3.3-70b-versatile", label: "Llama 3.3 70B Versatile (Meta / Groq)", description: "Poder analítico de 70B com a velocidade absurda do hardware LPU." },
    { value: "llama-3.1-8b-instant", label: "Llama 3.1 8B Instant (Rápido / Groq)", description: "Espinha dorsal para interações de alta frequência e baixa latência." },
    { value: "meta-llama/llama-4-scout-17b-16e-instruct", label: "Llama 4 Scout 17B (Groq / SambaNova)", description: "Nova geração Llama 4 otimizada para eficiência e precisão." },
    { value: "qwen/qwen3-32b", label: "Qwen 3 32B (Groq / Alibaba)", description: "Excelente performance em lógica, matemática e codificação." },
    { value: "llama-3.2-11b-vision-preview", label: "Llama 3.2 11B Vision (Groq)", description: "Análise visual, OCR e interpretação de imagens em tempo real." },
    { value: "groq/compound", label: "Groq Compound System", description: "Sistema autônomo com busca web e execução de código nativa." },
    { value: "mixtral-8x7b-32768", label: "Mixtral 8x7B MoE (Groq)", description: "Arquitetura Mixture-of-Experts para respostas versáteis." },
    { value: "claude-3-5-sonnet-latest", label: "Claude 3.5 Sonnet (Anthropic)", description: "O 'cérebro' para análise estratégica e escrita refinada." },
    { value: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku (Anthropic)", description: "Rápido e preciso para extração de dados estruturados." },
    { value: "Llama-4-Scout-17B-16E-Instruct", label: "Llama 4 Scout 17B (SambaNova)", description: "Performance Llama 4 em infraestrutura RDU de alta densidade." },
    { value: "Meta-Llama-3.3-70B-Instruct", label: "Llama 3.3 70B (SambaNova)", description: "Modelo 70B completo rodando em hardware SambaNova." },
    { value: "deepseek-chat", label: "DeepSeek Chat V3", description: "Modelo versátil com excelente custo-benefício e lógica." },
    { value: "llama3.1-8b", label: "Llama 3.1 8B (Cerebras)", description: "Velocidade supersônica via hardware CS-3." },
    { value: "llama-3.3-70b", label: "Llama 3.3 70B (Cerebras)", description: "70B com latência mínima recorde na indústria." },
    { value: "qwen-3-235b-a22b-instruct-2507", label: "Qwen 3 235B Instruct (Alibaba / Cerebras)", description: "Modelo gigante executado em velocidade inacreditável via hardware Cerebras CS-3." },
    { value: "qwen-3-235b-instruct", label: "Qwen 3 235B Instruct (Cerebras)", description: "Modelo de 235 bilhões de parâmetros com extrema profundidade cognitiva." },
    { value: "gpt-oss-120b", label: "GPT OSS 120B (Cerebras)", description: "Modelo open-source de grande porte para orquestração avançada." },
    { value: "zai-glm-4.7", label: "GLM 4.7 (Cerebras)", description: "Modelo de raciocínio lógico claro com suporte nativo a thinking." },
    { value: "qwen2.5:3b", label: "Qwen 2.5 3B (Ollama Local)", description: "Privacidade total rodando localmente na sua máquina (3B)." },
    { value: "qwen2.5:1.5b", label: "Qwen 2.5 1.5B (Ollama Local)", description: "Modelo leve rodando em hardware local para máxima eficiência e privacidade (1.5B)." },
];

export const PreferencesView: React.FC<PreferencesViewProps> = ({ onBack }) => {
    // LLM Tab hooks
    const [preferredModel, setPreferredModel] = useState('gemini-2.5-flash');
    const [strictMode, setStrictMode] = useState(false);
    const [quotas, setQuotas] = useState<QuotasResponse>({});
    const [loadingQuotas, setLoadingQuotas] = useState(true);
    const [saving, setSaving] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
    const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({
        gemini: true,
    });

    // Navigation state
    const [activeTab, setActiveTab] = useState<'llm' | 'profile' | 'products' | 'references' | 'value_props' | 'icp' | 'hierarchy' | 'integrations'>('llm');

    // 👤 Perfil Comercial State
    const [companyName, setCompanyName] = useState('');
    const [companySegment, setCompanySegment] = useState('');
    const [sellerName, setSellerName] = useState('');
    const [sellerRole, setSellerRole] = useState('');
    const [companyDifferentials, setCompanyDifferentials] = useState<string[]>([]);

    // 📦 Catálogo de Produtos State
    const [productsList, setProductsList] = useState<any[]>([]);
    const [showProductForm, setShowProductForm] = useState(false);
    const [editingProductIdx, setEditingProductIdx] = useState<number | null>(null);
    const [prodName, setProdName] = useState('');
    const [prodDesc, setProdDesc] = useState('');
    const [prodUseCases, setProdUseCases] = useState<string[]>([]);

    // 🤝 Clientes de Referência State
    const [referenceClients, setReferenceClients] = useState<any[]>([]);
    const [showClientForm, setShowClientForm] = useState(false);
    const [editingClientIdx, setEditingClientIdx] = useState<number | null>(null);
    const [clientName, setClientName] = useState('');
    const [clientSegment, setClientSegment] = useState('');

    // 🔥 Dores & Propostas de Valor State
    const [painPoints, setPainPoints] = useState<string[]>([]);
    const [valueProps, setValueProps] = useState<Record<string, string>>({});

    // 🎯 ICP & Qualificação State
    const [icpSegments, setIcpSegments] = useState<string[]>([]);
    const [targetIndustries, setTargetIndustries] = useState<string[]>([]);
    const [companyProfiles, setCompanyProfiles] = useState<string[]>([]);
    const [decisionMakers, setDecisionMakers] = useState<string[]>([]);
    const [disqualifiers, setDisqualifiers] = useState<string[]>([]);
    const [highFitKeywords, setHighFitKeywords] = useState<string[]>([]);
    const [mediumFitKeywords, setMediumFitKeywords] = useState<string[]>([]);
    const [lowFitKeywords, setLowFitKeywords] = useState<string[]>([]);

    // ⛓️ Regras de Hierarquia State
    const [forbiddenKeywords, setForbiddenKeywords] = useState<Record<string, string[]>>({ compras: [], logistica: [] });
    const [purchasingKeywords, setPurchasingKeywords] = useState<string[]>([]);
    const [logisticsKeywords, setLogisticsKeywords] = useState<string[]>([]);

    // 🌐 Integrações State
    const [pipedriveToken, setPipedriveToken] = useState('');
    const [pipedriveUserId, setPipedriveUserId] = useState('');
    const [whatsappServiceUrl, setWhatsappServiceUrl] = useState('');
    const [emailUser, setEmailUser] = useState('');
    const [emailPassword, setEmailPassword] = useState('');
    const [emailPort, setEmailPort] = useState('');

    const toggleProvider = (provKey: string) => {
        setExpandedProviders(prev => ({
            ...prev,
            [provKey]: !prev[provKey]
        }));
    };

    const pollingInterval = useRef<NodeJS.Timeout | null>(null);

    const showToast = (type: 'success' | 'error', message: string) => {
        setToast({ type, message });
        setTimeout(() => setToast(null), 4000);
    };

    const loadPreferences = async () => {
        try {
            // Load LLM preferences
            const res = await ai.getPreference();
            if (res) {
                setPreferredModel(res.preferred_model || 'gemini-2.5-flash');
                setStrictMode(res.strict_mode || false);
            }

            // Load all SaaS context V2
            const ctx = await ai.getFullContext();
            if (ctx) {
                // Perfil Comercial
                setCompanyName(ctx.company_name || '');
                setCompanySegment(ctx.company_segment || '');
                setSellerName(ctx.seller_name || '');
                setSellerRole(ctx.seller_role || '');
                setCompanyDifferentials(ctx.company_differentials || []);

                // Produtos
                const prods = ctx.products ? Object.values(ctx.products) : [];
                setProductsList(prods);

                // Clientes
                setReferenceClients(ctx.reference_clients || []);

                // ICP
                const icp = ctx.icp || {};
                setTargetIndustries(icp.industries || []);
                setCompanyProfiles(icp.company_profiles || []);
                setDecisionMakers(icp.decision_makers || []);
                setDisqualifiers(icp.disqualifiers || []);
                setPainPoints(icp.pain_points || []);
                setValueProps(ctx.value_propositions || {});
                
                // Mapear regras de score do banco para as listas legadas (para manter compatibilidade UI)
                const high = icp.score_rules?.filter((r: any) => r.score >= 40).map((r: any) => r.pattern) || [];
                const medium = icp.score_rules?.filter((r: any) => r.score >= 20 && r.score < 40).map((r: any) => r.pattern) || [];
                const low = icp.score_rules?.filter((r: any) => r.score < 0).map((r: any) => r.pattern) || [];
                setHighFitKeywords(high);
                setMediumFitKeywords(medium);
                setLowFitKeywords(low);

                // Hierarquia
                const hie = ctx.hierarchy || {};
                setForbiddenKeywords(hie.forbidden_keywords || { compras: [], logistica: [] });
                
                const whitelist = hie.whitelist_keywords || {};
                if (Array.isArray(whitelist)) {
                    setPurchasingKeywords(whitelist);
                    setLogisticsKeywords([]);
                } else {
                    setPurchasingKeywords(whitelist.compras || []);
                    setLogisticsKeywords(whitelist.logistica || []);
                }

                // Integrações
                try {
                    const ints = await ai.getIntegrations();
                    if (ints) {
                        const pipe = ints.pipedrive?.credentials || {};
                        setPipedriveToken(pipe.api_token || '');
                        setPipedriveUserId(pipe.user_id || '');
                        
                        const whats = ints.whatsapp?.credentials || {};
                        setWhatsappServiceUrl(whats.service_url || '');
                        
                        const mail = ints.outlook?.credentials || {};
                        setEmailUser(mail.email_user || '');
                        setEmailPassword(mail.email_password || '');
                        setEmailPort(mail.email_port || '');
                    }
                } catch (intErr) {
                    console.error("Erro ao carregar integrações:", intErr);
                }
            }
        } catch (e: any) {
            console.error("Erro ao carregar preferências:", e);
            showToast('error', "Alguns dados não puderam ser carregados do banco de dados.");
        }
    };

    const fetchQuotas = async (silent = false) => {
        if (!silent) setLoadingQuotas(true);
        else setIsRefreshing(true);
        try {
            const res = await ai.getQuotas();
            if (res) {
                setQuotas(res);
            }
        } catch (e: any) {
            console.error("Erro ao buscar cotas:", e);
        } finally {
            setLoadingQuotas(false);
            setIsRefreshing(false);
        }
    };

    // Save Handlers
    const handleSaveLLM = async () => {
        setSaving(true);
        try {
            const res = await ai.updatePreference(preferredModel, strictMode);
            if (res && res.status === 'ok') {
                showToast('success', `Modelo preferido atualizado para ${preferredModel}!`);
            } else {
                showToast('error', "Erro ao salvar preferências.");
            }
        } catch (e: any) {
            showToast('error', e.message || "Erro de rede ao salvar preferências.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveProfile = async () => {
        setSaving(true);
        try {
            const payload = {
                segment: companySegment,
                differentials: companyDifferentials,
                seller_name: sellerName,
                seller_role: sellerRole
            };
            await ai.updateProfile(payload);
            showToast('success', "Perfil comercial atualizado com sucesso (V2)!");
        } catch (e: any) {
            showToast('error', "Erro ao salvar perfil comercial.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveProducts = async () => {
        setSaving(true);
        try {
            // Em V2, vamos limpar e re-adicionar para simplicidade do batch
            // Nota: Em prod real, faríamos diff ou endpoint de batch
            for (const p of productsList) {
                await ai.addProductV2(p);
            }
            showToast('success', "Catálogo de produtos sincronizado!");
        } catch (e: any) {
            showToast('error', "Erro ao salvar catálogo de produtos.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveReferences = async () => {
        setSaving(true);
        try {
            await ai.updateSetting('reference_clients', { list: referenceClients }, 'business');
            showToast('success', "Clientes de referência salvos!");
        } catch (e: any) {
            showToast('error', "Erro ao salvar clientes.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveICP = async () => {
        setSaving(true);
        try {
            const rules = [
                ...highFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: 40, reason: "Alto encaixe" })),
                ...mediumFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: 20, reason: "Médio encaixe" })),
                ...lowFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: -20, reason: "Baixo encaixe" })),
            ];

            const payload = {
                industries_target: targetIndustries,
                company_size_target: companyProfiles,
                decision_makers: decisionMakers,
                disqualifiers: disqualifiers,
                score_rules: rules
            };
            await ai.updateICPV2(payload);
            showToast('success', "Configuração de ICP (V2) salva!");
        } catch (e: any) {
            showToast('error', "Erro ao salvar ICP.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveHierarchy = async () => {
        setSaving(true);
        try {
            const payload = {
                department_focus: 'compras',
                forbidden_keywords: forbiddenKeywords,
                whitelist_keywords: {
                    compras: purchasingKeywords,
                    logistica: logisticsKeywords
                },
                seniority_rules: { "diretor": 5, "gerente": 4, "coordenador": 3, "analista": 2 },
                department_mapping_rules: { "compras": "Suprimentos", "logistica": "Logística" }
            };
            await ai.updateHierarchyV2(payload);
            showToast('success', "Regras de hierarquia (V2) atualizadas!");
        } catch (e: any) {
            showToast('error', "Erro ao salvar regras.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveValueProps = async () => {
        setSaving(true);
        try {
            const payloadProfile = {
                segment: companySegment,
                differentials: companyDifferentials,
                seller_name: sellerName,
                seller_role: sellerRole,
                value_propositions: valueProps
            };
            await ai.updateProfile(payloadProfile);

            const payloadICP = {
                industries_target: targetIndustries,
                company_size_target: companyProfiles,
                decision_makers: decisionMakers,
                disqualifiers: disqualifiers,
                pain_points: painPoints,
                score_rules: [
                    ...highFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: 40, reason: "Alto encaixe" })),
                    ...mediumFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: 20, reason: "Médio encaixe" })),
                    ...lowFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: -20, reason: "Baixo encaixe" })),
                ]
            };
            await ai.updateICPV2(payloadICP);

            showToast('success', "Dores e propostas de valor atualizadas com sucesso!");
        } catch (e: any) {
            showToast('error', "Erro ao salvar dores e propostas de valor.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveIntegrations = async () => {
        setSaving(true);
        try {
            // 1. Salvar Pipedrive
            await ai.updateIntegration('pipedrive', {
                credentials: {
                    api_token: pipedriveToken,
                    user_id: pipedriveUserId
                },
                custom_settings: {}
            });

            // 2. Salvar WhatsApp
            await ai.updateIntegration('whatsapp', {
                credentials: {
                    service_url: whatsappServiceUrl
                },
                custom_settings: {}
            });

            // 3. Salvar Outlook/Email
            await ai.updateIntegration('outlook', {
                credentials: {
                    email_user: emailUser,
                    email_password: emailPassword,
                    email_port: emailPort
                },
                custom_settings: {}
            });

            showToast('success', "Todas as integrações foram atualizadas com sucesso!");
        } catch (e: any) {
            console.error("Erro ao salvar integrações:", e);
            showToast('error', "Erro ao salvar credenciais das integrações.");
        } finally {
            setSaving(false);
        }
    };

    useEffect(() => {
        loadPreferences();
        fetchQuotas();

        pollingInterval.current = setInterval(() => {
            fetchQuotas(true);
        }, 5000);

        return () => {
            if (pollingInterval.current) {
                clearInterval(pollingInterval.current);
            }
        };
    }, []);

    const getProgressColorClass = (pct: number) => {
        if (pct >= 50) return styles.progressGreen;
        if (pct >= 20) return styles.progressOrange;
        return styles.progressRed;
    };

    // Helper product lists actions
    const handleAddOrUpdateProduct = () => {
        if (!prodName.trim()) {
            showToast('error', "O nome do produto é obrigatório.");
            return;
        }

        const newProd = {
            name: prodName.trim(),
            description: prodDesc.trim(),
            use_cases: prodUseCases
        };

        if (editingProductIdx !== null) {
            const updated = [...productsList];
            updated[editingProductIdx] = newProd;
            setProductsList(updated);
            setEditingProductIdx(null);
        } else {
            setProductsList([...productsList, newProd]);
        }

        setProdName('');
        setProdDesc('');
        setProdUseCases([]);
        setShowProductForm(false);
    };

    const handleEditProduct = (index: number) => {
        const p = productsList[index];
        setEditingProductIdx(index);
        setProdName(p.name);
        setProdDesc(p.description || '');
        setProdUseCases(p.use_cases || []);
        setShowProductForm(true);
    };

    const handleDeleteProduct = (index: number) => {
        if (confirm("Tem certeza que deseja remover este produto?")) {
            setProductsList(productsList.filter((_, i) => i !== index));
        }
    };

    // Helper reference client actions
    const handleAddOrUpdateClient = () => {
        if (!clientName.trim() || !clientSegment.trim()) {
            showToast('error', "Preencha o nome e segmento do cliente.");
            return;
        }

        const newClient = {
            name: clientName.trim(),
            segment: clientSegment.trim()
        };

        if (editingClientIdx !== null) {
            const updated = [...referenceClients];
            updated[editingClientIdx] = newClient;
            setReferenceClients(updated);
            setEditingClientIdx(null);
        } else {
            setReferenceClients([...referenceClients, newClient]);
        }

        setClientName('');
        setClientSegment('');
        setShowClientForm(false);
    };

    const handleEditClient = (index: number) => {
        const c = referenceClients[index];
        setEditingClientIdx(index);
        setClientName(c.name);
        setClientSegment(c.segment);
        setShowClientForm(true);
    };

    const handleDeleteClient = (index: number) => {
        setReferenceClients(referenceClients.filter((_, i) => i !== index));
    };

    // Inline StringListEditor component
    const StringListEditor: React.FC<{
        list: string[];
        onChange: (newList: string[]) => void;
        label: string;
        placeholder?: string;
        description?: string;
    }> = ({ list, onChange, label, placeholder, description }) => {
        const [inputValue, setInputValue] = useState('');

        const handleAdd = () => {
            if (inputValue.trim() && !list.includes(inputValue.trim())) {
                onChange([...list, inputValue.trim()]);
                setInputValue('');
            }
        };

        const handleRemove = (index: number) => {
            onChange(list.filter((_, i) => i !== index));
        };

        return (
            <div className={styles.formGroup} style={{ gap: '8px' }}>
                <label className={styles.label}>{label}</label>
                {description && (
                    <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.35)', marginTop: '-2px', marginBottom: '4px', lineHeight: '1.4' }}>
                        {description}
                    </span>
                )}
                <div style={{ display: 'flex', gap: '8px' }}>
                    <input
                        type="text"
                        className={styles.select}
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd(); } }}
                        placeholder={placeholder || 'Adicionar item...'}
                        style={{ flex: 1 }}
                    />
                    <button 
                        type="button" 
                        onClick={handleAdd}
                        className={styles.saveBtn}
                        style={{ padding: '0 18px', borderRadius: '6px', height: '46px' }}
                    >
                        <Plus size={16} />
                    </button>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '6px' }}>
                    {list.map((item, idx) => (
                        <div 
                            key={idx} 
                            style={{ 
                                display: 'flex', 
                                alignItems: 'center', 
                                gap: '8px', 
                                backgroundColor: 'rgba(255,255,255,0.03)', 
                                border: '1px solid rgba(255,255,255,0.08)', 
                                borderRadius: '4px', 
                                padding: '6px 12px', 
                                fontSize: '12px',
                                color: 'rgba(255,255,255,0.85)' 
                            }}
                        >
                            <span>{item}</span>
                            <X 
                                size={14} 
                                onClick={() => handleRemove(idx)} 
                                style={{ color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center' }} 
                            />
                        </div>
                    ))}
                    {list.length === 0 && (
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.25)', fontStyle: 'italic' }}>Nenhum item adicionado.</span>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className={styles.container}>
            {/* Header */}
            <header className={styles.header}>
                <div className={styles.titleArea}>
                    <h1 className={styles.title}>
                        <Settings2 size={24} /> Configurações do Sistema
                    </h1>
                    <span className={styles.subtitle}>
                        Gerencie as preferências de IA, perfil do negócio, dores, propostas de valor, ICP de leads e regras de mapeamento no DB.
                    </span>
                </div>
                <button className={styles.backBtn} onClick={onBack}>
                    <ChevronLeft size={16} /> Voltar
                </button>
            </header>

            {/* Split Layout */}
            <div className={styles.settingsLayout}>
                {/* Left Sidebar Tabs Menu */}
                <aside className={styles.settingsSidebar}>
                    <div className={styles.sidebarSectionTitle}>Categorias</div>
                    <nav className={styles.sidebarMenu}>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'llm' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('llm')}
                        >
                            <Sparkles size={16} />
                            <span>Preferências & Limites LLM</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'profile' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('profile')}
                        >
                            <Briefcase size={16} />
                            <span>Perfil Comercial</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'products' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('products')}
                        >
                            <Package size={16} />
                            <span>Catálogo de Produtos</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'references' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('references')}
                        >
                            <Users size={16} />
                            <span>Clientes de Referência</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'value_props' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('value_props')}
                        >
                            <Flame size={16} />
                            <span>Dores & Propostas de Valor</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'icp' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('icp')}
                        >
                            <Target size={16} />
                            <span>Regras de ICP & Qualificação</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'hierarchy' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('hierarchy')}
                        >
                            <GitFork size={16} />
                            <span>Regras de Hierarquia</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'integrations' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('integrations')}
                        >
                            <Database size={16} />
                            <span>Conexões & Integrações</span>
                        </div>
                    </nav>
                </aside>

                {/* Right Tab Contents */}
                <div className={styles.settingsContent}>
                    
                    {/* TOAST SYSTEM */}
                    {toast && (
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '12px',
                            padding: '16px 20px',
                            borderRadius: '6px',
                            border: `1px solid ${toast.type === 'success' ? 'rgba(52,209,124,0.15)' : 'rgba(239,68,68,0.15)'}`,
                            backgroundColor: toast.type === 'success' ? 'rgba(52,209,124,0.05)' : 'rgba(239,68,68,0.05)',
                            color: toast.type === 'success' ? '#34d17c' : '#ef4444',
                            fontSize: '13px',
                            fontFamily: 'var(--font-primary)',
                            animation: 'fadeIn 0.2s ease',
                            marginBottom: '12px'
                        }}>
                            {toast.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                            <span>{toast.message}</span>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 1: LLM PREFERENCES & QUOTAS 
                        ========================================================== */}
                    {activeTab === 'llm' && (
                        <div className={styles.dashboardContainer}>
                            <div className={styles.card}>
                                <h2 className={styles.cardTitle}>
                                    <span className={styles.cardTitleText}>
                                        <Cpu size={18} /> Modelos & Preferências de IA
                                    </span>
                                </h2>

                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Modelo Preferido (Padrão do Sistema)</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        O cérebro de IA preferido para orquestrar as cadeias de agentes, ler biografias do LinkedIn, classificar cargos, estruturar hierarquias e redigir propostas de vendas.
                                    </span>
                                    <select 
                                        className={styles.select}
                                        value={preferredModel}
                                        onChange={(e) => setPreferredModel(e.target.value)}
                                    >
                                        {HUMAN_MODELS.map(m => (
                                            <option key={m.value} value={m.value}>{m.label}</option>
                                        ))}
                                    </select>
                                </div>

                                <div 
                                    className={styles.checkboxContainer}
                                    onClick={() => setStrictMode(!strictMode)}
                                >
                                    <div className={styles.checkbox}>
                                        {strictMode && <CheckCircle2 size={12} color="#3b82f6" />}
                                    </div>
                                    <div className={styles.checkboxText}>
                                        <span className={styles.checkboxLabel}>Strict Mode (Forçar Modelo)</span>
                                        <span className={styles.checkboxSub}>
                                            Se ativado, o sistema sempre tentará usar o modelo acima com retries agressivos, 
                                            desativando o fallback automático para outros provedores em caso de falha.
                                        </span>
                                    </div>
                                </div>

                                <button 
                                    className={styles.saveBtn}
                                    onClick={handleSaveLLM}
                                    disabled={saving}
                                >
                                    {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                    {saving ? "Salvando..." : "Salvar Preferências"}
                                </button>
                            </div>

                            <div style={{ height: '32px' }} />

                            {/* Quota Dashboard */}
                            <div className={styles.card}>
                                <h2 className={styles.cardTitle}>
                                    <span className={styles.cardTitleText}>
                                        <Activity size={18} /> Limites de Cotas em Tempo Real
                                    </span>
                                    {isRefreshing && (
                                        <div className={styles.refreshingIndicator}>
                                            <RefreshCw size={14} className={styles.spin} />
                                            <span style={{ fontSize: '11px' }}>atualizando...</span>
                                        </div>
                                    )}
                                </h2>

                                {loadingQuotas ? (
                                    <div className={styles.noDataText} style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                                        <RefreshCw size={24} className={styles.spin} />
                                        <span>Sincronizando quotas com os provedores de IA...</span>
                                    </div>
                                ) : (
                                    <div className={styles.providersList}>
                                        {Object.entries(quotas).map(([provKey, modelsMap]) => {
                                            const meta = HUMAN_PROVIDERS[provKey] || { label: provKey, logo: "🤖", color: "#3b82f6" };
                                            const isRateLimited = Object.values(modelsMap).some(m => m.status === 'rate_limited');
                                            const isAnyNoCredits = Object.values(modelsMap).some(m => m.status === 'no_credits');
                                            const isExpanded = expandedProviders[provKey] ?? false;

                                            return (
                                                <div key={provKey} className={styles.providerCard}>
                                                    <div 
                                                        className={styles.providerHeader}
                                                        onClick={() => toggleProvider(provKey)}
                                                        style={{ cursor: 'pointer', userSelect: 'none' }}
                                                    >
                                                        <div className={styles.providerBrand}>
                                                            {meta.image ? (
                                                                <img 
                                                                    src={meta.image} 
                                                                    alt={meta.label} 
                                                                    className={styles.providerLogoImage} 
                                                                />
                                                            ) : (
                                                                <span className={styles.providerLogoEmoji}>{meta.logo}</span>
                                                            )}
                                                            <span className={styles.providerName}>{meta.label}</span>
                                                        </div>
                                                        <div className={styles.providerHeaderRight}>
                                                            <div className={`${styles.providerBadge} ${(isRateLimited || isAnyNoCredits) ? styles.badgeCritical : styles.badgeHealthy}`}>
                                                                {isRateLimited ? (
                                                                    <>
                                                                        <AlertTriangle size={12} />
                                                                        <span>RATE LIMITED / COOLDOWN</span>
                                                                    </>
                                                                ) : isAnyNoCredits ? (
                                                                    <>
                                                                        <AlertTriangle size={12} />
                                                                        <span>SEM CRÉDITOS</span>
                                                                    </>
                                                                ) : (
                                                                    <>
                                                                        <CheckCircle2 size={12} />
                                                                        <span>ATIVO E DISPONÍVEL</span>
                                                                    </>
                                                                )}
                                                            </div>
                                                            <ChevronDown 
                                                                size={16} 
                                                                className={`${styles.chevron} ${isExpanded ? styles.chevronExpanded : ''}`}
                                                            />
                                                        </div>
                                                    </div>

                                                    {isExpanded && (
                                                        <div className={styles.providerContent}>
                                                            {Object.entries(modelsMap).length === 0 ? (
                                                                <div className={styles.noDataText}>Nenhum modelo registrado.</div>
                                                            ) : (
                                                                Object.entries(modelsMap).map(([modelName, detail]) => {
                                                                    const isModelRateLimited = detail.status === 'rate_limited' || detail.status === 'cooldown';
                                                                    const isNoCredits = detail.status === 'no_credits';
                                                                    const pct = (isModelRateLimited || isNoCredits) ? 0 : detail.pct;

                                                                    return (
                                                                        <div key={modelName} className={styles.modelRow}>
                                                                            <div className={styles.modelInfo}>
                                                                                <span className={styles.modelName}>{modelName}</span>
                                                                                <span className={styles.modelStats}>
                                                                                    {isModelRateLimited ? (
                                                                                        <span className={styles.modelStatsCritical}>COOLDOWN (RATE LIMITED)</span>
                                                                                    ) : isNoCredits ? (
                                                                                        <span className={styles.modelStatsCritical}>INDISPONÍVEL (SEM SALDO)</span>
                                                                                    ) : (
                                                                                        <>
                                                                                            Disponível: <span className={styles.modelStatsHighlight}>{pct}%</span> ({detail.remaining} / {detail.limit} reqs)
                                                                                        </>
                                                                                    )}
                                                                                </span>
                                                                            </div>
                                                                            <div className={styles.progressContainer}>
                                                                                <div 
                                                                                    className={`${styles.progressBar} ${(isModelRateLimited || isNoCredits) ? styles.progressRed : getProgressColorClass(pct)}`}
                                                                                    style={{ width: `${pct}%` }}
                                                                                />
                                                                            </div>
                                                                            {detail.tokens_limit ? (
                                                                                <div className={styles.tokenStats}>
                                                                                    <Database size={10} />
                                                                                    <span>Tokens: {detail.tokens_pct}% ({Math.round((detail.tokens_remaining || 0) / 1000)}k / {Math.round(detail.tokens_limit / 1000)}k restantes)</span>
                                                                                </div>
                                                                            ) : null}
                                                                        </div>
                                                                    );
                                                                })
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 2: PERFIL COMERCIAL
                        ========================================================== */}
                    {activeTab === 'profile' && (
                        <div className={styles.card}>
                            <h2 className={styles.cardTitle}>
                                <span className={styles.cardTitleText}>
                                    <Briefcase size={18} /> Identidade & Perfil Comercial da Empresa
                                </span>
                            </h2>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Nome da Empresa</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        O nome oficial ou fantasia que a inteligência artificial mencionará nas mensagens ao falar em nome da sua empresa.
                                    </span>
                                    <input 
                                        type="text" 
                                        className={styles.select}
                                        value={companyName}
                                        onChange={(e) => setCompanyName(e.target.value)}
                                        placeholder="Nome fantasia da sua empresa (Ex: J.Ferres)"
                                    />
                                </div>
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Segmento / Atuação</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        O nicho específico de mercado que descreve a sua operação para dar contexto ao robô na prospecção.
                                    </span>
                                    <input 
                                        type="text" 
                                        className={styles.select}
                                        value={companySegment}
                                        onChange={(e) => setCompanySegment(e.target.value)}
                                        placeholder="Setor detalhado (Ex: Embalagens de Papelão Ondulado)"
                                    />
                                </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Nome do Vendedor Principal</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        Nome de quem assinará as mensagens de prospecção fria enviadas por e-mail ou WhatsApp.
                                    </span>
                                    <input 
                                        type="text" 
                                        className={styles.select}
                                        value={sellerName}
                                        onChange={(e) => setSellerName(e.target.value)}
                                        placeholder="Ex: João Luccas"
                                    />
                                </div>
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Cargo do Vendedor</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        Cargo institucional do remetente (Ex: Executivo de Contas, Diretor Comercial, etc.) para assinar os e-mails.
                                    </span>
                                    <input 
                                        type="text" 
                                        className={styles.select}
                                        value={sellerRole}
                                        onChange={(e) => setSellerRole(e.target.value)}
                                        placeholder="Ex: Representante Comercial"
                                    />
                                </div>
                            </div>

                            <StringListEditor 
                                list={companyDifferentials}
                                onChange={setCompanyDifferentials}
                                label="Diferenciais Competitivos da Empresa"
                                placeholder="Insira um diferencial e aperte Enter"
                                description="Destaques exclusivos, prêmios ou diferenciais da sua empresa que a IA lerá para gerar argumentos de autoridade e convencimento."
                            />

                            <button 
                                className={styles.saveBtn}
                                onClick={handleSaveProfile}
                                disabled={saving}
                                style={{ marginTop: '12px' }}
                            >
                                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                {saving ? "Salvando..." : "Salvar Perfil Comercial"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 3: CATÁLOGO DE PRODUTOS
                        ========================================================== */}
                    {activeTab === 'products' && (
                        <div className={styles.card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h2 className={styles.cardTitle} style={{ margin: 0 }}>
                                    <span className={styles.cardTitleText}>
                                        <Package size={18} /> Catálogo de Produtos e Serviços Ofertados
                                    </span>
                                </h2>
                                {!showProductForm && (
                                    <button 
                                        onClick={() => {
                                            setEditingProductIdx(null);
                                            setProdName('');
                                            setProdDesc('');
                                            setProdUseCases([]);
                                            setShowProductForm(true);
                                        }}
                                        className={styles.saveBtn}
                                        style={{ padding: '8px 16px', fontSize: '12px' }}
                                    >
                                        <Plus size={14} /> Adicionar Produto
                                    </button>
                                )}
                            </div>

                            {/* Product Form */}
                            {showProductForm && (
                                <div style={{ 
                                    padding: '24px', 
                                    border: '1px solid rgba(255,255,255,0.08)', 
                                    borderRadius: '8px', 
                                    backgroundColor: 'rgba(255,255,255,0.01)',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '16px',
                                    animation: 'fadeIn 0.2s ease'
                                }}>
                                    <h3 style={{ fontSize: '14px', fontWeight: 500, color: '#fff', margin: 0, display: 'flex', justifyContent: 'space-between' }}>
                                        <span>{editingProductIdx !== null ? "Editar Produto" : "Novo Produto"}</span>
                                        <X size={16} style={{ cursor: 'pointer', opacity: 0.5 }} onClick={() => setShowProductForm(false)} />
                                    </h3>

                                    <div className={styles.formGroup}>
                                        <label className={styles.label}>Nome do Produto / Serviço</label>
                                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                            O nome comercial do item ou serviço oferecido. A IA usará este termo exato ao elaborar as abordagens.
                                        </span>
                                        <input 
                                            type="text" 
                                            className={styles.select}
                                            value={prodName}
                                            onChange={(e) => setProdName(e.target.value)}
                                            placeholder="Ex: Caixas de Papelão Ondulado"
                                        />
                                    </div>

                                    <div className={styles.formGroup}>
                                        <label className={styles.label}>Descrição Completa (Utilizada pela IA em ganchos)</label>
                                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                            Especificações técnicas, benefícios e materiais. A inteligência artificial lê este campo para entender as vantagens do produto e gerar ganchos altamente contextualizados.
                                        </span>
                                        <textarea 
                                            className={styles.select}
                                            rows={4}
                                            value={prodDesc}
                                            onChange={(e) => setProdDesc(e.target.value)}
                                            placeholder="Descreva as especificações, materiais e finalidade do produto..."
                                            style={{ fontFamily: 'inherit', resize: 'vertical' }}
                                        />
                                    </div>

                                    <StringListEditor 
                                        list={prodUseCases}
                                        onChange={setProdUseCases}
                                        label="Casos de Uso / Aplicações Típicas"
                                        placeholder="Ex: Kitting de linha de montagem automotiva"
                                        description="Aplicações práticas ou cenários de uso do produto, permitindo que a IA monte ganchos de argumentação adaptados ao segmento de cada lead."
                                    />

                                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                                        <button 
                                            type="button"
                                            className={styles.backBtn}
                                            onClick={() => setShowProductForm(false)}
                                        >
                                            Cancelar
                                        </button>
                                        <button 
                                            type="button"
                                            className={styles.saveBtn}
                                            onClick={handleAddOrUpdateProduct}
                                            style={{ padding: '8px 20px', borderRadius: '4px' }}
                                        >
                                            {editingProductIdx !== null ? "Atualizar na Lista" : "Adicionar à Lista"}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Products Grid */}
                            <div className={styles.providersList}>
                                {productsList.map((prod, idx) => (
                                    <div key={idx} className={styles.providerCard} style={{ padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                        <div style={{ flex: 1, paddingRight: '20px' }}>
                                            <h4 style={{ fontSize: '15px', color: '#fff', fontWeight: 600, margin: '0 0 6px 0' }}>{prod.name}</h4>
                                            <p style={{ fontSize: '13px', opacity: 0.7, lineHeight: '1.6', fontWeight: 300, margin: '0 0 12px 0' }}>{prod.description}</p>
                                            {prod.use_cases && prod.use_cases.length > 0 && (
                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                                    {prod.use_cases.map((uc: string, uIdx: number) => (
                                                        <span key={uIdx} style={{ fontSize: '10px', backgroundColor: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.15)', color: '#3b82f6', padding: '3px 8px', borderRadius: '4px' }}>
                                                            {uc}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <button 
                                                onClick={() => handleEditProduct(idx)}
                                                className={styles.backBtn} 
                                                style={{ padding: '6px' }}
                                                title="Editar"
                                            >
                                                <Edit3 size={15} />
                                            </button>
                                            <button 
                                                onClick={() => handleDeleteProduct(idx)}
                                                className={styles.backBtn} 
                                                style={{ padding: '6px', color: '#ef4444' }}
                                                title="Deletar"
                                            >
                                                <Trash2 size={15} />
                                            </button>
                                        </div>
                                    </div>
                                ))}

                                {productsList.length === 0 && (
                                    <div className={styles.noDataText}>O catálogo de produtos está vazio. Adicione um novo produto acima.</div>
                                )}
                            </div>

                            <button 
                                className={styles.saveBtn}
                                onClick={handleSaveProducts}
                                disabled={saving}
                                style={{ marginTop: '16px' }}
                            >
                                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                {saving ? "Salvando..." : "Salvar Catálogo de Produtos"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 4: CLIENTES DE REFERÊNCIA
                        ========================================================== */}
                    {activeTab === 'references' && (
                        <div className={styles.card}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h2 className={styles.cardTitle} style={{ margin: 0 }}>
                                    <span className={styles.cardTitleText}>
                                        <Users size={18} /> Clientes de Referência (Autoridade no Outreach)
                                    </span>
                                </h2>
                                {!showClientForm && (
                                    <button 
                                        onClick={() => {
                                            setEditingClientIdx(null);
                                            setClientName('');
                                            setClientSegment('');
                                            setShowClientForm(true);
                                        }}
                                        className={styles.saveBtn}
                                        style={{ padding: '8px 16px', fontSize: '12px' }}
                                    >
                                        <Plus size={14} /> Adicionar Cliente
                                    </button>
                                )}
                            </div>

                            {/* Client Form */}
                            {showClientForm && (
                                <div style={{ 
                                    padding: '20px', 
                                    border: '1px solid rgba(255,255,255,0.08)', 
                                    borderRadius: '8px', 
                                    backgroundColor: 'rgba(255,255,255,0.01)',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '14px',
                                    animation: 'fadeIn 0.2s ease'
                                }}>
                                    <h3 style={{ fontSize: '13px', fontWeight: 500, color: '#fff', margin: 0, display: 'flex', justifyContent: 'space-between' }}>
                                        <span>{editingClientIdx !== null ? "Editar Cliente de Referência" : "Novo Cliente de Referência"}</span>
                                        <X size={16} style={{ cursor: 'pointer', opacity: 0.5 }} onClick={() => setShowClientForm(false)} />
                                    </h3>

                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Nome do Cliente (Marca/Empresa)</label>
                                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                                Nome de uma marca de destaque que já seja seu cliente ativo para atuar como prova social.
                                            </span>
                                            <input 
                                                type="text" 
                                                className={styles.select}
                                                value={clientName}
                                                onChange={(e) => setClientName(e.target.value)}
                                                placeholder="Ex: Toyota TMD"
                                            />
                                        </div>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Segmento / Descrição de Par</label>
                                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                                O setor de atuação ou perfil do cliente. A IA lerá esta descrição para fazer matching de segmento com os novos leads analisados.
                                            </span>
                                            <input 
                                                type="text" 
                                                className={styles.select}
                                                value={clientSegment}
                                                onChange={(e) => setClientSegment(e.target.value)}
                                                placeholder="Ex: Montadora automotiva"
                                            />
                                        </div>
                                    </div>

                                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '6px' }}>
                                        <button 
                                            type="button"
                                            className={styles.backBtn}
                                            onClick={() => setShowClientForm(false)}
                                        >
                                            Cancelar
                                        </button>
                                        <button 
                                            type="button"
                                            className={styles.saveBtn}
                                            onClick={handleAddOrUpdateClient}
                                            style={{ padding: '8px 20px', borderRadius: '4px' }}
                                        >
                                            {editingClientIdx !== null ? "Atualizar na Lista" : "Adicionar à Lista"}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Clients list */}
                            <div className={styles.providersList}>
                                {referenceClients.map((client, idx) => (
                                    <div key={idx} className={styles.providerCard} style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <div>
                                            <h4 style={{ fontSize: '14px', color: '#fff', fontWeight: 600, margin: 0 }}>{client.name}</h4>
                                            <span style={{ fontSize: '12px', opacity: 0.5, fontWeight: 300 }}>{client.segment}</span>
                                        </div>
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <button 
                                                onClick={() => handleEditClient(idx)}
                                                className={styles.backBtn} 
                                                style={{ padding: '6px' }}
                                                title="Editar"
                                            >
                                                <Edit3 size={15} />
                                            </button>
                                            <button 
                                                onClick={() => handleDeleteClient(idx)}
                                                className={styles.backBtn} 
                                                style={{ padding: '6px', color: '#ef4444' }}
                                                title="Deletar"
                                            >
                                                <Trash2 size={15} />
                                            </button>
                                        </div>
                                    </div>
                                ))}

                                {referenceClients.length === 0 && (
                                    <div className={styles.noDataText}>Nenhum cliente de referência cadastrado ainda.</div>
                                )}
                            </div>

                            <button 
                                className={styles.saveBtn}
                                onClick={handleSaveReferences}
                                disabled={saving}
                                style={{ marginTop: '16px' }}
                            >
                                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                {saving ? "Salvando..." : "Salvar Clientes de Referência"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 5: DORES & PROPOSTAS DE VALOR
                        ========================================================== */}
                    {activeTab === 'value_props' && (
                        <div className={styles.card}>
                            <h2 className={styles.cardTitle}>
                                <span className={styles.cardTitleText}>
                                    <Flame size={18} /> Argumentos de Venda, Dores e Propostas de Valor
                                </span>
                            </h2>

                            <StringListEditor 
                                list={painPoints}
                                onChange={setPainPoints}
                                label="Dores Críticas que Resolvemos (Dores do Lead)"
                                placeholder="Ex: Fornecedor atual atrasa ou tem rupturas de estoque frequentes"
                                description="Lista de problemas que os clientes costumam vivenciar. O robô usará esses tópicos de forma consultiva para criar ganchos de dor hiper-relevantes nas abordagens."
                            />

                            <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                                <span className={styles.label} style={{ fontSize: '12px' }}>Textos de Propostas de Valor (Ângulos de Abordagem)</span>
                                
                                <div className={styles.formGroup}>
                                    <label className={styles.label} style={{ fontSize: '10px' }}>Abordagem 1: Plano B / Mitigação de Risco</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        Texto focado em posicionar sua empresa como fornecedora alternativa ou reserva estratégica (Plano B) para garantir a segurança da operação do lead.
                                    </span>
                                    <textarea 
                                        className={styles.select}
                                        rows={3}
                                        value={valueProps.plano_b || ''}
                                        onChange={(e) => setValueProps({ ...valueProps, plano_b: e.target.value })}
                                        placeholder="Argumento de vendas focando em servir como alternativa confiável..."
                                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                                    />
                                </div>

                                <div className={styles.formGroup}>
                                    <label className={styles.label} style={{ fontSize: '10px' }}>Abordagem 2: Modelo Kanban / Estoque em Fábrica</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        Mensagem destacando soluções de entregas programadas sob demanda (Kanban) e estoque de segurança dedicado para evitar rupturas de fábrica.
                                    </span>
                                    <textarea 
                                        className={styles.select}
                                        rows={3}
                                        value={valueProps.kanban_stock || ''}
                                        onChange={(e) => setValueProps({ ...valueProps, kanban_stock: e.target.value })}
                                        placeholder="Argumento sobre modelo Kanban e segurança just-in-time..."
                                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                                    />
                                </div>

                                <div className={styles.formGroup}>
                                    <label className={styles.label} style={{ fontSize: '10px' }}>Abordagem 3: Embalagens Manuais / Alta Customização</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        Mensagem direcionada para soluções sob medida, embalagens complexas ou pequenos lotes altamente customizados que grandes fornecedores não atendem.
                                    </span>
                                    <textarea 
                                        className={styles.select}
                                        rows={3}
                                        value={valueProps.custom_manufacturing || ''}
                                        onChange={(e) => setValueProps({ ...valueProps, custom_manufacturing: e.target.value })}
                                        placeholder="Argumento sobre customização e o que concorrentes grandes não fazem..."
                                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                                    />
                                </div>

                                <div className={styles.formGroup}>
                                    <label className={styles.label} style={{ fontSize: '10px' }}>Abordagem 4: Especialistas em CKD / Exportação</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        Texto voltado especificamente para indústrias exportadoras ou que utilizam sistemas de CKD (Complete Knock Down) exigindo alta resistência estrutural.
                                    </span>
                                    <textarea 
                                        className={styles.select}
                                        rows={3}
                                        value={valueProps.ckd_export || ''}
                                        onChange={(e) => setValueProps({ ...valueProps, ckd_export: e.target.value })}
                                        placeholder="Argumento para indústrias exportadoras que usam embalagens CKD..."
                                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                                    />
                                </div>

                                <div className={styles.formGroup}>
                                    <label className={styles.label} style={{ fontSize: '10px' }}>Abordagem 5: Just-In-Time / Agilidade Extrema</label>
                                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                        Discurso ressaltando flexibilidade operacional, velocidade de resposta rápida, lead times curtos e entregas ágeis no modelo Just-In-Time.
                                    </span>
                                    <textarea 
                                        className={styles.select}
                                        rows={3}
                                        value={valueProps.just_in_time || ''}
                                        onChange={(e) => setValueProps({ ...valueProps, just_in_time: e.target.value })}
                                        placeholder="Argumento sobre agilidade, lead time curto e entrega garantida..."
                                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                                    />
                                </div>
                            </div>

                            <button 
                                className={styles.saveBtn}
                                onClick={handleSaveValueProps}
                                disabled={saving}
                                style={{ marginTop: '12px' }}
                            >
                                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                {saving ? "Salvando..." : "Salvar Dores e Propostas"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 6: ICP & QUALIFICAÇÃO
                        ========================================================== */}
                    {activeTab === 'icp' && (
                        <div className={styles.card}>
                            <h2 className={styles.cardTitle}>
                                <span className={styles.cardTitleText}>
                                    <Target size={18} /> Parametrizadores de ICP e Pontuação de Leads (0-100)
                                </span>
                            </h2>

                            <StringListEditor 
                                list={icpSegments}
                                onChange={setIcpSegments}
                                label="Segmentos de Mercado Pesquisados (Prospecção Ativa)"
                                placeholder="Ex: autopeças"
                                description="Termos e nichos principais que orientarão as buscas ativas do crawler no Google Maps e LinkedIn para descobrir novas empresas."
                            />

                            <StringListEditor 
                                list={targetIndustries}
                                onChange={setTargetIndustries}
                                label="Indústrias Alvo (Foco Principal)"
                                placeholder="Ex: Autopeças e montadoras"
                                description="Indústrias ou setores de atuação prioritários do seu público-alvo (ICP) para as quais a sua proposta se adapta melhor."
                            />

                            <StringListEditor 
                                list={companyProfiles}
                                onChange={setCompanyProfiles}
                                label="Perfil Ideais de Empresa (Mapeamento)"
                                placeholder="Ex: Empresas de médio e grande porte (100+ funcionários)"
                                description="Características ideais das empresas (ex: faturamento, número de funcionários, plantas industriais) para filtragem cognitiva da IA."
                            />

                            <StringListEditor 
                                list={decisionMakers}
                                onChange={setDecisionMakers}
                                label="Cargos de Decisores Mapeados (Mapeamento)"
                                placeholder="Ex: Gerente / Analista de Compras"
                                description="Cargos e títulos de tomadores de decisão que o crawler tentará encontrar e mapear (ex: Comprador, Supervisor de Logística, etc.)."
                            />

                            <StringListEditor 
                                list={disqualifiers}
                                onChange={setDisqualifiers}
                                label="Critérios de Desqualificação Categorizados"
                                placeholder="Ex: Empresas de varejo ou food/beverage"
                                description="Regras claras e restritivas que desqualificam um lead de forma automática, economizando o tempo de vendas com perfis indesejados."
                            />

                            <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                                <span className={styles.label} style={{ fontSize: '12px' }}>Pontuação de Lead (Keywords para Matching de Segmento)</span>
                                
                                <StringListEditor 
                                    list={highFitKeywords}
                                    onChange={setHighFitKeywords}
                                    label="Keywords de Alto Encaixe (Ganho de +40 pontos no Lead)"
                                    placeholder="Ex: autopeça"
                                    description="Termos de altíssimo alinhamento que, se encontrados na descrição da empresa ou CNAE, garantem +40 pontos na qualificação do lead."
                                />

                                <StringListEditor 
                                    list={mediumFitKeywords}
                                    onChange={setMediumFitKeywords}
                                    label="Keywords de Encaixe Médio (Ganho de +20 pontos no Lead)"
                                    placeholder="Ex: plástico"
                                    description="Termos relevantes que somam +20 pontos na nota de qualificação de ICP se encontrados no perfil ou segmento da empresa."
                                />

                                <StringListEditor 
                                    list={lowFitKeywords}
                                    onChange={setLowFitKeywords}
                                    label="Keywords Rejeitadas / Baixo Encaixe (Perda de -20 pontos no Lead)"
                                    placeholder="Ex: varejo"
                                    description="Palavras-chave de baixo alinhamento ou setores indesejados que reduzem a pontuação do lead em -20 pontos para evitar falso-positivos."
                                />
                            </div>

                            <button 
                                className={styles.saveBtn}
                                onClick={handleSaveICP}
                                disabled={saving}
                                style={{ marginTop: '12px' }}
                            >
                                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                {saving ? "Salvando..." : "Salvar Configurações de ICP"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 7: HIERARCHY RULES
                        ========================================================== */}
                    {activeTab === 'hierarchy' && (
                        <div className={styles.card}>
                            <h2 className={styles.cardTitle}>
                                <span className={styles.cardTitleText}>
                                    <GitFork size={18} /> Filtros de Contato e Regras de Hierarquia
                                </span>
                            </h2>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                                <span className={styles.label} style={{ fontSize: '12px' }}>Filtros de Veto Categórico (Para evitar cargos incorretos nos departamentos)</span>
                                
                                <StringListEditor 
                                    list={forbiddenKeywords.compras || []}
                                    onChange={(newList) => setForbiddenKeywords({ ...forbiddenKeywords, compras: newList })}
                                    label="Keywords Proibidas em COMPRAS (Veto imediato)"
                                    placeholder="Ex: sales, comercial, marketing"
                                    description="Se o cargo do profissional contiver alguma dessas palavras, o sistema o desqualificará e vetará imediatamente do fluxo de Compras (impede cadastros indesejados)."
                                 />

                                <StringListEditor 
                                    list={forbiddenKeywords.logistica || []}
                                    onChange={(newList) => setForbiddenKeywords({ ...forbiddenKeywords, logistica: newList })}
                                    label="Keywords Proibidas em LOGÍSTICA & SUPPLY CHAIN (Veto imediato)"
                                    placeholder="Ex: financeiro, rh, vendas"
                                    description="Se o cargo do profissional contiver alguma dessas palavras, ele será descartado instantaneamente do fluxo de Logística (evita misturar departamentos)."
                                />
                            </div>

                            <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                                <span className={styles.label} style={{ fontSize: '12px' }}>Termos de Busca Utilizados no Crawler de Contatos</span>

                                <StringListEditor 
                                    list={purchasingKeywords}
                                    onChange={setPurchasingKeywords}
                                    label="Dicionário de Termos de Compras (Buscas Live LinkedIn)"
                                    placeholder="Ex: Comprador, Procurement, Buyer"
                                    description="Cargos e termos positivos que o robô de busca utilizará no LinkedIn para localizar e aprovar os tomadores de decisão em Compras."
                                />

                                <StringListEditor 
                                    list={logisticsKeywords}
                                    onChange={setLogisticsKeywords}
                                    label="Dicionário de Termos de Logística (Buscas Live LinkedIn)"
                                    placeholder="Ex: Logística, Supply Chain, Almoxarifado"
                                    description="Cargos e termos positivos utilizados pelo robô para rastrear, encontrar e aprovar profissionais do departamento de Logística."
                                />
                            </div>

                            <button 
                                className={styles.saveBtn}
                                onClick={handleSaveHierarchy}
                                disabled={saving}
                                style={{ marginTop: '12px' }}
                            >
                                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                {saving ? "Salvando..." : "Salvar Regras de Hierarquia"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 8: CONNECTIONS & INTEGRATIONS
                        ========================================================== */}
                    {activeTab === 'integrations' && (
                        <div className={styles.card}>
                            <h2 className={styles.cardTitle}>
                                <span className={styles.cardTitleText}>
                                    <Database size={18} /> Chaves de Conexão & Integrações SaaS
                                </span>
                            </h2>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
                                
                                {/* Pipedrive Section */}
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                        <img src="/pipedrive.png" alt="Pipedrive" style={{ width: '20px', height: '20px', objectFit: 'contain', borderRadius: '4px' }} />
                                        <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#38bdf8' }}>Integração CRM Pipedrive</h3>
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Pipedrive API Token</label>
                                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                                Chave secreta usada para criar contatos e atualizar negócios direto no seu funil do Pipedrive CRM.
                                            </span>
                                            <input 
                                                type="password" 
                                                className={styles.select} 
                                                value={pipedriveToken} 
                                                onChange={(e) => setPipedriveToken(e.target.value)} 
                                                placeholder="Insira o Token de API do seu Pipedrive..."
                                            />
                                        </div>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Pipedrive Default User ID</label>
                                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                                ID numérico do proprietário no Pipedrive que será o responsável pelos contatos criados no CRM.
                                            </span>
                                            <input 
                                                type="text" 
                                                className={styles.select} 
                                                value={pipedriveUserId} 
                                                onChange={(e) => setPipedriveUserId(e.target.value)} 
                                                placeholder="Ex: 24921888"
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* WhatsApp Section */}
                                <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                        <img src="/wppicon.png" alt="WhatsApp" style={{ width: '20px', height: '20px', objectFit: 'contain', borderRadius: '4px' }} />
                                        <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#22c55e' }}>Integração WhatsApp Service</h3>
                                    </div>
                                    <div className={styles.formGroup}>
                                        <label className={styles.label}>WhatsApp Service URL (API)</label>
                                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                            URL de conexão do robô de WhatsApp responsável por disparar as abordagens e prospecções em lote.
                                        </span>
                                        <input 
                                            type="text" 
                                            className={styles.select} 
                                            value={whatsappServiceUrl} 
                                            onChange={(e) => setWhatsappServiceUrl(e.target.value)} 
                                            placeholder="Ex: http://localhost:8001/api/v1/whatsapp"
                                        />
                                    </div>
                                </div>

                                {/* Outlook Email Section */}
                                <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                        <img src="/outlook.png" alt="Outlook" style={{ width: '20px', height: '20px', objectFit: 'contain', borderRadius: '4px' }} />
                                        <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f59e0b' }}>Conexão Email SMTP & IMAP (Outlook)</h3>
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px' }}>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>E-mail de Envio (User)</label>
                                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                                Sua conta do Outlook. No Windows, o sistema se conecta diretamente ao seu aplicativo Outlook Desktop para enviar e ler e-mails. Se houver múltiplas contas configuradas, este campo escolhe qual conta utilizar.
                                            </span>
                                            <input 
                                                type="email" 
                                                className={styles.select} 
                                                value={emailUser} 
                                                onChange={(e) => setEmailUser(e.target.value)} 
                                                placeholder="seu-usuario@outlook.com"
                                            />
                                        </div>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Senha do E-mail</label>
                                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                                Senha normal ou Senha de Aplicativo. Só é necessária para servidores SMTP de fallback se o aplicativo Outlook Desktop local estiver indisponível.
                                            </span>
                                            <input 
                                                type="password" 
                                                className={styles.select} 
                                                value={emailPassword} 
                                                onChange={(e) => setEmailPassword(e.target.value)} 
                                                placeholder="••••••••••••"
                                            />
                                        </div>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Porta SMTP</label>
                                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                                                Porta segura do servidor SMTP (Office 365) para conexões de fallback. O padrão TLS recomendado é 587.
                                            </span>
                                            <input 
                                                type="text" 
                                                className={styles.select} 
                                                value={emailPort} 
                                                onChange={(e) => setEmailPort(e.target.value)} 
                                                placeholder="Ex: 587"
                                            />
                                        </div>
                                    </div>
                                </div>

                            </div>

                            <button 
                                className={styles.saveBtn}
                                onClick={handleSaveIntegrations}
                                disabled={saving}
                                style={{ marginTop: '24px' }}
                            >
                                {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
                                {saving ? "Salvando..." : "Salvar Chaves & Conexões"}
                            </button>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
};