import React from 'react';
import { X, Check } from 'lucide-react';
import styles from './styles/Toolbar.module.css';
import { Avatar } from '../ui';
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
    const tierColor = lead.icp_tier === 'A' ? 'var(--sw-status-success)' : 'var(--sw-status-warning)';

    return (
        <div
            data-lead-id={lead.id}
            className={`${styles.brandCard} ${isSelected ? styles.brandCardActive : ''} ${isHovered ? styles.brandCardHovered : ''}`}
            onClick={() => onSelect(lead)}
        >
            {/* Avatar Column */}
            <div className={styles.brandAvatarWrapper} style={{ position: 'relative' }}>
                <Avatar
                    kind="company"
                    data={lead}
                    size={34}
                />
                <div style={{
                    position: 'absolute',
                    bottom: -3,
                    right: -3,
                    background: tierColor,
                    color: '#fff',
                    fontSize: '8px',
                    fontWeight: 900,
                    width: 14,
                    height: 14,
                    borderRadius: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                    zIndex: 5,
                    border: '1px solid var(--sw-border)',
                }}>
                    {lead.icp_tier}
                </div>
            </div>

            {/* Info Content */}
            <div className={styles.brandInfo}>
                <div className={styles.brandNameLine}>
                    {lead.name}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: 1 }}>
                    <span style={{
                        fontSize: '9px',
                        fontWeight: 800,
                        color: tierColor,
                    }}>
                        {lead.icp_score} pts
                    </span>
                    {lead.pipedrive_status === 'new' ? (
                        <span style={{
                            fontSize: '9px',
                            fontWeight: 800,
                            color: 'var(--sw-status-success)',
                            textTransform: 'uppercase',
                        }}>
                            Novo
                        </span>
                    ) : (
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '3px',
                        }}>
                            <img src="/pipedrive.png" alt="P" style={{ width: 8, height: 8, filter: 'grayscale(0.3)' }} />
                            <span style={{
                                fontSize: '8px',
                                fontWeight: 800,
                                color: lead.pipedrive_status === 'lost_deal' ? 'var(--sw-status-danger)' : 'var(--sw-status-warning)',
                                textTransform: 'uppercase',
                            }}>
                                {lead.pipedrive_status === 'lost_deal' ? 'Perdido' : 'Parado'}
                            </span>
                        </div>
                    )}
                </div>

                {lead.segment && (
                    <div className={styles.brandFollowers} style={{ marginTop: 1 }}>
                        {lead.segment}
                    </div>
                )}
            </div>

            {/* LinkedIn Icon */}
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

            {/* Quick Actions (only visible on hover through CSS) */}
            <div className={styles.cardQuickActions}>
                <button
                    type="button"
                    className={styles.rejectBtn}
                    onClick={(e) => { e.stopPropagation(); onReject(lead.id); }}
                    title="Rejeitar lead"
                >
                    <X size={12} />
                </button>
                <button
                    type="button"
                    className={styles.approveBtn}
                    onClick={(e) => { e.stopPropagation(); onApprove(lead.id); }}
                    title="Criar no Pipedrive"
                >
                    <Check size={12} />
                </button>
            </div>
        </div>
    );
};
