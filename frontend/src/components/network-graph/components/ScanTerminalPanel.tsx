"use client";
import React from 'react';
import styles from '../styles/Toolbar.module.css';

interface ScanTerminalPanelProps {
    consoleLogs: string[];
    isVisible: boolean;
}

export const ScanTerminalPanel: React.FC<ScanTerminalPanelProps> = ({ consoleLogs, isVisible }) => {
    const scrollRef = React.useRef<HTMLDivElement>(null);
    const [isCollapsed, setIsCollapsed] = React.useState(false);

    const getLogColor = (line: string): string => {
        if (line.includes('[System]')) return 'var(--terminal-system)';
        if (line.includes('✅') || line.includes('🎉') || line.includes('Login detectado')) return 'var(--terminal-success)';
        if (line.includes('👤') || line.includes('[Extraído]') || line.includes('[Operator]')) return 'var(--terminal-info)';
        if (line.includes('⚠️') || line.includes('Warning')) return 'var(--terminal-warning)';
        if (line.includes('❌') || line.includes('[Erro') || line.includes('[System Error]')) return 'var(--terminal-error)';
        if (line.includes('📊') || line.includes('[Progresso]')) return 'var(--terminal-muted)';
        if (line.startsWith('=')) return 'var(--terminal-system)';
        if (line.startsWith('-')) return 'var(--terminal-muted)';
        return 'var(--terminal-text)';
    };

    const cleanLogLine = (line: string): string => {
        if (!line) return '';
        // Comprehensive emoji regex + specific common emojis used in automation logs
        const emojiRegex = /[\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDC00-\uDFFF]|✅|🎉|👤|⚠️|❌|📊/g;
        let cleaned = line.replace(emojiRegex, '');
        return cleaned.trimStart();
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
                style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', userSelect: 'none' }}
            >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                    <span>LIVE AUTOMATION CONSOLE</span>
                </div>
                <div style={{ marginRight: '4px', opacity: 0.7, fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 'bold' }}>
                    {isCollapsed ? '[+]' : '[-]'}
                </div>
            </div>
            {!isCollapsed && (
                <div className={styles.scanTerminalBody} ref={scrollRef}>
                    {filteredLogs.map((log, i) => (
                        <div key={i} className={styles.scanTerminalLine} style={{ color: getLogColor(log) }}>
                            {cleanLogLine(log)}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
