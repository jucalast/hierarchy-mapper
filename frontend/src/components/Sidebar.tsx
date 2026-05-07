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
} from 'lucide-react';

import styles from './NetworkGraph.module.css';

interface SidebarProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    theme: string;
    onToggleTheme: () => void;
    onReset: () => void;
    onCopyData: () => void;
    onRefine?: () => void;
    onSmartSync?: () => void;
    onOpenProspecting?: () => void;
    isProspecting?: boolean;
    onOpenPreferences?: () => void;
    isPreferences?: boolean;
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
    onOpenProspecting,
    isProspecting,
    onOpenPreferences,
    isPreferences,
}) => {

    return (
        <aside className={styles.sidenav}>
            <div className={styles.headerLogo} style={{ marginBottom: '12px', color: '#3B82F6' }}>
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


            <div className={styles.navIcon} title="Smart Sync" onClick={onSmartSync}>
                <Zap size={20} className={styles.iconSide} />
            </div>

            <div
                className={`${styles.navIcon} ${isProspecting ? styles.navIconActive : ''}`}
                title="Prospecção Inteligente"
                onClick={onOpenProspecting}
            >
                <Radar size={20} className={styles.iconSide} />
            </div>

            {/* Ícone de acesso ao Módulo de WhatsApp */}
            <div 
                className={styles.navIcon} 
                title="Mensagens (WhatsApp)" 
                onClick={() => window.location.href = '/whatsapp'}
                style={{ overflow: 'hidden', padding: '6px' }}
            >
                <img 
                    src="/wppicon.png" 
                    alt="WhatsApp" 
                    style={{ 
                        width: '100%', 
                        height: '100%', 
                        objectFit: 'contain', 
                        borderRadius: '6px',
                        transition: 'transform 0.2s'
                    }}
                />
            </div>

            <div className={styles.navIcon} title="Nova Empresa" onClick={onReset}>
                <CirclePlus size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Copiar Dados (Debug)" onClick={onCopyData}>
                <Bug size={20} className={styles.iconSide} />
            </div>


            <div className="mt-auto flex flex-col gap-5 text-white/40 w-full">
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
