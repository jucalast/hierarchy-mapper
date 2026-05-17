import React from 'react';
import { Users, Briefcase, Clock, DollarSign, User } from 'lucide-react';
import { Avatar, Spinner, Badge } from '../../';
import { HistoryTimeline } from '../../../prospecting/HistoryTimeline';
import { ContactList } from '../../../prospecting/ContactList';
import styles from '../Drawer.module.css';

interface FocusedOrgViewProps {
    focusedOrg: any;
    expandedOrgId: number;
    orgDetails: Record<number, any>;
    loadingDetails: Record<number, boolean>;
    activeTab: string;
    setActiveTab: (tab: string) => void;
    editingNameOrgId: number | null;
    editingNameValue: string;
    setEditingNameValue: (val: string) => void;
    setEditingNameOrgId: (id: number | null) => void;
    handleRenameOrg: (orgId: number) => Promise<void>;
    scanningOrgId: number | null;
    selectedOrgId?: number | null;
    selectedOrgLogo?: string;
}

export const FocusedOrgView: React.FC<FocusedOrgViewProps> = ({
    focusedOrg,
    expandedOrgId,
    orgDetails,
    loadingDetails,
    activeTab,
    setActiveTab,
    editingNameOrgId,
    editingNameValue,
    setEditingNameValue,
    setEditingNameOrgId,
    handleRenameOrg,
    scanningOrgId,
    selectedOrgId,
    selectedOrgLogo,
}) => {
    return (
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
                                    handleRenameOrg(expandedOrgId);
                                } else if (e.key === 'Escape') {
                                    setEditingNameOrgId(null);
                                }
                            }}
                            onBlur={() => handleRenameOrg(expandedOrgId)}
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
    );
};
