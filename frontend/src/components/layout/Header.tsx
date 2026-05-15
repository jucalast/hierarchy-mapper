import { Database } from 'lucide-react';
import styles from './Header.module.css';

interface HeaderProps {
    confirmedBrand: string;
}

export const Header: React.FC<HeaderProps> = ({ confirmedBrand }) => {
    return (
        <header className={styles.header} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', paddingRight: '16px' }}>
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
