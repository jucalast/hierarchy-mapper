import React from 'react';
import { Search, X, RefreshCw, Settings, RefreshCcw, Trash2 } from 'lucide-react';
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
    onOpenDetailsModal: () => void;
    onNavigateToRoot?: () => void;
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
    onOpenDetailsModal,
    onNavigateToRoot,
}) => {


    const dropdownItems = React.useMemo(() => [
        {
            label: 'Detalhes e Configurações',
            onClick: () => onOpenDetailsModal(),
            icon: <Settings size={14} />
        },
        {
            label: 'Sincronizar Dados',
            onClick: () => setConfirmKind('reset'),
            icon: <RefreshCcw size={14} />,
            style: { color: '#f59e0b' }
        },
        {
            label: 'Excluir Empresa',
            onClick: () => setConfirmKind('delete'),
            icon: <Trash2 size={14} />,
            danger: true
        }
    ], [setConfirmKind, onOpenDetailsModal]);

    return (
        <div className={styles.drawerHeader}>
            {expandedOrgId ? (
                <div className={styles.focusHeader}>
                    <button onClick={() => {
                        setExpandedOrgId(null);
                        if (onNavigateToRoot) {
                            onNavigateToRoot();
                        }
                    }} className={styles.backToListBtn}>
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
                <div className={styles.mainHeader}>
                    <div className={styles.drawerInputWrapper}>
                        <Search size={16} className={styles.inputIcon} />
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            placeholder="Pesquisar no Pipedrive..."
                            className={styles.drawerInput}
                        />
                        {searchTerm && (
                            <button 
                                className={styles.clearSearchBtn}
                                onClick={() => setSearchTerm('')}
                                title="Limpar pesquisa"
                            >
                                <X size={14} />
                            </button>
                        )}
                    </div>
                    
                    <div className={styles.headerRightActions}>
                        <button onClick={() => setShowDrawer(false)} className={styles.backBtn} title="Fechar">
                            <X size={16} />
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
