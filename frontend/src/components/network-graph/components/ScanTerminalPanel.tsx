"use client";
import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import styles from '../styles/Toolbar.module.css';

interface ScanTerminalPanelProps {
    consoleLogs: string[];
    isVisible: boolean;
}

export const ScanTerminalPanel: React.FC<ScanTerminalPanelProps> = ({ consoleLogs, isVisible }) => {
    const scrollRef = React.useRef<HTMLDivElement>(null);
    const [isCollapsed, setIsCollapsed] = React.useState(false);

    const getLogColor = (line: string): string => {
        if (line.includes('[System]')) return 'var(--sw-primary)';
        if (line.includes('✅') || line.includes('🎉') || line.includes('Login detectado')) return '#4ade80';
        if (line.includes('👤') || line.includes('[Extraído]') || line.includes('[Operator]')) return '#38bdf8';
        if (line.includes('⚠️') || line.includes('Warning')) return '#fbbf24';
        if (line.includes('❌') || line.includes('[Erro') || line.includes('[System Error]')) return '#f87171';
        if (line.includes('📊') || line.includes('[Progresso]')) return 'rgba(255,255,255,0.55)';
        if (line.startsWith('=')) return 'var(--sw-primary)';
        if (line.startsWith('-')) return 'rgba(255,255,255,0.3)';
        return 'rgba(255,255,255,0.8)';
    };

    const filteredLogs = React.useMemo(() => {
        const header = [
            "=====================================================================",
            "              LINKB2B - HIERARCHYSCAN TERMINAL (LinkedIn)",
            "=====================================================================",
            "",
            "Esse terminal exibirá em tempo real todo o processo de automação,",
            "rolagens de página e contagem de perfis extraídos do LinkedIn.",
            "",
            "---------------------------------------------------------------------"
        ];

        // Filtra para mostrar apenas logs relevantes do processo de scan/mapeamento
        const activityLogs = consoleLogs.filter(log => 
            log.includes('[Terminal Scraper]') || 
            log.includes('[System]') || 
            log.includes('[Operator]') ||
            log.includes('[Worker]') ||
            log.includes('[Extraído]') ||
            log.includes('[Progresso]') ||
            log.includes('[Error]')
        );

        return [...header, ...activityLogs];
    }, [consoleLogs]);

    // Auto-scroll to bottom when new logs arrive
    React.useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [filteredLogs]);

    if (!isVisible || consoleLogs.length === 0) return null;

    return (
        <div className={styles.scanTerminalPanel}>
            <div 
                className={styles.scanTerminalHeader} 
                onClick={() => setIsCollapsed(!isCollapsed)}
                style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div className={styles.previewLiveDot} />
                    <span>LIVE AUTOMATION CONSOLE</span>
                </div>
                <div style={{ marginRight: '4px', opacity: 0.7, display: 'flex', alignItems: 'center' }}>
                    {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                </div>
            </div>
            {!isCollapsed && (
                <div className={styles.scanTerminalBody} ref={scrollRef}>
                    {filteredLogs.map((log, i) => (
                        <div key={i} className={styles.scanTerminalLine} style={{ color: getLogColor(log) }}>
                            {log}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
