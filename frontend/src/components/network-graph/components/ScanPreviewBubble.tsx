"use client";
import React, { useState, useEffect } from 'react';
import { Maximize2, Minimize2, CornerDownLeft, Delete, Send, MonitorPlay, Loader2 } from 'lucide-react';
import styles from '../styles/Toolbar.module.css';

interface ScanPreviewBubbleProps {
    hasPreview: boolean;
    previewUrl: string;
    isScanning: boolean;
    expanded: boolean;
    onToggleExpand: () => void;
    onImageClick: (e: React.MouseEvent<HTMLImageElement>) => void;
    onSendText: (text: string) => void;
    onPressEnter: () => void;
    onPressBackspace: () => void;
    consoleLogs: string[];
}

export const ScanPreviewBubble: React.FC<ScanPreviewBubbleProps> = ({
    hasPreview, previewUrl, isScanning, expanded, onToggleExpand,
    onImageClick, onSendText, onPressEnter, onPressBackspace, consoleLogs
}) => {
    const [inputText, setInputText] = useState('');

    // Auto-expand when login is needed
    useEffect(() => {
        const lastLogs = consoleLogs.slice(-5).join(' ').toLowerCase();
        if (lastLogs.includes('login') && lastLogs.includes('navegador') && !expanded) {
            onToggleExpand();
        }
        if (lastLogs.includes('login detectado com sucesso') && expanded) {
            const timer = setTimeout(() => onToggleExpand(), 2000);
            return () => clearTimeout(timer);
        }
    }, [consoleLogs]);

    const handleSend = () => {
        if (inputText.trim()) {
            onSendText(inputText.trim());
            setInputText('');
        }
    };

    return (
        <div className={`${styles.previewBubble} ${expanded ? styles.previewExpanded : styles.previewCollapsed}`}>
            {/* Live badge */}
            {isScanning && (
                <div className={styles.previewLiveBadge}>
                    <span className={styles.previewLiveDot} />
                    LIVE
                </div>
            )}

            {/* Expand/Collapse button */}
            <button className={styles.previewToggleBtn} onClick={onToggleExpand} title={expanded ? 'Minimizar' : 'Expandir'}>
                {expanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
            </button>

            {/* Preview image */}
            {hasPreview ? (
                <img
                    src={previewUrl}
                    alt="Browser Preview"
                    className={styles.previewImage}
                    onClick={expanded ? onImageClick : onToggleExpand}
                    style={{ cursor: expanded ? 'crosshair' : 'pointer' }}
                    draggable={false}
                />
            ) : (
                <div className={styles.previewPlaceholder}>
                    {isScanning ? (
                        <Loader2 size={20} className={styles.loadingAnim} style={{ opacity: 0.4 }} />
                    ) : (
                        <MonitorPlay size={20} style={{ opacity: 0.3 }} />
                    )}
                </div>
            )}

            {/* Interaction bar — only in expanded mode while scanning */}
            {expanded && isScanning && (
                <div className={styles.previewInteractionBar}>
                    <input
                        type="text"
                        value={inputText}
                        onChange={e => setInputText(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSend()}
                        placeholder="Digitar texto..."
                        className={styles.previewInput}
                    />
                    <button onClick={handleSend} className={styles.previewActionBtn} title="Enviar texto">
                        <Send size={12} />
                    </button>
                    <button onClick={onPressEnter} className={styles.previewActionBtn} title="Enter">
                        <CornerDownLeft size={12} />
                    </button>
                    <button onClick={onPressBackspace} className={styles.previewActionBtn} title="Backspace">
                        <Delete size={12} />
                    </button>
                </div>
            )}
        </div>
    );
};
