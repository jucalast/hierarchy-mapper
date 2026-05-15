import React from 'react';
import { ArrowLeft, PanelRightOpen, PanelRightClose, Activity } from 'lucide-react';
import { Avatar } from '@/components/ui';
import styles from '../styles/components/ChatSubHeader.module.css';

interface ChatSubHeaderProps {
    onBack: () => void;
    selectedOrgName: string;
    selectedOrgLogo?: string;
    activeThreadTitle?: string;
    showActivitySidebar: boolean;
    setShowActivitySidebar: (show: boolean) => void;
    activityCount: number;
}

export const ChatSubHeader: React.FC<ChatSubHeaderProps> = ({
    onBack,
    selectedOrgName,
    selectedOrgLogo,
    activeThreadTitle,
    showActivitySidebar,
    setShowActivitySidebar,
    activityCount
}) => {
    return (
        <div className={styles.chatSubHeader}>
            <button className={styles.chatBackBtn} onClick={onBack} title="Voltar para a lista">
                <ArrowLeft size={18} />
            </button>
            
            <Avatar 
                src={selectedOrgLogo} 
                name={selectedOrgName} 
                size="xs" 
                className={styles.chatSubHeaderAvatar}
            />
            
            <div className={styles.chatSubHeaderInfo}>
                <span className={styles.chatSubHeaderTitle}>{activeThreadTitle || 'Conversa'}</span>
                <span className={styles.chatSubHeaderOrg}>{selectedOrgName}</span>
            </div>

            <div className={styles.headerActions}>
                <button 
                    className={`${styles.chatHeaderIconBtn} ${showActivitySidebar ? styles.chatHeaderIconBtnActive : ''}`}
                    onClick={() => setShowActivitySidebar(!showActivitySidebar)}
                    title="Atividades recentes"
                >
                    <div style={{ position: 'relative' }}>
                        <Activity size={18} />
                        {activityCount > 0 && <span className={styles.asCount} style={{ position: 'absolute', top: -8, right: -10, scale: '0.8' }}>{activityCount}</span>}
                    </div>
                </button>
                <button 
                    className={styles.chatHeaderIconBtn}
                    onClick={() => setShowActivitySidebar(!showActivitySidebar)}
                    title={showActivitySidebar ? "Ocultar Lateral" : "Mostrar Lateral"}
                >
                    {showActivitySidebar ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
                </button>
            </div>
        </div>
    );
};
