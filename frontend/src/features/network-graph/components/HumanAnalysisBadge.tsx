"use client";

import React from 'react';
import { Users } from 'lucide-react';
import { getAvatarUrl, getProxiedUrl } from '@/utils/avatarUtils';
import styles from '../styles/NetworkGraph.module.css';

interface HierarchyEmployee {
    id: string;
    name: string;
    role?: string;
    department?: string;
    linkedin?: string;
    [key: string]: any;
}

interface HumanAnalysisBadgeProps {
    employees: HierarchyEmployee[];
    activeCandidates: HierarchyEmployee[];
    onToggle: (candidates: any[]) => void;
    onClose: () => void;
}

export const HumanAnalysisBadge: React.FC<HumanAnalysisBadgeProps> = ({
    employees,
    activeCandidates,
    onToggle,
    onClose,
}) => {
    const humanPending = employees.filter(e => e.role === 'Análise Humana');
    if (humanPending.length === 0) return null;

    const isShowingHuman = activeCandidates.length > 0 && activeCandidates[0]?.type === 'person';
    const stack = humanPending.slice(0, 3);

    const handleClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (isShowingHuman) { onClose(); return; }
        const candidates = humanPending.map(p => ({
            name: p.name,
            logo: getAvatarUrl(p),
            followers: p.department || (p.role === 'Análise Humana' ? 'Review Pendente' : p.role),
            type: 'person',
            id: p.id,
            originalEmployee: p,
        }));
        onToggle(candidates);
    };

    return (
        <div className={styles.humanAnalysisTrigger} onClick={handleClick}>
            <div className={styles.humanAnalysisAvatarStack}>
                {stack.map((node, idx) => {
                    const rawUrl = getAvatarUrl(node);
                    const proxiedUrl = getProxiedUrl(rawUrl);
                    return (
                        <div key={node.id} className={`${styles.humanAnalysisStackedAvatar} ${styles[`stackLayer${idx}`]}`}>
                            {proxiedUrl ? (
                                <img
                                    src={proxiedUrl}
                                    alt=""
                                    onError={(e) => {
                                        const target = e.target as HTMLImageElement;
                                        target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(node.name || 'P')}&background=ffab00&color=fff&bold=true&rounded=true&size=128`;
                                    }}
                                />
                            ) : (
                                <div className={styles.humanAnalysisAvatarPlaceholder}>
                                    <Users size={idx === 0 ? 20 : 14} />
                                </div>
                            )}
                            {idx === 0 && (
                                <div className={styles.humanAnalysisNotification}>{humanPending.length}</div>
                            )}
                        </div>
                    );
                })}
            </div>

            <div className={styles.humanAnalysisList}>
                <div className={styles.humanAnalysisListTitle}>Análise Humana Pendente</div>
                {humanPending.slice(0, 15).map((n, i) => {
                    const rawUrl = getAvatarUrl(n);
                    const proxiedUrl = getProxiedUrl(rawUrl);
                    return (
                        <div key={i} className={styles.humanAnalysisCard}>
                            {proxiedUrl ? (
                                <img
                                    className={styles.humanAnalysisCardAvatar}
                                    src={proxiedUrl}
                                    alt={n.name}
                                    onError={(e) => {
                                        const target = e.target as HTMLImageElement;
                                        target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(n.name || 'P')}&background=ffab00&color=fff&bold=true&rounded=true&size=128`;
                                    }}
                                />
                            ) : (
                                <Users className={styles.humanAnalysisCardAvatar} size={14} />
                            )}
                            <div className={styles.humanAnalysisCardInfo}>
                                <div className={styles.humanAnalysisCardName}>{n.name}</div>
                                <div className={styles.humanAnalysisCardSub}>Cargo não identificado</div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
