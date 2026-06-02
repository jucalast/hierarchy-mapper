import React from 'react';
import { 
    User, 
    Mail, 
    Phone, 
    MessageSquare, 
    ExternalLink, 
    Briefcase,
    Info,
    Trash2
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
    onDiscoverEmail?: (person: any) => Promise<void> | void;
    orgName?: string;
}

export const ContactList: React.FC<ContactListProps> = ({ 
    persons, 
    onEditPerson, 
    onSaveToPipedrive, 
    onUpdateInPipedrive, 
    onDeleteFromPipedrive,
    onDiscoverEmail,
    orgName = "Empresa"
}) => {
    const [loadingDiscover, setLoadingDiscover] = React.useState<Record<string, boolean>>({});
    const [discoveryActiveId, setDiscoveryActiveId] = React.useState<string | null>(null);
    const [anchorRect, setAnchorRect] = React.useState<DOMRect | null>(null);

    const handleDiscoverEmail = (person: any, e: React.MouseEvent) => {
        // Tenta encontrar o elemento de e-mail na mesma linha do contato
        const row = e.currentTarget.closest(`.${styles.contactRow}`);
        const emailEl = row?.querySelector(`.${styles.metaItem}`);
        
        const rect = emailEl ? emailEl.getBoundingClientRect() : e.currentTarget.getBoundingClientRect();
        setAnchorRect(rect);
        setDiscoveryActiveId(person.id);
    };

    const handleDiscoveryComplete = async (email: string) => {
        if (!onDiscoverEmail || !discoveryActiveId) return;
        
        // Localiza a pessoa ativa
        const person = persons.find(p => p.id === discoveryActiveId);
        if (!person) return;

        setLoadingDiscover(prev => ({ ...prev, [person.id]: true }));
        try {
            await onDiscoverEmail(person);
        } catch (error) {
            console.error("Erro na descoberta manual de e-mail:", error);
        } finally {
            setLoadingDiscover(prev => ({ ...prev, [person.id]: false }));
        }
    };

    const getDropdownItems = (person: any) => {
        const items = [];
        const email = person.email?.[0]?.value || person.email;
        const phone = person.phone?.[0]?.value || person.phone;

        if (onEditPerson && person.emp_id) {
            items.push({
                label: 'Detalhes e Configurações',
                onClick: () => onEditPerson(person.emp_id),
                icon: <Info size={14} />
            });
        }

        if (onDiscoverEmail) {
            const isDiscovering = loadingDiscover[person.id];
            items.push({
                label: isDiscovering ? 'Descobrindo E-mail...' : 'Descobrir E-mail',
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
            {persons.length === 0 && (
                <div className={styles.empty}>Nenhum contato encontrado para esta empresa.</div>
            )}
            
            {persons.map((person) => {
                const dropdownItems = getDropdownItems(person);

                return (
                    <div key={person.id} className={styles.contactRow}>
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
                                {person.email && person.email[0]?.value && (
                                    <div className={styles.metaItem}>
                                        <Mail size={12} />
                                        <a 
                                            href={`mailto:${person.email[0].value}`} 
                                            className={`${styles.emailLink} ${discoveryActiveId === person.id ? styles.emailDiscovering : ''}`}
                                        >
                                            {person.email[0].value}
                                        </a>
                                    </div>
                                )}
                                
                                {person.phone && person.phone[0]?.value && (
                                    <div className={styles.metaItem}>
                                        <Phone size={12} />
                                        <span>{person.phone[0].value}</span>
                                    </div>
                                )}

                                {!person.email?.[0]?.value && !person.phone?.[0]?.value && (
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
                />
            )}
        </div>
    );
};
