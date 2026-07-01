import React, { useState } from 'react';
import { ChevronDown, Terminal, Database, Code2 } from 'lucide-react';
import styles from '../styles/ChatPanel.module.css';

interface DebugSectionProps {
    title: string;
    icon: React.ReactNode;
    content: string | object;
}

const DebugSection: React.FC<DebugSectionProps> = ({ title, icon, content }) => {
    const [isOpen, setIsOpen] = useState(false);
    const contentStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);

    return (
        <div className={styles.debugSection}>
            <div className={styles.debugHeader} onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer', userSelect: 'none' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {icon}
                    <span>{title}</span>
                </div>
                <ChevronDown size={14} className={isOpen ? styles.rotated : ''} style={{ transition: 'transform 0.2s ease' }} />
            </div>
            {isOpen && (
                <pre className={styles.debugPre}>{contentStr}</pre>
            )}
        </div>
    );
};

export const DebugPanel: React.FC<{ debug: any; isOpen: boolean }> = ({ debug, isOpen }) => {
    if (!isOpen || !debug) return null;
    return (
        <div className={styles.debugPanel}>
            <DebugSection
                title="Prompt Enviado"
                icon={<Terminal size={14} />}
                content={debug.full_prompt || "Nenhum prompt disponível"}
            />
            <DebugSection
                title="Dados Consultados"
                icon={<Database size={14} />}
                content={debug.raw_context}
            />
            <DebugSection
                title="Intenção Classificada"
                icon={<Code2 size={14} />}
                content={debug.intent}
            />
        </div>
    );
};
