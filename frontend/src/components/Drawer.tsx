import React, { useState } from 'react';
import {
    ChevronRight,
    Search,
    X,
    Building,
    Loader2,
    ChevronDown,
    ChevronUp,
    Users,
    Calendar,
    Briefcase,
    MessageSquare,
    Clock,
    UserCheck,
    DollarSign,
    Target,
    Trash2
} from 'lucide-react';
import styles from './NetworkGraph.module.css';
import { HistoryTimeline } from './HistoryTimeline';
import { ContactList } from './ContactList';
import type { NotificationType } from './Notification';

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
    activeJobId?: string | null;
    graphEmployees?: any[];
    refreshDetailsTrigger?: number; // Para forçar a recarga dos detalhes
    addNotification?: (type: NotificationType, message: string) => void;
}

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
    activeJobId = null,
    graphEmployees = [],
    refreshDetailsTrigger = 0,
    addNotification = () => {}
}) => {
    const [expandedOrgId, setExpandedOrgId] = useState<number | null>(null);
    const [orgDetails, setOrgDetails] = useState<Record<number, any>>({});
    const [loadingDetails, setLoadingDetails] = useState<Record<number, boolean>>({});
    const [activeTab, setActiveTab] = useState<string>('activities');
    const [editingNameOrgId, setEditingNameOrgId] = useState<number | null>(null);
    const [editingNameValue, setEditingNameValue] = useState<string>('');

    const fetchOrgDetails = async (orgId: number, force: boolean = false) => {
        if (!force && orgDetails[orgId]) return; // Já carregado

        setLoadingDetails(prev => ({ ...prev, [orgId]: true }));
        try {
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            const resp = await fetch(`${API_BASE}/api/v1/pipedrive/organizations/${orgId}/details`);
            const data = await resp.json();
            setOrgDetails(prev => ({ ...prev, [orgId]: data }));
        } catch (e: any) {
            console.error("Erro ao carregar detalhes:", e.message || e);
        } finally {
            setLoadingDetails(prev => ({ ...prev, [orgId]: false }));
        }
    };

    React.useEffect(() => {
        if (refreshDetailsTrigger > 0) {
            // Em nova varredura ou job explícito, zera estado local
            setOrgDetails({});
            setExpandedOrgId(null);
        }
    }, [refreshDetailsTrigger]);

    const toggleExpand = (e: React.MouseEvent, orgId: number) => {
        e.stopPropagation();
        if (expandedOrgId === orgId) {
            setExpandedOrgId(null);
        } else {
            setExpandedOrgId(orgId);
            fetchOrgDetails(orgId);
        }
    };

    const handleResetOrgData = async (e: React.MouseEvent, orgId: number) => {
        e.stopPropagation();
        
        if (!confirm("Tem certeza que quer resetar TODOS os dados salvos desta empresa? (Banco + Cache)")) {
            return;
        }
        
        try {
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            const resp = await fetch(`${API_BASE}/api/v1/pipedrive/organizations/${orgId}/reset`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (resp.ok) {
                const data = await resp.json();
                console.log("[Drawer] Dados e cache resetados com sucesso:", data);
                
                // 🗑️ Limpar cache local (localStorage)
                const cacheKeys = [
                    `org-${orgId}-details`,
                    `org-${orgId}-logo`,
                    `org-${orgId}-hierarchy`,
                    `pipedrive-orgs-cache`,
                    `layout-cache-${orgId}`,
                    `edges-cache-${orgId}`
                ];
                cacheKeys.forEach(key => {
                    if (localStorage.getItem(key)) {
                        localStorage.removeItem(key);
                        console.log(`[LocalStorage] Removido: ${key}`);
                    }
                });
                
                // Atualizar a lista localmente removendo os dados
                setOrgDetails(prev => {
                    const updated = { ...prev };
                    delete updated[orgId];
                    return updated;
                });
                setExpandedOrgId(null);
                
                // 🔄 Chamar callback para resetar UI (FloatingToolbar, Grafo)
                if (onOrgReset) {
                    onOrgReset(orgId);
                }
                
                addNotification('success', "Todos os dados e cache da empresa foram resetados!");
            } else {
                addNotification('error', "Erro ao resetar dados. Tente novamente.");
            }
        } catch (e: any) {
            console.error("Erro ao resetar:", e.message || e);
            addNotification('error', "Erro ao resetar dados.");
        }
    };

    const handleRenameOrg = async (orgId: number) => {
        if (!editingNameValue || editingNameValue.trim() === '') {
            setEditingNameOrgId(null);
            return;
        }

        try {
            const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
            const resp = await fetch(`${API_BASE}/api/v1/pipedrive/organizations/${orgId}/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: editingNameValue.trim() })
            });

            if (resp.ok) {
                const data = await resp.json();
                console.log("[Drawer] Empresa renomeada:", data);

                // Atualizar no local state
                const updatedOrg = filteredOrgs.find(o => Number(o.id) === orgId);
                if (updatedOrg) {
                    updatedOrg.name = editingNameValue.trim();
                }

                // Atualizar orgDetails se estiver carregado
                setOrgDetails(prev => {
                    if (prev[orgId]) {
                        return {
                            ...prev,
                            [orgId]: { ...prev[orgId], name: editingNameValue.trim() }
                        };
                    }
                    return prev;
                });

                setEditingNameOrgId(null);
                
                // 📢 Notificar componente pai da mudança de nome
                if (onOrgRenamed) {
                    onOrgRenamed(orgId, editingNameValue.trim());
                }
                
                addNotification('success', "Nome da empresa atualizado!");
            } else {
                addNotification('error', "Erro ao renomear empresa. Tente novamente.");
            }
        } catch (e: any) {
            console.error("Erro ao renomear:", e.message || e);
            addNotification('error', "Erro ao renomear empresa.");
        }
    };

    const formatDate = (dateStr: string) => {
        if (!dateStr) return '';
        return new Date(dateStr).toLocaleDateString('pt-BR');
    };

    // Filtra a organização que está em foco
    const focusedOrg = expandedOrgId ? filteredOrgs.find(o => Number(o.id) === expandedOrgId) : null;
    
    // Identificar qual organização está escaneando/mapeando ativamente agora
    let scanningOrgId: number | null = null;
    if (activeJobId) {
        try {
            const jobStr = localStorage.getItem('active-discovery-job');
            if (jobStr) scanningOrgId = JSON.parse(jobStr).orgId;
        } catch (e: any) {}
    }

    return (
        <div className={styles.drawer}>
            <div className={styles.drawerHeader}>
                {expandedOrgId ? (
                    <div className={styles.focusHeader}>
                        <button onClick={() => setExpandedOrgId(null)} className={styles.backToListBtn}>
                            <X size={14} />
                            <span>Voltar para a lista</span>
                        </button>
                        <button 
                            onClick={(e) => handleResetOrgData(e, expandedOrgId)} 
                            className={styles.backToListBtn}
                            title="Resetar todos os dados desta empresa"
                            style={{ color: '#ef4444', marginLeft: '8px' }}
                        >
                            <Trash2 size={14} />
                            <span>Resetar Dados</span>
                        </button>
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
                        <Loader2 size={32} className={styles.loadingAnim} />
                    </div>
                ) : expandedOrgId && focusedOrg ? (
                    /* MODO FOCO TOTAL (UMA ÚNICA EMPRESA) */
                    <div className={styles.focusedOrgView}>
                        <div className={styles.focusedOrgHero}>
                            <div className={styles.focusedOrgLogoWrapper}>
                                {focusedOrg.logo ? (
                                    <img src={focusedOrg.logo} alt="" className={styles.focusedOrgLogo} />
                                ) : (
                                    <Building size={24} className={styles.orgIcon} />
                                )}
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
                                        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
                                    >
                                        {focusedOrg.name}
                                        {scanningOrgId === expandedOrgId && (
                                            <Loader2 size={16} className={styles.loadingAnim} style={{ color: 'rgb(122, 139, 255)' }} />
                                        )}
                                    </h2>
                                )}
                                <div className={styles.focusedMetaRow}>
                                    <span className={styles.focusedOrgAddress}>
                                        {focusedOrg.address.toLowerCase().replace(/(^\w|\s\w)/g, (m: string) => m.toUpperCase())}
                                    </span>

                                </div>
                            </div>
                        </div>

                        <div className={styles.detailsPane}>
                            {loadingDetails[expandedOrgId] ? (
                                <div className={styles.detailsLoading}>
                                    <Loader2 size={16} className={styles.loadingAnim} />
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
                                                persons={orgDetails[expandedOrgId].persons} 
                                            />
                                        )}

                                        {activeTab === 'deals' && (
                                            <div className={styles.dealList}>
                                                {orgDetails[expandedOrgId].deals.length === 0 && <div className={styles.emptyState}>Sem negócios.</div>}
                                                {orgDetails[expandedOrgId].deals.map((d: any) => (
                                                    <div key={d.id} className={styles.dealItem}>
                                                        <div className={styles.dealTitle}>{d.title}</div>
                                                        <div className={styles.dealMeta}>
                                                            <span className={styles.dealValue}>
                                                                <DollarSign size={10} /> {d.formatted_value || 'R$ 0'}
                                                            </span>
                                                            <span className={`${styles.dealStatus} ${styles[d.status]}`}>
                                                                {d.status === 'open' ? 'Aberto' : d.status === 'won' ? 'Ganho' : 'Perdido'}
                                                            </span>
                                                        </div>
                                                    </div>
                                                ))}
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
                                emp.id !== "root_company" &&
                                emp.department !== "Quadro Societário" &&
                                emp.department !== "Quadro de Sócios (QSA)" &&
                                emp.level !== 6 &&
                                !String(emp.id).startsWith("partner_")
                            );

                            const graphPics = validEmps
                                .map(emp => emp.profile_pic || emp.avatar)
                                .filter(pic => pic && pic.length > 10);

                            // Sobrescreve sempre, para zerar as imagems caso comece um novo mapeamento
                            displayPics = graphPics;
                            displayCount = validEmps.length;
                        }

                        return (
                            <div
                                key={org.local_id || org.id}
                                className={`${styles.orgItem} ${isSelected ? styles.selectedOrgItem : ''}`}
                                onClick={() => onOrgClick(org)}
                            >
                                <div className={styles.orgMainInfo}>
                                    <div className={styles.orgLogoWrapper}>
                                        {org.logo ? (
                                            <img src={org.logo} alt="" className={styles.orgLogo} />
                                        ) : (
                                            <Building size={16} className={styles.orgIcon} />
                                        )}
                                    </div>
                                    <div className={styles.orgIdentity}>
                                        <span className={styles.orgName} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                            {org.name}
                                            {scanningOrgId === orgId && (
                                                <Loader2 size={14} className={styles.loadingAnim} style={{ color: 'rgb(122, 139, 255)' }} />
                                            )}
                                        </span>
                                        {org.address && (
                                            <div className={styles.orgAddress}>
                                                {org.address.toLowerCase().replace(/(^\w|\s\w)/g, (m: string) => m.toUpperCase())}
                                            </div>
                                        )}
                                    </div>
                                    <button
                                        className={styles.expandToggle}
                                        onClick={(e) => toggleExpand(e, orgId)}
                                        title="Expandir"
                                    >
                                        <ChevronRight size={16} />
                                    </button>
                                </div>

                                <div className={styles.orgFooter}>
                                    <div className={styles.employeeStack}>
                                        {(displayCount > 0 || isSelected) ? (
                                            <>
                                                <div style={{ display: 'flex', alignItems: 'center', marginRight: '8px' }}>
                                                    {displayPics.length > 0 ? (
                                                        displayPics.slice(0, 3).map((pic: string, i: number) => (
                                                            <img
                                                                key={i}
                                                                src={pic}
                                                                alt=""
                                                                className={styles.stackedAvatar}
                                                                style={{ zIndex: 3 - i }}
                                                            />
                                                        ))
                                                    ) : (
                                                        [0, 1, 2].map((i) => (
                                                            <div key={i} className={styles.stackedAvatar} style={{
                                                                background: i === 0 ? '#2a2a2a' : i === 1 ? '#333' : '#1a1a1a',
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                justifyContent: 'center',
                                                                zIndex: 3 - i
                                                            }}>
                                                                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'rgba(255,255,255,0.1)' }} />
                                                            </div>
                                                        ))
                                                    )}
                                                </div>
                                                <span className={styles.empCountBadge}>
                                                    {displayCount || 'Pronta para'} {displayCount === 1 ? 'funcionário' : 'mapeamento'}
                                                </span>
                                            </>
                                        ) : null}
                                    </div>
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
};
