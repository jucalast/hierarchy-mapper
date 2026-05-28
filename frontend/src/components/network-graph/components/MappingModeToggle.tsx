"use client";
import React from 'react';
import { Search, Radio } from 'lucide-react';
import styles from '../styles/Toolbar.module.css';

interface MappingModeToggleProps {
    mode: 'discovery' | 'scan';
    onChange: (mode: 'discovery' | 'scan') => void;
    visible: boolean; // only show after brand confirmation
}

export const MappingModeToggle: React.FC<MappingModeToggleProps> = ({ mode, onChange, visible }) => {
    if (!visible) return null;
    return (
        <div className={styles.mappingModeToggle}>
            <button
                className={`${styles.modeBtn} ${mode === 'discovery' ? styles.modeBtnActive : ''}`}
                onClick={() => onChange('discovery')}
                title="Discovery — Mapeamento via IA"
            >
                <Search size={16} />
            </button>
            <button
                className={`${styles.modeBtn} ${mode === 'scan' ? styles.modeBtnActive : ''}`}
                onClick={() => onChange('scan')}
                title="Scan — Varredura LinkedIn"
            >
                <Radio size={16} />
            </button>
        </div>
    );
};
