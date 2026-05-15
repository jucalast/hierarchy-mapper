import React from 'react';
import { Sun, Moon, X } from 'lucide-react';
import styles from '../styles/ChatPanel.module.css';

interface ChatHeaderProps {
    theme: string;
    onToggleTheme: (() => void) | undefined;
    onClose: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ theme, onToggleTheme, onClose }) => {
    return (
        <div className={styles.chatHeader}>
            <h2 className={styles.chatTitle}>Novo Chat</h2>
            <div className={styles.headerActions}>
                <button 
                    className={styles.themeToggle} 
                    onClick={onToggleTheme}
                    title={theme === 'light' ? 'Ativar Modo Escuro' : 'Ativar Modo Claro'}
                >
                    {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
                </button>
                <button 
                    className={styles.closeBtn} 
                    onClick={onClose}
                    title="Fechar Chat"
                >
                    <X size={18} />
                </button>
            </div>
        </div>
    );
};
