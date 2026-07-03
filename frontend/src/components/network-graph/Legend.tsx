import React from 'react';
import styles from './styles/Legend.module.css';

export const Legend: React.FC = () => {
    return (
        <div className={styles.legend}>
            <div className={styles.legendItem}>
                <div className={styles.legendColor} style={{ background: '#A78BFA', boxShadow: '0 0 10px rgba(167, 139, 250, 0.4)' }}></div>
                <span>High Priority Leads</span>
            </div>
            <div className={styles.legendItem}>
                <div className={styles.legendColor} style={{ background: '#60A5FA', boxShadow: '0 0 10px rgba(96, 165, 250, 0.4)' }}></div>
                <span>Tactical Management</span>
            </div>
            <div className={styles.legendItem}>
                <div className={styles.legendColor} style={{ background: '#34D399', boxShadow: '0 0 10px rgba(52, 211, 153, 0.4)' }}></div>
                <span>Operations Expert</span>
            </div>
        </div>
    );
};
