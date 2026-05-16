import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
    ChevronRight,
    Search,
    X,
    Users,
    Briefcase,
    Clock,
    DollarSign,
    Trash2,
    MoreHorizontal,
    AlertTriangle,
    RefreshCw,
    User,
} from 'lucide-react';
import styles from './Drawer.module.css';
import { HistoryTimeline } from '../prospecting/HistoryTimeline';
import { ContactList } from '../prospecting/ContactList';
import { OrgListItem } from '../prospecting/OrgListItem';
import type { NotificationType } from './Notification';
import { organizations as orgsApi } from '@/services/api';
import { Avatar, Button, Modal, Spinner, Badge } from './index';

interface DrawerProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    searchTerm: string;
    setSearchTerm: (term: string) => void;
    filteredOrgs: any[];
    onOrgClick: (org: any) => void;
    onOrgReset?: (orgId: number) => void;
    onOrgRenamed?: (orgId: number, newName: string) => void;
    isLoading?: boolean;
    selectedOrgId?: number | null;
    selectedOrgLogo?: string;
    activeJobId?: string | null;
    graphEmployees?: any[];
    refreshDetailsTrigger?: number; // Para forçar a recarga dos detalhes
    addNotification?: (type: NotificationType, message: string) => void;
}

const LOCAL_CACHE_KEYS = (orgId: number) => [
    `org-${orgId}-details`,
    `org-${orgId}-logo`,
    `org-${orgId}-hierarchy`,
    `pipedrive-orgs-cache`,
    `layout-cache-${orgId}`,
    `edges-cache-${orgId}`,
];

function clearLocalOrgCaches(orgId: number) {
    try {
        LOCAL_CACHE_KEYS(orgId).forEach((key) => {
            if (typeof window !== 'undefined' && window.localStorage.getItem(key)) {
                window.localStorage.removeItem(key);
            }
        });
    } catch {
        /* ignore */
    }
}

type ConfirmKind = 'reset' | 'delete' | null;

export const Drawer: React.FC<DrawerProps> = ({
    showDrawer,
    setShowDrawer,
    searchTerm,
    setSearchTerm,
    filteredOrgs,
    onOrgClick,
    onOrgReset,
    onOrgRenamed,
    isLoading = false,
    selectedOrgId = null,
    selectedOrgLogo = '',
    activeJobId = null,
    graphEmployees = [],
    refreshDetailsTrigger = 0,
    addNotification = () => {},
}) => {
    const [expandedOrgId, setExpandedOrgIdState] = useState<number | null>(() => {
        if (typeof window !== 'undefined') {
            const saved = window.localStorage.getItem('drawer-expanded-org-id');
            return saved ? Number(saved) : null;
        }
        return null;
    });

    const setExpandedOrgId = (orgId: number | null) => {
        setExpandedOrgIdState(orgId);
        if (typeof window !== 'undefined') {
            if (orgId === null) {
                window.localStorage.removeItem('drawer-expanded-org-id');
            } else {
                window.localStorage.setItem('drawer-expanded-org-id', orgId.toString());
            }
        }
    };

    const [orgDetails, setOrgDetails] = useState<Record<number, any>>(() => {
        if (typeof window !== 'undefined' && expandedOrgId) {
            const cached = window.localStorage.getItem(`org-${expandedOrgId}-details`);
            if (cached) {
                try {
                    return { [expandedOrgId]: JSON.parse(cached) };
                } catch {}
            }
        }
        return {};
    });
    const [loadingDetails, setLoadingDetails] = useState<Record<number, boolean>>({});
    
    const [activeTab, setActiveTabState] = useState<string>(() => {
        if (typeof window !== 'undefined') {
            return window.localStorage.getItem('drawer-active-tab') || 'activities';
        }
        return 'activities';
    });

    const setActiveTab = (tab: string) => {
        setActiveTabState(tab);
        if (typeof window !== 'undefined') {
            window.localStorage.setItem('drawer-active-tab', tab);
        }
    };

    // 🚀 Carregamento inicial de detalhes se já houver empresa expandida
    useEffect(() => {
        if (expandedOrgId) {
            void fetchOrgDetails(expandedOrgId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const [editingNameOrgId, setEditingNameOrgId] = useState<number | null>(null);
    const [editingNameValue, setEditingNameValue] = useState<string>('');
    const [showOptionsDropdown, setShowOptionsDropdown] = useState<boolean>(false);
    const [confirmKind, setConfirmKind] = useState<ConfirmKind>(null);
    const [confirmBusy, setConfirmBusy] = useState<boolean>(false);
    const [scanningOrgId, setScanningOrgId] = useState<number | null>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setShowOptionsDropdown(false);
            }
        };
        if (showOptionsDropdown) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [showOptionsDropdown]);

    const fetchOrgDetails = useCallback(async (orgId: number, force: boolean = false) => {
        if (!force && orgDetails[orgId]) return; // Já carregado

        setLoadingDetails(prev => ({ ...prev, [orgId]: true }));
        try {
            const data = await orgsApi.getOrganizationDetails(orgId);
            setOrgDetails(prev => ({ ...prev, [orgId]: data }));
            if (typeof window !== 'undefined') {
                window.localStorage.setItem(`org-${orgId}-details`, JSON.stringify(data));
            }
            if (force) {
                addNotification('success', 'Dados sincronizados com o Pipedrive.');
            }
        } catch (e: any) {
            console.error('Erro ao carregar detalhes:', e.message || e);
            if (force) {
                const msg = (e as any)?.message || 'Erro ao sincronizar. Tente novamente.';
                addNotification('error', msg);
            }
        } finally {
            setLoadingDetails(prev => ({ ...prev, [orgId]: false }));
        }
    }, [orgDetails, addNotification]);

    useEffect(() => {
        if (refreshDetailsTrigger > 0) {
            // Em nova varredura ou job explícito, zera estado local
            setOrgDetails({});
            setExpandedOrgId(null);
        }
    }, [refreshDetailsTrigger]);

    useEffect(() => {
        if (activeJobId) {
            try {
                const jobStr = typeof window !== 'undefined' ? window.localStorage.getItem('active-discovery-job') : null;
                if (jobStr) {
                    const parsed = JSON.parse(jobStr);
                    setScanningOrgId(parsed.orgId);
                }
            } catch {
                setScanningOrgId(null);
            }
        } else {
            setScanningOrgId(null);
        }
    }, [activeJobId]);

    const toggleExpand = (e: React.MouseEvent, orgId: number) => {
        e.stopPropagation();
        if (expandedOrgId === orgId) {
            setExpandedOrgId(null);
        } else {
            setExpandedOrgId(orgId);
            void fetchOrgDetails(orgId);
        }
    };

    const performReset = async (orgId: number) => {
        setConfirmBusy(true);
        try {
            await orgsApi.resetOrganization(orgId);

            clearLocalOrgCaches(orgId);
            setOrgDetails(prev => {
                const updated = { ...prev };
                delete updated[orgId];
                return updated;
            });
            setExpandedOrgId(null);

            if (onOrgReset) onOrgReset(orgId);
            addNotification('success', 'Todos os dados e cache da empresa foram resetados!');
        } catch (e: any) {
            console.error('Erro ao resetar:', e.message || e);
            addNotification('error', 'Erro ao resetar dados.');
        } finally {
            setConfirmBusy(false);
            setConfirmKind(null);
        }
    };

    const performDelete = async (orgId: number) => {
        setConfirmBusy(true);
        try {
            await orgsApi.deleteOrganization(orgId);

            clearLocalOrgCaches(orgId);
            setOrgDetails(prev => {
                const updated = { ...prev };
                delete updated[orgId];
                return updated;
            });
            setExpandedOrgId(null);

            if (onOrgReset) onOrgReset(orgId);
            addNotification('success', 'Empresa foi apagada do CRM com sucesso!');
        } catch (e: any) {
            console.error('Erro ao excluir:', e.message || e);
            addNotification('error', 'Erro ao excluir empresa.');
        } finally {
            setConfirmBusy(false);
            setConfirmKind(null);
        }
    };

    const handleRenameOrg = async (orgId: number) => {
        if (!editingNameValue || editingNameValue.trim() === '') {
            setEditingNameOrgId(null);
            return;
        }

        try {
            await orgsApi.renameOrganization(orgId, editingNameValue.trim());

            // Atualizar no local state (mutação controlada do array do pai)
            const updatedOrg = filteredOrgs.find(o => Number(o.id) === orgId);
            if (updatedOrg) {
                updatedOrg.name = editingNameValue.trim();
            }

            setOrgDetails(prev => {
                if (prev[orgId]) {
                    return {
                        ...prev,
                        [orgId]: { ...prev[orgId], name: editingNameValue.trim() },
                    };
                }
                return prev;
            });

            setEditingNameOrgId(null);

            if (onOrgRenamed) onOrgRenamed(orgId, editingNameValue.trim());
            addNotification('success', 'Nome da empresa atualizado!');
        } catch (e: any) {
            console.error('Erro ao renomear:', e.message || e);
            addNotification('error', 'Erro ao renomear empresa.');
        }
    };

    const formatDate = (dateStr: string) => {
        if (!dateStr) return '';
        return new Date(dateStr).toLocaleDateString('pt-BR');
    };

    // Filtra a organização que está em foco
    const focusedOrg = expandedOrgId ? filteredOrgs.find(o => Number(o.id) === expandedOrgId) : null;

    if (!showDrawer) return null;

    return (
        <div className={styles.drawer}>
            <div className={styles.drawerHeader}>
                {expandedOrgId ? (
                    <div className={styles.focusHeader}>
                        <button onClick={() => setExpandedOrgId(null)} className={styles.backToListBtn}>
                            <X size={14} />
                            <span>Voltar para a lista</span>
                        </button>

                        <div className={styles.focusHeaderActions} ref={dropdownRef}>
                            <button
                                onClick={() => setShowOptionsDropdown(!showOptionsDropdown)}
                                className={styles.moreOptionsBtn}
                                title="Mais opções"
                            >
                                <MoreHorizontal size={20} />
                            </button>

                            <button
                                onClick={() => fetchOrgDetails(expandedOrgId!, true)}
                                className={styles.refreshBtn}
                                title="Sincronizar agora"
                                disabled={loadingDetails[expandedOrgId!]}
                            >
                                <RefreshCw size={14} className={loadingDetails[expandedOrgId!] ? styles.spin : ''} />
                            </button>

                            {showOptionsDropdown && (
                                <div className={styles.dropdownMenu}>
                                    <button
                                        onClick={() => {
                                            setShowOptionsDropdown(false);
                                            setConfirmKind('reset');
                                        }}
                                        className={styles.dropdownItem}
                                        style={{ color: 'var(--sw-warning)' }}
                                    >
                                        <Trash2 size={14} />
                                        <span>Resetar Cache</span>
                                    </button>
                                    <button
                                        onClick={() => {
                                            setShowOptionsDropdown(false);
                                            setConfirmKind('delete');
                                        }}
                                        className={styles.dropdownItem}
                                        style={{ color: 'var(--sw-alert-text)' }}
                                    >
                                        <X size={14} />
                                        <span>Excluir Empresa</span>
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <>
                        <div className={styles.drawerInputWrapper}>
                            <Search size={14} className={styles.inputIcon} />
                            <input
                                type="text"
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                placeholder="Pesquisar no Pipedrive..."
                                className={styles.drawerInput}
                            />
                        </div>
                        <button onClick={() => setShowDrawer(false)} className={styles.backBtn} title="Fechar">
                            <X size={14} />
                        </button>
                    </>
                )}
            </div>

            <div className={styles.drawerList}>
                {isLoading ? (
                    <div className={styles.drawerLoading}>
                        <Spinner size={32} />
                    </div>
                ) : expandedOrgId && focusedOrg ? (
                    /* MODO FOCO TOTAL (UMA ÚNICA EMPRESA) */
                    <div className={styles.focusedOrgView}>
                        <div className={styles.focusedOrgHero}>
                            <div className={styles.focusedOrgLogoWrapper}>
                                <Avatar
                                    kind="company"
                                    src={focusedOrg.logo || (Number(focusedOrg.id) === selectedOrgId || Number(focusedOrg.local_id) === selectedOrgId ? selectedOrgLogo : undefined)}
                                    name={focusedOrg.name}
                                    data={focusedOrg}
                                    size={48}
                                />
                            </div>
                            <div className={styles.focusedOrgIdentity}>
                                {editingNameOrgId === expandedOrgId ? (
                                    <input
                                        type="text"
                                        value={editingNameValue}
                                        onChange={(e) => setEditingNameValue(e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                                handleRenameOrg(expandedOrgId!);
                                            } else if (e.key === 'Escape') {
                                                setEditingNameOrgId(null);
                                            }
                                        }}
                                        onBlur={() => handleRenameOrg(expandedOrgId!)}
                                        autoFocus
                                        className={styles.focusedOrgNameEdit}
                                        placeholder="Nome da empresa..."
                                    />
                                ) : (
                                    <h2
                                        className={styles.focusedOrgName}
                                        onDoubleClick={() => {
                                            setEditingNameOrgId(expandedOrgId);
                                            setEditingNameValue(focusedOrg.name);
                                        }}
                                        title="Clique duas vezes para renomear"
                                        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px', width: '100%', overflow: 'hidden' }}
                                    >
                                        <span style={{ 
                                            whiteSpace: 'nowrap', 
                                            overflow: 'hidden', 
                                            textOverflow: 'ellipsis',
                                            flex: '0 1 auto'
                                        }}>
                                            {focusedOrg.name}
                                        </span>
                                        {orgDetails[expandedOrgId]?.icp_tier && (
                                            <Badge 
                                                tone={orgDetails[expandedOrgId].icp_tier === 'A' ? 'success' : orgDetails[expandedOrgId].icp_tier === 'B' ? 'warning' : 'neutral'}
                                                size="sm"
                                                style={{ fontSize: '11px', padding: '2px 8px', flexShrink: 0 }}
                                                title={`ICP Score: ${orgDetails[expandedOrgId].icp_score}`}
                                            >
                                                Tier {orgDetails[expandedOrgId].icp_tier} • {orgDetails[expandedOrgId].icp_score}%
                                            </Badge>
                                        )}
                                        {scanningOrgId === expandedOrgId && (
                                            <Spinner size={16} inline color="var(--sw-primary)" />
                                        )}
                                    </h2>
                                )}
                                <div className={styles.focusedMetaRow}>
                                    {focusedOrg.address && (
                                        <span className={styles.focusedOrgAddress}>
                                            {focusedOrg.address.toLowerCase().replace(/(^\w|\s\w)/g, (m: string) => m.toUpperCase())}
                                        </span>
                                    )}
                                    {orgDetails[expandedOrgId]?.org?.owner_name && (
                                        <span className={styles.focusedOrgOwner} title="Responsável pela empresa">
                                            <User size={12} style={{ marginRight: '4px', opacity: 0.6 }} />
                                            {orgDetails[expandedOrgId].org.owner_name}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className={styles.detailsPane}>
                            {loadingDetails[expandedOrgId] ? (
                                <div className={styles.detailsLoading}>
                                    <Spinner size={16} inline />
                                    <span>Sincronizando...</span>
                                </div>
                            ) : orgDetails[expandedOrgId] ? (
                                <div className={styles.detailsContent}>
                                    <div className={styles.mainNav}>
                                        <button
                                            className={activeTab === 'activities' ? styles.mainNavActive : styles.mainNavBtn}
                                            onClick={() => setActiveTab('activities')}
                                        >
                                            <Clock size={16} /> Timeline
                                        </button>
                                        <button
                                            className={activeTab === 'persons' ? styles.mainNavActive : styles.mainNavBtn}
                                            onClick={() => setActiveTab('persons')}
                                        >
                                            <Users size={16} /> People
                                        </button>
                                        <button
                                            className={activeTab === 'deals' ? styles.mainNavActive : styles.mainNavBtn}
                                            onClick={() => setActiveTab('deals')}
                                        >
                                            <Briefcase size={16} /> Deals
                                        </button>
                                    </div>


                                    <div className={styles.tabScrollAreaFocus}>
                                        {activeTab === 'activities' && (
                                            <HistoryTimeline
                                                details={orgDetails[expandedOrgId]}
                                                orgName={focusedOrg.name}
                                            />
                                        )}

                                        {activeTab === 'persons' && (
                                            <ContactList
                                                persons={(() => {
                                                    const seen = new Set();
                                                    return (orgDetails[expandedOrgId].persons || []).filter((p: any) => {
                                                        if (!p.id || seen.has(p.id)) return false;
                                                        seen.add(p.id);
                                                        return true;
                                                    });
                                                })()}
                                            />
                                        )}

                                        {activeTab === 'deals' && (
                                            <div className={styles.dealList}>
                                                {orgDetails[expandedOrgId].deals.length === 0 && <div className={styles.emptyState}>Sem negócios.</div>}
                                                {(() => {
                                                    const seen = new Set();
                                                    return (orgDetails[expandedOrgId].deals || [])
                                                        .filter((d: any) => {
                                                            if (!d.id || seen.has(d.id)) return false;
                                                            seen.add(d.id);
                                                            return true;
                                                        })
                                                        .map((d: any) => (
                                                            <div key={d.id} className={styles.dealItem}>
                                                                <div className={styles.dealTitle}>{d.title}</div>
                                                                <div className={styles.dealOwner} title="Responsável pelo negócio">
                                                                    <Users size={10} style={{ marginRight: '4px', opacity: 0.5 }} />
                                                                    {d.user_id?.name || d.owner_name || 'Sem responsável'}
                                                                </div>
                                                                <div className={styles.dealMeta}>
                                                                    <span className={styles.dealValue}>
                                                                        <DollarSign size={10} /> {d.formatted_value || 'R$ 0'}
                                                                    </span>
                                                                    <span className={`${styles.dealStatus} ${styles[d.status]}`}>
                                                                        {d.status === 'open' ? 'Aberto' : d.status === 'won' ? 'Ganho' : 'Perdido'}
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        ));
                                                })()}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ) : null}
                        </div>
                    </div>
                ) : (
                    /* MODO LISTA (PADRÃO) */
                    filteredOrgs.map(org => {
                        const orgId = Number(org.id);
                        const isSelected = orgId === selectedOrgId || Number(org.local_id) === selectedOrgId;

                        let displayPics = org.employee_pics || [];
                        let displayCount = org.employee_count || 0;

                        if (isSelected && graphEmployees.length > 0) {
                            const validEmps = graphEmployees.filter(emp =>
                                emp.id !== 'root_company' &&
                                emp.department !== 'Quadro Societário' &&
                                emp.department !== 'Quadro de Sócios (QSA)' &&
                                emp.level !== 6 &&
                                !String(emp.id).startsWith('partner_') &&
                                emp.role !== 'Análise Humana'
                            );

                            const graphPics = validEmps
                                .map(emp => emp.profile_pic || emp.avatar)
                                .filter(pic => pic && pic.length > 10);

                            // Sobrescreve sempre, para zerar as imagems caso comece um novo mapeamento
                            displayPics = graphPics;
                            displayCount = validEmps.length;
                        }

                        // Se o org está selecionado e não tem logo próprio, usa o confirmedLogo do estado
                        const orgWithLogo = isSelected && !org.logo && selectedOrgLogo
                            ? { ...org, logo: selectedOrgLogo }
                            : org;

                        return (
                            <OrgListItem
                                key={orgId}
                                org={orgWithLogo}
                                isSelected={isSelected}
                                onClick={(clickedOrg) => {
                                    onOrgClick(clickedOrg);
                                    const clickedOrgId = Number(clickedOrg.id || clickedOrg.pipedrive_id);
                                    setExpandedOrgId(clickedOrgId);
                                    void fetchOrgDetails(clickedOrgId);
                                }}
                                onToggleExpand={toggleExpand}
                                displayCount={displayCount}
                                displayPics={displayPics}
                                scanningOrgId={scanningOrgId}
                            />
                        );
                    })
                )}
            </div>

            {/* Modal de confirmação para resetar ou excluir */}
            <Modal
                isOpen={confirmKind !== null}
                onClose={() => !confirmBusy && setConfirmKind(null)}
                title={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <AlertTriangle
                            size={18}
                            color={confirmKind === 'delete' ? '#ef4444' : '#f59e0b'}
                        />
                        <span>
                            {confirmKind === 'delete'
                                ? 'Excluir empresa definitivamente'
                                : 'Resetar dados da empresa'}
                        </span>
                    </div>
                }
                width={460}
                closeOnOverlay={!confirmBusy}
                closeOnEsc={!confirmBusy}
                footer={
                    <>
                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setConfirmKind(null)}
                            disabled={confirmBusy}
                        >
                            Cancelar
                        </Button>
                        <Button
                            variant={confirmKind === 'delete' ? 'danger' : 'warning'}
                            size="sm"
                            loading={confirmBusy}
                            onClick={() => {
                                if (!expandedOrgId || !confirmKind) return;
                                if (confirmKind === 'delete') void performDelete(expandedOrgId);
                                else void performReset(expandedOrgId);
                            }}
                        >
                            {confirmKind === 'delete' ? 'Excluir definitivamente' : 'Resetar tudo'}
                        </Button>
                    </>
                }
            >
                {confirmKind === 'delete' ? (
                    <p style={{ margin: 0, lineHeight: 1.5, color: '#d1d5db' }}>
                        Esta ação <strong style={{ color: '#ef4444' }}>remove a empresa do Pipedrive</strong> e apaga
                        todos os dados locais (hierarquia, cache, logos, layouts). Operação irreversível.
                    </p>
                ) : (
                    <p style={{ margin: 0, lineHeight: 1.5, color: '#d1d5db' }}>
                        Isso limpa o <strong>cache, hierarquia e layout</strong> salvos desta empresa, mantendo o
                        registro no Pipedrive. O próximo mapeamento partirá do zero.
                    </p>
                )}
            </Modal>
        </div>
    );
};
