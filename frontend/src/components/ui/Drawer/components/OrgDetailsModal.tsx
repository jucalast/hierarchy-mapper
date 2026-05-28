import React, { useState, useEffect } from 'react';
import { Globe, ChevronDown } from 'lucide-react';
import { Modal } from '../../Modal';
import { Dropdown } from '../../Dropdown/Dropdown';
import { Spinner, Badge } from '../../';
import styles from '../Drawer.module.css';

interface OrgDetailsModalProps {
    isOpen: boolean;
    onClose: () => void;
    expandedOrgId: number | null;
    orgDetails: Record<number, any>;
    focusedOrg: any;
    handleUpdateOrg: (orgId: number, data: Record<string, any>) => Promise<void>;
}

const formatCNPJ = (val: string) => {
    const digits = val.replace(/\D/g, '').slice(0, 14);
    let formatted = digits;
    if (digits.length > 2) formatted = digits.slice(0, 2) + '.' + digits.slice(2);
    if (digits.length > 5) formatted = formatted.slice(0, 6) + '.' + formatted.slice(6);
    if (digits.length > 8) formatted = formatted.slice(0, 10) + '/' + formatted.slice(10);
    if (digits.length > 12) formatted = formatted.slice(0, 15) + '-' + formatted.slice(15);
    return formatted;
};

export const OrgDetailsModal: React.FC<OrgDetailsModalProps> = ({
    isOpen,
    onClose,
    expandedOrgId,
    orgDetails,
    focusedOrg,
    handleUpdateOrg
}) => {
    // Local form states
    const [formName, setFormName] = useState('');
    const [formCnpj, setFormCnpj] = useState('');
    const [formDomain, setFormDomain] = useState('');
    const [formAddress, setFormAddress] = useState('');
    const [formLinkedinUrl, setFormLinkedinUrl] = useState('');
    const [formDescription, setFormDescription] = useState('');
    const [formCategory, setFormCategory] = useState('');
    const [formProductFocus, setFormProductFocus] = useState('');
    const [formTemperature, setFormTemperature] = useState('');
    const [formProspectingContext, setFormProspectingContext] = useState('');
    const [isSaving, setIsSaving] = useState(false);

    // Sync form state when modal opens or org changes
    useEffect(() => {
        if (isOpen && expandedOrgId && orgDetails[expandedOrgId] && focusedOrg) {
            const d = orgDetails[expandedOrgId];
            const o = d.org || {};
            setFormName(d.name || o.name || focusedOrg.name || '');
            setFormCnpj(d.cnpj || '');
            setFormDomain(d.domain || o.website || '');
            setFormAddress(d.address || o.address || '');
            setFormLinkedinUrl(d.linkedin_url || o.linkedin_url || d.linkedin || '');
            setFormDescription(d.description || '');
            setFormCategory(d.category || '');
            setFormProductFocus(d.product_focus || '');
            setFormTemperature(d.temperature || '');
            setFormProspectingContext(d.prospecting_context || '');
        }
    }, [isOpen, expandedOrgId, orgDetails, focusedOrg]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!expandedOrgId) return;
        
        setIsSaving(true);
        try {
            await handleUpdateOrg(expandedOrgId, {
                name: formName,
                cnpj: formCnpj,
                domain: formDomain,
                address: formAddress,
                linkedin_url: formLinkedinUrl,
                description: formDescription,
                category: formCategory,
                product_focus: formProductFocus,
                temperature: formTemperature,
                prospecting_context: formProspectingContext
            });
            onClose();
        } catch (err) {
            // Error is handled inside handleUpdateOrg notification
        } finally {
            setIsSaving(false);
        }
    };

    if (!isOpen || !expandedOrgId || !orgDetails[expandedOrgId]) return null;

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Detalhes e Configurações"
            width={640}
        >
            <form onSubmit={handleSubmit} className={styles.detailsForm} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                
                {/* Card ICP */}
                {orgDetails[expandedOrgId]?.icp_tier && (
                    <div className={styles.icpStatusCard}>
                        <div className={styles.icpStatusHeader}>
                            <span className={styles.icpStatusTitle}>Análise de ICP</span>
                            <Badge 
                                tone={orgDetails[expandedOrgId].icp_tier === 'A' ? 'success' : orgDetails[expandedOrgId].icp_tier === 'B' ? 'warning' : 'neutral'}
                                size="sm"
                            >
                                Tier {orgDetails[expandedOrgId].icp_tier}
                            </Badge>
                        </div>
                        <div className={styles.icpProgressBarWrapper}>
                            <div className={styles.icpProgressLabel}>
                                <span>Grau de Aderência</span>
                                <span>{orgDetails[expandedOrgId].icp_score}%</span>
                            </div>
                            <div className={styles.icpProgressBarTrack}>
                                <div 
                                    className={styles.icpProgressBarFill} 
                                    style={{ 
                                        width: `${orgDetails[expandedOrgId].icp_score}%`,
                                        background: orgDetails[expandedOrgId].icp_tier === 'A' ? 'var(--sw-success)' : orgDetails[expandedOrgId].icp_tier === 'B' ? 'var(--sw-warning)' : 'var(--sw-text-muted)'
                                    }} 
                                />
                            </div>
                        </div>
                    </div>
                )}

                <div className={styles.formSectionTitle}>Informações Principais</div>
                
                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label>Nome da Empresa</label>
                        <input 
                            type="text" 
                            value={formName} 
                            onChange={(e) => setFormName(e.target.value)} 
                            required 
                            className={styles.formInput}
                            placeholder="Nome comercial da organização"
                        />
                    </div>

                    <div className={styles.formGroup}>
                        <label>CNPJ</label>
                        <input 
                            type="text" 
                            value={formCnpj} 
                            onChange={(e) => setFormCnpj(formatCNPJ(e.target.value))} 
                            className={styles.formInput}
                            placeholder="00.000.000/0000-00"
                        />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Website / Domínio</label>
                        <div className={styles.formInputWithIcon}>
                            <Globe size={14} className={styles.formInputIcon} />
                            <input 
                                type="text" 
                                value={formDomain} 
                                onChange={(e) => setFormDomain(e.target.value)} 
                                className={styles.formInput}
                                placeholder="exemplo.com.br"
                            />
                        </div>
                    </div>

                    <div className={styles.formGroup}>
                        <label>LinkedIn URL</label>
                        <input 
                            type="text" 
                            value={formLinkedinUrl} 
                            onChange={(e) => setFormLinkedinUrl(e.target.value)} 
                            className={styles.formInput}
                            placeholder="https://linkedin.com/company/..."
                        />
                    </div>
                </div>

                <div className={styles.formGroup}>
                    <label>Endereço</label>
                    <input 
                        type="text" 
                        value={formAddress} 
                        onChange={(e) => setFormAddress(e.target.value)} 
                        className={styles.formInput}
                        placeholder="Rua, Número, Bairro, Cidade - UF"
                    />
                </div>

                <div className={styles.formSectionTitle}>Perfil Comercial</div>

                <div className={styles.formGrid}>
                    <div className={styles.formGroup} style={{ position: 'relative' }}>
                        <label>Temperatura</label>
                        <Dropdown 
                            align="left"
                            triggerClassName={styles.formSelect}
                            customTrigger={
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                                    <span>
                                        {formTemperature === 'cold' ? '❄️ Frio (Cold)' : 
                                         formTemperature === 'warm' ? '🌅 Morno (Warm)' : 
                                         formTemperature === 'hot' ? '🔥 Quente (Hot)' : 
                                         formTemperature === 'contacted' ? '📞 Contatado' : 
                                         'Selecione...'}
                                    </span>
                                    <ChevronDown size={14} style={{ opacity: 0.5 }} />
                                </div>
                            }
                            items={[
                                { label: 'Selecione...', onClick: () => setFormTemperature('') },
                                { label: '❄️ Frio (Cold)', onClick: () => setFormTemperature('cold') },
                                { label: '🌅 Morno (Warm)', onClick: () => setFormTemperature('warm') },
                                { label: '🔥 Quente (Hot)', onClick: () => setFormTemperature('hot') },
                                { label: '📞 Contatado', onClick: () => setFormTemperature('contacted') },
                            ]}
                        />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Categoria</label>
                        <input 
                            type="text" 
                            value={formCategory} 
                            onChange={(e) => setFormCategory(e.target.value)} 
                            className={styles.formInput}
                            placeholder="Ex: Compras, Logística, TI"
                        />
                    </div>

                    <div className={styles.formGroup}>
                        <label>Foco de Produto</label>
                        <input 
                            type="text" 
                            value={formProductFocus} 
                            onChange={(e) => setFormProductFocus(e.target.value)} 
                            className={styles.formInput}
                            placeholder="Ex: Auto Peças, Software"
                        />
                    </div>
                </div>

                <div className={styles.formGroup}>
                    <label>Descrição da Empresa</label>
                    <textarea 
                        value={formDescription} 
                        onChange={(e) => setFormDescription(e.target.value)} 
                        className={styles.formTextarea}
                        placeholder="Detalhes sobre a atuação da empresa..."
                        rows={3}
                    />
                </div>

                <div className={styles.formGroup}>
                    <label>Contexto de Prospecção</label>
                    <textarea 
                        value={formProspectingContext} 
                        onChange={(e) => setFormProspectingContext(e.target.value)} 
                        className={styles.formTextarea}
                        placeholder="Informações sobre a abordagem, dores mapeadas..."
                        rows={3}
                    />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '8px' }}>
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
