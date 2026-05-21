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
    X,
    Check
} from 'lucide-react';
import { ai } from '@/services/api';
import { ModelSelector, AIModel } from '@/components/chat/ModelSelector';
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
    const [subModelDropdownOpen, setSubModelDropdownOpen] = useState(false);
    const subModelDropdownRef = useRef<HTMLDivElement>(null);

    // Close sub-model dropdown on outside click
    useEffect(() => {
        if (!subModelDropdownOpen) return;
        const handler = (e: MouseEvent) => {
            if (subModelDropdownRef.current && !subModelDropdownRef.current.contains(e.target as Node)) {
                setSubModelDropdownOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [subModelDropdownOpen]);

    const getBaseModelFromFullString = (fullModel: string): AIModel => {
        const lower = fullModel.toLowerCase();
        if (lower.includes('gemini')) return 'gemini';
        if (lower.includes('claude')) return 'claude';
        if (lower.includes('cerebras') || lower.includes('llama3.1-8b') || lower.includes('qwen-3-235b') || lower.includes('gpt-oss') || lower.includes('zai-glm')) return 'cerebras';
        if (lower.includes('sambanova') || lower.includes('meta-llama-3.3-70b-instruct') || lower.includes('llama-4-scout')) return 'sambanova';
        if (lower.includes('deepseek')) return 'deepseek';
        if (lower.includes('groq') || lower.includes('llama') || lower.includes('qwen') || lower.includes('mixtral')) return 'groq';
        return 'gemini';
    };

    const handleBaseModelChange = (baseModel: AIModel) => {
        let defaultModel = 'gemini-2.5-flash';
        if (baseModel === 'gemini') defaultModel = 'gemini-2.5-flash';
        else if (baseModel === 'groq') defaultModel = 'llama-3.3-70b-versatile';
        else if (baseModel === 'claude') defaultModel = 'claude-3-5-sonnet-latest';
        else if (baseModel === 'sambanova') defaultModel = 'Meta-Llama-3.3-70B-Instruct';
        else if (baseModel === 'deepseek') defaultModel = 'deepseek-chat';
        else if (baseModel === 'cerebras') defaultModel = 'llama-3.3-70b';
        setPreferredModel(defaultModel);
    };

    const getFilteredSubModels = (baseModel: AIModel) => {
        return HUMAN_MODELS.filter(m => getBaseModelFromFullString(m.value) === baseModel);
    };
    const [quotas, setQuotas] = useState<QuotasResponse>({});
    const [loadingQuotas, setLoadingQuotas] = useState(true);
    const [saving, setSaving] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
    const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({
        gemini: true,
    });
    const [openQuotaModelDropdown, setOpenQuotaModelDropdown] = useState<string | null>(null);
    const [quotaSelectedModel, setQuotaSelectedModel] = useState<Record<string, string>>({});
    const quotaDropdownRef = useRef<Record<string, HTMLDivElement | null>>({});

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
            <div className={styles.formGroup}>
                <label className={styles.label}>{label}</label>
                {description && (
                    <p className={styles.fieldDesc}>{description}</p>
                )}
                <div className={styles.addRow}>
                    <input
                        type="text"
                        className={styles.select}
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd(); } }}
                        placeholder={placeholder || 'Adicionar item...'}
                    />
                    <button type="button" onClick={handleAdd} className={styles.saveBtn}>
                        <Plus size={13} />
                    </button>
                </div>
                <div className={styles.tagList}>
                    {list.map((item, idx) => (
                        <div key={idx} className={styles.tag}>
                            <span>{item}</span>
                            <button type="button" className={styles.tagRemove} onClick={() => handleRemove(idx)}>
                                <X size={12} />
                            </button>
                        </div>
                    ))}
                    {list.length === 0 && (
                        <span className={styles.tagEmpty}>Nenhum item adicionado.</span>
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
                        <Settings2 size={18} /> Configurações do Sistema
                    </h1>
                    <span className={styles.subtitle}>
                        Gerencie as preferências de IA, perfil do negócio, dores, propostas de valor, ICP de leads e regras de mapeamento no DB.
                    </span>
                </div>
                <button className={styles.backBtn} onClick={onBack}>
                    <ChevronLeft size={14} /> Voltar
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
                            <Sparkles size={14} />
                            <span>Preferências & Limites LLM</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'profile' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('profile')}
                        >
                            <Briefcase size={14} />
                            <span>Perfil Comercial</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'products' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('products')}
                        >
                            <Package size={14} />
                            <span>Catálogo de Produtos</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'references' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('references')}
                        >
                            <Users size={14} />
                            <span>Clientes de Referência</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'value_props' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('value_props')}
                        >
                            <Flame size={14} />
                            <span>Dores & Propostas de Valor</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'icp' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('icp')}
                        >
                            <Target size={14} />
                            <span>Regras de ICP & Qualificação</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'hierarchy' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('hierarchy')}
                        >
                            <GitFork size={14} />
                            <span>Regras de Hierarquia</span>
                        </div>
                        <div 
                            className={`${styles.sidebarItem} ${activeTab === 'integrations' ? styles.sidebarItemActive : ''}`}
                            onClick={() => setActiveTab('integrations')}
                        >
                            <Database size={14} />
                            <span>Conexões & Integrações</span>
                        </div>
                    </nav>
                </aside>

                {/* Right Tab Contents */}
                <div className={styles.settingsContent}>
                    
                    {/* TOAST SYSTEM */}
                    {toast && (
                        <div className={`${styles.toastBar} ${styles[toast.type]}`}>
                            {toast.type === 'success' ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
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
                                        <Cpu size={15} /> Modelos & Preferências de IA
                                    </span>
                                </h2>

                                <div className={styles.formGroup} style={{ marginBottom: '16px' }}>
                                    <label className={styles.label} style={{ marginBottom: '8px', display: 'block' }}>Provedor & Modelo Favorito (Padrão do Sistema)</label>
                                    <p className={styles.fieldDesc}>
                                        O cérebro de IA preferido para orquestrar as cadeias de agentes, ler biografias do LinkedIn, classificar cargos, estruturar hierarquias e redigir propostas de vendas.
                                    </p>
                                    <ModelSelector 
                                        model={getBaseModelFromFullString(preferredModel)} 
                                        setModel={handleBaseModelChange} 
                                        strictMode={strictMode} 
                                        setStrictMode={setStrictMode} 
                                        theme="dark"
                                    />
                                </div>

                                <div className={styles.formGroup} style={{ marginBottom: '20px' }}>
                                    <label className={styles.label}>Modelo Específico do Provedor</label>
                                    <p className={styles.fieldDesc}>
                                        Escolha a versão ou variante de modelo exata para o provedor de IA selecionado acima.
                                    </p>
                                    {/* Premium Sub-Model Dropdown */}
                                    <div className={styles.subModelWrapper} ref={subModelDropdownRef}>
                                        {(() => {
                                            const subModels = getFilteredSubModels(getBaseModelFromFullString(preferredModel));
                                            const selectedSub = subModels.find(m => m.value === preferredModel) || subModels[0];
                                            const providerInfo = HUMAN_PROVIDERS[getBaseModelFromFullString(preferredModel) as keyof typeof HUMAN_PROVIDERS];
                                            return (
                                                <>
                                                    <button
                                                        type="button"
                                                        className={styles.subModelTrigger}
                                                        onClick={() => setSubModelDropdownOpen(v => !v)}
                                                    >
                                                        {providerInfo?.image && (
                                                            <img
                                                                src={providerInfo.image}
                                                                alt={providerInfo.label}
                                                                className={styles.subModelTriggerLogo}
                                                            />
                                                        )}
                                                        <span className={styles.subModelTriggerLabel}>
                                                            {selectedSub?.label || preferredModel}
                                                        </span>
                                                        {selectedSub?.description && (
                                                            <span className={styles.subModelTriggerDesc}>
                                                                {selectedSub.description}
                                                            </span>
                                                        )}
                                                        <ChevronDown
                                                            size={14}
                                                            className={`${styles.subModelChevron}${subModelDropdownOpen ? ' ' + styles.open : ''}`}
                                                        />
                                                    </button>

                                                    {subModelDropdownOpen && (
                                                        <div className={styles.subModelDropdown}>
                                                            <div className={styles.subModelOptions}>
                                                                {subModels.map(m => {
                                                                    const isSelected = m.value === preferredModel;
                                                                    return (
                                                                        <button
                                                                            key={m.value}
                                                                            type="button"
                                                                            className={`${styles.subModelOption}${isSelected ? ' ' + styles.selected : ''}`}
                                                                            onClick={() => {
                                                                                setPreferredModel(m.value);
                                                                                setSubModelDropdownOpen(false);
                                                                            }}
                                                                        >
                                                                            {providerInfo?.image && (
                                                                                <img
                                                                                    src={providerInfo.image}
                                                                                    alt={providerInfo.label}
                                                                                    className={styles.subModelOptionLogo}
                                                                                />
                                                                            )}
                                                                            <div className={styles.subModelOptionInfo}>
                                                                                <span className={styles.subModelOptionName}>{m.label}</span>
                                                                                {m.description && (
                                                                                    <span className={styles.subModelOptionDesc}>{m.description}</span>
                                                                                )}
                                                                            </div>
                                                                            <div className={styles.subModelOptionCheck}>
                                                                                {isSelected && <Check size={13} />}
                                                                            </div>
                                                                        </button>
                                                                    );
                                                                })}
                                                            </div>
                                                        </div>
                                                    )}
                                                </>
                                            );
                                        })()}
                                    </div>
                                </div>

                                <div className={styles.switchWrapper} style={{ marginBottom: '20px' }}>
                                    <button 
                                        type="button" 
                                        onClick={() => setStrictMode(!strictMode)} 
                                        className={`${styles.switchButton} ${strictMode ? styles.switchActive : ''}`}
                                    >
                                        <div className={styles.switchInfo}>
                                            <span className={styles.switchTitle}>{strictMode ? "Strict Mode Ativo" : "Strict Mode Inativo"}</span>
                                            <span className={styles.switchDesc}>
                                                {strictMode 
                                                    ? "Forçando o uso exclusivo do modelo preferido com retries agressivos" 
                                                    : "Permite fallback automático para outros provedores se houver rate-limiting"}
                                             </span>
                                        </div>
                                        <div className={styles.switchToggle}>
                                            <div className={styles.switchKnob} />
                                        </div>
                                    </button>
                                </div>

                                <button 
                                    className={styles.saveBtn}
                                    onClick={handleSaveLLM}
                                    disabled={saving}
                                >
                                    {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
                                    {saving ? "Salvando..." : "Salvar Preferências"}
                                </button>
                            </div>

                            <div style={{ height: '32px' }} />

                            {/* Quota Dashboard */}
                            <div className={styles.card}>
                                <h2 className={styles.cardTitle}>
                                    <span className={styles.cardTitleText}>
                                        <Activity size={15} /> Limites de Cotas em Tempo Real
                                    </span>
                                    {isRefreshing && (
                                        <div className={styles.refreshingIndicator}>
                                            <RefreshCw size={13} className={styles.spin} />
                                            <span style={{ fontSize: '11px' }}>atualizando...</span>
                                        </div>
                                    )}
                                </h2>

                                {loadingQuotas ? (
                                    <div className={styles.noDataText} style={{ display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                                        <RefreshCw size={18} className={styles.spin} />
                                        <span>Sincronizando quotas com os provedores de IA...</span>
                                    </div>
                                ) : (
                                    <div className={styles.providersList}>
                                        {Object.entries(quotas).map(([provKey, modelsMap]) => {
                                            const meta = HUMAN_PROVIDERS[provKey] || { label: provKey, logo: "🤖", color: "var(--sw-primary)" };
                                            const isRateLimited = Object.values(modelsMap).some(m => m.status === 'rate_limited');
                                            const isAnyNoCredits = Object.values(modelsMap).some(m => m.status === 'no_credits');
                                            const isExpanded = expandedProviders[provKey] ?? false;

                                            return (
                                                <div key={provKey} className={styles.section}>
                                                    <div 
                                                        className={styles.sectionHeader}
                                                        onClick={() => toggleProvider(provKey)}
                                                        style={{ cursor: 'pointer', userSelect: 'none' }}
                                                    >
                                                        <div className={styles.sectionHeaderLeft}>
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
                                                        <div className={styles.sectionHeaderRight}>
                                                            <div className={`${styles.providerBadge} ${(isRateLimited || isAnyNoCredits) ? styles.badgeCritical : styles.badgeHealthy}`}>
                                                                {isRateLimited ? (
                                                                    <>
                                                                        <AlertTriangle size={12} />
                                                                        <span>COOLDOWN</span>
                                                                    </>
                                                                ) : isAnyNoCredits ? (
                                                                    <>
                                                                        <AlertTriangle size={12} />
                                                                        <span>SEM SALDO</span>
                                                                    </>
                                                                ) : (
                                                                    <>
                                                                        <CheckCircle2 size={12} />
                                                                        <span>ATIVO</span>
                                                                    </>
                                                                )}
                                                            </div>
                                                            <ChevronDown 
                                                                size={14} 
                                                                className={`${styles.chevron} ${isExpanded ? styles.chevronExpanded : ''}`}
                                                            />
                                                        </div>
                                                    </div>

                                                    {isExpanded && (
                                                        <div className={styles.modelQuotaList}>
                                                            {/* Quota Rows — ModelSelector-style */}
                                                            {Object.entries(modelsMap).length === 0 ? (
                                                                <div className={styles.noDataText}>Nenhum modelo registrado.</div>
                                                            ) : Object.entries(modelsMap).map(([modelName, detail]) => {
                                                                const isRL = detail.status === 'rate_limited' || detail.status === 'cooldown';
                                                                const isNC = detail.status === 'no_credits';
                                                                const pct = (isRL || isNC) ? 0 : detail.pct;
                                                                const descLine = isRL
                                                                    ? 'Rate limited — em cooldown'
                                                                    : isNC
                                                                        ? 'Sem créditos disponíveis'
                                                                        : `${detail.remaining} / ${detail.limit} req${detail.tokens_limit ? ` · ${detail.tokens_pct}% tokens (${Math.round((detail.tokens_remaining || 0) / 1000)}k/${Math.round(detail.tokens_limit / 1000)}k)` : ''}`;
                                                                return (
                                                                    <div key={modelName} className={styles.quotaModelRow}>
                                                                        <div className={styles.quotaModelRowIcon}>
                                                                            {meta.image
                                                                                ? <img src={meta.image} alt={meta.label} className={styles.quotaModelRowLogo} />
                                                                                : <span style={{ fontSize: '14px' }}>{meta.logo}</span>
                                                                            }
                                                                        </div>
                                                                        <div className={styles.quotaModelRowInfo}>
                                                                            <div className={styles.quotaModelRowNameRow}>
                                                                                <span className={styles.quotaModelRowName}>{modelName}</span>
                                                                                <span className={`${styles.quotaModelRowBadge} ${isRL || isNC ? styles.quotaModelRowBadgeCritical : styles.quotaModelRowBadgeOk}`}>
                                                                                    {isRL ? 'COOLDOWN' : isNC ? 'SEM SALDO' : `${pct}%`}
                                                                                </span>
                                                                            </div>
                                                                            <span className={styles.quotaModelRowDesc}>{descLine}</span>
                                                                            <div className={styles.quotaModelRowBar}>
                                                                                <div
                                                                                    className={`${styles.quotaModelRowBarFill} ${(isRL || isNC) ? styles.progressRed : getProgressColorClass(pct)}`}
                                                                                    style={{ width: `${pct}%` }}
                                                                                />
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })}
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
                                    <Briefcase size={15} /> Identidade & Perfil Comercial da Empresa
                                </span>
                            </h2>

                            <div className={styles.grid2}>
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Nome da Empresa</label>
                                    <p className={styles.fieldDesc}>
                                        O nome oficial ou fantasia que a inteligência artificial mencionará nas mensagens ao falar em nome da sua empresa.
                                    </p>
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
                                    <p className={styles.fieldDesc}>
                                        O nicho específico de mercado que descreve a sua operação para dar contexto ao robô na prospecção.
                                    </p>
                                    <input 
                                        type="text" 
                                        className={styles.select}
                                        value={companySegment}
                                        onChange={(e) => setCompanySegment(e.target.value)}
                                        placeholder="Setor detalhado (Ex: Embalagens de Papelão Ondulado)"
                                    />
                                </div>
                            </div>

                            <div className={styles.grid2}>
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Nome do Vendedor Principal</label>
                                    <p className={styles.fieldDesc}>
                                        Nome de quem assinará as mensagens de prospecção fria enviadas por e-mail ou WhatsApp.
                                    </p>
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
                                    <p className={styles.fieldDesc}>
                                        Cargo institucional do remetente (Ex: Executivo de Contas, Diretor Comercial, etc.) para assinar os e-mails.
                                    </p>
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
                                {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
                                {saving ? "Salvando..." : "Salvar Perfil Comercial"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 3: CATÁLOGO DE PRODUTOS
                        ========================================================== */}
                    {activeTab === 'products' && (
                        <div className={styles.card}>
                            <div className={styles.cardTitleRow}>
                                <h2 className={styles.cardTitle}>
                                    <span className={styles.cardTitleText}>
                                        <Package size={15} /> Catálogo de Produtos e Serviços Ofertados
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
                                    >
                                        <Plus size={13} /> Adicionar Produto
                                    </button>
                                )}
                            </div>

                            {/* Product Form */}
                            {showProductForm && (
                                <div className={styles.inlineForm}>
                                    <h3 className={styles.inlineFormHeader}>
                                        <span>{editingProductIdx !== null ? "Editar Produto" : "Novo Produto"}</span>
                                        <button type="button" className={styles.inlineFormClose} onClick={() => setShowProductForm(false)}>
                                            <X size={14} />
                                        </button>
                                    </h3>

                                    <div className={styles.formGroup}>
                                        <label className={styles.label}>Nome do Produto / Serviço</label>
                                        <p className={styles.fieldDesc}>
                                            O nome comercial do item ou serviço oferecido. A IA usará este termo exato ao elaborar as abordagens.
                                        </p>
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
                                        <p className={styles.fieldDesc}>
                                            Especificações técnicas, benefícios e materiais. A inteligência artificial lê este campo para entender as vantagens do produto e gerar ganchos altamente contextualizados.
                                        </p>
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

                                    <div className={styles.inlineFormActions}>
                                        <button type="button" className={styles.backBtn} onClick={() => setShowProductForm(false)}>
                                            Cancelar
                                        </button>
                                        <button type="button" className={styles.saveBtn} onClick={handleAddOrUpdateProduct}>
                                            {editingProductIdx !== null ? "Atualizar na Lista" : "Adicionar à Lista"}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Products Grid */}
                            <div className={styles.settingsList}>
                                {productsList.map((prod, idx) => (
                                    <div key={idx} className={styles.productCard}>
                                        <div className={styles.productCardHeader}>
                                            <div className={styles.productTitleArea}>
                                                <Package size={14} className={styles.productIcon} />
                                                <span className={styles.productTitle}>{prod.name}</span>
                                            </div>
                                            <div className={styles.productActions}>
                                                <button onClick={() => handleEditProduct(idx)} className={styles.editBtn} title="Editar">
                                                    <Edit3 size={13} />
                                                </button>
                                                <button onClick={() => handleDeleteProduct(idx)} className={styles.deleteBtn} title="Deletar">
                                                    <Trash2 size={13} />
                                                </button>
                                            </div>
                                        </div>
                                        
                                        {prod.description && (
                                            <div className={styles.productDescription}>
                                                {prod.description}
                                            </div>
                                        )}

                                        {prod.use_cases && prod.use_cases.length > 0 && (
                                            <div className={styles.productUseCases}>
                                                {prod.use_cases.map((uc: string, uIdx: number) => (
                                                    <span key={uIdx} className={styles.useCaseTag}>{uc}</span>
                                                ))}
                                            </div>
                                        )}
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
                                {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
                                {saving ? "Salvando..." : "Salvar Catálogo de Produtos"}
                            </button>
                        </div>
                    )}

                    {/* ==========================================================
                        TAB 4: CLIENTES DE REFERÊNCIA
                        ========================================================== */}
                    {activeTab === 'references' && (
                        <div className={styles.card}>
                            <div className={styles.cardTitleRow}>
                                <h2 className={styles.cardTitle}>
                                    <span className={styles.cardTitleText}>
                                        <Users size={15} /> Clientes de Referência (Autoridade no Outreach)
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
                                    >
                                        <Plus size={13} /> Adicionar Cliente
                                    </button>
                                )}
                            </div>

                            {/* Client Form */}
                            {showClientForm && (
                                <div className={styles.inlineForm}>
                                    <h3 className={styles.inlineFormHeader}>
                                        <span>{editingClientIdx !== null ? "Editar Cliente de Referência" : "Novo Cliente de Referência"}</span>
                                        <button type="button" className={styles.inlineFormClose} onClick={() => setShowClientForm(false)}>
                                            <X size={14} />
                                        </button>
                                    </h3>

                                    <div className={styles.grid2}>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Nome do Cliente (Marca/Empresa)</label>
                                            <p className={styles.fieldDesc}>
                                                Nome de uma marca de destaque que já seja seu cliente ativo para atuar como prova social.
                                            </p>
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
                                            <p className={styles.fieldDesc}>
                                                O setor de atuação ou perfil do cliente. A IA lerá esta descrição para fazer matching de segmento com os novos leads analisados.
                                            </p>
                                            <input 
                                                type="text" 
                                                className={styles.select}
                                                value={clientSegment}
                                                onChange={(e) => setClientSegment(e.target.value)}
                                                placeholder="Ex: Montadora automotiva"
                                            />
                                        </div>
                                    </div>

                                    <div className={styles.inlineFormActions}>
                                        <button type="button" className={styles.backBtn} onClick={() => setShowClientForm(false)}>
                                            Cancelar
                                        </button>
                                        <button type="button" className={styles.saveBtn} onClick={handleAddOrUpdateClient}>
                                            {editingClientIdx !== null ? "Atualizar na Lista" : "Adicionar à Lista"}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Clients list */}
                            <div className={styles.settingsList}>
                                {referenceClients.map((client, idx) => (
                                    <div key={idx} className={styles.clientCard}>
                                        <div className={styles.clientCardHeader}>
                                            <div className={styles.clientTitleArea}>
                                                <Users size={14} className={styles.clientIcon} />
                                                <span className={styles.clientTitle}>{client.name}</span>
                                                <span className={styles.clientSeparator}>•</span>
                                                <span className={styles.clientSegment}>{client.segment}</span>
                                            </div>
                                            <div className={styles.clientActions}>
                                                <button onClick={() => handleEditClient(idx)} className={styles.editBtn} title="Editar">
                                                    <Edit3 size={13} />
                                                </button>
                                                <button onClick={() => handleDeleteClient(idx)} className={styles.deleteBtn} title="Deletar">
                                                    <Trash2 size={13} />
                                                </button>
                                            </div>
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
                                {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
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

                            <div className={styles.sectionDivider}>
                                <span className={styles.sectionLabel}>Textos de Propostas de Valor (Ângulos de Abordagem)</span>
                                
                                <div className={styles.formGroup}>
                                    <label className={styles.label}>Abordagem 1: Plano B / Mitigação de Risco</label>
                                    <p className={styles.fieldDesc}>
                                        Texto focado em posicionar sua empresa como fornecedora alternativa ou reserva estratégica (Plano B) para garantir a segurança da operação do lead.
                                    </p>
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
                                    <label className={styles.label}>Abordagem 2: Modelo Kanban / Estoque em Fábrica</label>
                                    <p className={styles.fieldDesc}>
                                        Mensagem destacando soluções de entregas programadas sob demanda (Kanban) e estoque de segurança dedicado para evitar rupturas de fábrica.
                                    </p>
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
                                    <label className={styles.label}>Abordagem 3: Embalagens Manuais / Alta Customização</label>
                                    <p className={styles.fieldDesc}>
                                        Mensagem direcionada para soluções sob medida, embalagens complexas ou pequenos lotes altamente customizados que grandes fornecedores não atendem.
                                    </p>
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
                                    <label className={styles.label}>Abordagem 4: Especialistas em CKD / Exportação</label>
                                    <p className={styles.fieldDesc}>
                                        Texto voltado especificamente para indústrias exportadoras ou que utilizam sistemas de CKD (Complete Knock Down) exigindo alta resistência estrutural.
                                    </p>
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
                                    <label className={styles.label}>Abordagem 5: Just-In-Time / Agilidade Extrema</label>
                                    <p className={styles.fieldDesc}>
                                        Discurso ressaltando flexibilidade operacional, velocidade de resposta rápida, lead times curtos e entregas ágeis no modelo Just-In-Time.
                                    </p>
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
                                {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
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
                                    <Target size={15} /> Parametrizadores de ICP e Pontuação de Leads (0-100)
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

                            <div className={styles.sectionDivider}>
                                <span className={styles.sectionLabel}>Pontuação de Lead (Keywords para Matching de Segmento)</span>
                                
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
                                {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
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
                                    <GitFork size={15} /> Filtros de Contato e Regras de Hierarquia
                                </span>
                            </h2>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                                <span className={styles.sectionLabel}>Filtros de Veto Categórico (Para evitar cargos incorretos nos departamentos)</span>
                                
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

                            <div className={styles.sectionDivider}>
                                <span className={styles.sectionLabel}>Termos de Busca Utilizados no Crawler de Contatos</span>

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
                                {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
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
                                    <Database size={15} /> Chaves de Conexão & Integrações SaaS
                                </span>
                            </h2>

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
                                
                                {/* Pipedrive Section */}
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                                    <h3 className={styles.integrationTitle}>
                                        <img src="/pipedrive.png" alt="Pipedrive" className={styles.integrationTitleIcon} />
                                        Integração CRM Pipedrive
                                    </h3>
                                    <div className={styles.grid2}>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>Pipedrive API Token</label>
                                            <p className={styles.fieldDesc}>
                                                Chave secreta usada para criar contatos e atualizar negócios direto no seu funil do Pipedrive CRM.
                                            </p>
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
                                            <p className={styles.fieldDesc}>
                                                ID numérico do proprietário no Pipedrive que será o responsável pelos contatos criados no CRM.
                                            </p>
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
                                <div className={styles.sectionDivider}>
                                    <h3 className={styles.integrationTitle}>
                                        <img src="/wppicon.png" alt="WhatsApp" className={styles.integrationTitleIcon} />
                                        Integração WhatsApp Service
                                    </h3>
                                    <div className={styles.formGroup}>
                                        <label className={styles.label}>WhatsApp Service URL (API)</label>
                                        <p className={styles.fieldDesc}>
                                            URL de conexão do robô de WhatsApp responsável por disparar as abordagens e prospecções em lote.
                                        </p>
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
                                <div className={styles.sectionDivider}>
                                    <h3 className={styles.integrationTitle}>
                                        <img src="/outlook.png" alt="Outlook" className={styles.integrationTitleIcon} />
                                        Conexão Email SMTP & IMAP (Outlook)
                                    </h3>
                                    <div className={styles.grid3}>
                                        <div className={styles.formGroup}>
                                            <label className={styles.label}>E-mail de Envio (User)</label>
                                            <p className={styles.fieldDesc}>
                                                Sua conta do Outlook. No Windows, o sistema se conecta diretamente ao seu aplicativo Outlook Desktop para enviar e ler e-mails. Se houver múltiplas contas configuradas, este campo escolhe qual conta utilizar.
                                            </p>
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
                                            <p className={styles.fieldDesc}>
                                                Senha normal ou Senha de Aplicativo. Só é necessária para servidores SMTP de fallback se o aplicativo Outlook Desktop local estiver indisponível.
                                            </p>
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
                                            <p className={styles.fieldDesc}>
                                                Porta segura do servidor SMTP (Office 365) para conexões de fallback. O padrão TLS recomendado é 587.
                                            </p>
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
                                {saving ? <RefreshCw size={13} className={styles.spin} /> : <Save size={13} />}
                                {saving ? "Salvando..." : "Salvar Chaves & Conexões"}
                            </button>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
};