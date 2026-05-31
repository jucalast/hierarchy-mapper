import React from 'react';
import {
    Asterisk,
    CirclePlus,
    Zap,
    Sun,
    Moon,
    Settings,
    Bug,
    Workflow,
    Radar,
    Loader2
} from 'lucide-react';

import styles from './Sidebar.module.css';

interface SidebarProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    theme: string;
    onToggleTheme: () => void;
    onReset: () => void;
    onCopyData: () => void;
    onRefine?: () => void;
    onSmartSync?: () => void;
    isSmartSyncLoading?: boolean;
    onOpenProspecting?: () => void;
    isProspecting?: boolean;
    onOpenPreferences?: () => void;
    isPreferences?: boolean;
    onOpenLinkedinScrape?: () => void;
    isLinkedinScrape?: boolean;
    isScanActive?: boolean;
}


export const Sidebar: React.FC<SidebarProps> = ({
    showDrawer,
    setShowDrawer,
    theme,
    onToggleTheme,
    onReset,
    onCopyData,
    onRefine,
    onSmartSync,
    isSmartSyncLoading,
    onOpenProspecting,
    isProspecting,
    onOpenPreferences,
    isPreferences,
    onOpenLinkedinScrape,
    isLinkedinScrape,
    isScanActive,
}) => {

    return (
        <aside className={styles.sidenav}>
            <div className={styles.headerLogo} style={{ marginBottom: '12px', color: 'var(--sw-primary)' }}>
                <Asterisk size={24} />
            </div>

            <div
                className={`${styles.navIcon} ${showDrawer ? styles.navIconActive : ''}`}
                style={{ overflow: 'hidden', padding: '6px' }}
                onClick={() => setShowDrawer(!showDrawer)}
                title="Empresas Pipedrive"
            >
                <img 
                    src="/pipedrive.png" 
                    alt="Pipedrive" 
                    style={{ 
                        width: '100%', 
                        height: '100%', 
                        objectFit: 'contain', 
                        borderRadius: '8px', 
                        opacity: 1, /* Removed transparency per user request */
                        transition: 'transform 0.2s'
                    }}
                    className={styles.sidebarBrandIcon}
                />
            </div>


            <div 
                className={styles.navIcon} 
                title="Analista de IA"
                onClick={onRefine}
            >
                <Workflow size={20} className={styles.iconSide} />
            </div>


            <div className={styles.navIcon} title="Smart Sync" onClick={isSmartSyncLoading ? undefined : onSmartSync}>
                {isSmartSyncLoading ? (
                    <div className={styles.spin}>
                        <Loader2 size={20} />
                    </div>
                ) : (
                    <Zap size={20} className={styles.iconSide} />
                )}
            </div>

            <div
                className={`${styles.navIcon} ${isProspecting ? styles.navIconActive : ''}`}
                title="Prospecção Inteligente"
                onClick={onOpenProspecting}
            >
                <Radar size={20} className={styles.iconSide} />
            </div>

            <div
                className={`${styles.navIcon} ${isLinkedinScrape ? styles.navIconActive : ''}`}
                title={isScanActive ? 'Raspador LinkedIn — Scan em andamento em background' : 'Raspador LinkedIn'}
                onClick={onOpenLinkedinScrape}
                style={{ position: 'relative' }}
            >
                <svg 
                    xmlns="http://www.w3.org/2000/svg" 
                    width="20" 
                    height="20" 
                    viewBox="0 0 24 24" 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="2" 
                    strokeLinecap="round" 
                    strokeLinejoin="round"
                    className={styles.iconSide}
                >
                    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
                    <rect x="2" y="9" width="4" height="12" />
                    <circle cx="4" cy="4" r="2" />
                </svg>
                {isScanActive && (
                    <span style={{
                        position: 'absolute',
                        top: '4px',
                        right: '4px',
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: '#4ade80',
                        border: '1.5px solid var(--sw-bg)',
                        animation: 'pulse 1.5s infinite ease-in-out',
                        display: 'block',
                    }} />
                )}
            </div>

            <div className={styles.navIcon} title="Nova Empresa" onClick={onReset}>
                <CirclePlus size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Copiar Dados (Debug)" onClick={onCopyData}>
                <Bug size={20} className={styles.iconSide} />
            </div>


            <div className="mt-auto flex flex-col gap-5 w-full" style={{ color: 'var(--sw-text-muted)' }}>
                <div className={styles.navIcon} onClick={onToggleTheme} title="Alternar Tema">
                    {theme === "dark" ? <Sun size={20} className={styles.iconSide} /> : <Moon size={20} className={styles.iconSide} />}
                </div>

                <div 
                    className={`${styles.navIcon} ${isPreferences ? styles.navIconActive : ''}`} 
                    title="Preferências"
                    onClick={onOpenPreferences}
                >
                    <Settings size={20} className={styles.iconSide} />
                </div>
            </div>
        </aside>
    );
};
