import React from 'react';
import styles from './GlassContainer.module.css';

interface GlassContainerProps {
    children: React.ReactNode;
    className?: string;
}

export const GlassContainer: React.FC<GlassContainerProps> = ({ children, className = '' }) => {
    return (
        <div className={`${styles.glassBase} ${className}`}>
            <div className={styles.blurLayer} />
            <div className={styles.contentLayer}>
                {children}
            </div>
        </div>
    );
};
