"use client";
import React, { useRef, useEffect } from 'react';
import { Terminal } from 'lucide-react';
import styles from '../styles/Toolbar.module.css';

interface ScanTerminalPanelProps {
    consoleLogs: string[];
    isVisible: boolean;
}

export const ScanTerminalPanel: React.FC<ScanTerminalPanelProps> = ({ consoleLogs, isVisible }) => {
    const endRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [consoleLogs]);

    if (!isVisible) return null;

    const getLogColor = (line: string): string => {
        if (line.includes('[System]')) return 'var(--sw-primary)';
        if (line.includes('✅') || line.includes('🎉') || line.includes('Login detectado')) return '#4ade80';
        if (line.includes('👤') || line.includes('[Operator]')) return '#38bdf8';
        if (line.includes('⚠️') || line.includes('Warning')) return '#fbbf24';
        if (line.includes('❌') || line.includes('[Erro') || line.includes('[System Error]')) return '#f87171';
        if (line.includes('📊')) return 'rgba(255,255,255,0.55)';
        return 'rgba(255,255,255,0.8)';
    };

    return (
        <div className={styles.scanTerminalPanel}>
            <div className={styles.scanTerminalHeader}>
                <Terminal size={12} style={{ opacity: 0.5 }} />
                <span>agent@linkb2b:~ (hierarchy_scan)</span>
            </div>
            <div className={styles.scanTerminalBody}>
                {consoleLogs.length === 0 ? (
                    <div style={{ color: 'var(--sw-text-muted)', fontStyle: 'italic', fontSize: '11px' }}>
                        Aguardando tarefas... Terminal inativo.
                    </div>
                ) : (
                    consoleLogs.map((line, i) => (
                        <div key={i} className={styles.scanTerminalLine} style={{ color: getLogColor(line) }}>
                            {line}
                        </div>
                    ))
                )}
                <div ref={endRef} />
            </div>
        </div>
    );
};
