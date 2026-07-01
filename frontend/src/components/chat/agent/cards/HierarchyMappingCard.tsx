import React, { useState, useEffect, useRef } from 'react';
import { Loader2, CheckCircle2, Network } from 'lucide-react';
import styles from '../../styles/ChatPanel.module.css';
import { AgentEvent, MappedContact, MappingStatus } from '../types';

/**
 * Card de status do mapeamento de hierarquia.
 * NÃO inicia o scan — apenas abre a empresa no Drawer (via CustomEvent) e aguarda
 * o sinal `hierarchy_scan_done` disparado pelo useHierarchy quando o worker termina.
 * Os contatos recebidos já passaram pelo carrossel "Análise Humana" do grafo.
 */
export const HierarchyMappingCard: React.FC<{
    event: AgentEvent;
    onMappingDone: (contacts: MappedContact[]) => void;
    isStreaming?: boolean;
}> = ({ event, onMappingDone, isStreaming }) => {
    const [status, setStatus] = useState<MappingStatus>(() => {
        if (typeof window !== 'undefined') {
            const saved = window.localStorage.getItem(`active-discovery-job-${event.org_id}`);
            if (saved) {
                try {
                    JSON.parse(saved);
                    return 'scanning';
                } catch { /* ignore */ }
            }
            // Se o chat está esperando por este mapeamento, começamos como 'waiting' (útil para scan manual)
            const pending = window.localStorage.getItem('pending-hierarchy-continuation');
            if (pending) {
                try {
                    const parsed = JSON.parse(pending);
                    if (parsed && (parsed.org_id === event.org_id || Number(parsed.org_id) === Number(event.org_id))) {
                        return 'waiting';
                    }
                } catch { /* ignore */ }
            }
        }
        return isStreaming ? 'waiting' : 'done';
    });
    const [contactCount, setContactCount] = useState(0);
    const doneCalledRef = useRef(false);
    // Marcado true assim que open_org_in_drawer é disparado — impede que o fim
    // do stream do agente encerre o card antes do worker terminar.
    const drawerOpenedRef = useRef(false);

    useEffect(() => {
        let isActiveJobRunning = false;
        let isWaitingForChat = false;
        if (typeof window !== 'undefined') {
            const saved = window.localStorage.getItem(`active-discovery-job-${event.org_id}`);
            if (saved) {
                try {
                    JSON.parse(saved);
                    isActiveJobRunning = true;
                } catch { /* ignore */ }
            }
            const pending = window.localStorage.getItem('pending-hierarchy-continuation');
            if (pending) {
                try {
                    const parsed = JSON.parse(pending);
                    if (parsed && (parsed.org_id === event.org_id || Number(parsed.org_id) === Number(event.org_id))) {
                        isWaitingForChat = true;
                    }
                } catch { /* ignore */ }
            }
        }

        // Só encerra prematuramente se: não está em streaming, sem job ativo, sem pendência de chat
        // E o drawer nunca foi aberto nesta sessão do componente.
        if (!isStreaming && !isActiveJobRunning && !isWaitingForChat && !drawerOpenedRef.current) {
            setStatus('done');
            return;
        }

        // Abre a org no background graph apenas uma vez
        if (!drawerOpenedRef.current) {
            drawerOpenedRef.current = true;
            const payload = { org_id: event.org_id, org_name: event.org_name, openDrawer: false };
            setTimeout(() => {
                window.dispatchEvent(new CustomEvent('open_org_in_drawer', { detail: payload }));
            }, 800);
        }

        const handleScanDone = (e: Event) => {
            const detail = (e as CustomEvent).detail || {};
            const eventOrgId = detail.orgId;
            // Validar se este evento é realmente para esta empresa
            if (eventOrgId && Number(eventOrgId) !== Number(event.org_id)) {
                return;
            }
            // Se o scan finalizado não foi iniciado pelo chat panel, não faz nada no chat
            if (detail.chatPrompted === false) {
                return;
            }
            const contacts: MappedContact[] = detail.contacts || [];
            setContactCount(contacts.length);
            setStatus('done');
            if (!doneCalledRef.current) {
                doneCalledRef.current = true;
                // Pequeno delay para o grafo processar os aprovados antes do agente agir
                setTimeout(() => onMappingDone(contacts), 600);
            }
        };

        const handleScanStart = () => setStatus('scanning');

        window.addEventListener('hierarchy_scan_done', handleScanDone);
        window.addEventListener('hierarchy_scan_started', handleScanStart);
        return () => {
            window.removeEventListener('hierarchy_scan_done', handleScanDone);
            window.removeEventListener('hierarchy_scan_started', handleScanStart);
        };
    }, [isStreaming, event.org_id, event.org_name]); // eslint-disable-line react-hooks/exhaustive-deps

    const color = '#818cf8';

    return (
        <div className={styles.logLine} style={{ marginBottom: 8 }}>
            {status === 'waiting' && (
                <>
                    <Network size={12} style={{ color, flexShrink: 0 }} />
                    <span>
                        Mapeamento de Hierarquia · <strong style={{ color: 'var(--sw-text-base)', fontWeight: 500 }}>{event.org_name}</strong>
                        <span style={{ opacity: 0.5, marginLeft: 5 }}>· empresa aberta, insira o CNPJ para mapear</span>
                    </span>
                </>
            )}
            {status === 'scanning' && (
                <>
                    <Loader2 size={12} className={styles.spinner} style={{ color, flexShrink: 0 }} />
                    <span>
                        Mapeamento de Hierarquia · <strong style={{ color: 'var(--sw-text-base)', fontWeight: 500 }}>{event.org_name}</strong>
                        <span style={{ opacity: 0.5, marginLeft: 5 }}>· mapeando...</span>
                    </span>
                </>
            )}
            {status === 'done' && (
                <>
                    <CheckCircle2 size={12} style={{ color: '#10b981', flexShrink: 0 }} />
                    <span>
                        Mapeamento concluído · <strong style={{ color: 'var(--sw-text-base)', fontWeight: 500 }}>{event.org_name}</strong>
                        <span style={{ opacity: 0.5, marginLeft: 5 }}>· {contactCount} contato(s) aprovados · analisando…</span>
                    </span>
                </>
            )}
        </div>
    );
};
