import React from 'react';
import { Database } from 'lucide-react';
import styles from './NetworkGraph.module.css';

interface HeaderProps {
    confirmedBrand: string;
}

export const Header: React.FC<HeaderProps> = ({ confirmedBrand }) => {
    return (
        <header className={styles.header}>
            <div className={styles.breadcrumbs}>
                <div className={styles.headerIconWrapper}>
                    <Database size={14} className={styles.headerIcon} />
                </div>
                <span className={styles.breadcrumbItem}>Pipedrive Workspace</span>
                <span className={styles.breadcrumbDivider}>/</span>
                <span className={styles.breadcrumbActive}>{confirmedBrand || 'OSINT Flow'}</span>
                <span className={styles.statusBadge}>DRAFT</span>
            </div>
        </header>
    );
};
