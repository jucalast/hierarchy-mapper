"use client";
import React from 'react';
import styles from '../styles/Toolbar.module.css';

interface ScanTerminalPanelProps {
    consoleLogs: string[];
    isVisible: boolean;
}

export const ScanTerminalPanel: React.FC<ScanTerminalPanelProps> = ({ consoleLogs, isVisible }) => {
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

    const lastLog = consoleLogs.length > 0 
        ? consoleLogs[consoleLogs.length - 1] 
        : "Aguardando tarefas... Terminal inativo.";

    return (
        <div className={styles.scanTerminalPanel}>
            <div className={styles.scanTerminalBody}>
                <div className={styles.scanTerminalLine} style={{ color: getLogColor(lastLog) }}>
                    {lastLog}
                </div>
            </div>
        </div>
    );
};

