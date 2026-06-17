import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Loader2, ShieldCheck } from 'lucide-react';
import styles from './EmailDiscoveryView.module.css';
import { apiPost, API_BASE_URL } from '@/services/config';
interface EmailDiscoveryViewProps {
    personName: string;
    orgName: string;
    anchorRect: DOMRect;
    onClose: () => void;
    onComplete?: (email: string) => void;
    jobTitle?: string;
}

type DiscoveryStep = 'loading' | 'success' | 'error';

export const EmailDiscoveryView: React.FC<EmailDiscoveryViewProps> = ({
    personName,
    orgName,
    anchorRect,
    onClose,
    onComplete,
    jobTitle
}) => {
    const [step, setStep] = useState<DiscoveryStep>('loading');
    const [discoveredEmail, setDiscoveredEmail] = useState('');
    const [isVerified, setIsVerified] = useState(false);
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
        const abortController = new AbortController();
        const timeoutId = setTimeout(() => abortController.abort(), 240000); // 4 minutos

        const doDiscovery = async () => {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`${API_BASE_URL}/api/v1/intelligence/discover-email`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                    },
                    body: JSON.stringify({
                        contact_name: personName,
                        org_name: orgName,
                        job_title: jobTitle
                    }),
                    signal: abortController.signal
                });
                
                clearTimeout(timeoutId);

                if (!response.ok) {
                    if (!abortController.signal.aborted) setStep('error');
                    return;
                }

                const data = await response.json();
                
                if (abortController.signal.aborted) return;

                if (data.ok && (data.recommended || data.email)) {
                    const email = data.recommended || data.email;
                    setDiscoveredEmail(email);
                    setIsVerified(data.smtp_result === 'valid');
                    setStep('success');
                    if (onComplete) onComplete(email);
                } else {
                    setStep('error');
                }
            } catch (error: any) {
                if (error.name === 'AbortError' || abortController.signal.aborted) {
                    console.log('Busca cancelada (unmount).');
                    return;
                }
                setStep('error');
            }
        };

        doDiscovery();

        return () => {
            abortController.abort();
            clearTimeout(timeoutId);
            setMounted(false);
        };
    }, [personName, orgName]);

    if (!mounted) return null;

    // Alinhamento centralizado verticalmente com o e-mail do Drawer
    const popoverStyle: React.CSSProperties = {
        top: anchorRect.top + anchorRect.height / 2 - 25,
        left: anchorRect.right + 15,
    };

    return createPortal(
        <div 
            className={`${styles.container} ${step === 'error' ? styles.error : ''} ${step === 'success' && !isVerified ? styles.warning : ''}`} 
            style={popoverStyle} 
            onClick={(e) => {
                e.stopPropagation();
                if (step !== 'loading') onClose();
            }}
        >
            {step === 'loading' && (
                <div className={styles.loadingText}>
                    <Loader2 size={16} className={styles.spin} />
                    <span>Validando...</span>
                </div>
            )}

            {step === 'success' && (
                <>
                    <div className={styles.emailLine}>
                        <ShieldCheck size={16} className={styles.securityIcon} />
                        <div className={styles.emailSuccess} title={discoveredEmail}>
                            {discoveredEmail}
                        </div>
                    </div>
                    <div className={styles.instruction}>
                        {isVerified ? 'Verificado' : 'Estimado'} • <span className={styles.closeHint}>clique para fechar</span>
                    </div>
                </>
            )}

            {step === 'error' && (
                <>
                    <div className={styles.emailSuccess}>Não encontrado</div>
                    <div className={styles.instruction}>clique para fechar</div>
                </>
            )}
        </div>,
        document.body
    );
};
