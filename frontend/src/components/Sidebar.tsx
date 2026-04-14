import React from 'react';
import { 
    Asterisk, 
    LayoutDashboard, 
    CirclePlus, 
    History, 
    Zap, 
    Eraser, 
    Sun, 
    Moon, 
    Settings,
    Bug,
    Workflow,
    MessageCircle
} from 'lucide-react';

import styles from './NetworkGraph.module.css';

interface SidebarProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    showChat: boolean;
    setShowChat: (show: boolean) => void;
    theme: string;
    onToggleTheme: () => void;
    onReset: () => void;
    onCopyData: () => void;
    onRefine?: () => void;
    onSmartSync?: () => void;
}


export const Sidebar: React.FC<SidebarProps> = ({ 
    showDrawer, 
    setShowDrawer,
    showChat,
    setShowChat,
    theme, 
    onToggleTheme, 
    onReset,
    onCopyData,
    onRefine,
    onSmartSync
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
                className={`${styles.navIcon} ${showChat ? styles.navIconActive : ''}`}
                onClick={() => setShowChat(!showChat)}
                title="Assistente IA"
            >
                <MessageCircle size={20} className={styles.iconSide} />
            </div>

            <div
                className={styles.navIcon}
                onClick={onReset}
                title="Nova Busca"
            >
                <CirclePlus size={20} className={styles.iconSide} />
            </div>

            <div 
                className={styles.navIcon} 
                title="Analista de IA"
                onClick={onRefine}
            >
                <Workflow size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Histórico">
                <History size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Smart Sync" onClick={onSmartSync}>
                <Zap size={20} className={styles.iconSide} />
            </div>

            {/* Ícone de acesso ao Módulo de WhatsApp */}
            <div 
                className={styles.navIcon} 
                title="Mensagens (WhatsApp)" 
                onClick={() => window.location.href = '/whatsapp'}
            >
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={styles.iconSide}>
                    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
                </svg>
            </div>

            <div className={styles.navIcon} title="Limpar Canvas" onClick={onReset}>
                <Eraser size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Copiar Dados (Debug)" onClick={onCopyData}>
                <Bug size={20} className={styles.iconSide} />
            </div>


            <div className="mt-auto flex flex-col gap-5 text-white/40 w-full">
                <div className={styles.navIcon} onClick={onToggleTheme} title="Alternar Tema">
                    {theme === "dark" ? <Sun size={20} className={styles.iconSide} /> : <Moon size={20} className={styles.iconSide} />}
                </div>

                <div className={styles.navIcon} title="Preferências">
                    <Settings size={20} className={styles.iconSide} />
                </div>
            </div>
        </aside>
    );
};
