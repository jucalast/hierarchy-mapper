import { useState, useCallback, useRef, useEffect } from 'react';
import { hierarchy, organizations } from '@/services/api';
import { useNotifications } from '@/contexts/NotificationContext';

interface DiscoveryWorkflowProps {
    defaultCnpj?: string;
    useHierarchy: any;
    currentOrgId: number | null;
    setCurrentOrgId: (id: number | null) => void;
    setChatOrgId: (id: number | null) => void;
    rawEmployees: any[];
    fetchPipedriveOrgs: () => void;
    setPipedriveOrgs: (updater: (prev: any[]) => any[]) => void;
    pathname: string;
}

export function useDiscoveryWorkflow({
    defaultCnpj = "",
    useHierarchy,
    currentOrgId,
    setCurrentOrgId,
    setChatOrgId,
    rawEmployees,
    fetchPipedriveOrgs,
    setPipedriveOrgs,
    pathname
}: DiscoveryWorkflowProps) {
    const { addNotification } = useNotifications();
    const [step, setStep] = useState<"input" | "confirm" | "scanning" | "loading" | "initial">("input");
    const [selectedModel, setSelectedModelState] = useState<string>(() => {
        if (typeof window !== "undefined") {
            return localStorage.getItem("selected-hierarchy-model") || "gemini";
        }
        return "gemini";
    });
    const [strictMode, setStrictModeState] = useState<boolean>(() => {
        if (typeof window !== "undefined") {
            return localStorage.getItem("selected-hierarchy-strict-mode") === "true";
        }
        return false;
    });

    const setSelectedModel = useCallback((val: string) => {
        setSelectedModelState(val);
        localStorage.setItem("selected-hierarchy-model", val);
    }, []);

    const setStrictMode = useCallback((val: boolean) => {
        setStrictModeState(val);
        localStorage.setItem("selected-hierarchy-strict-mode", String(val));
    }, []);
    const [cnpj, setCnpj] = useState(defaultCnpj);
    const [domainTarget, setDomainTarget] = useState("");
    const [productFocus, setProductFocus] = useState("");
    const [areaFocus, setAreaFocus] = useState<"compras" | "logistica">("compras");
    const [confirmedBrand, setConfirmedBrand] = useState("");
    const [confirmedLogo, setConfirmedLogo] = useState("");
    const [confirmedFollowers, setConfirmedFollowers] = useState("");

    useEffect(() => {
        console.log(`[useDiscoveryWorkflow State Monitor] step: "${step}", confirmedBrand: "${confirmedBrand}", cnpj: "${cnpj}", domainTarget: "${domainTarget}"`);
    }, [step, confirmedBrand, cnpj, domainTarget]);

    const [refreshDrawerTrigger, setRefreshDrawerTrigger] = useState(0);
    const [enrichingIds, setEnrichingIds] = useState<Set<number>>(new Set());
    const [partners, setPartners] = useState<any[]>([]);
    const [mappingMode, setMappingMode] = useState<'discovery' | 'scan'>('discovery');
    const [confirmedLinkedInUrl, setConfirmedLinkedInUrl] = useState('');

    const {
        discoverBrandStream,
        fetchHierarchy,
        brandOptions,
        setBrandOptions,
        discovering,
        cancelDiscovery,
        confirmIntelligence,
        resetHierarchy
    } = useHierarchy;

    useEffect(() => {
        const isOrgRoute = pathname.match(/\/org\/(\d+)/);
        if (!isOrgRoute) {
            console.log("[useDiscoveryWorkflow] Path changed to non-org route. Resetting states.");
            setStep("input");
            setCnpj("");
            setDomainTarget("");
            setProductFocus("");
            setAreaFocus("compras");
            setConfirmedBrand("");
            setConfirmedLogo("");
            setConfirmedFollowers("");
            setBrandOptions([]);
            setPartners([]);
            setMappingMode('discovery');
            setConfirmedLinkedInUrl('');
        }
    }, [pathname, setBrandOptions]);

    // Helper para sanitizar valores
    const sanitizeVal = (val: any) => {
        if (!val || typeof val !== "string") return "";
        const junk = ["not provided", "n/a", "unknown", "null", "none"];
        return junk.includes(val.toLowerCase().trim()) ? "" : val;
    };

    // Helper para formatar CNPJ
    const formatCnpj = (val: string) => {
        const s = val.replace(/\D/g, '').slice(0, 14);
        if (s.length <= 2) return s;
        if (s.length <= 5) return `${s.slice(0, 2)}.${s.slice(2)}`;
        if (s.length <= 8) return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5)}`;
        if (s.length <= 12) return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8)}`;
        return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`;
    };

    const handleSearch = useCallback(async (e?: React.FormEvent) => {
        if (e) e.preventDefault();
        
        if (step === "input") {
            if (!domainTarget && !confirmedBrand) {
                addNotification('error', "Insira o Domínio ou o Nome para busca no LinkedIn");
                return;
            }
            try {
                await discoverBrandStream(cnpj, domainTarget, true, (candidate: any) => {
                    console.log(`[Discovery] Candidato: ${candidate.name}`);
                });
            } catch (err) {
                addNotification('error', "Erro de conexão ao buscar marca.");
            }
        } else if (step === "confirm" || step === "scanning") {
            if (!confirmedBrand) { addNotification('error', "Marca inválida."); return; }

            setStep("scanning");
            setBrandOptions([]);
            setRefreshDrawerTrigger(prev => prev + 1);

            // 🎯 Identifica se estamos mapeando a mesma empresa que já está na tela
            const rootNode = rawEmployees.find(e => e.id === 'root_company' || e.level === 0);
            const isSameCompany = rootNode && (
                rootNode.name.toLowerCase().includes(confirmedBrand.toLowerCase()) || 
                confirmedBrand.toLowerCase().includes(rootNode.name.toLowerCase()) ||
                (rootNode as any).cnpj === cnpj.replace(/\D/g, '') ||
                (rootNode as any).domain === domainTarget
            );

            // Se for a mesma empresa, filtramos para manter Root, Sócios e contatos
            // do Pipedrive (CRM) — estes últimos não são "descobertos" pelo scan, então
            // não devem sumir; se o scan os reencontrar, o merge por linkedin/nome/
            // pipedrive_id atualiza o registro em vez de duplicar.
            const rootAndPartnersOnly = isSameCompany ? rawEmployees.filter(emp => {
                const isRoot = emp.id === 'root_company' || emp.level === 0;
                const isPartner = emp.level === 6 || String(emp.id).startsWith('partner_');
                const isPartnerDept = emp.department && (
                    emp.department.includes('QSA') ||
                    emp.department.includes('Sócio') ||
                    emp.department.includes('Societário') ||
                    emp.department.includes('Conselho')
                );
                const isPipedrive = emp.source === 'pipedrive' || !!emp.pipedrive_id;
                return isRoot || isPartner || isPartnerDept || isPipedrive;
            }) : [];

            // 🧹 Limpa o estado persistido ANTES de iniciar novo scan para garantir começo do zero
            if (currentOrgId) {
                const { useChatStore } = await import('../store/chatStore');
                useChatStore.getState().setRawEmployees(currentOrgId, []);
                useChatStore.getState().setRawBackendEdges(currentOrgId, []);
                // Limpa cache de layout para o novo mapeamento
                localStorage.removeItem(`layout-cache-${currentOrgId}`);
                localStorage.removeItem(`edges-cache-${currentOrgId}`);
            }

            fetchHierarchy(
                cnpj,
                domainTarget,
                confirmedBrand,
                confirmedLogo,
                productFocus,
                areaFocus,
                addNotification,
                partners,
                currentOrgId,
                rootAndPartnersOnly,
                selectedModel,
                strictMode
            );
        }
    }, [
        step, cnpj, domainTarget, confirmedBrand, confirmedLogo, productFocus, areaFocus,
        discoverBrandStream, fetchHierarchy, addNotification, 
        partners, currentOrgId, rawEmployees, setBrandOptions, selectedModel, strictMode
    ]);

    const handleBrandSelect = useCallback(async (brandObj: any) => {
        if (discovering) cancelDiscovery();

        if (!brandObj) {
            setConfirmedBrand("");
            setConfirmedLogo("");
            setConfirmedFollowers("");
            setPartners([]);
            setStep("input");
            return;
        }

        if (brandObj.type === 'person') {
            const linkedin = brandObj.originalEmployee?.linkedin || brandObj.originalEmployee?.url;
            if (linkedin && linkedin.startsWith('http')) {
                window.open(linkedin, '_blank');
            } else {
                addNotification('info', `Analisando ${brandObj.name} (LinkedIn não disponível)`);
            }
            return;
        }

        const name = brandObj.name || brandObj.url || "";
        const logo = brandObj.logo || "";
        const followers = brandObj.followers || "";
        const newPartners = brandObj.partners || [];

        const cleanBrandName = name.replace(/\|?\s*Linked\s*In/gi, '').trim();
        setConfirmedBrand(cleanBrandName);
        setConfirmedLogo(logo);
        setConfirmedFollowers(followers);
        setPartners(newPartners);
        setConfirmedLinkedInUrl(brandObj.url || '');
        setStep("confirm");
        setBrandOptions([]);

        if (cnpj) {
            const result = await confirmIntelligence({
                name: cleanBrandName,
                cnpj,
                domain: domainTarget,
                address: "",
                pipedrive_id: currentOrgId || undefined,
                linkedin_url: brandObj.url || "",
                logo_url: logo,
                partners: newPartners
            });

            if (result && result.status !== "error") {
                const isUpdate = result.is_update || result.status === "updated" || result.status === "success";
                const newOrgId = result.pipedrive_id || result.local_id;

                if (!currentOrgId && newOrgId) {
                    setCurrentOrgId(Number(newOrgId));
                    // Expande a empresa no Drawer automaticamente
                    localStorage.setItem('drawer-expanded-org-id', newOrgId.toString());
                    window.dispatchEvent(new CustomEvent('drawer_reset_expansion'));
                    // Dispara também um evento para abrir o drawer caso esteja fechado
                    window.dispatchEvent(new CustomEvent('drawer_open'));
                }
                addNotification('success', isUpdate ? "Empresa atualizada!" : "Empresa integrada!");

                if (!currentOrgId) fetchPipedriveOrgs();
                else {
                    setPipedriveOrgs(prev => prev.map(org =>
                        Number(org.id) === currentOrgId
                            ? { ...org, cnpj, domain: domainTarget, logo, name: cleanBrandName }
                            : org
                    ));
                }
            } else {
                addNotification('error', "Erro ao salvar dados da empresa.");
            }
        }
    }, [
        discovering, cancelDiscovery, addNotification, cnpj, domainTarget,
        currentOrgId, setCurrentOrgId, fetchPipedriveOrgs, setPipedriveOrgs,
        confirmIntelligence, setBrandOptions
    ]);

    const handleAutoEnrich = useCallback(async () => {
        if (!cnpj || enrichingIds.has(999)) return;
        setEnrichingIds(prev => new Set(prev).add(999));
        try {
            const data = await hierarchy.enrichIntelligence({
                name: confirmedBrand.trim() || 'Empresa',
                cnpj,
                force: true,
            });

            if (data.success && data.main_option) {
                const main = data.main_option;
                const cleanDomain = sanitizeVal(main.domain);
                const cleanCnpj = formatCnpj(sanitizeVal(main.cnpj));
                const officialName = sanitizeVal(main.official_name);

                if (cleanDomain) setDomainTarget(cleanDomain);
                if (cleanCnpj) setCnpj(cleanCnpj);

                if (!currentOrgId && cleanCnpj) {
                    try {
                        if (officialName) setConfirmedBrand(officialName);
                        await new Promise(resolve => setTimeout(resolve, 500));
                        await fetchPipedriveOrgs();

                        const rawCnpjClean = cleanCnpj.replace(/\D/g, '');
                        const orgsList = await organizations.listOrganizations();
                        const newOrg = Array.isArray(orgsList)
                            ? orgsList.find((o: any) => o.cnpj && o.cnpj.replace(/\D/g, '') === rawCnpjClean)
                            : null;

                        if (newOrg) {
                            setCurrentOrgId(Number(newOrg.id));
                            localStorage.setItem('last-viewed-org', JSON.stringify(newOrg));
                            
                            // Expande a empresa no Drawer automaticamente
                            localStorage.setItem('drawer-expanded-org-id', newOrg.id.toString());
                            window.dispatchEvent(new CustomEvent('drawer_reset_expansion'));
                            window.dispatchEvent(new CustomEvent('drawer_open'));
                            
                            if (newOrg.logo) setConfirmedLogo(newOrg.logo);
                            addNotification('success', `Empresa '${officialName || "Nova Empresa"}' integrada!`);
                        }
                    } catch (linkErr) {
                        console.error("[NewCompany] Erro ao vincular:", linkErr);
                    }
                }
            } else {
                addNotification('error', "Dados não encontrados para este CNPJ.");
            }
        } catch (err) {
            addNotification('error', "Erro ao consultar inteligência.");
        } finally {
            setEnrichingIds(prev => {
                const n = new Set(prev);
                n.delete(999);
                return n;
            });
        }
    }, [cnpj, enrichingIds, confirmedBrand, currentOrgId, fetchPipedriveOrgs, addNotification, setCurrentOrgId, setConfirmedBrand, setConfirmedLogo]);

    const lastSearchedCnpj = useRef("");

    const resetWorkflow = useCallback(() => {
        setStep("input");
        setCnpj("");
        setDomainTarget("");
        setProductFocus("");
        setAreaFocus("compras");
        setConfirmedBrand("");
        setConfirmedLogo("");
        setConfirmedFollowers("");
        setBrandOptions([]);
        setCurrentOrgId(null);
        setChatOrgId(null);
        setPartners([]);
        setMappingMode('discovery');
        setConfirmedLinkedInUrl('');
        resetHierarchy();
        localStorage.removeItem('last-viewed-org');
        lastSearchedCnpj.current = "";
    }, [setBrandOptions, setCurrentOrgId, setChatOrgId, resetHierarchy]);

    useEffect(() => {
        const digits = cnpj.replace(/\D/g, '');
        if (digits.length === 14) {
            const formatted = formatCnpj(digits);
            if (cnpj !== formatted) {
                setCnpj(formatted);
            }
            // Only auto-enrich when actively typing in the input step (no org loaded yet)
            if (lastSearchedCnpj.current !== digits && step === "input" && !currentOrgId) {
                lastSearchedCnpj.current = digits;
                handleAutoEnrich();
            }
        } else if (digits.length === 0) {
            lastSearchedCnpj.current = "";
        }
    }, [cnpj, step, currentOrgId, handleAutoEnrich]);

    return {
        step, setStep,
        cnpj, setCnpj,
        domainTarget, setDomainTarget,
        productFocus, setProductFocus,
        areaFocus, setAreaFocus,
        confirmedBrand, setConfirmedBrand,
        confirmedLogo, setConfirmedLogo,
        confirmedFollowers, setConfirmedFollowers,
        refreshDrawerTrigger, setRefreshDrawerTrigger,
        enrichingIds, setEnrichingIds,
        partners, setPartners,
        handleSearch,
        handleBrandSelect,
        handleAutoEnrich,
        resetWorkflow,
        selectedModel,
        setSelectedModel,
        strictMode,
        setStrictMode,
        mappingMode,
        setMappingMode,
        confirmedLinkedInUrl,
        setConfirmedLinkedInUrl
    };
}
