import React, { useEffect } from 'react';
import { CheckCircle, XCircle, Info, X } from 'lucide-react';
import styles from './Notification.module.css';

export type NotificationType = 'success' | 'error' | 'info';

interface NotificationProps {
    id: string;
    type: NotificationType;
    message: string;
    onClose: (id: string) => void;
}

export const Notification: React.FC<NotificationProps> = ({ id, type, message, onClose }) => {
    useEffect(() => {
        const timer = setTimeout(() => {
            onClose(id);
        }, 5000);
        return () => clearTimeout(timer);
    }, [id, onClose]);

    const Icon = {
        success: CheckCircle,
        error: XCircle,
        info: Info
    }[type];

    return (
        <div className={`${styles.notification} ${styles[type]}`}>
            <div className={styles.iconWrapper}>
                <Icon size={18} />
            </div>
            <div className={styles.content}>
                <p className={styles.message}>{message}</p>
            </div>
            <button className={styles.closeBtn} onClick={() => onClose(id)}>
                <X size={14} />
            </button>
            <div className={styles.progressBar} />
        </div>
    );
};

interface NotificationContainerProps {
    notifications: Array<{ id: string; type: NotificationType; message: string }>;
    removeNotification: (id: string) => void;
}

export const NotificationContainer: React.FC<NotificationContainerProps> = ({ notifications, removeNotification }) => {
    return (
        <div className={styles.container}>
            {notifications.map((n) => (
                <Notification
                    key={n.id}
                    id={n.id}
                    type={n.type}
                    message={n.message}
                    onClose={removeNotification}
                />
            ))}
        </div>
    );
};
