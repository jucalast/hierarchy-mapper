import React, { useState, useEffect } from 'react';
import { User, Building2, Check, Sparkles, Loader2, Trash2 } from 'lucide-react';
import { Dropdown } from '../ui/Dropdown/Dropdown';
import { ConfirmModal } from '../ui/ConfirmModal';
import { organizations } from '@/services/api';
import toast from 'react-hot-toast';
import styles from './HistoryTimeline.module.css';

export type TimelineEvent = {
    id: string | number;
    type: 'activity' | 'note' | 'update';
    timestamp: string;
    dueDate?: string;
    title: string;
    subtext?: string;
    content?: string;
    user?: string;
    contact?: string;
    company?: string;
    icon: React.ReactNode;
    done?: boolean;
    activityType?: string;
};

interface TimelineEventRowProps {
    event: TimelineEvent;
    isLast?: boolean;
    hasBackground?: boolean;
}

export const TimelineEventRow: React.FC<TimelineEventRowProps> = ({ event, isLast, hasBackground }) => {
    const [doneState, setDoneState] = useState(!!event.done);
    const [isCompleting, setIsCompleting] = useState(false);
    const [isConfirmOpen, setIsConfirmOpen] = useState(false);

    useEffect(() => {
        setDoneState(!!event.done);
    }, [event.done]);

    const handleCompleteTask = async (e?: React.MouseEvent) => {
        if (e) {
            e.stopPropagation();
            e.preventDefault();
        }
        if (doneState || isCompleting) return;
        setIsCompleting(true);
        try {
            const rawId = String(event.id).replace('act-', '');
            await organizations.updateActivity(rawId, { done: true });
            setDoneState(true);
            toast.success('Tarefa marcada como concluída no Pipedrive.');
            window.dispatchEvent(new CustomEvent('crm_task_completed', { detail: { activityId: rawId } }));
        } catch (error) {
            console.error('Failed to complete task:', error);
            toast.error('Não foi possível marcar a tarefa como concluída no Pipedrive.');
        } finally {
            setIsCompleting(false);
        }
    };

    const handleUncompleteTask = async (e?: React.MouseEvent) => {
        if (e) {
            e.stopPropagation();
            e.preventDefault();
        }
        if (!doneState || isCompleting) return;
        setIsCompleting(true);
        try {
            const rawId = String(event.id).replace('act-', '');
            await organizations.updateActivity(rawId, { done: 0 });
            setDoneState(false);
            toast.success('Tarefa desmarcada no Pipedrive.');
            window.dispatchEvent(new CustomEvent('crm_task_uncompleted', { detail: { activityId: rawId } }));
        } catch (error) {
            console.error('Failed to uncomplete task:', error);
            toast.error('Não foi possível desmarcar a tarefa no Pipedrive.');
        } finally {
            setIsCompleting(false);
        }
    };

    const handleDelete = async () => {
        if (isCompleting) return;
        setIsConfirmOpen(false);
        setIsCompleting(true);
        try {
            if (event.type === 'activity') {
                const rawId = String(event.id).replace('act-', '');
                await organizations.deleteActivity(rawId);
                toast.success('Atividade excluída com sucesso.');
            } else if (event.type === 'note') {
                const rawId = String(event.id).replace('note-', '');
                await organizations.deleteNote(rawId);
                toast.success('Anotação excluída com sucesso.');
            }
            window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
        } catch (error) {
            console.error('Failed to delete:', error);
            toast.error('Não foi possível excluir o item no Pipedrive.');
            setIsCompleting(false); 
        }
    };

    const formatDateTime = (ts: string) => {

        if (!ts) return '';
        try {
            const d = new Date(ts);
            if (isNaN(d.getTime())) return ts;
            
            const day = d.getDate();
            const month = d.toLocaleDateString('pt-BR', { month: 'long' });
            
            // Se for apenas data (sem hora relevante ou informada como 00:00:00)
            const hasTime = ts.includes('T') || ts.includes(':') || ts.includes(' ');
            
            if (!hasTime) {
                return `${day} de ${month}`;
            }
 
            const hours = d.getHours().toString().padStart(2, '0');
            const minutes = d.getMinutes().toString().padStart(2, '0');
            
            return `${day} de ${month} às ${hours}:${minutes}`;
        } catch (e) {
            return ts;
        }
    };
 
    // Helper para renderizar itens com separadores
    const metaItems = [];
    if (event.timestamp) metaItems.push(<span className={styles.metaItem}>{formatDateTime(event.timestamp)}</span>);
    if (event.user) metaItems.push(<span className={styles.metaItem}>{event.user}</span>);
    if (event.contact) metaItems.push(
        <span className={styles.metaItem}>
            <User size={10} /> {event.contact}
        </span>
    );
    if (event.company) metaItems.push(
        <span className={styles.metaItem}>
            <Building2 size={10} /> {event.company}
        </span>
    );
 
    const handleExecuteWithAgent = () => {
        const t = event.title.toLowerCase();
        const org = event.company ? ` para a empresa ${event.company}` : '';
        const contact = event.contact ? ` com ${event.contact}` : '';
 
        let taskInstruction: string;
 
        // Busca/encontrar/conseguir contato
        if (['procurar contato','encontrar contato','conseguir contato','buscar contato','achar contato','identificar contato','localizar contato','contato na rodada','rodada de negócios'].some(k => t.includes(k))) {
            taskInstruction = `encontrar o contato/decisor de compras da empresa${org}. Verifique primeiro se já existe contato com canal válido no CRM. Se não houver, abra o mapeador de hierarquia (open_hierarchy_drawer). NÃO crie nova tarefa no Pipedrive — a atividade já existe no CRM.`;
        // Cobrar retorno / follow-up
        } else if (['cobrar retorno','cobrar resposta','acompanhamento','follow-up','follow up','dar retorno','verificar retorno'].some(k => t.includes(k)) || (t.includes('retorno') && !t.includes('cobrar'))) {
            taskInstruction = `executar o follow-up "${event.title}"${contact}${org}. Analise o histórico de comunicações e execute a ação de cobrança de retorno mais adequada pelo canal disponível`;
        // Ligar / ligação
        } else if (['ligar','ligação','telefonar','realizar ligação'].some(k => t.includes(k))) {
            taskInstruction = `executar a ligação "${event.title}"${contact}${org}. Obtenha o número REAL do CRM antes de qualquer ação`;
        // Agendar reunião / visita
        } else if (['agendar reunião','marcar reunião','agendar visita','marcar visita','agendar apresentação'].some(k => t.includes(k))) {
            taskInstruction = `agendar a reunião/visita "${event.title}"${contact}${org}. Identifique o decisor e proponha o agendamento pelo canal disponível`;
        // Orçamento / cotação
        } else if (['orçamento','cotação','proposta comercial','realizar orçamento','enviar proposta'].some(k => t.includes(k))) {
            taskInstruction = `realizar o orçamento/cotação "${event.title}"${contact}${org}. Identifique o contato responsável e gere a proposta personalizada`;
        // Envio de mensagem
        } else if (['enviar mensagem','primeira mensagem','abordagem inicial','primeiro contato'].some(k => t.includes(k))) {
            taskInstruction = `executar a abordagem "${event.title}"${contact}${org}. Identifique o canal disponível e gere a mensagem personalizada`;
        // Genérico
        } else {
            taskInstruction = `realizar a atividade "${event.title}"${contact}${org}. Raciocine sobre o que a tarefa requer e use as ferramentas adequadas`;
        }
 
        const promptText = `Execute a seguinte atividade do CRM: ${taskInstruction} (ID da tarefa no Pipedrive: ${String(event.id).replace('act-', '')}). Use as ferramentas disponíveis para executar isso agora.`;
        window.dispatchEvent(new CustomEvent('submit_agent_prompt', { detail: { prompt: promptText } }));
    };

 
    const dropdownItems = [];
    
    if (event.type === 'activity') {
        if (!doneState) {
            dropdownItems.push({
                label: 'Marcar como concluída',
                icon: isCompleting ? <Loader2 size={12} className={styles.spinner} /> : <Check size={12} />,
                onClick: () => handleCompleteTask()
            });
        } else {
            dropdownItems.push({
                label: 'Desmarcar como concluída',
                icon: isCompleting ? <Loader2 size={12} className={styles.spinner} /> : <Check size={12} style={{ opacity: 0.5 }} />,
                onClick: () => handleUncompleteTask()
            });
        }
        
        dropdownItems.push({
            label: 'Fazer com o agente',
            icon: <Sparkles size={12} />,
            onClick: handleExecuteWithAgent
        });
    }

    dropdownItems.push({
        label: 'Excluir',
        icon: <Trash2 size={12} style={{ color: '#ef4444' }} />,
        onClick: () => setIsConfirmOpen(true)
    });
 
    return (
        <div className={styles.eventRow}>
            {/* Linha e Ícone Lateral */}
            <div className={styles.timelineSide}>
                <div className={`${styles.iconCircle} ${doneState ? styles.iconCircleDone : ''}`}>
                    {event.icon}
                </div>
                {!isLast && <div className={styles.dashedLine} />}
            </div>
 
            {/* Conteúdo do Card */}
            <div className={`${styles.eventCard} ${doneState ? styles.eventCardDone : ''} ${hasBackground ? styles.cardWithBg : ''}`}>
                <div className={styles.eventHeader} style={{ position: 'relative' }}>
                    <div className={styles.titleArea}>
                        {event.type === 'activity' ? (
                            doneState ? (
                                <button
                                    style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                                    onClick={handleUncompleteTask}
                                    disabled={isCompleting}
                                    title="Desmarcar tarefa como concluída"
                                >
                                    {isCompleting ? (
                                        <Loader2 size={12} className={styles.spinner} style={{ color: 'var(--sw-status-success)' }} />
                                    ) : (
                                        <Check size={12} className={styles.doneCheck} />
                                    )}
                                </button>
                            ) : (
                                <button 
                                    className={`${styles.checkboxBtn} ${isCompleting ? styles.checkboxBtnLoading : ''}`}
                                    onClick={handleCompleteTask}
                                    disabled={isCompleting}
                                    title="Marcar tarefa como concluída"
                                >
                                    {isCompleting ? (
                                        <Loader2 size={10} className={styles.spinner} />
                                    ) : (
                                        <Check size={10} className={styles.checkboxCheckIcon} />
                                    )}
                                </button>
                            )
                        ) : null}
                        <span className={styles.eventTitle}>{event.title}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Dropdown 
                            items={dropdownItems} 
                            iconType="horizontal" 
                            align="right" 
                            title="Ações da atividade"
                        />
                    </div>
                </div>
 
                <div className={styles.eventMeta}>
                    {metaItems.map((item, index) => (
                        <React.Fragment key={index}>
                            {item}
                            {index < metaItems.length - 1 && <span className={styles.metaSeparator}>•</span>}
                        </React.Fragment>
                    ))}
                </div>
 
                {event.subtext && (
                    <div className={styles.eventSubtext}>
                        {event.subtext}
                    </div>
                )}
 
                {event.content && (
                    <div className={`${styles.eventContent} ${styles.callNote}`}>
                        <div dangerouslySetInnerHTML={{ __html: event.content }} />
                    </div>
                )}
            </div>

            <ConfirmModal 
                isOpen={isConfirmOpen}
                title={`Excluir ${event.type === 'note' ? 'Anotação' : 'Tarefa'}`}
                message={`Tem certeza que deseja excluir esta ${event.type === 'note' ? 'anotação' : 'tarefa'}? Esta ação não pode ser desfeita.`}
                confirmLabel="Excluir"
                cancelLabel="Cancelar"
                onConfirm={handleDelete}
                onCancel={() => setIsConfirmOpen(false)}
                type="danger"
            />
        </div>
    );
};
