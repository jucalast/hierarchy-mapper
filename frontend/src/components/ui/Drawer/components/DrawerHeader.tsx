import React from 'react';
import { Search, X, RefreshCw } from 'lucide-react';
import styles from './DrawerHeader.module.css';
import { Dropdown } from '../../Dropdown';

interface DrawerHeaderProps {
    expandedOrgId: number | null;
    setExpandedOrgId: (id: number | null) => void;
    searchTerm: string;
    setSearchTerm: (term: string) => void;
    setShowDrawer: (show: boolean) => void;
    fetchOrgDetails: (orgId: number, force?: boolean) => Promise<void>;
    loadingDetails: Record<number, boolean>;
    setConfirmKind: (kind: 'reset' | 'delete' | null) => void;
}

export const DrawerHeader: React.FC<DrawerHeaderProps> = ({
    expandedOrgId,
    setExpandedOrgId,
    searchTerm,
    setSearchTerm,
    setShowDrawer,
    fetchOrgDetails,
    loadingDetails,
    setConfirmKind,
}) => {
    const dropdownItems = React.useMemo(() => [
        {
            label: 'Resetar Cache',
            onClick: () => setConfirmKind('reset'),
            icon: <Search size={14} />,
            style: { color: '#f59e0b' }
        },
        {
            label: 'Excluir Empresa',
            onClick: () => setConfirmKind('delete'),
            icon: <X size={14} />,
            danger: true
        }
    ], [setConfirmKind]);

    return (
        <div className={styles.drawerHeader}>
            {expandedOrgId ? (
                <div className={styles.focusHeader}>
                    <button onClick={() => setExpandedOrgId(null)} className={styles.backToListBtn}>
                        <X size={14} />
                        <span>Voltar para a lista</span>
                    </button>

                    <div className={styles.focusHeaderActions}>
                        <Dropdown
                            items={dropdownItems}
                            iconType="horizontal"
                            iconSize={20}
                            title="Mais opções"
                        />

                        <button
                            onClick={() => fetchOrgDetails(expandedOrgId, true)}
                            className={styles.refreshBtn}
                            title="Sincronizar agora"
                            disabled={loadingDetails[expandedOrgId]}
                        >
                            <RefreshCw size={14} className={loadingDetails[expandedOrgId] ? styles.spin : ''} />
                        </button>
                    </div>
                </div>
            ) : (
                <>
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
                </>
            )}
        </div>
    );
};
