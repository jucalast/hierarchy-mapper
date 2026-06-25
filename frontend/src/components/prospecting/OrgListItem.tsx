import React from 'react';
import { ChevronRight } from 'lucide-react';
import { Avatar, Spinner, Badge } from '../ui';
import { getProxiedUrl } from '../../utils/avatarUtils';
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
    onMouseEnter?: () => void;
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
    style,
    onMouseEnter
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

    const isMapping = scanningOrgId === orgId;

    return (
        <div
            className={`${styles.orgItem} ${isSelected ? styles.selectedOrgItem : ''} ${isMapping ? styles.mappingOrgItem : ''} ${className}`}
            onClick={() => onClick?.(org)}
            onMouseEnter={onMouseEnter}
            style={{
                cursor: onClick ? 'pointer' : 'default',
                ...style
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%' }}>
                <div className={styles.orgMainInfo} style={{ flex: 1, marginBottom: 0 }}>
                    <div className={styles.orgLogoWrapper} style={{ position: 'relative' }}>
                        {(() => {
                            const hasLogo = !!(org.logo || org.organization_logo || org.logo_url || org.company_logo);
                            return (
                                <>
                                <Avatar
                                    kind="company"
                                    src={org.logo || org.organization_logo || org.logo_url || org.company_logo}
                                    name={org.name || org.title || org.label || org.org_name || 'Empresa'}
                                    data={org}
                                    size={32}
                                    noInitialFallback={displayCount === 0}
                                    style={{ border: hasLogo ? '3px solid var(--sw-border-strong)' : 'none' }}
                                />
                                {isMapping && (
                                    <span className={styles.mappingDot} title="Mapeamento em andamento" />
                                )}
                                </>
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
                                        color: org.icp_tier === 'A' ? '#34d17c' : org.icp_tier === 'B' ? '#f59e0b' : 'var(--sw-text-muted)',
                                        width: 20,
                                        height: 20,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        flexShrink: 0,
                                        lineHeight: 1,
                                        marginLeft: isToday ? '0' : '6px'
                                    }}
                                >
                                    {org.icp_tier}
                                </span>
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
                                    <img src="/linkedin.png" alt="LinkedIn" style={{ width: 18, height: 18, objectFit: 'contain' }} />
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
                    >
                        <ChevronRight size={16} />
                    </button>
                )}
            </div>

            <div className={styles.orgFooter}>
                <div className={styles.employeeStack}>
                    {isMapping ? (
                        <div className={styles.mappingBadge}>
                            <Spinner size={11} inline color="rgb(122, 139, 255)" />
                            <span>Mapeando...</span>
                        </div>
                    ) : (hasMapping || isSelected) ? (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', marginRight: '8px' }}>
                                {displayPics.length > 0 ? (
                                    displayPics.slice(0, 3).map((pic: string, i: number) => (
                                        <Avatar
                                            key={i}
                                            src={pic}
                                            name="Pessoa"
                                            kind="person"
                                            size={20}
                                            className={styles.stackedAvatar}
                                            style={{ 
                                                zIndex: 3 - i,
                                                border: 'var(--sw-border-width) solid var(--sw-border)',
                                                width: '20px',
                                                height: '20px'
                                            }}
                                        />
                                    ))
                                ) : (
                                    [0, 1, 2].map((i) => (
                                        <div key={i} className={styles.stackedAvatar} style={{
                                            background: i === 0 ? 'var(--sw-surface-raised)' : i === 1 ? 'var(--sw-hover)' : 'var(--sw-border-strong)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            zIndex: 3 - i
                                        }}>
                                            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--sw-text-muted)', opacity: 0.3 }} />
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
