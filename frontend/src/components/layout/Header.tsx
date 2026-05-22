'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Database, X, MessageSquare } from 'lucide-react';
import styles from './Header.module.css';

interface HeaderProps {
    confirmedBrand: string;
    activeView?: string;
    onToggleMessages?: () => void;
    unreadCount?: number;
}

type AnimState = 'idle' | 'hover' | 'filling' | 'filled';

export const Header: React.FC<HeaderProps> = ({
    confirmedBrand,
    activeView,
    onToggleMessages,
    unreadCount = 0,
}) => {
    const messagesActive = activeView === 'messages';
    const [animState, setAnimState] = useState<AnimState>('idle');
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Ao abrir messages de fora (ex: reload com activeView='messages'), reseta animação
    useEffect(() => {
        if (!messagesActive) setAnimState('idle');
    }, [messagesActive]);

    const clearTimer = () => {
        if (timerRef.current) clearTimeout(timerRef.current);
    };

    const handleHoverIn = () => {
        if (messagesActive || animState === 'filling' || animState === 'filled') return;
        setAnimState('hover');
    };

    const handleHoverOut = () => {
        if (animState === 'hover') setAnimState('idle');
    };

    const handleClick = () => {
        if (messagesActive) {
            // Fecha imediatamente
            onToggleMessages?.();
            return;
        }
        if (animState === 'filling' || animState === 'filled') return;

        clearTimer();
        setAnimState('filling');
        // Aguarda a animação completar antes de abrir a view
        timerRef.current = setTimeout(() => {
            setAnimState('filled');
            onToggleMessages?.();
            // Strip desaparece após a view abrir
            timerRef.current = setTimeout(() => setAnimState('idle'), 250);
        }, 250);
    };

    const stripClass = (() => {
        if (messagesActive) return '';
        if (animState === 'hover') return styles.stripHover;
        if (animState === 'filling') return styles.stripFilling;
        if (animState === 'filled') return styles.stripFilled;
        return '';
    })();

    return (
        <header
            className={`${styles.header} ${messagesActive ? styles.headerMessages : ''}`}
            style={{ position: 'relative', overflow: 'hidden' }}
        >
            {/* Faixa verde animada */}
            {!messagesActive && (
                <div className={`${styles.greenStrip} ${stripClass}`} />
            )}

            {/* Conteúdo — sempre acima da faixa */}
            <div className={styles.headerInner}>
                {messagesActive ? (
                    /* ── Modo mensagens ── */
                    <div className={styles.breadcrumbs}>
                        <div className={styles.headerIconWrapper}>
                            <MessageSquare size={14} className={styles.headerIcon} />
                        </div>
                        <span className={styles.breadcrumbItem}>Mensagens</span>
                        <span className={styles.breadcrumbDivider}>/</span>
                        <span className={styles.breadcrumbActive}>{confirmedBrand || 'Empresa'}</span>
                    </div>
                ) : (
                    /* ── Modo normal ── */
                    <div className={styles.breadcrumbs}>
                        <div className={styles.headerIconWrapper}>
                            <Database size={14} className={styles.headerIcon} />
                        </div>
                        <span className={styles.breadcrumbItem}>Pipedrive Workspace</span>
                        <span className={styles.breadcrumbDivider}>/</span>
                        <span className={styles.breadcrumbActive}>{confirmedBrand || 'OSINT Flow'}</span>
                        <span className={styles.statusBadge}>DRAFT</span>
                    </div>
                )}

                {onToggleMessages && (
                    messagesActive ? (
                        /* Botão fechar no modo mensagens */
                        <button
                            className={styles.closeMessagesBtn}
                            onClick={handleClick}
                            title="Fechar mensagens"
                        >
                            <X size={13} />
                            <span>Fechar</span>
                        </button>
                    ) : (
                        /* Botão de abertura de mensagens */
                        <button
                            className={styles.messagesTab}
                            onMouseEnter={handleHoverIn}
                            onMouseLeave={handleHoverOut}
                            onClick={handleClick}
                            title="Abrir mensagens"
                        >
                            <div className={styles.iconStack}>
                                <img src="/outlook.png" alt="Email" className={styles.emailIconBtn} />
                                <img src="/wppicon.png" alt="WA" className={styles.waIconBtnStacked} />
                            </div>
                            <span>Mensagens</span>
                            {unreadCount > 0 && (
                                <span className={styles.unreadPill}>{unreadCount}</span>
                            )}
                        </button>
                    )
                )}
            </div>
        </header>
    );
};
