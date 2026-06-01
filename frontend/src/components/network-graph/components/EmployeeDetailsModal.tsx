import React, { useState, useEffect } from 'react';
import { Modal } from '../../ui/Modal';
import { Dropdown } from '../../ui/Dropdown';
import { Spinner } from '../../ui';
import { ChevronDown, Mail, Phone, MapPin } from 'lucide-react';
import { LinkedInIcon } from '../../icons/LinkedInIcon';
import styles from '../../ui/Drawer/Drawer.module.css';
import { HierarchyEmployee } from '@/types';
import { hierarchy as hierarchyApi } from '@/services/api';
import { Sparkles, Brain } from 'lucide-react';
import { useNotifications } from '@/hooks/useNotifications';

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
    const { success, error } = useNotifications();
    const [formName, setFormName] = useState('');
    const [formRole, setFormRole] = useState('');
    const [formDepartment, setFormDepartment] = useState('');
    const [formLevel, setFormLevel] = useState<number>(5);
    const [formEmail, setFormEmail] = useState('');
    const [formPhone, setFormPhone] = useState('');
    const [formLinkedin, setFormLinkedin] = useState('');
    const [formLocation, setFormLocation] = useState('');
    const [formObservations, setFormObservations] = useState('');
    const [formEducation, setFormEducation] = useState('');
    const [linkedinText, setLinkedinText] = useState('');
    const [isSaving, setIsSaving] = useState(false);
    const [isEnriching, setIsEnriching] = useState(false);

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
                setFormObservations(typeof emp.observations === 'string' ? emp.observations : (typeof emp.description === 'string' ? emp.description : ''));
                setFormEducation(emp.education || '');
            }
        }
    }, [isOpen, empId, rawEmployees]);

    const handleEnrichManual = async () => {
        if (!empId || !linkedinText.trim()) return;

        setIsEnriching(true);
        try {
            // Limpeza básica para reduzir payload e ruído
            const cleanedText = linkedinText
                .split('\n')
                .map(line => line.trim())
                .filter(line => line.length > 0)
                .join('\n')
                .slice(0, 15000); // Limite de segurança

            const data = await hierarchyApi.enrichManual(empId, cleanedText);
            if (data.employee) {
                const e = data.employee;
                setFormName(e.name || formName);
                setFormRole(e.role || formRole);
                setFormDepartment(e.department || formDepartment);
                setFormLevel(e.seniority || e.level || formLevel);
                setFormLocation(e.location || formLocation);
                setFormObservations(typeof e.observations === 'string' ? e.observations : formObservations);
                setFormEducation(e.education || formEducation);
                // Opcional: Limpar o texto após sucesso
                setLinkedinText('');
                success(`Dados de ${e.name} refinados com sucesso via IA!`);
            }
        } catch (err: any) {
            console.error(err);
            error("Erro ao refinar perfil: " + (err.response?.data?.detail || err.message));
        } finally {
            setIsEnriching(false);
        }
    };

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
                location: formLocation,
                observations: formObservations,
                education: formEducation
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
            width={720}
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
                                    <ChevronDown size={16} style={{ opacity: 0.5 }} />
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
                            <Mail size={16} className={styles.formInputIcon} />
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
                            <Phone size={16} className={styles.formInputIcon} />
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
                            <LinkedInIcon size={16} className={styles.formInputIcon} />
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
                            <MapPin size={16} className={styles.formInputIcon} />
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

                <div className={styles.formSectionTitle}>Informações Adicionais (IA)</div>
                <div className={styles.formGroup}>
                    <label>Biografia / Observações</label>
                    <textarea 
                        value={formObservations} 
                        onChange={(e) => setFormObservations(e.target.value)} 
                        className={styles.formInput}
                        placeholder="Resumo profissional e evidências..."
                        style={{ height: '80px', resize: 'vertical' }}
                    />
                </div>
                <div className={styles.formGroup}>
                    <label>Educação / Formação</label>
                    <textarea 
                        value={formEducation} 
                        onChange={(e) => setFormEducation(e.target.value)} 
                        className={styles.formInput}
                        placeholder="Principais formações acadêmicas..."
                        style={{ height: '60px', resize: 'vertical' }}
                    />
                </div>

                <div className={styles.formSectionTitle} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Sparkles size={16} color="#6366f1" />
                    Refinar com IA (LinkedIn)
                </div>
                <div className={styles.formGroup}>
                    <label style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '8px', display: 'block' }}>
                        Copie todo o texto da página do perfil no LinkedIn (Ctrl+A, Ctrl+C) e cole abaixo para que a IA extraia os detalhes automaticamente.
                    </label>
                    <textarea 
                        value={linkedinText}
                        onChange={(e) => setLinkedinText(e.target.value)}
                        placeholder="Cole aqui o conteúdo do perfil LinkedIn..."
                        className={styles.formInput}
                        style={{ height: '120px', resize: 'vertical', padding: '12px', fontSize: '0.85rem', background: 'rgba(0,0,0,0.2)' }}
                    />
                    <button 
                        type="button"
                        onClick={handleEnrichManual}
                        disabled={isEnriching || !linkedinText.trim()}
                        style={{ 
                            marginTop: '12px', 
                            background: isEnriching || !linkedinText.trim() ? 'rgba(255, 255, 255, 0.05)' : 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
                            color: isEnriching || !linkedinText.trim() ? 'rgba(255, 255, 255, 0.4)' : '#ffffff',
                            border: isEnriching || !linkedinText.trim() ? '1px solid rgba(255, 255, 255, 0.1)' : 'none',
                            padding: '12px 24px',
                            borderRadius: '8px',
                            fontWeight: 600,
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center',
                            gap: '10px',
                            width: '100%',
                            cursor: isEnriching || !linkedinText.trim() ? 'not-allowed' : 'pointer',
                            transition: 'all 0.2s ease',
                            boxShadow: isEnriching || !linkedinText.trim() ? 'none' : '0 4px 12px rgba(99, 102, 241, 0.3)'
                        }}
                        onMouseEnter={(e) => {
                            if (!isEnriching && linkedinText.trim()) {
                                e.currentTarget.style.transform = 'translateY(-1px)';
                                e.currentTarget.style.boxShadow = '0 6px 16px rgba(99, 102, 241, 0.4)';
                            }
                        }}
                        onMouseLeave={(e) => {
                            if (!isEnriching && linkedinText.trim()) {
                                e.currentTarget.style.transform = 'translateY(0)';
                                e.currentTarget.style.boxShadow = '0 4px 12px rgba(99, 102, 241, 0.3)';
                            }
                        }}
                    >
                        {isEnriching ? (
                            <>
                                <Spinner size={16} inline />
                                <span>Processando Perfil...</span>
                            </>
                        ) : (
                            <>
                                <Brain size={18} />
                                <span>Extrair Dados via IA</span>
                            </>
                        )}
                    </button>
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
