import React, { useState, useEffect } from 'react';
import { Modal } from '../../ui/Modal';
import { Dropdown } from '../../ui/Dropdown';
import { Spinner } from '../../ui';
import { ChevronDown, Mail, Phone, MapPin } from 'lucide-react';
import { LinkedInIcon } from '../../icons/LinkedInIcon';
import styles from '../../ui/Drawer/Drawer.module.css';
import { HierarchyEmployee } from '@/types';

interface EmployeeDetailsModalProps {
    isOpen: boolean;
    onClose: () => void;
    empId: string | null;
    rawEmployees: HierarchyEmployee[];
    handleUpdateEmployee: (id: string, updates: Partial<HierarchyEmployee>) => void;
}

export const EmployeeDetailsModal: React.FC<EmployeeDetailsModalProps> = ({
    isOpen,
    onClose,
    empId,
    rawEmployees,
    handleUpdateEmployee
}) => {
    const [formName, setFormName] = useState('');
    const [formRole, setFormRole] = useState('');
    const [formDepartment, setFormDepartment] = useState('');
    const [formLevel, setFormLevel] = useState<number>(5);
    const [formEmail, setFormEmail] = useState('');
    const [formPhone, setFormPhone] = useState('');
    const [formLinkedin, setFormLinkedin] = useState('');
    const [formLocation, setFormLocation] = useState('');
    const [isSaving, setIsSaving] = useState(false);

    useEffect(() => {
        if (isOpen && empId) {
            const emp = rawEmployees.find(e => e.id.toString() === empId);
            if (emp) {
                setFormName(emp.name || '');
                setFormRole(emp.role || '');
                setFormDepartment(emp.department || '');
                setFormLevel(emp.level ?? 5);
                setFormEmail(emp.email || '');
                setFormPhone(emp.phone || '');
                setFormLinkedin(emp.linkedin || emp.linkedin_url || '');
                setFormLocation(emp.location || '');
            }
        }
    }, [isOpen, empId, rawEmployees]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!empId) return;
        
        setIsSaving(true);
        try {
            await handleUpdateEmployee(empId, {
                name: formName,
                role: formRole,
                department: formDepartment,
                level: formLevel,
                email: formEmail,
                phone: formPhone,
                linkedin: formLinkedin,
                location: formLocation
            });
            onClose();
        } catch (err) {
            console.error(err);
        } finally {
            setIsSaving(false);
        }
    };

    if (!isOpen || !empId) return null;

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Detalhes do Profissional"
            width={580}
        >
            <form onSubmit={handleSubmit} className={styles.detailsForm} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className={styles.formSectionTitle}>Informações Principais</div>
                
                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label>Nome Completo</label>
                        <input 
                            type="text" 
                            value={formName} 
                            onChange={(e) => setFormName(e.target.value)} 
                            required 
                            className={styles.formInput}
                            placeholder="Nome do profissional"
                        />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Cargo / Headline</label>
                        <input 
                            type="text" 
                            value={formRole} 
                            onChange={(e) => setFormRole(e.target.value)} 
                            required 
                            className={styles.formInput}
                            placeholder="Ex: Diretor de Compras"
                        />
                    </div>
                </div>

                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label>Departamento</label>
                        <input 
                            type="text" 
                            value={formDepartment} 
                            onChange={(e) => setFormDepartment(e.target.value)} 
                            className={styles.formInput}
                            placeholder="Ex: Supply Chain"
                        />
                    </div>

                    <div className={styles.formGroup} style={{ position: 'relative' }}>
                        <label>Senioridade (Tier)</label>
                        <Dropdown 
                            align="left"
                            triggerClassName={styles.formSelect}
                            customTrigger={
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                                    <span>
                                        {formLevel === 6 ? 'Tier 6 - Board / C-Level' : 
                                         formLevel === 5 ? 'Tier 5 - Diretor / Regional' : 
                                         formLevel === 4 ? 'Tier 4 - Manager / Head' : 
                                         formLevel === 3 ? 'Tier 3 - Coordenador' : 
                                         formLevel === 2 ? 'Tier 2 - Especialista / Sênior' : 
                                         formLevel === 1 ? 'Tier 1 - Operacional' : 
                                         'Selecione...'}
                                    </span>
                                    <ChevronDown size={14} style={{ opacity: 0.5 }} />
                                </div>
                            }
                            items={[
                                { label: 'Tier 6 - Board / C-Level', onClick: () => setFormLevel(6) },
                                { label: 'Tier 5 - Diretor / Regional', onClick: () => setFormLevel(5) },
                                { label: 'Tier 4 - Manager / Head', onClick: () => setFormLevel(4) },
                                { label: 'Tier 3 - Coordenador', onClick: () => setFormLevel(3) },
                                { label: 'Tier 2 - Especialista / Sênior', onClick: () => setFormLevel(2) },
                                { label: 'Tier 1 - Operacional', onClick: () => setFormLevel(1) },
                            ]}
                        />
                    </div>
                </div>

                <div className={styles.formSectionTitle}>Contato & Localização</div>

                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label>Email</label>
                        <div className={styles.formInputWithIcon}>
                            <Mail size={14} className={styles.formInputIcon} />
                            <input 
                                type="email" 
                                value={formEmail} 
                                onChange={(e) => setFormEmail(e.target.value)} 
                                className={styles.formInput}
                                placeholder="email@empresa.com"
                            />
                        </div>
                    </div>

                    <div className={styles.formGroup}>
                        <label>Telefone</label>
                        <div className={styles.formInputWithIcon}>
                            <Phone size={14} className={styles.formInputIcon} />
                            <input 
                                type="text" 
                                value={formPhone} 
                                onChange={(e) => setFormPhone(e.target.value)} 
                                className={styles.formInput}
                                placeholder="+55 11 99999-9999"
                            />
                        </div>
                    </div>
                </div>

                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label>LinkedIn URL</label>
                        <div className={styles.formInputWithIcon}>
                            <LinkedInIcon size={14} className={styles.formInputIcon} />
                            <input 
                                type="text"  
                                value={formLinkedin} 
                                onChange={(e) => setFormLinkedin(e.target.value)} 
                                className={styles.formInput}
                                placeholder="https://linkedin.com/in/..."
                            />
                        </div>
                    </div>

                    <div className={styles.formGroup}>
                        <label>Localidade</label>
                        <div className={styles.formInputWithIcon}>
                            <MapPin size={14} className={styles.formInputIcon} />
                            <input 
                                type="text" 
                                value={formLocation} 
                                onChange={(e) => setFormLocation(e.target.value)} 
                                className={styles.formInput}
                                placeholder="Ex: São Paulo, Brasil"
                            />
                        </div>
                    </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
                    <button 
                        type="submit" 
                        disabled={isSaving} 
                        className={styles.saveBtn}
                        style={{ padding: '10px 24px', borderRadius: '8px' }}
                    >
                        {isSaving ? (
                            <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                <Spinner size={14} inline />
                                <span>Salvando...</span>
                            </span>
                        ) : (
                            <span>Salvar Alterações</span>
                        )}
                    </button>
                </div>
            </form>
        </Modal>
    );
};
