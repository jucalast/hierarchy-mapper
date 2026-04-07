import React from 'react';
import { 
    Asterisk, 
    LayoutDashboard, 
    CirclePlus, 
    Bot, 
    History, 
    Zap, 
    Eraser, 
    Sun, 
    Moon, 
    Settings 
} from 'lucide-react';
import styles from './NetworkGraph.module.css';

interface SidebarProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    theme: string;
    onToggleTheme: () => void;
    onReset: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ 
    showDrawer, 
    setShowDrawer, 
    theme, 
    onToggleTheme, 
    onReset 
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
                onClick={onReset}
                title="Nova Busca"
            >
                <CirclePlus size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Analista de IA">
                <Bot size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Histórico">
                <History size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Smart Sync">
                <Zap size={20} className={styles.iconSide} />
            </div>

            <div className={styles.navIcon} title="Limpar Canvas">
                <Eraser size={20} className={styles.iconSide} />
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
