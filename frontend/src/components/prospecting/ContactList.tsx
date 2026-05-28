import React from 'react';
import { 
    User, 
    Mail, 
    Phone, 
    MessageSquare, 
    ExternalLink, 
    Briefcase
} from 'lucide-react';
import toast from 'react-hot-toast';
import styles from './ContactList.module.css';
import { Dropdown } from '../ui/Dropdown';

interface ContactListProps {
    persons: any[];
    onEditPerson?: (empId: string) => void;
    onSaveToPipedrive?: (empId: string) => void;
}

export const ContactList: React.FC<ContactListProps> = ({ persons, onEditPerson, onSaveToPipedrive }) => {
    const getDropdownItems = (person: any) => {
        const items = [];
        const email = person.email?.[0]?.value || person.email;
        const phone = person.phone?.[0]?.value || person.phone;

        if (onEditPerson && person.emp_id) {
            items.push({
                label: 'Detalhes e Configurações',
                onClick: () => onEditPerson(person.emp_id),
                icon: <Briefcase size={14} />
            });
        }

        if (onSaveToPipedrive && person.emp_id && !person.sources?.includes('pipedrive')) {
            items.push({
                label: 'Salvar no Pipedrive',
                onClick: () => {
                    onSaveToPipedrive(person.emp_id);
                    toast.success('Salvando contato no Pipedrive...');
                },
                icon: <User size={14} />
            });
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
                                <Dropdown 
                                    items={dropdownItems}
                                    iconType="horizontal"
                                    iconSize={16}
                                    title="Ações do contato"
                                    triggerClassName={styles.actionBtn}
                                />
                            </div>

                            <div className={styles.metaList}>
                                {person.email && person.email[0]?.value && (
                                    <div className={styles.metaItem}>
                                        <Mail size={12} />
                                        <a 
                                            href={`mailto:${person.email[0].value}`} 
                                            className={styles.emailLink}
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
        </div>
    );
};
