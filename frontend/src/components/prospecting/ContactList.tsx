import React from 'react';
import { 
    User, 
    Mail, 
    Phone, 
    MessageSquare, 
    ExternalLink, 
    Briefcase,
    Info,
    Trash2,
    BadgeCheck,
    X
} from 'lucide-react';
import toast from 'react-hot-toast';
import styles from './ContactList.module.css';
import { Dropdown } from '../ui/Dropdown';
import { Spinner } from '../ui/Spinner';
import { EmailDiscoveryView } from './EmailDiscoveryView';

interface ContactListProps {
    persons: any[];
    onEditPerson?: (empId: string) => void;
    onSaveToPipedrive?: (person: any) => Promise<void> | void;
    onUpdateInPipedrive?: (person: any) => Promise<void> | void;
    onDeleteFromPipedrive?: (person: any) => Promise<void> | void;
    onEmailDiscovered?: (person: any, email: string) => Promise<void> | void;
    onBatchValidateEmails?: () => void;
    isBatchValidating?: boolean;
    orgName?: string;
}

export const ContactList: React.FC<ContactListProps> = ({ 
    persons, 
    onEditPerson, 
    onSaveToPipedrive, 
    onUpdateInPipedrive, 
    onDeleteFromPipedrive,
    onEmailDiscovered,
    onBatchValidateEmails,
    isBatchValidating = false,
    orgName = "Empresa"
}) => {
    const [loadingDiscover, setLoadingDiscover] = React.useState<Record<string, boolean>>({});
    const [discoveryActiveId, setDiscoveryActiveId] = React.useState<string | null>(null);
    const [anchorRect, setAnchorRect] = React.useState<DOMRect | null>(null);
    const [isBatchValidatingLocal, setIsBatchValidatingLocal] = React.useState(false);
    const [batchProgress, setBatchProgress] = React.useState<{ current: number, total: number } | null>(null);
    const [localEmailUpdates, setLocalEmailUpdates] = React.useState<Record<string, { email?: string, verified?: boolean, deleted?: boolean }>>({});
    const isCancelledRef = React.useRef(false);

    const handleCancelBatch = () => {
        isCancelledRef.current = true;
        setIsBatchValidatingLocal(false);
        setBatchProgress(null);
        setDiscoveryActiveId(null);
        toast.error("Validação em lote cancelada.");
    };

    const handleDiscoverEmail = (person: any, e: React.MouseEvent) => {
        // Tenta encontrar o elemento de e-mail na mesma linha do contato
        const row = e.currentTarget.closest(`.${styles.contactRow}`);
        const emailEl = row?.querySelector(`.${styles.metaItem}`);
        
        const rect = emailEl ? emailEl.getBoundingClientRect() : e.currentTarget.getBoundingClientRect();
        setAnchorRect(rect);
        setDiscoveryActiveId(person.id);
    };

    const handleDiscoveryComplete = async (email: string) => {
        if (!onEmailDiscovered || !discoveryActiveId) return;
        
        // Localiza a pessoa ativa
        const person = persons.find(p => p.id === discoveryActiveId);
        if (!person) return;

        setLoadingDiscover(prev => ({ ...prev, [person.id]: true }));
        try {
            setLocalEmailUpdates(prev => ({ ...prev, [person.id]: { email: email, verified: true } }));
            await onEmailDiscovered(person, email);
        } catch (error) {
            console.error("Erro ao salvar e-mail descoberto:", error);
        } finally {
            setLoadingDiscover(prev => ({ ...prev, [person.id]: false }));
            setDiscoveryActiveId(null);
        }
    };

    const handleStartBatch = async () => {
        const queue = persons.filter(p => {
            if (p.sources?.includes('pipedrive')) return false;
            if (p.email && Array.isArray(p.email)) {
                return !p.email.some((e: any) => e.label === 'verified');
            }
            return true;
        });
        
        if (queue.length === 0) {
            toast.success("Todos os contatos listados já estão validados!");
            return;
        }

        isCancelledRef.current = false;
        setIsBatchValidatingLocal(true);
        setBatchProgress({ current: 1, total: queue.length });

        for (let i = 0; i < queue.length; i++) {
            if (isCancelledRef.current) break;
            const person = queue[i];
            setBatchProgress({ current: i + 1, total: queue.length });
            setDiscoveryActiveId(person.id);
            setLoadingDiscover(prev => ({ ...prev, [person.id]: true }));
            
            const row = document.getElementById(`contact-row-${person.id}`);
            if (row) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }

            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/intelligence/discover-email`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                    },
                    body: JSON.stringify({
                        contact_name: person.name,
                        org_name: orgName,
                        job_title: person.job_title || person.role
                    })
                });

                if (isCancelledRef.current) break;

                if (response.ok) {
                    const data = await response.json();
                    if (isCancelledRef.current) break;
                    const discoveredEmail = data.recommended || data.email;
                    
                    if (data.ok && discoveredEmail && onEmailDiscovered) {
                        setLocalEmailUpdates(prev => ({ ...prev, [person.id]: { email: discoveredEmail, verified: true } }));
                        await onEmailDiscovered(person, discoveredEmail);
                    } else if (!data.ok && onDeleteFromPipedrive && person.sources?.includes('pipedrive')) {
                        setLocalEmailUpdates(prev => ({ ...prev, [person.id]: { deleted: true } }));
                        await onDeleteFromPipedrive(person);
                    } else if (!data.ok || !discoveredEmail) {
                        setLocalEmailUpdates(prev => ({ ...prev, [person.id]: { deleted: true } }));
                        if (onDeleteFromPipedrive && person.sources?.includes('pipedrive')) {
                            await onDeleteFromPipedrive(person);
                        }
                    }
                } else if (onDeleteFromPipedrive && person.sources?.includes('pipedrive')) {
                    setLocalEmailUpdates(prev => ({ ...prev, [person.id]: { deleted: true } }));
                    await onDeleteFromPipedrive(person);
                } else {
                    setLocalEmailUpdates(prev => ({ ...prev, [person.id]: { deleted: true } }));
                }
            } catch (error) {
                console.error("Erro no lote para", person.name, error);
            } finally {
                setLoadingDiscover(prev => ({ ...prev, [person.id]: false }));
            }
            if (isCancelledRef.current) break;
            await new Promise(r => setTimeout(r, 1500));
            if (isCancelledRef.current) break;
        }
        
        if (!isCancelledRef.current) {
            setDiscoveryActiveId(null);
            setIsBatchValidatingLocal(false);
            setBatchProgress(null);
            toast.success("Validação em lote concluída!");
            window.dispatchEvent(new CustomEvent('crm_timeline_changed'));
        }
    };

    const getDropdownItems = (person: any) => {
        const items = [];
        const override = localEmailUpdates[person.id];
        const email = override?.deleted ? null : (override?.email || person.email?.[0]?.value || person.email);
        const phone = person.phone?.[0]?.value || person.phone;

        if (onEditPerson && person.emp_id) {
            items.push({
                label: 'Detalhes e Configurações',
                onClick: () => onEditPerson(person.emp_id),
                icon: <Info size={14} />
            });
        }

        if (onEmailDiscovered) {
            const isDiscovering = loadingDiscover[person.id];
            items.push({
                label: isDiscovering ? 'Salvando E-mail...' : 'Descobrir E-mail',
                onClick: (e: React.MouseEvent) => handleDiscoverEmail(person, e),
                icon: isDiscovering ? <Spinner size={14} inline /> : <Mail size={14} />,
                style: isDiscovering ? { opacity: 0.5, pointerEvents: 'none' as const } : undefined
            });
        }

        if (onSaveToPipedrive && person.emp_id && !person.sources?.includes('pipedrive')) {
            items.push({
                label: 'Salvar no Pipedrive',
                onClick: async () => {
                    try {
                        await onSaveToPipedrive(person);
                    } catch (e) {
                        console.error("Erro ao salvar no pipedrive", e);
                    }
                },
                icon: <img src="/pipedrive.png" alt="Pipedrive" style={{ width: 14, height: 14, objectFit: 'contain', borderRadius: '2px' }} />
            });
        }

        if (person.sources?.includes('pipedrive')) {
            if (onUpdateInPipedrive) {
                items.push({
                    label: 'Atualizar no Pipedrive',
                    onClick: async () => {
                        try {
                            await onUpdateInPipedrive(person);
                        } catch (e) {
                            console.error("Erro ao atualizar no pipedrive", e);
                        }
                    },
                    icon: <img src="/pipedrive.png" alt="Pipedrive" style={{ width: 14, height: 14, objectFit: 'contain', borderRadius: '2px' }} />
                });
            }
            if (onDeleteFromPipedrive) {
                items.push({
                    label: 'Remover do Pipedrive',
                    onClick: async () => {
                        try {
                            await onDeleteFromPipedrive(person);
                        } catch (e) {
                            console.error("Erro ao remover do pipedrive", e);
                        }
                    },
                    icon: <Trash2 size={14} style={{ color: '#ef4444' }} />
                });
            }
        }

        if (email) {
            items.push({
                label: 'Copiar E-mail',
                onClick: () => {
                    void navigator.clipboard.writeText(email);
                    toast.success('E-mail copiado com sucesso!');
                },
                icon: <Mail size={14} />
            });
        }
        if (phone) {
            items.push({
                label: 'Copiar Telefone',
                onClick: () => {
                    void navigator.clipboard.writeText(phone);
                    toast.success('Telefone copiado com sucesso!');
                },
                icon: <Phone size={14} />
            });
        }
        if (items.length === 0) {
            items.push({
                label: 'Sem ações',
                onClick: () => {},
                style: { opacity: 0.5, pointerEvents: 'none' as const }
            });
        }
        return items;
    };

    return (
        <div className={styles.container}>
            {persons.length > 0 && (
                <div className={styles.listHeaderVertical}>
                    <span className={styles.listCount}>Contatos ({persons.length})</span>
                    {onBatchValidateEmails && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <button 
                                className={`${styles.batchActionBtn} ${isBatchValidatingLocal ? styles.batchActionBtnLoading : ''}`}
                                onClick={handleStartBatch}
                                disabled={isBatchValidatingLocal}
                                title="Validar e-mails de todos os contatos listados"
                            >
                                {isBatchValidatingLocal ? <Spinner size={14} inline color="currentColor" /> : <Mail size={14} />}
                                {isBatchValidatingLocal && batchProgress 
                                    ? `Validando em Lote... (${batchProgress.current}/${batchProgress.total})` 
                                    : 'Validar todos os e-mails'
                                }
                            </button>
                            {isBatchValidatingLocal && (
                                <button 
                                    onClick={handleCancelBatch}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '6px',
                                        padding: '4px 10px', background: '#ef4444', color: '#fff',
                                        border: 'none', borderRadius: '6px', fontSize: '12px',
                                        fontWeight: 600, cursor: 'pointer'
                                    }}
                                    title="Cancelar a validação em lote"
                                >
                                    <X size={14} /> Cancelar
                                </button>
                            )}
                        </div>
                    )}
                </div>
            )}
            
            {persons.length === 0 && (
                <div className={styles.empty}>Nenhum contato encontrado para esta empresa.</div>
            )}
            
            {persons.map((person) => {
                const dropdownItems = getDropdownItems(person);
                const override = localEmailUpdates[person.id];
                const emailToDisplay = override?.deleted ? null : (override?.email || person.email?.[0]?.value);
                const isVerified = override ? override.verified : (person.sources?.includes('pipedrive') || person.email?.[0]?.label === 'verified');

                return (
                    <div key={person.id} id={`contact-row-${person.id}`} className={styles.contactRow}>
                        <div className={styles.contentCard}>
                            <div className={styles.contactHeader}>
                                <div>
                                    <div className={styles.nameContainer}>
                                        {person.profile_pic && (
                                            <img 
                                                src={person.profile_pic} 
                                                alt={person.name} 
                                                style={{ width: 24, height: 24, borderRadius: '50%', objectFit: 'cover' }} 
                                            />
                                        )}
                                        <h3 className={styles.name}>{person.name}</h3>
                                        <div className={styles.sourceIcons}>
                                            {person.sources?.includes('pipedrive') && (
                                                <img src="/pipedrive.png" alt="Pipedrive" title="Cadastrado no Pipedrive" className={`${styles.sourceIcon} ${styles.pipedriveIcon}`} />
                                            )}
                                            {person.sources?.includes('mapped') && (
                                                <a 
                                                    href={person.linkedin || `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(person.name)}`} 
                                                    target="_blank" 
                                                    rel="noopener noreferrer" 
                                                    style={{ display: 'flex', alignItems: 'center' }}
                                                >
                                                    <img src="/linkedin.png" alt="Mapeado" title={person.linkedin ? "Ver no LinkedIn" : "Pesquisar no LinkedIn"} className={`${styles.sourceIcon} ${styles.linkedinIcon}`} />
                                                </a>
                                            )}
                                        </div>
                                    </div>
                                    <div className={styles.role}>
                                        {person.job_title || 'Cargo não informado'}
                                    </div>
                                </div>
                                
                                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                                    <Dropdown 
                                        items={dropdownItems}
                                        iconType="horizontal"
                                        iconSize={16}
                                        title="Ações do contato"
                                        triggerClassName={styles.actionBtn}
                                    />
                                </div>
                            </div>

                            <div className={styles.metaList}>
                                {emailToDisplay && (
                                    <div className={styles.metaItem}>
                                        <Mail size={12} />
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <a 
                                                href={`mailto:${emailToDisplay}`} 
                                                className={`${styles.emailLink} ${discoveryActiveId === person.id ? styles.emailDiscovering : ''}`}
                                            >
                                                {emailToDisplay}
                                            </a>
                                            {isVerified && (
                                                <span title="E-mail verificado pelo sistema" style={{ display: 'flex', alignItems: 'center' }}>
                                                    <BadgeCheck size={14} fill="var(--sw-status-success)" color="var(--sw-status-success)" className={styles.verifiedBadge} />
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                )}
                                
                                {person.phone && person.phone[0]?.value && (
                                    <div className={styles.metaItem}>
                                        <Phone size={12} />
                                        <span>{person.phone[0].value}</span>
                                    </div>
                                )}

                                {!emailToDisplay && !person.phone?.[0]?.value && (
                                    <div className={styles.metaItem}>
                                        <MessageSquare size={12} />
                                        <span>Sem dados de contato direto</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                );
            })}

            {discoveryActiveId && anchorRect && (
                <EmailDiscoveryView
                    personName={persons.find(p => p.id === discoveryActiveId)?.name || ''}
                    orgName={orgName}
                    anchorRect={anchorRect}
                    onClose={() => setDiscoveryActiveId(null)}
                    onComplete={handleDiscoveryComplete}
                    jobTitle={persons.find(p => p.id === discoveryActiveId)?.job_title || ''}
                />
            )}
        </div>
    );
};
