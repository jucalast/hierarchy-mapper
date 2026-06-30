import { useEffect, useRef } from 'react';
import { useChatStore } from '@/store/chatStore';
import { useGlobalHierarchyScan } from '@/contexts/HierarchyScanContext';

interface UseRouterSyncProps {
    pathname: string;
    currentOrgId: number | null;
    setCurrentOrgId: (id: number | null) => void;
    setChatOrgId: (id: number | null) => void;
    pipedriveOrgs: any[];
    hierarchy: any; // Expects return from useHierarchy
    discovery: any; // Expects return from useDiscoveryWorkflow
    setShouldFitView: (val: boolean) => void;
    addNotification: (type: 'success' | 'error' | 'warning' | 'info', message: string) => void;
}

const LAST_ORG_KEYS = ['id', 'name', 'logo', 'cnpj', 'domain', 'linkedin_url', 'linkedin', 'product_focus', 'category'] as const;

const saveLastViewedOrg = (org: any) => {
    if (!org) return;
    const slim: Record<string, unknown> = {};
    for (const k of LAST_ORG_KEYS) if (org[k] !== undefined) slim[k] = org[k];
    try {
        localStorage.setItem('last-viewed-org', JSON.stringify(slim));
    } catch (e) {
        console.warn('[useRouterSync] localStorage quota excedida ao salvar last-viewed-org:', e);
    }
};

const cleanName = (name: string) => {
    if (!name) return "";
    return name
        .replace(/\|?\s*Linked\s*In/gi, '')
        .replace(/\(\s*LinkedIn\s*\)/gi, '')
        .trim();
};

const formatCnpj = (val: string) => {
    const s = val.replace(/\D/g, '').slice(0, 14);
    if (s.length <= 2) return s;
    if (s.length <= 5) return `${s.slice(0, 2)}.${s.slice(2)}`;
    if (s.length <= 8) return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5)}`;
    if (s.length <= 12) return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8)}`;
    return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}`;
};

export function useRouterSync({
    pathname,
    currentOrgId,
    setCurrentOrgId,
    setChatOrgId,
    pipedriveOrgs,
    hierarchy,
    discovery,
    setShouldFitView,
    addNotification
}: UseRouterSyncProps) {
    const { reconnectScan: reconnectLinkedinScan } = useGlobalHierarchyScan();
    const hasAttemptedReconnect = useRef(false);
    const reconnectLockRef = useRef(false);  // Prevents duplicate reconnect notifications
    const currentPathRef = useRef(pathname);
    currentPathRef.current = pathname;

    const {
        resetHierarchy,
        loadStoredHierarchy,
        reconnectToActiveJob,
        setBrandOptions
    } = hierarchy;

    const {
        setStep,
        setCnpj,
        setDomainTarget,
        setConfirmedBrand,
        setConfirmedLogo,
        setConfirmedLinkedInUrl,
        setProductFocus,
        setAreaFocus
    } = discovery;

    // Reconnection & Initial Load logic
    useEffect(() => {
        if (hasAttemptedReconnect.current) return;
        hasAttemptedReconnect.current = true;

        const checkLastOrg = async () => {
            const match = pathname.match(/\/org\/(\d+)/);
            let orgId: number | null = null;
            let org: any = null;

            if (match && match[1]) {
                orgId = parseInt(match[1]);
                const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
                if (cachedOrgsStr) {
                    try {
                        const list = JSON.parse(cachedOrgsStr);
                        if (Array.isArray(list)) {
                            org = list.find((o: any) => Number(o.id) === orgId);
                        }
                    } catch (e) {
                        console.error(e);
                    }
                }
                
                if (!org) {
                    try {
                        const { organizations } = await import('@/services/api');
                        const res = await organizations.getOrganizationDetails(orgId);
                        if (res && res.org) org = res.org;
                    } catch (e) {
                        console.error("Erro ao buscar detalhes da org da URL no boot:", e);
                    }
                }
            }

            if (!org) {
                const lastOrgStr = localStorage.getItem('last-viewed-org');
                if (lastOrgStr && lastOrgStr !== "NaN" && lastOrgStr !== "undefined") {
                    try {
                        org = JSON.parse(lastOrgStr);
                        if (org && org.id) orgId = Number(org.id);
                    } catch (e) {
                        console.error(e);
                    }
                }
            }

            if (org && orgId) {
                try {
                    const cleanOrgName = org.name || "";
                    setConfirmedBrand(cleanOrgName);
                    setConfirmedLogo(org.logo || "");

                    let targetCnpj = org.cnpj || "";
                    const onlyNums = targetCnpj.replace(/\D/g, '');
                    if (onlyNums.length >= 5) {
                        setCnpj(formatCnpj(targetCnpj));
                    }
                    setDomainTarget(org.domain || "");
                    setCurrentOrgId(orgId);
                    setChatOrgId(orgId);
                    useChatStore.getState().setCurrentOrgId(orgId);
                    saveLastViewedOrg(org);

                    const isValidLinkedin = (url: any) => typeof url === 'string' && url.includes('linkedin.com');
                    const lUrl = isValidLinkedin(org.linkedin_url) ? org.linkedin_url : isValidLinkedin(org.linkedin) ? org.linkedin : "";
                    if (lUrl) setConfirmedLinkedInUrl(lUrl);

                    const data = await loadStoredHierarchy(orgId, true);
                    if (data && data.nodes && data.nodes.length > 1) {
                        setStep("confirm");
                        const rootLinkedin = data.nodes[0]?.linkedin || data.nodes[0]?.url;
                        if (rootLinkedin && rootLinkedin.startsWith('http')) {
                            setConfirmedLinkedInUrl(rootLinkedin);
                        }
                        setTimeout(() => setShouldFitView(true), 100);
                    } else if (isValidLinkedin(org.linkedin_url) || isValidLinkedin(org.linkedin) || (org.cnpj && org.domain)) {
                        setStep("confirm");
                    } else {
                        setStep("input");
                    }
                } catch (e) {
                    console.error("[Last Org Check] Erro", e);
                    setConfirmedBrand("");
                    setStep("input");
                }
            } else {
                setConfirmedBrand("");
                setStep("input");
            }
        };

        const checkActiveJob = async () => {
            // Verifica primeiro se havia um scan LinkedIn em andamento — o job roda
            // no worker ARQ desacoplado da página, então só precisamos reabrir o WS.
            const linkedinScanStr = localStorage.getItem('active-linkedin-scan');
            const linkedinScansStr = localStorage.getItem('active-linkedin-scans');
            const hasLegacyScan = !!(linkedinScanStr && linkedinScanStr !== "NaN" && linkedinScanStr !== "undefined");
            const hasNewFormatScan = (() => {
                if (!linkedinScansStr) return false;
                try { const p = JSON.parse(linkedinScansStr); return p && typeof p === 'object' && Object.keys(p).length > 0; }
                catch { return false; }
            })();

            if (hasLegacyScan) {
                // 🔄 Reconciliação REST ANTES de reabrir o WS — espelha o que o discovery já
                // fazia (loadStoredHierarchy). Sem isso, um reload de página fazia o
                // connectionManager achar o store vazio e recomeçar do zero visualmente,
                // mesmo com nós já persistidos no banco pelos lotes recebidos antes do reload.
                try {
                    const scanJobData = JSON.parse(linkedinScanStr!);
                    if (scanJobData?.orgId) {
                        const data = await loadStoredHierarchy(Number(scanJobData.orgId), true);
                        if (data && data.nodes && data.nodes.length > 0) {
                            console.log(`[Job Check] ${data.nodes.length} nós da varredura restaurados do banco.`);
                        }
                        setCurrentOrgId(Number(scanJobData.orgId));
                        setChatOrgId(Number(scanJobData.orgId));
                        useChatStore.getState().setCurrentOrgId(Number(scanJobData.orgId));
                        setStep("scanning");
                    }
                } catch (e) {
                    console.warn('[Job Check] Erro ao reconciliar hierarquia da varredura via REST:', e);
                }

                const reconnected = await reconnectLinkedinScan();
                if (reconnected) {
                    addNotification('info', 'Reconectado à varredura do LinkedIn em andamento...');
                } else {
                    addNotification('info', 'A varredura do LinkedIn já havia sido concluída ou expirado.');
                }
            } else if (hasNewFormatScan) {
                // Novo formato (active-linkedin-scans): chama reconnectLinkedinScan para
                // verificar o backend e limpar entradas expiradas. Sem isso, orgs continuam
                // mostrando "Mapeando..." ao reiniciar mesmo após o scan ter concluído.
                await reconnectLinkedinScan();
            }

            let jobDataStr: string | null = null;
            for (let _i = 0; _i < localStorage.length; _i++) {
                const _k = localStorage.key(_i);
                if (_k && _k.startsWith('active-discovery-job-')) {
                    const _v = localStorage.getItem(_k);
                    if (_v && _v !== "NaN" && _v !== "undefined") { jobDataStr = _v; break; }
                }
            }
            if (jobDataStr) {
                try {
                    const jobData = JSON.parse(jobDataStr);
                    const { job_id, brand, logo, domain, orgId, cnpj } = jobData;
                    console.log(`[Job Check] Detectado Job Ativo para ${brand}. Carregando dados prévios...`);

                    if (orgId) {
                        const data = await loadStoredHierarchy(Number(orgId), true);
                        if (data && data.nodes && data.nodes.length > 0) {
                            console.log(`[Job Check] ${data.nodes.length} nós restaurados do banco.`);
                        }
                    }

                    setStep("scanning");
                    setConfirmedBrand(brand);
                    if (logo) setConfirmedLogo(logo);
                    if (domain) setDomainTarget(domain);
                    if (cnpj) {
                        const onlyNums = cnpj.replace(/\D/g, '');
                        if (onlyNums.length >= 5) {
                            setCnpj(formatCnpj(cnpj));
                        }
                    }
                    if (orgId) {
                        setCurrentOrgId(orgId);
                        setChatOrgId(orgId);
                        useChatStore.getState().setCurrentOrgId(orgId);
                    }

                    // Guard against duplicate calls (e.g. from React double-invoking effects in dev or Next.js hydration)
                    if (reconnectLockRef.current) return;
                    reconnectLockRef.current = true;
                    const reconnected = await reconnectToActiveJob(addNotification, Number(orgId));
                    if (!reconnected) {
                        console.warn("[Job Check] Job expirou no backend.");
                        setStep("confirm");
                    }
                } catch (e) {
                    console.error("[Job Check] Erro", e);
                    if (pathname !== '/') {
                        checkLastOrg();
                    } else {
                        setStep("input");
                        setConfirmedBrand("");
                        setConfirmedLogo("");
                        setCnpj("");
                        setDomainTarget("");
                    }
                }
            } else {
                if (pathname !== '/') {
                    checkLastOrg();
                } else {
                    setStep("input");
                    setConfirmedBrand("");
                    setConfirmedLogo("");
                    setCnpj("");
                    setDomainTarget("");
                }
            }
        };

        checkActiveJob();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);  // Empty deps: this must only run once on mount. Internal refs capture the latest values.

    // Sincroniza a empresa baseando-se no pathname (URL) ao navegar entre rotas
    useEffect(() => {
        if (!hasAttemptedReconnect.current) return;

        const match = pathname.match(/\/org\/(\d+)/);
        console.log(`[Router Sync Effect] pathname: "${pathname}", match: ${match ? match[1] : 'null'}`);
        if (match && match[1]) {
            const orgId = parseInt(match[1]);
            if (currentOrgId !== orgId) {
                console.log(`[Router Sync] Navigating from org ${currentOrgId} to ${orgId}. Switching state.`);
                
                // Switch the active org ID
                setCurrentOrgId(orgId);
                setChatOrgId(orgId);
                useChatStore.getState().setCurrentOrgId(orgId);

                // Reset Discovery workflow LOCAL states immediately
                setStep("input");
                setCnpj("");
                setDomainTarget("");
                setConfirmedBrand("");
                setConfirmedLogo("");

                const syncOrgFromUrl = async () => {
                    try {
                        let org = pipedriveOrgs.find(o => Number(o.id) === orgId);
                        if (!org) {
                            const cachedOrgsStr = localStorage.getItem('pipedrive-orgs-cache');
                            if (cachedOrgsStr) {
                                try {
                                    const list = JSON.parse(cachedOrgsStr);
                                    if (Array.isArray(list)) {
                                        org = list.find((o: any) => Number(o.id) === orgId);
                                    }
                                } catch (e) {
                                    console.error(e);
                                }
                            }
                        }
                        if (!org) {
                            const { organizations } = await import('@/services/api');
                            const res = await organizations.getOrganizationDetails(orgId);
                            if (res && res.org) org = res.org;
                        }

                        if (currentPathRef.current !== `/org/${orgId}`) return;

                        if (org) {
                            console.log(`[Router Sync] Organization details fetched for org ${orgId}. Applying details.`);
                            saveLastViewedOrg(org);

                            const jobDataStr = localStorage.getItem(`active-discovery-job-${orgId}`);
                            if (jobDataStr) {
                                try {
                                    const jobData = JSON.parse(jobDataStr);
                                    if (Number(jobData.orgId) === orgId) {
                                        setStep("loading");
                                        setConfirmedBrand(jobData.brand || cleanName(org.name || ""));
                                        setConfirmedLogo(jobData.logo || org.logo || "");
                                        
                                        let targetCnpj = jobData.cnpj || org.cnpj || "";
                                        const onlyNums = targetCnpj.replace(/\D/g, '');
                                        if (onlyNums.length >= 5) {
                                            setCnpj(formatCnpj(targetCnpj));
                                        }
                                        setDomainTarget(jobData.domain || org.domain || "");
                                        if (org.product_focus) setProductFocus(org.product_focus);
                                        if (org.category === "compras" || org.category === "logistica") setAreaFocus(org.category);
                                        
                                        // Silently reconnect - the user sees the "Mapeando..." badge on the card
                                        const reconnected = await reconnectToActiveJob(undefined, orgId);
                                        if (reconnected) return;
                                        setStep("initial");
                                    }
                                } catch (e) {
                                    console.error(e);
                                }
                            }

                            const mappingState = useChatStore.getState().mappings[orgId];
                            let hasNodes = mappingState && mappingState.rawEmployees && mappingState.rawEmployees.length > 1;
                            let data = null;

                            // Immediate step evaluation to prevent UI delay
                            // Only apply if we are still on this org's route
                            if (currentPathRef.current === `/org/${orgId}` &&
                               (hasNodes || 
                               (typeof org.linkedin_url === 'string' && org.linkedin_url.includes('linkedin.com')) || 
                               (typeof org.linkedin === 'string' && org.linkedin.includes('linkedin.com')) || 
                               (org.cnpj && org.domain))) {
                                setConfirmedBrand(cleanName(org.name || ""));
                                setConfirmedLogo(org.logo || "");
                                setCnpj(formatCnpj(org.cnpj || ""));
                                setDomainTarget(org.domain || "");
                                setStep("confirm");
                            }

                            if (!hasNodes && !mappingState?.discovering && !mappingState?.activeJobId) {
                                data = await loadStoredHierarchy(orgId, true);
                                hasNodes = data && data.nodes && data.nodes.length > 1;
                            }

                            if (currentPathRef.current !== `/org/${orgId}`) return;

                            if (hasNodes) {
                                setConfirmedBrand(cleanName(org.name || ""));
                                setConfirmedLogo(org.logo || "");
                                setCnpj(formatCnpj(org.cnpj || ""));
                                setDomainTarget(org.domain || "");
                                setStep("confirm");
                                setShouldFitView(true);

                                const rootLinkedin = (data && data.nodes && data.nodes[0]?.linkedin) || (data && data.nodes && data.nodes[0]?.url) || (mappingState?.rawEmployees && mappingState.rawEmployees[0]?.linkedin) || (mappingState?.rawEmployees && mappingState.rawEmployees[0]?.url) || org.linkedin_url || org.linkedin;
                                if (rootLinkedin && rootLinkedin.startsWith('http')) {
                                    setConfirmedLinkedInUrl(rootLinkedin);
                                }
                            } else if ((typeof org.linkedin_url === 'string' && org.linkedin_url.includes('linkedin.com')) || 
                                       (typeof org.linkedin === 'string' && org.linkedin.includes('linkedin.com')) || 
                                       (org.cnpj && org.domain)) {
                                setConfirmedBrand(cleanName(org.name || ""));
                                setConfirmedLogo(org.logo || "");
                                setCnpj(formatCnpj(org.cnpj || ""));
                                setDomainTarget(org.domain || "");
                                setStep("confirm");

                                const rootLinkedin = org.linkedin_url || org.linkedin;
                                if (rootLinkedin && rootLinkedin.startsWith('http')) {
                                    setConfirmedLinkedInUrl(rootLinkedin);
                                }
                            } else {
                                setConfirmedBrand(cleanName(org.name || ""));
                                setConfirmedLogo(org.logo || "");
                                setStep("input");
                            }

                            if (org.product_focus) setProductFocus(org.product_focus);
                            if (org.category === "compras" || org.category === "logistica") setAreaFocus(org.category);
                        } else {
                            console.warn(`[Router Sync] Organization details NOT found for org ${orgId}. Leaving UI cleared.`);
                        }
                    } catch (e) {
                        console.error(e);
                    }
                };
                void syncOrgFromUrl();
            }
        } else {
            if (currentOrgId !== null) {
                console.log(`[Router Sync] Navigated to root. Clearing organization local state.`);
                
                // Do not call resetHierarchy() so we preserve Zustand cache for the old org
                setCurrentOrgId(null);
                setChatOrgId(null);
                useChatStore.getState().setCurrentOrgId(null);
                setStep("input");
                setCnpj("");
                setDomainTarget("");
                setConfirmedBrand("");
                setConfirmedLogo("");
                setConfirmedLinkedInUrl("");
                localStorage.removeItem('last-viewed-org');
            }
        }
    }, [pathname, currentOrgId, pipedriveOrgs, resetHierarchy, loadStoredHierarchy, setConfirmedBrand, setConfirmedLogo, setCnpj, setDomainTarget, setConfirmedLinkedInUrl, setStep, setShouldFitView, setProductFocus, setAreaFocus, reconnectToActiveJob, addNotification, setCurrentOrgId, setChatOrgId, setBrandOptions]);

}
