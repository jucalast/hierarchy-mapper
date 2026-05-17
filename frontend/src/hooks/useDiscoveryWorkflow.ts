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
}

export function useDiscoveryWorkflow({
    defaultCnpj = "",
    useHierarchy,
    currentOrgId,
    setCurrentOrgId,
    setChatOrgId,
    rawEmployees,
    fetchPipedriveOrgs,
    setPipedriveOrgs
}: DiscoveryWorkflowProps) {
    const { addNotification } = useNotifications();
    const [step, setStep] = useState<"input" | "confirm" | "scanning" | "loading" | "initial">("input");
    const [cnpj, setCnpj] = useState(defaultCnpj);
    const [domainTarget, setDomainTarget] = useState("");
    const [productFocus, setProductFocus] = useState("");
    const [areaFocus, setAreaFocus] = useState<"compras" | "logistica">("compras");
    const [confirmedBrand, setConfirmedBrand] = useState("");
    const [confirmedLogo, setConfirmedLogo] = useState("");
    const [confirmedFollowers, setConfirmedFollowers] = useState("");
    const [refreshDrawerTrigger, setRefreshDrawerTrigger] = useState(0);
    const [enrichingIds, setEnrichingIds] = useState<Set<number>>(new Set());
    const [partners, setPartners] = useState<any[]>([]);

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

            const rootAndPartnersOnly = rawEmployees.filter(emp => {
                const isRoot = emp.id === 'root_company' || emp.level === 0;
                const isPartner = emp.level === 6 || String(emp.id).startsWith('partner_');
                const isPartnerDept = emp.department && (
                    emp.department.includes('QSA') ||
                    emp.department.includes('Sócio') ||
                    emp.department.includes('Societário') ||
                    emp.department.includes('Conselho')
                );
                return isRoot || isPartner || isPartnerDept;
            });

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
                rootAndPartnersOnly
            );
        }
    }, [
        step, cnpj, domainTarget, confirmedBrand, confirmedLogo, productFocus, areaFocus,
        discoverBrandStream, fetchHierarchy, addNotification, 
        partners, currentOrgId, rawEmployees, setBrandOptions
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
        setStep("confirm");

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

                if (!currentOrgId && newOrgId) setCurrentOrgId(Number(newOrgId));
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
        confirmIntelligence
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

    const resetWorkflow = useCallback(() => {
        setStep("input");
        setCnpj("");
        setDomainTarget("");
        setProductFocus("");
        setConfirmedBrand("");
        setConfirmedLogo("");
        setConfirmedFollowers("");
        setBrandOptions([]);
        setCurrentOrgId(null);
        setChatOrgId(null);
        setPartners([]);
        resetHierarchy();
        localStorage.removeItem('last-viewed-org');
    }, [setBrandOptions, setCurrentOrgId, setChatOrgId, resetHierarchy]);

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
        resetWorkflow
    };
}
