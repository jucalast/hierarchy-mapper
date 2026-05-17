import React from 'react';
import { Search, X, MoreHorizontal, RefreshCw } from 'lucide-react';
import styles from './DrawerHeader.module.css';

interface DrawerHeaderProps {
    expandedOrgId: number | null;
    setExpandedOrgId: (id: number | null) => void;
    searchTerm: string;
    setSearchTerm: (term: string) => void;
    setShowDrawer: (show: boolean) => void;
    showOptionsDropdown: boolean;
    setShowOptionsDropdown: (show: boolean) => void;
    fetchOrgDetails: (orgId: number, force?: boolean) => Promise<void>;
    loadingDetails: Record<number, boolean>;
    setConfirmKind: (kind: 'reset' | 'delete' | null) => void;
    dropdownRef: React.RefObject<HTMLDivElement | null>;
}

export const DrawerHeader: React.FC<DrawerHeaderProps> = ({
    expandedOrgId,
    setExpandedOrgId,
    searchTerm,
    setSearchTerm,
    setShowDrawer,
    showOptionsDropdown,
    setShowOptionsDropdown,
    fetchOrgDetails,
    loadingDetails,
    setConfirmKind,
    dropdownRef,
}) => {
    return (
        <div className={styles.drawerHeader}>
            {expandedOrgId ? (
                <div className={styles.focusHeader}>
                    <button onClick={() => setExpandedOrgId(null)} className={styles.backToListBtn}>
                        <X size={14} />
                        <span>Voltar para a lista</span>
                    </button>

                    <div className={styles.focusHeaderActions} ref={dropdownRef}>
                        <button
                            onClick={() => setShowOptionsDropdown(!showOptionsDropdown)}
                            className={styles.moreOptionsBtn}
                            title="Mais opções"
                        >
                            <MoreHorizontal size={20} />
                        </button>

                        <button
                            onClick={() => fetchOrgDetails(expandedOrgId, true)}
                            className={styles.refreshBtn}
                            title="Sincronizar agora"
                            disabled={loadingDetails[expandedOrgId]}
                        >
                            <RefreshCw size={14} className={loadingDetails[expandedOrgId] ? styles.spin : ''} />
                        </button>

                        {showOptionsDropdown && (
                            <div className={styles.dropdownMenu}>
                                <button
                                    onClick={() => {
                                        setShowOptionsDropdown(false);
                                        setConfirmKind('reset');
                                    }}
                                    className={styles.dropdownItem}
                                    style={{ color: '#f59e0b' }}
                                >
                                    <Search size={14} />
                                    <span>Resetar Cache</span>
                                </button>
                                <button
                                    onClick={() => {
                                        setShowOptionsDropdown(false);
                                        setConfirmKind('delete');
                                    }}
                                    className={styles.dropdownItem}
                                    style={{ color: '#ef4444' }}
                                >
                                    <X size={14} />
                                    <span>Excluir Empresa</span>
                                </button>
                            </div>
                        )}
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
