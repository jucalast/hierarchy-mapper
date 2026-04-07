import React from 'react';
import { 
    Info as LucideInfo, 
    Search, 
    X, 
    Building 
} from 'lucide-react';
import styles from './NetworkGraph.module.css';

interface DrawerProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    searchTerm: string;
    setSearchTerm: (term: string) => void;
    filteredOrgs: any[];
    onOrgClick: (org: any) => void;
}

export const Drawer: React.FC<DrawerProps> = ({
    showDrawer,
    setShowDrawer,
    searchTerm,
    setSearchTerm,
    filteredOrgs,
    onOrgClick
}) => {
    if (!showDrawer) return null;

    return (
        <div className={styles.drawer}>
            <div className={styles.drawerHeader}>
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
            </div>
            
            <div className={styles.drawerList}>
                {filteredOrgs.map(org => (
                    <div 
                        key={org.id} 
                        className={styles.orgItem} 
                        onClick={() => onOrgClick(org)}
                    >
                        <div className={styles.orgMainInfo}>
                            <Building size={14} className={styles.orgIcon} />
                            <span className={styles.orgName}>{org.name}</span>
                        </div>
                        <span className={styles.orgAddress}>
                            {org.address || 'Localização não definida'}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
};
