import React from 'react';
import { 
    User, 
    Mail, 
    Phone, 
    MessageSquare, 
    ExternalLink, 
    MoreHorizontal,
    Briefcase
} from 'lucide-react';
import styles from './ContactList.module.css';

interface ContactListProps {
    persons: any[];
}

export const ContactList: React.FC<ContactListProps> = ({ persons }) => {
    return (
        <div className={styles.container}>
            {persons.length === 0 && (
                <div className={styles.empty}>Nenhum contato encontrado para esta empresa.</div>
            )}
            
            {persons.map((person) => (
                <div key={person.id} className={styles.contactRow}>
                    <div className={styles.contentCard}>
                        <div className={styles.contactHeader}>
                            <div>
                                <h3 className={styles.name}>{person.name}</h3>
                                <div className={styles.role}>
                                    {person.job_title || 'Cargo não informado'}
                                </div>
                            </div>
                            <button className={styles.actionBtn}>
                                <MoreHorizontal size={16} />
                            </button>
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
            ))}
        </div>
    );
};
