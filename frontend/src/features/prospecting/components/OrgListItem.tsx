import React from 'react';
import { ChevronRight, AlertTriangle, TrendingUp } from 'lucide-react';
import { Avatar, Spinner, Badge } from '@/components/ui';
import { getProxiedUrl } from '@/utils/avatarUtils';
import styles from './OrgListItem.module.css';

interface TaskSummary {
    next_due_date: string;
    overdue_count: number;
    pending_count: number;
}

interface OrgListItemProps {
    org: any;
    isSelected?: boolean;
    onClick?: (org: any) => void;
    onToggleExpand?: (e: React.MouseEvent, orgId: number) => void;
    displayCount?: number;
    displayPics?: string[];
    scanningOrgId?: number | null;
    showExpandToggle?: boolean;
    className?: string;
    style?: React.CSSProperties;
}

function formatDueDate(dateStr: string): string {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const due = new Date(dateStr + 'T00:00:00');
    const diff = Math.round((due.getTime() - today.getTime()) / 86400000);
    if (diff < 0) return `${Math.abs(diff)}d atrasada`;
    if (diff === 0) return 'hoje';
    if (diff === 1) return 'amanhã';
    return `em ${diff}d`;
}

export const OrgListItem: React.FC<OrgListItemProps> = ({
    org,
    isSelected = false,
    onClick,
    onToggleExpand,
    displayCount: propDisplayCount,
    displayPics: propDisplayPics,
    scanningOrgId = null,
    showExpandToggle = true,
    className = '',
    style
}) => {
    const orgId = org.id || org.pipedrive_id;
    const taskSummary: TaskSummary | null = org._taskSummary || null;
    const isOverdue = taskSummary ? taskSummary.overdue_count > 0 : false;
    const brToday = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Sao_Paulo' });
    const isToday = taskSummary && !isOverdue
        ? taskSummary.next_due_date === brToday
        : false;
    const isNoTask = !isOverdue && !isToday && (!taskSummary || taskSummary.pending_count === 0);

    // Calcular dados internos se não fornecidos
    const displayCount = propDisplayCount !== undefined ? propDisplayCount : (org.employees_count || org.employee_count || org.mapped_count || 0);
    const displayPics = (propDisplayPics && propDisplayPics.length > 0) ? propDisplayPics : (
        (org.decision_makers || org.employees || [])
            .map((dm: any) => dm.profile_pic || dm.avatar)
            .filter(Boolean) || []
    );

    const hasMapping = displayCount > 0 || displayPics.length > 0;

    return (
        <div
            className={`${styles.orgItem} ${isSelected ? styles.selectedOrgItem : ''} ${className}`}
            onClick={() => onClick?.(org)}
            style={{
                cursor: onClick ? 'pointer' : 'default',
                ...style
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%' }}>
                <div className={styles.orgMainInfo} style={{ flex: 1, marginBottom: 0 }}>
                    <div className={styles.orgLogoWrapper}>
                        {(() => {
                            const hasLogo = !!(org.logo || org.organization_logo || org.logo_url || org.company_logo);
                            return (
                                <Avatar
                                    kind="company"
                                    src={org.logo || org.organization_logo || org.logo_url || org.company_logo}
                                    name={org.name || org.title || org.label || org.org_name || 'Empresa'}
                                    data={org}
                                    size={32}
                                    noInitialFallback={displayCount === 0}
                                    style={{ border: hasLogo ? '3px solid var(--sw-border)' : 'none' }}
                                />
                            );
                        })()}
                    </div>
                    <div className={styles.orgIdentity}>
                        <div className={styles.orgName} style={{ display: 'flex', alignItems: 'center', gap: '6px', width: '100%' }}>
                            <span style={{
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                flex: '0 1 auto'
                            }}>
                                {(() => {
                                    const fullName = org.name || org.title || org.label || org.org_name || org.company_name || 'Empresa';
                                    return fullName.length > 12 ? `${fullName.substring(0, 12)}...` : fullName;
                                })()}
                            </span>

                            {org.icp_tier && (
                                <span
                                    title={`Score ICP: ${org.icp_score || 'N/A'}`}
                                    style={{
                                        fontSize: '13px',
                                        fontWeight: 500,
                                        color: org.icp_tier === 'A' ? 'var(--sw-status-success)' : org.icp_tier === 'B' ? 'var(--sw-status-warning)' : 'var(--sw-text-muted)',
                                        width: 20,
                                        height: 20,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        flexShrink: 0,
                                        lineHeight: 1
                                    }}
                                >
                                    {org.icp_tier}
                                </span>
                            )}

                            {scanningOrgId === orgId && (
                                <Spinner size={14} inline color="var(--sw-primary)" />
                            )}
                            {(org.linkedin || org.linkedin_url) && (
                                <a
                                    href={org.linkedin || org.linkedin_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className={styles.orgLinkedinLink}
                                    onClick={(e) => e.stopPropagation()}
                                    style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', flexShrink: 0 }}
                                >
                                    <img src="/linkedin.png" alt="LinkedIn" style={{ width: 20, height: 20, objectFit: 'contain' }} />
                                </a>
                            )}
                        </div>
                        {(() => {
                            const addr = org.address || org.org_address;
                            if (!addr) return null;

                            // Pipedrive às vezes retorna endereço como objeto
                            let displayAddr = "";
                            if (typeof addr === 'object' && addr !== null) {
                                displayAddr = addr.label || addr.formatted_address || addr.address || "";
                            } else {
                                displayAddr = String(addr);
                            }

                            if (!displayAddr || displayAddr === "undefined") return null;

                            return (
                                <div className={styles.orgAddress}>
                                    {displayAddr.toLowerCase().replace(/(^\w|\s\w)/g, (m: string) => m.toUpperCase())}
                                </div>
                            );
                        })()}
                    </div>
                </div>
                {showExpandToggle && onToggleExpand && (
                    <button
                        className={`${styles.expandToggle} ${isOverdue ? styles.overdue : isToday ? styles.today : isNoTask ? styles.noTask : ''}`}
                        onClick={(e) => onToggleExpand(e, orgId)}
                        title={isOverdue ? 'Tarefa atrasada' : isToday ? 'Tarefa hoje' : isNoTask ? 'Sem tarefa agendada' : 'Expandir'}
                        style={{ position: 'relative', top: 'auto', right: 'auto', flexShrink: 0 }}
                    >
                        <ChevronRight size={16} />
                    </button>
                )}
            </div>

            <div className={styles.orgFooter}>
                <div className={styles.employeeStack}>
                    {(hasMapping || isSelected) ? (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', marginRight: '8px' }}>
                                {displayPics.length > 0 ? (
                                    displayPics.slice(0, 3).map((pic: string, i: number) => (
                                        <img
                                            key={i}
                                            src={getProxiedUrl(pic)}
                                            alt=""
                                            className={styles.stackedAvatar}
                                            style={{ zIndex: 3 - i }}
                                        />
                                    ))
                                ) : (
                                    [0, 1, 2].map((i) => (
                                        <div key={i} className={styles.stackedAvatar} style={{
                                            background: 'var(--sw-surface-raised)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            zIndex: 3 - i
                                        }}>
                                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--sw-border)' }} />
                                        </div>
                                    ))
                                )}
                            </div>
                            <span className={styles.empCountBadge}>
                                {displayCount > 0 ? `${displayCount} ${displayCount === 1 ? 'funcionário' : 'mapeamento'}` : 'Pronta para mapeamento'}
                            </span>
                        </>
                    ) : null}
                </div>
            </div>
        </div>
    );
};
