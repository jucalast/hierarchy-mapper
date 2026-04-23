import React from 'react';
import { ChevronRight } from 'lucide-react';
import { Avatar, Spinner } from './ui';
import styles from './NetworkGraph.module.css';

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
            style={{ cursor: onClick ? 'pointer' : 'default', ...style }}
        >
            <div className={styles.orgMainInfo}>
                <div className={styles.orgLogoWrapper}>
                    <Avatar
                        kind="company"
                        src={org.logo || org.organization_logo}
                        name={org.name || org.title || org.label || org.org_name || 'Empresa'}
                        data={org}
                        size={32}
                        noInitialFallback={displayCount === 0}
                    />
                </div>
                <div className={styles.orgIdentity}>
                    <span className={styles.orgName} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {org.name || org.title || org.label || org.org_name || org.company_name || 'Empresa'}
                        {scanningOrgId === orgId && (
                            <Spinner size={14} inline color="rgb(122, 139, 255)" />
                        )}
                    </span>
                    {(org.address || org.org_address) && (
                        <div className={styles.orgAddress}>
                            {(org.address || org.org_address).toLowerCase().replace(/(^\w|\s\w)/g, (m: string) => m.toUpperCase())}
                        </div>
                    )}
                </div>
                {showExpandToggle && onToggleExpand && (
                    <button
                        className={styles.expandToggle}
                        onClick={(e) => onToggleExpand(e, orgId)}
                        title="Expandir"
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
                                {displayCount > 0 ? `${displayCount} ${displayCount === 1 ? 'funcionário' : 'mapeamento'}` : 'Pronta para mapeamento'}
                            </span>
                        </>
                    ) : null}
                </div>
            </div>
        </div>
    );
};
