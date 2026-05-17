import React from 'react';
import { useNotifications } from '@/contexts/NotificationContext';
import styles from './NotificationOverlay.module.css';
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';

export const NotificationOverlay: React.FC = () => {
    const { notifications, removeNotification } = useNotifications();

    if (notifications.length === 0) return null;

    return (
        <div className={styles.notificationStack}>
            {notifications.map((n) => (
                <div key={n.id} className={`${styles.notification} ${styles[n.type]}`}>
                    <div className={styles.iconWrapper}>
                        {n.type === 'success' && <CheckCircle2 size={18} />}
                        {n.type === 'error' && <AlertCircle size={18} />}
                        {n.type === 'info' && <Info size={18} />}
                        {n.type === 'warning' && <AlertTriangle size={18} />}
                    </div>
                    <div className={styles.message}>{n.message}</div>
                    <button className={styles.closeBtn} onClick={() => removeNotification(n.id)}>
                        <X size={14} />
                    </button>
                </div>
            ))}
        </div>
    );
};
