import { useState, useRef, useEffect } from 'react';
import { ai } from '@/services/api';
import type { ActiveTab, QuotasResponse, Product, ReferenceClient } from '../types';

export function usePreferences() {
    const [activeTab, setActiveTab] = useState<ActiveTab>('llm');
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

    // LLM
    const [preferredModel, setPreferredModel] = useState('gemini-2.5-flash');
    const [strictMode, setStrictMode] = useState(false);
    const [quotas, setQuotas] = useState<QuotasResponse>({});
    const [loadingQuotas, setLoadingQuotas] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({ gemini: true });

    // Profile
    const [companyName, setCompanyName] = useState('');
    const [companySegment, setCompanySegment] = useState('');
    const [sellerName, setSellerName] = useState('');
    const [sellerRole, setSellerRole] = useState('');
    const [companyDifferentials, setCompanyDifferentials] = useState<string[]>([]);

    // Products
    const [productsList, setProductsList] = useState<Product[]>([]);
    const [showProductForm, setShowProductForm] = useState(false);
    const [editingProductIdx, setEditingProductIdx] = useState<number | null>(null);
    const [prodName, setProdName] = useState('');
    const [prodDesc, setProdDesc] = useState('');
    const [prodUseCases, setProdUseCases] = useState<string[]>([]);

    // References
    const [referenceClients, setReferenceClients] = useState<ReferenceClient[]>([]);
    const [showClientForm, setShowClientForm] = useState(false);
    const [editingClientIdx, setEditingClientIdx] = useState<number | null>(null);
    const [clientName, setClientName] = useState('');
    const [clientSegment, setClientSegment] = useState('');

    // Value Props
    const [painPoints, setPainPoints] = useState<string[]>([]);
    const [valueProps, setValueProps] = useState<Record<string, string>>({});

    // ICP
    const [icpSegments, setIcpSegments] = useState<string[]>([]);
    const [targetIndustries, setTargetIndustries] = useState<string[]>([]);
    const [companyProfiles, setCompanyProfiles] = useState<string[]>([]);
    const [decisionMakers, setDecisionMakers] = useState<string[]>([]);
    const [disqualifiers, setDisqualifiers] = useState<string[]>([]);
    const [highFitKeywords, setHighFitKeywords] = useState<string[]>([]);
    const [mediumFitKeywords, setMediumFitKeywords] = useState<string[]>([]);
    const [lowFitKeywords, setLowFitKeywords] = useState<string[]>([]);

    // Hierarchy
    const [forbiddenKeywords, setForbiddenKeywords] = useState<Record<string, string[]>>({ compras: [], logistica: [] });
    const [purchasingKeywords, setPurchasingKeywords] = useState<string[]>([]);
    const [logisticsKeywords, setLogisticsKeywords] = useState<string[]>([]);

    // Integrations
    const [pipedriveToken, setPipedriveToken] = useState('');
    const [pipedriveUserId, setPipedriveUserId] = useState('');
    const [whatsappServiceUrl, setWhatsappServiceUrl] = useState('');
    const [emailUser, setEmailUser] = useState('');
    const [emailPassword, setEmailPassword] = useState('');
    const [emailPort, setEmailPort] = useState('');

    const pollingInterval = useRef<NodeJS.Timeout | null>(null);

    const showToast = (type: 'success' | 'error', message: string) => {
        setToast({ type, message });
        setTimeout(() => setToast(null), 4000);
    };

    const loadPreferences = async () => {
        try {
            const res = await ai.getPreference();
            if (res) {
                setPreferredModel(res.preferred_model || 'gemini-2.5-flash');
                setStrictMode(res.strict_mode || false);
            }

            const ctx = await ai.getFullContext();
            if (ctx) {
                setCompanyName(ctx.company_name || '');
                setCompanySegment(ctx.company_segment || '');
                setSellerName(ctx.seller_name || '');
                setSellerRole(ctx.seller_role || '');
                setCompanyDifferentials(ctx.company_differentials || []);

                const prods = ctx.products ? Object.values(ctx.products) : [];
                setProductsList(prods as Product[]);

                setReferenceClients(ctx.reference_clients || []);

                const icp = ctx.icp || {};
                setTargetIndustries(icp.industries || []);
                setCompanyProfiles(icp.company_profiles || []);
                setDecisionMakers(icp.decision_makers || []);
                setDisqualifiers(icp.disqualifiers || []);
                setPainPoints(icp.pain_points || []);
                setValueProps(ctx.value_propositions || {});

                const high = icp.score_rules?.filter((r: any) => r.score >= 40).map((r: any) => r.pattern) || [];
                const medium = icp.score_rules?.filter((r: any) => r.score >= 20 && r.score < 40).map((r: any) => r.pattern) || [];
                const low = icp.score_rules?.filter((r: any) => r.score < 0).map((r: any) => r.pattern) || [];
                setHighFitKeywords(high);
                setMediumFitKeywords(medium);
                setLowFitKeywords(low);

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
            if (res) setQuotas(res);
        } catch (e: any) {
            console.error("Erro ao buscar cotas:", e);
        } finally {
            setLoadingQuotas(false);
            setIsRefreshing(false);
        }
    };

    useEffect(() => {
        loadPreferences();
        fetchQuotas();
        pollingInterval.current = setInterval(() => fetchQuotas(true), 5000);
        return () => {
            if (pollingInterval.current) clearInterval(pollingInterval.current);
        };
    }, []);

    const toggleProvider = (provKey: string) => {
        setExpandedProviders(prev => ({ ...prev, [provKey]: !prev[provKey] }));
    };


    // ── Save handlers ────────────────────────────────────────────────────────────

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
            await ai.updateProfile({ segment: companySegment, differentials: companyDifferentials, seller_name: sellerName, seller_role: sellerRole });
            showToast('success', "Perfil comercial atualizado com sucesso (V2)!");
        } catch {
            showToast('error', "Erro ao salvar perfil comercial.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveProducts = async () => {
        setSaving(true);
        try {
            for (const p of productsList) await ai.addProductV2(p);
            showToast('success', "Catálogo de produtos sincronizado!");
        } catch {
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
        } catch {
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
            await ai.updateICPV2({
                industries_target: targetIndustries,
                company_size_target: companyProfiles,
                decision_makers: decisionMakers,
                disqualifiers,
                score_rules: rules,
            });
            showToast('success', "Configuração de ICP (V2) salva!");
        } catch {
            showToast('error', "Erro ao salvar ICP.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveHierarchy = async () => {
        setSaving(true);
        try {
            await ai.updateHierarchyV2({
                department_focus: 'compras',
                forbidden_keywords: forbiddenKeywords,
                whitelist_keywords: { compras: purchasingKeywords, logistica: logisticsKeywords },
                seniority_rules: { "diretor": 5, "gerente": 4, "coordenador": 3, "analista": 2 },
                department_mapping_rules: { "compras": "Suprimentos", "logistica": "Logística" },
            });
            showToast('success', "Regras de hierarquia (V2) atualizadas!");
        } catch {
            showToast('error', "Erro ao salvar regras.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveValueProps = async () => {
        setSaving(true);
        try {
            await ai.updateProfile({ segment: companySegment, differentials: companyDifferentials, seller_name: sellerName, seller_role: sellerRole, value_propositions: valueProps });
            await ai.updateICPV2({
                industries_target: targetIndustries,
                company_size_target: companyProfiles,
                decision_makers: decisionMakers,
                disqualifiers,
                pain_points: painPoints,
                score_rules: [
                    ...highFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: 40, reason: "Alto encaixe" })),
                    ...mediumFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: 20, reason: "Médio encaixe" })),
                    ...lowFitKeywords.map(k => ({ rule_type: 'segment', value_pattern: k, weight_score: -20, reason: "Baixo encaixe" })),
                ],
            });
            showToast('success', "Dores e propostas de valor atualizadas com sucesso!");
        } catch {
            showToast('error', "Erro ao salvar dores e propostas de valor.");
        } finally {
            setSaving(false);
        }
    };

    const handleSaveIntegrations = async () => {
        setSaving(true);
        try {
            await ai.updateIntegration('pipedrive', { credentials: { api_token: pipedriveToken, user_id: pipedriveUserId }, custom_settings: {} });
            await ai.updateIntegration('whatsapp', { credentials: { service_url: whatsappServiceUrl }, custom_settings: {} });
            await ai.updateIntegration('outlook', { credentials: { email_user: emailUser, email_password: emailPassword, email_port: emailPort }, custom_settings: {} });
            showToast('success', "Todas as integrações foram atualizadas com sucesso!");
        } catch (e: any) {
            console.error("Erro ao salvar integrações:", e);
            showToast('error', "Erro ao salvar credenciais das integrações.");
        } finally {
            setSaving(false);
        }
    };

    // ── Product helpers ──────────────────────────────────────────────────────────

    const handleAddOrUpdateProduct = (onError: (msg: string) => void) => {
        if (!prodName.trim()) { onError("O nome do produto é obrigatório."); return; }
        const newProd = { name: prodName.trim(), description: prodDesc.trim(), use_cases: prodUseCases };
        if (editingProductIdx !== null) {
            const updated = [...productsList];
            updated[editingProductIdx] = newProd;
            setProductsList(updated);
            setEditingProductIdx(null);
        } else {
            setProductsList([...productsList, newProd]);
        }
        setProdName(''); setProdDesc(''); setProdUseCases([]); setShowProductForm(false);
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

    // ── Client helpers ───────────────────────────────────────────────────────────

    const handleAddOrUpdateClient = (onError: (msg: string) => void) => {
        if (!clientName.trim() || !clientSegment.trim()) { onError("Preencha o nome e segmento do cliente."); return; }
        const newClient = { name: clientName.trim(), segment: clientSegment.trim() };
        if (editingClientIdx !== null) {
            const updated = [...referenceClients];
            updated[editingClientIdx] = newClient;
            setReferenceClients(updated);
            setEditingClientIdx(null);
        } else {
            setReferenceClients([...referenceClients, newClient]);
        }
        setClientName(''); setClientSegment(''); setShowClientForm(false);
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

    return {
        activeTab, setActiveTab,
        saving, toast, showToast,
        // LLM
        preferredModel, setPreferredModel,
        strictMode, setStrictMode,
        quotas, loadingQuotas, isRefreshing,
        expandedProviders, toggleProvider,
        handleSaveLLM, fetchQuotas,
        // Profile
        companyName, setCompanyName,
        companySegment, setCompanySegment,
        sellerName, setSellerName,
        sellerRole, setSellerRole,
        companyDifferentials, setCompanyDifferentials,
        handleSaveProfile,
        // Products
        productsList,
        showProductForm, setShowProductForm,
        editingProductIdx, setEditingProductIdx,
        prodName, setProdName,
        prodDesc, setProdDesc,
        prodUseCases, setProdUseCases,
        handleAddOrUpdateProduct, handleEditProduct, handleDeleteProduct, handleSaveProducts,
        // References
        referenceClients,
        showClientForm, setShowClientForm,
        editingClientIdx, setEditingClientIdx,
        clientName, setClientName,
        clientSegment, setClientSegment,
        handleAddOrUpdateClient, handleEditClient, handleDeleteClient, handleSaveReferences,
        // Value Props
        painPoints, setPainPoints,
        valueProps, setValueProps,
        handleSaveValueProps,
        // ICP
        icpSegments, setIcpSegments,
        targetIndustries, setTargetIndustries,
        companyProfiles, setCompanyProfiles,
        decisionMakers, setDecisionMakers,
        disqualifiers, setDisqualifiers,
        highFitKeywords, setHighFitKeywords,
        mediumFitKeywords, setMediumFitKeywords,
        lowFitKeywords, setLowFitKeywords,
        handleSaveICP,
        // Hierarchy
        forbiddenKeywords, setForbiddenKeywords,
        purchasingKeywords, setPurchasingKeywords,
        logisticsKeywords, setLogisticsKeywords,
        handleSaveHierarchy,
        // Integrations
        pipedriveToken, setPipedriveToken,
        pipedriveUserId, setPipedriveUserId,
        whatsappServiceUrl, setWhatsappServiceUrl,
        emailUser, setEmailUser,
        emailPassword, setEmailPassword,
        emailPort, setEmailPort,
        handleSaveIntegrations,
    };
}

export type UsePreferencesReturn = ReturnType<typeof usePreferences>;
