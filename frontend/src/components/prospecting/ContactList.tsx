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
import { useEmailValidationStore, EMPTY_SESSION, orgKeyOf } from '@/store/emailValidationStore';

interface GenericContact {
    id: string;
    email?: string;
    phone?: string;
    label: string;  // "compras", "suprimentos", "google_maps"
}

interface ContactListProps {
    persons: any[];
    genericContacts?: GenericContact[];
    onEditPerson?: (empId: string) => void;
    onSaveToPipedrive?: (person: any) => Promise<void> | void;
    onUpdateInPipedrive?: (person: any) => Promise<void> | void;
    onDeleteFromPipedrive?: (person: any) => Promise<void> | void;
    onEmailDiscovered?: (person: any, email: string) => Promise<void> | void;
    onBatchValidateEmails?: () => void;
    isBatchValidating?: boolean;
    orgName?: string;
    orgId?: number;
}

export const ContactList: React.FC<ContactListProps> = ({
    persons,
    genericContacts = [],
    onEditPerson,
    onSaveToPipedrive,
    onUpdateInPipedrive,
    onDeleteFromPipedrive,
    onEmailDiscovered,
    onBatchValidateEmails,
    isBatchValidating = false,
    orgName = "Empresa",
    orgId,
}) => {
    const [loadingDiscover, setLoadingDiscover] = React.useState<Record<string, boolean>>({});
    const [discoveryActiveId, setDiscoveryActiveId] = React.useState<string | null>(null);
    const [anchorRect, setAnchorRect] = React.useState<DOMRect | null>(null);
    const [localEmailUpdates, setLocalEmailUpdates] = React.useState<Record<string, { email?: string, verified?: boolean, deleted?: boolean }>>({});

    // Estado da validação em lote vem do store global (sobrevive a troca de aba/página).
    const orgKey = orgKeyOf(orgId);
    const batchSession = useEmailValidationStore(s => s.sessions[orgKey]) ?? EMPTY_SESSION;
    const startValidation = useEmailValidationStore(s => s.startValidation);
    const cancelValidation = useEmailValidationStore(s => s.cancelValidation);

    const isBatchValidatingLocal = batchSession.isRunning;
    const batchProgress = batchSession.progress;
    // Overlay de e-mails validados: store (lote) + estado local (descoberta manual).
    const mergedEmailUpdates = React.useMemo(
        () => ({ ...batchSession.emailUpdates, ...localEmailUpdates }),
        [batchSession.emailUpdates, localEmailUpdates]
    );
    // Contato com animação ativa: descoberta manual tem prioridade sobre o lote.
    const activeShimmerId = discoveryActiveId ?? batchSession.activeContactId;

    const handleCancelBatch = () => {
        cancelValidation(orgKey);
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

    const handleStartBatch = () => {
        const queue = persons.filter(p => {
            if (p.is_generic) return false;
            if (p.sources?.includes('pipedrive')) return false;
            return true;
        });

        if (queue.length === 0) {
            // Todos os pendentes são do Pipedrive — delega ao backend
            if (onBatchValidateEmails) {
                onBatchValidateEmails();
            } else {
                toast.success("Todos os contatos listados já estão validados!");
            }
            return;
        }

        // Dispara o loop no store global — roda independente deste componente.
        startValidation(orgKey, queue, { orgName, orgId });
    };

    const getDropdownItems = (person: any) => {
        const items = [];
        const override = mergedEmailUpdates[person.id];
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
            const isDiscovering = loadingDiscover[person.id] || batchSession.loadingIds[person.id];
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
            {/* Canais genéricos de entrada — acima do contador de contatos */}
            {genericContacts.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                    {genericContacts.map((gc) => (
                        <div key={gc.id} style={{ display: 'flex', alignItems: 'center' }}>
                            {gc.email && (
                                <a
                                    href={`mailto:${gc.email}`}
                                    style={{ color: 'var(--sw-primary, #6366f1)', textDecoration: 'none', fontWeight: 500 }}
                                    onClick={(e) => e.stopPropagation()}
                                >
                                    {gc.email}
                                </a>
                            )}
                            {gc.phone && (
                                <a
                                    href={`tel:${gc.phone}`}
                                    style={{ color: 'var(--sw-primary, #6366f1)', textDecoration: 'none', fontWeight: 500 }}
                                    onClick={(e) => e.stopPropagation()}
                                >
                                    {gc.phone}
                                </a>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {persons.length > 0 && (
                <>
                    <div className={styles.listHeaderVertical}>
                        <span className={styles.listCount}>Contatos ({persons.length})</span>
                        {onBatchValidateEmails && !isBatchValidatingLocal && !isBatchValidating && (
                            <button
                                className={styles.batchActionBtn}
                                onClick={handleStartBatch}
                                title="Validar e-mails de todos os contatos listados"
                            >
                                <Mail size={14} /> Validar tudo
                            </button>
                        )}
                    </div>
                    {(isBatchValidatingLocal || isBatchValidating) && (
                        <div className={styles.batchProgressBar}>
                            <span className={styles.batchProgressLabel}>
                                <Spinner size={14} inline color="currentColor" />
                                {batchProgress
                                    ? `${batchProgress.pattern ? `Padrão ${batchProgress.pattern}` : 'Validando'} · ${batchProgress.current}/${batchProgress.total}`
                                    : 'Validando no servidor…'}
                            </span>
                            {isBatchValidatingLocal && (
                                <button
                                    className={styles.batchCancelBtn}
                                    onClick={handleCancelBatch}
                                    title="Cancelar a validação em lote"
                                >
                                    <X size={14} /> Cancelar
                                </button>
                            )}
                        </div>
                    )}
                </>
            )}
            
            {persons.length === 0 && (
                <div className={styles.empty}>Nenhum contato encontrado para esta empresa.</div>
            )}
            
            {persons.map((person) => {
                const dropdownItems = getDropdownItems(person);
                const override = mergedEmailUpdates[person.id];
                const rawEmail = person.email?.[0]?.value ?? (typeof person.email === 'string' ? person.email : null);
                const emailToDisplay = override?.deleted ? null : (override?.email || rawEmail);
                const isVerified = override
                    ? !!override.verified
                    : (person.email_verified || person.sources?.includes('pipedrive') || person.email?.[0]?.label === 'verified');

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
                                                className={`${styles.emailLink} ${activeShimmerId === person.id ? styles.emailDiscovering : ''}`}
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

            {discoveryActiveId && anchorRect && (() => {
                const activePerson = persons.find(p => p.id === discoveryActiveId);
                const activePersonId = activePerson?.emp_id ?? (typeof activePerson?.id === 'number' ? activePerson.id : undefined);
                return (
                    <EmailDiscoveryView
                        personName={activePerson?.name || ''}
                        orgName={orgName}
                        anchorRect={anchorRect}
                        onClose={() => setDiscoveryActiveId(null)}
                        onComplete={handleDiscoveryComplete}
                        jobTitle={activePerson?.job_title || ''}
                        personId={activePersonId}
                        orgId={orgId}
                    />
                );
            })()}
        </div>
    );
};
