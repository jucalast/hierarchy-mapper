import React from 'react';
import Link from 'next/link';
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
    Loader2,
    Headset,
    PanelRight,
    LogOut,
    CheckCircle2
} from 'lucide-react';
import { TriggerNotifications } from '@/components/ui/TriggerNotifications';
import { Avatar } from '@/components/ui';
import { API_BASE_URL } from '@/services/config';

import styles from './Sidebar.module.css';

interface SidebarProps {
    showDrawer: boolean;
    setShowDrawer: (show: boolean) => void;
    theme: string;
    onToggleTheme: () => void;
    onReset: () => void;
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
    onOpenLigacao?: () => void;
    isLigacao?: boolean;
    currentUser?: { name: string; avatar: string | null; company_name?: string } | null;
    tasksForToday?: number | null;
    onToggleChat?: () => void;
    onLogout?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
    showDrawer,
    setShowDrawer,
    theme,
    onToggleTheme,
    onReset,
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
    onOpenLigacao,
    isLigacao,
    currentUser,
    tasksForToday,
    onToggleChat,
    onLogout
}) => {

    return (
        <aside className={styles.sidenav}>
            <header style={{ height: 'var(--header-height)', display: 'flex', alignItems: 'center', width: '100%', flexShrink: 0 }}>
                <div className={styles.headerLogoWrapper} style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                    <div className={styles.iconContainer}>
                        <Asterisk size={28} />
                    </div>
                    <span className={styles.label} style={{ fontSize: '16px', fontWeight: 'bold' }}>LINKB2B</span>
                </div>
            </header>

            {/* User Profile */}
            {currentUser && (
                <div className={styles.navIcon} style={{ height: 'auto', padding: '12px 0', flexDirection: 'column', alignItems: 'flex-start', cursor: 'default' }}>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', width: 'calc(100% - 12px)', margin: '0 6px', background: '#131313', borderRadius: '12px', padding: '4px 0 8px 0', overflow: 'hidden' }}>
                        
                        {/* ROW 1: Avatar + Name/Company */}
                        <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                            <div style={{ minWidth: '44px', display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                                <div style={{ position: 'relative' }}>
                                    <div style={{ width: 36, height: 36, borderRadius: '10px', overflow: 'hidden', position: 'relative', border: `1px solid #2a2d4b`, display: 'flex' }}>
                                        <Avatar
                                            kind="person"
                                            name={currentUser.name}
                                            src={currentUser.avatar}
                                            size={36}
                                            style={{ borderRadius: '10px' }}
                                        />
                                    </div>
                                    <div style={{
                                        position: 'absolute',
                                        bottom: -4,
                                        right: -4,
                                        width: 14,
                                        height: 14,
                                        borderRadius: '50%',
                                        border: `2px solid #1e2145`,
                                        backgroundColor: '#00aa55',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        overflow: 'hidden',
                                        boxSizing: 'content-box',
                                        zIndex: 10
                                    }}>
                                        <img 
                                            src="/pipedrive.png" 
                                            alt="Pipedrive" 
                                            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                                        />
                                    </div>
                                </div>
                            </div>
                            
                            <div className={styles.label} style={{ display: 'flex', flexDirection: 'column', paddingRight: '8px', paddingLeft: '8px', flex: 1, overflow: 'hidden' }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                                    <span style={{ fontWeight: 600, color: '#e4e4e7', fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {currentUser.name}
                                    </span>
                                    {onLogout && (
                                        <div 
                                            title="Sair" 
                                            onClick={(e) => { e.stopPropagation(); onLogout(); }}
                                            className={styles.logoutBtn}
                                        >
                                            <LogOut size={16} />
                                        </div>
                                    )}
                                </div>
                                {currentUser.company_name && (
                                    <span style={{ 
                                        fontSize: '11px', 
                                        color: '#a1a1aa', 
                                        fontWeight: 500,
                                        whiteSpace: 'nowrap',
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        maxWidth: '100%',
                                        marginTop: '2px'
                                    }}>
                                        {currentUser.company_name}
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* ROW 2: Number + "Tarefas pra hoje" */}
                        <div style={{ display: 'flex', alignItems: 'center', width: '100%', marginTop: '8px' }}>
                            <div style={{ minWidth: '44px', display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
                                {tasksForToday === null || tasksForToday === undefined ? (
                                    <Loader2 size={14} style={{ color: '#10b981', animation: 'spin 1s linear infinite' }} />
                                ) : (
                                    <span style={{ color: '#10b981', fontWeight: 700, fontSize: '14px', lineHeight: 1 }}>
                                        {tasksForToday}
                                    </span>
                                )}
                            </div>
                            <div className={styles.label} style={{ display: 'flex', alignItems: 'center', paddingRight: '8px', paddingLeft: '8px', flex: 1, overflow: 'hidden' }}>
                                <span style={{ color: '#10b981', fontWeight: 500, fontSize: '12px', whiteSpace: 'nowrap' }}>
                                    Tarefas pra hoje
                                </span>
                            </div>
                        </div>

                    </div>
                </div>
            )}

            <div className={styles.navIcon} title="Nova Empresa" onClick={onReset}>
                <div className={styles.iconContainer}>
                    <CirclePlus className={styles.iconSide} />
                </div>
                <span className={styles.label}>Nova Empresa</span>
            </div>

            <div 
                className={`${styles.navIcon} ${showDrawer ? styles.navIconActive : ''}`} 
                title={showDrawer ? "Ocultar Painel" : "Exibir Painel"}
                onClick={() => setShowDrawer(!showDrawer)}
            >
                <div className={styles.iconContainer}>
                    <PanelRight className={styles.iconSide} />
                </div>
                <span className={styles.label}>Painel</span>
            </div>

            <div 
                className={styles.navIconWrapper}
                onClick={(e) => {
                    const btn = e.currentTarget.querySelector('button');
                    if (btn && btn.contains(e.target as Node)) {
                        return; // already handled by button
                    }
                    window.dispatchEvent(new Event('toggle_notifications_panel'));
                }}
            >
                <div className={styles.iconContainer}>
                    <TriggerNotifications
                        apiBase={API_BASE_URL}
                        onOpenChat={(orgId, orgName) => {
                            window.dispatchEvent(new CustomEvent('toggle_chat', { detail: { open: true } }));
                        }}
                    />
                </div>
                <span className={styles.label}>Notificações</span>
            </div>




            <div className={styles.navIcon} title="Smart Sync" onClick={isSmartSyncLoading ? undefined : onSmartSync}>
                <div className={styles.iconContainer}>
                    {isSmartSyncLoading ? (
                        <div className={styles.spin} style={{ width: 22, height: 22 }}>
                            <Loader2 size={22} />
                        </div>
                    ) : (
                        <Zap className={styles.iconSide} />
                    )}
                </div>
                <span className={styles.label}>Smart Sync</span>
            </div>

            <div
                className={`${styles.navIcon} ${isProspecting ? styles.navIconActive : ''}`}
                title="Prospecção Inteligente"
                onClick={onOpenProspecting}
            >
                <div className={styles.iconContainer}>
                    <Radar className={styles.iconSide} />
                </div>
                <span className={styles.label}>Prospecção</span>
            </div>

            <div
                className={`${styles.navIcon} ${isLigacao ? styles.navIconActive : ''}`}
                title="Copiloto de Vendas"
                onClick={onOpenLigacao}
            >
                <div className={styles.iconContainer}>
                    <Headset className={styles.iconSide} />
                </div>
                <span className={styles.label}>Copiloto</span>
            </div>

            <div
                className={`${styles.navIcon} ${isLinkedinScrape ? styles.navIconActive : ''}`}
                title={isScanActive ? 'Raspador LinkedIn — Scan em andamento em background' : 'Raspador LinkedIn'}
                onClick={onOpenLinkedinScrape}
            >
                <div className={styles.iconContainer}>
                    <svg 
                        xmlns="http://www.w3.org/2000/svg" 
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
                            top: '12px',
                            right: '12px',
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: '#4ade80',
                            border: '1.5px solid var(--sw-bg)',
                            animation: 'pulse 1.5s infinite ease-in-out',
                        }} />
                    )}
                </div>
                <span className={styles.label}>Raspador LinkedIn</span>
            </div>

            <div className="mt-auto flex flex-col w-full" style={{ color: 'var(--sw-text-muted)', marginBottom: '16px' }}>
                <div className={styles.navIcon} onClick={onToggleTheme} title="Alternar Tema">
                    <div className={styles.iconContainer}>
                        {theme === "dark" ? <Sun className={styles.iconSide} /> : <Moon className={styles.iconSide} />}
                    </div>
                    <span className={styles.label}>Tema</span>
                </div>

                <div 
                    className={`${styles.navIcon} ${isPreferences ? styles.navIconActive : ''}`} 
                    title="Preferências"
                    onClick={onOpenPreferences}
                >
                    <div className={styles.iconContainer}>
                        <Settings className={styles.iconSide} />
                    </div>
                    <span className={styles.label}>Preferências</span>
                </div>

                </div>
        </aside>
    );
};
