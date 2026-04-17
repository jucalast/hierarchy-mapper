import React from 'react';
import { AlertTriangle, X } from 'lucide-react';
import styles from './ConfirmModal.module.css';

interface ConfirmModalProps {
    isOpen: boolean;
    title: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    onConfirm: () => void;
    onCancel: () => void;
    type?: 'danger' | 'info' | 'warning';
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
    isOpen,
    title,
    message,
    confirmLabel = "Confirmar",
    cancelLabel = "Cancelar",
    onConfirm,
    onCancel,
    type = 'danger'
}) => {
    if (!isOpen) return null;

    return (
        <div className={styles.overlay} onClick={onCancel}>
            <div className={styles.modal} onClick={e => e.stopPropagation()}>
                <button className={styles.closeBtn} onClick={onCancel}>
                    <X size={18} />
                </button>
                
                <div className={styles.content}>
                    <div className={`${styles.iconWrapper} ${styles[type]}`}>
                        <AlertTriangle size={24} />
                    </div>
                    
                    <div className={styles.textGroup}>
                        <h3 className={styles.title}>{title}</h3>
                        <p className={styles.message}>{message}</p>
                    </div>
                </div>
                
                <div className={styles.actions}>
                    <button className={styles.cancelBtn} onClick={onCancel}>
                        {cancelLabel}
                    </button>
                    <button 
                        className={`${styles.confirmBtn} ${styles[`confirm-${type}`]}`} 
                        onClick={onConfirm}
                    >
                        {confirmLabel}
                    </button>
                </div>
            </div>
        </div>
    );
};
