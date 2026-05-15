import React from 'react';
import { X, Check } from 'lucide-react';
import styles from './FloatingToolbar.module.css';
import { Avatar } from '@/components/ui';
import type { ProspectLead } from '@/hooks/useProspecting';

interface ProspectLeadCardProps {
    lead: ProspectLead;
    isSelected: boolean;
    isHovered: boolean;
    onSelect: (lead: ProspectLead) => void;
    onApprove: (id: string) => Promise<void>;
    onReject: (id: string) => Promise<void>;
}

export const ProspectLeadCard: React.FC<ProspectLeadCardProps> = ({
    lead,
    isSelected,
    isHovered,
    onSelect,
    onApprove,
    onReject,
}) => {
    const tierColor = lead.icp_tier === 'A' ? '#34d17c' : '#f59e0b';

    return (
        <div
            data-lead-id={lead.id}
            className={`${styles.brandCard} ${isSelected ? styles.brandCardActive : ''} ${isHovered ? styles.brandCardHovered : ''}`}
            onClick={() => onSelect(lead)}
            style={{
                minWidth: 220,
                maxWidth: 280,
                padding: '8px 10px',
                display: 'flex',
                gap: '10px',
                alignItems: 'center',
                position: 'relative',
                overflow: 'hidden',
            }}
        >
            {/* Logo Column */}
            <div style={{ position: 'relative', width: 42, height: 42, flexShrink: 0 }}>
                <Avatar
                    kind="company"
                    data={lead}
                    size={42}
                    className={styles.brandAvatar}
                    style={{
                        background: '#fff',
                        borderRadius: '8px',
                        border: '1px solid rgba(255,255,255,0.1)',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                    }}
                />
                <div style={{
                    position: 'absolute',
                    bottom: -4,
                    right: -4,
                    background: tierColor,
                    color: '#fff',
                    fontSize: '9px',
                    fontWeight: 900,
                    width: 18,
                    height: 18,
                    borderRadius: '5px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: '2px solid #141414',
                    zIndex: 5,
                }}>
                    {lead.icp_tier}
                </div>
            </div>

            {/* Info Content */}
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '3px', paddingRight: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div className={styles.brandNameLine} style={{
                        fontSize: '12px',
                        fontWeight: 700,
                        color: '#fff',
                        lineHeight: 1.2,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                    }}>
                        {lead.name}
                    </div>
                    <img
                        src="/linkedin.png"
                        alt="LinkedIn"
                        className={styles.linkedinIcon}
                        onClick={(e) => {
                            e.stopPropagation();
                            const url = lead.linkedin_url || `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(lead.name)}`;
                            window.open(url, '_blank');
                        }}
                        title="Ver no LinkedIn"
                    />
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{
                        fontSize: '10px',
                        fontWeight: 800,
                        color: tierColor,
                        background: 'rgba(255,255,255,0.06)',
                        padding: '2px 6px',
                        borderRadius: '5px',
                        border: '1px solid rgba(255,255,255,0.03)',
                    }}>
                        {lead.icp_score} pts
                    </span>
                    {lead.pipedrive_status === 'new' ? (
                        <div style={{
                            fontSize: '9px',
                            fontWeight: 800,
                            color: '#34d17c',
                            background: 'rgba(255,255,255,0.06)',
                            padding: '2px 8px',
                            borderRadius: '5px',
                            border: '1px solid rgba(255,255,255,0.03)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.02em',
                        }}>
                            Novo Radar
                        </div>
                    ) : (
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '5px',
                            background: 'rgba(255,255,255,0.06)',
                            padding: '2px 8px',
                            borderRadius: '5px',
                            border: '1px solid rgba(255,255,255,0.03)',
                        }}>
                            <img src="/pipedrive.png" alt="P" style={{ width: 10, height: 10, filter: 'grayscale(0.3)' }} />
                            <span style={{
                                fontSize: '9px',
                                fontWeight: 800,
                                color: lead.pipedrive_status === 'lost_deal' ? '#ef4444' : '#f59e0b',
                                textTransform: 'uppercase',
                                letterSpacing: '0.02em',
                            }}>
                                {lead.pipedrive_status === 'lost_deal'
                                    ? 'Perdido'
                                    : (lead.pipedrive_deal_info?.days_inactive ? `${lead.pipedrive_deal_info.days_inactive}d` : 'Parado')}
                            </span>
                        </div>
                    )}
                </div>

                {lead.segment && (
                    <div style={{
                        fontSize: '10px',
                        color: 'rgba(255,255,255,0.4)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        marginTop: '2px',
                    }}>
                        {lead.segment}
                    </div>
                )}
            </div>

            {/* Quick actions */}
            <div className={styles.cardQuickActions}>
                <button
                    type="button"
                    className={styles.rejectBtn}
                    onClick={(e) => { e.stopPropagation(); onReject(lead.id); }}
                    title="Rejeitar lead"
                >
                    <X size={14} />
                </button>
                <button
                    type="button"
                    className={styles.approveBtn}
                    onClick={(e) => { e.stopPropagation(); onApprove(lead.id); }}
                    title="Criar no Pipedrive"
                >
                    <Check size={14} />
                </button>
            </div>
        </div>
    );
};
