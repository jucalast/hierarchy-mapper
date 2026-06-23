import React from 'react';
import { Users, Briefcase, Clock, DollarSign, User, Info, Globe } from 'lucide-react';
import { Avatar, Spinner, Badge } from '../../';
import { HistoryTimeline } from '../../../prospecting/HistoryTimeline';
import { ContactList } from '../../../prospecting/ContactList';
import styles from '../Drawer.module.css';

interface FocusedOrgViewProps {
    focusedOrg: any;
    expandedOrgId: number;
    orgDetails: Record<number, any>;
    loadingDetails: Record<number, boolean>;
    activeTab: string;
    setActiveTab: (tab: string) => void;
    editingNameOrgId: number | null;
    editingNameValue: string;
    setEditingNameValue: (val: string) => void;
    setEditingNameOrgId: (id: number | null) => void;
    handleRenameOrg: (orgId: number) => Promise<void>;
    handleUpdateOrg: (orgId: number, data: Record<string, any>) => Promise<void>;
    scanningOrgId: number | null;
    selectedOrgId?: number | null;
    selectedOrgLogo?: string;
    graphEmployees?: any[];
    onEditEmployee?: (empId: string) => void;
    onSaveToPipedrive?: (person: any) => Promise<void> | void;
    onUpdateInPipedrive?: (person: any) => Promise<void> | void;
    onDeleteFromPipedrive?: (person: any) => Promise<void> | void;
    onEmailDiscovered?: (person: any, email: string) => Promise<void> | void;
}



export const FocusedOrgView: React.FC<FocusedOrgViewProps> = ({
    focusedOrg,
    expandedOrgId,
    orgDetails,
    loadingDetails,
    activeTab,
    setActiveTab,
    editingNameOrgId,
    editingNameValue,
    setEditingNameValue,
    setEditingNameOrgId,
    handleRenameOrg,
    handleUpdateOrg,
    scanningOrgId,
    selectedOrgId,
    selectedOrgLogo,
    graphEmployees = [],
    onEditEmployee,
    onSaveToPipedrive,
    onUpdateInPipedrive,
    onDeleteFromPipedrive,
    onEmailDiscovered
}) => {
    const rawUrls = [
        focusedOrg?.linkedin,
        focusedOrg?.linkedin_url,
        orgDetails[expandedOrgId]?.linkedin_url,
        orgDetails[expandedOrgId]?.org?.linkedin_url,
        orgDetails[expandedOrgId]?.org?.linkedin
    ];
    const rawLinkedinUrl = rawUrls.find(url => typeof url === 'string' && url.includes('linkedin.com/'));
    
    const linkedinUrl = rawLinkedinUrl || null;
    const linkedinTitle = "Ver no LinkedIn";



    const [isBatchValidating, setIsBatchValidating] = React.useState(false);

    const handleBatchValidateEmails = async () => {
        setIsBatchValidating(true);
        try {
            const orgId = focusedOrg.local_id || focusedOrg.id || expandedOrgId;
            const { organizations } = await import('@/services/api');
            const res = await organizations.batchValidateEmails(orgId);
            if (res.ok) {
                // Notifica sucesso visual
                const event = new CustomEvent('crm_notification', {
                    detail: { type: 'success', message: 'Superteste iniciado em segundo plano! A tela será atualizada em breve.' }
                });
                window.dispatchEvent(event);
                
                // Dispara o evento para atualizar a timeline e a UI de pessoas
                const changeEvent = new CustomEvent('crm_timeline_changed');
                window.dispatchEvent(changeEvent);
            }
        } catch (error) {
            console.error('Erro ao iniciar validação em lote:', error);
            const errorEvent = new CustomEvent('crm_notification', {
                detail: { type: 'error', message: 'Erro ao executar o superteste de e-mails em lote.' }
            });
            window.dispatchEvent(errorEvent);
        } finally {
            // Remove o estado de carregamento imediatamente após o backend responder
            setIsBatchValidating(false);
        }
    };

    return (
        <div className={styles.focusedOrgView}>
            <div className={styles.focusedOrgHero}>
                <div className={styles.focusedOrgLogoWrapper}>
                    <Avatar
                        kind="company"
                        src={focusedOrg.logo || (Number(focusedOrg.id) === selectedOrgId || Number(focusedOrg.local_id) === selectedOrgId ? selectedOrgLogo : undefined)}
                        name={focusedOrg.name}
                        data={focusedOrg}
                        size={48}
                    />
                </div>
                <div className={styles.focusedOrgIdentity}>
                    {editingNameOrgId === expandedOrgId ? (
                        <input
                            type="text"
                            value={editingNameValue}
                            onChange={(e) => setEditingNameValue(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    handleRenameOrg(expandedOrgId);
                                } else if (e.key === 'Escape') {
                                    setEditingNameOrgId(null);
                                }
                            }}
                            onBlur={() => handleRenameOrg(expandedOrgId)}
                            autoFocus
                            className={styles.focusedOrgNameEdit}
                            placeholder="Nome da empresa..."
                        />
                    ) : (
                        <h2
                            className={styles.focusedOrgName}
                            onDoubleClick={() => {
                                setEditingNameOrgId(expandedOrgId);
                                setEditingNameValue(focusedOrg.name);
                            }}
                            title="Clique duas vezes para renomear"
                            style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px', width: '100%', overflow: 'hidden' }}
                        >
                            <span style={{ 
                                whiteSpace: 'nowrap', 
                                overflow: 'hidden', 
                                textOverflow: 'ellipsis',
                                flex: '0 1 auto'
                            }}>
                                {focusedOrg.name}
                            </span>
                            {linkedinUrl && (
                                <a
                                    href={linkedinUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    title={linkedinTitle}
                                    onClick={(e) => e.stopPropagation()}
                                    onDoubleClick={(e) => e.stopPropagation()}
                                    style={{ 
                                        display: 'inline-flex', 
                                        alignItems: 'center', 
                                        flexShrink: 0, 
                                        transition: 'transform 0.2s ease-in-out',
                                        cursor: 'pointer'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.15)'}
                                    onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
                                >
                                    <img src="/linkedin.png" alt="LinkedIn" style={{ width: 18, height: 18, objectFit: 'contain' }} />
                                </a>
                            )}
                            {orgDetails[expandedOrgId]?.icp_tier && (
                                <Badge 
                                    tone={orgDetails[expandedOrgId].icp_tier === 'A' ? 'success' : orgDetails[expandedOrgId].icp_tier === 'B' ? 'warning' : 'neutral'}
                                    size="sm"
                                    style={{ fontSize: '11px', padding: '2px 8px', flexShrink: 0 }}
                                    title={`ICP Score: ${orgDetails[expandedOrgId].icp_score}`}
                                >
                                    Tier {orgDetails[expandedOrgId].icp_tier} • {orgDetails[expandedOrgId].icp_score}%
                                </Badge>
                            )}
                            {scanningOrgId === expandedOrgId && (
                                <Spinner size={16} inline color="var(--sw-primary)" />
                            )}
                        </h2>
                    )}
                    <div className={styles.focusedMetaRow}>
                        {focusedOrg.address && (
                            <span className={styles.focusedOrgAddress}>
                                {focusedOrg.address.toLowerCase().replace(/(^\w|\s\w)/g, (m: string) => m.toUpperCase())}
                            </span>
                        )}
                        {orgDetails[expandedOrgId]?.org?.owner_name && (
                            <span className={styles.focusedOrgOwner} title="Responsável pela empresa" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                <User size={12} style={{ marginRight: '4px', opacity: 0.6 }} />
                                {orgDetails[expandedOrgId].org.owner_name}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            <div className={styles.detailsPane}>
                {loadingDetails[expandedOrgId] ? (
                    <div className={styles.detailsLoading}>
                        <Spinner size={16} inline />
                        <span>Sincronizando...</span>
                    </div>
                ) : orgDetails[expandedOrgId] ? (
                    <div className={styles.detailsContent}>
                        <div className={styles.mainNav}>
                            <button
                                className={activeTab === 'activities' ? styles.mainNavActive : styles.mainNavBtn}
                                onClick={() => setActiveTab('activities')}
                            >
                                <Clock size={16} /> Timeline
                            </button>
                            <button
                                className={activeTab === 'persons' ? styles.mainNavActive : styles.mainNavBtn}
                                onClick={() => setActiveTab('persons')}
                            >
                                <Users size={16} /> People
                            </button>
                            <button
                                className={activeTab === 'deals' ? styles.mainNavActive : styles.mainNavBtn}
                                onClick={() => setActiveTab('deals')}
                            >
                                <Briefcase size={16} /> Deals
                            </button>
                        </div>

                        <div className={styles.tabScrollAreaFocus}>
                            {activeTab === 'activities' && (
                                <HistoryTimeline
                                    details={orgDetails[expandedOrgId]}
                                    orgName={focusedOrg.name}
                                />
                            )}

                            {activeTab === 'persons' && (
                                <ContactList
                                    orgName={focusedOrg.name}
                                    persons={(() => {
                                        const pipedrivePersons = orgDetails[expandedOrgId]?.persons || [];
                                        const validEmps = graphEmployees.filter(emp => {
                                            if (emp.id === 'root_company') return false;
                                            // Sócio com LinkedIn real → sempre inclui na aba People
                                            const hasRealLinkedIn = emp.linkedin && emp.linkedin.includes('linkedin.com/in/');
                                            const isQSA = emp.department === 'Quadro Societário' || emp.department === 'Quadro de Sócios (QSA)';
                                            const isPartnerNode = String(emp.id).startsWith('partner_') || emp.level === 6;
                                            if ((isQSA || isPartnerNode) && hasRealLinkedIn) return true;
                                            if (isQSA || isPartnerNode) return false;
                                            // Demais funcionários: exclui apenas "Análise Humana"
                                            if (emp.role && emp.role.toLowerCase().includes('humana')) return false;
                                            return true;
                                        });

                                        const merged = [];
                                        const seenPipedriveIds = new Set();
                                        const mappedByName = new Map();
                                        const mappedById = new Map();

                                        for (const p of pipedrivePersons) {
                                            if (!p.id || seenPipedriveIds.has(p.id)) continue;
                                            seenPipedriveIds.add(p.id);
                                            
                                            const nameKey = p.name ? p.name.trim().toLowerCase() : '';
                                            const personItem = {
                                                ...p,
                                                sources: ['pipedrive'],
                                                emp_id: validEmps.find(e => (e.pipedrive_id && Number(e.pipedrive_id) === Number(p.id)) || (e.name?.trim().toLowerCase() === nameKey))?.id
                                            };
                                            merged.push(personItem);
                                            if (nameKey) {
                                                mappedByName.set(nameKey, personItem);
                                            }
                                            mappedById.set(Number(p.id), personItem);
                                        }

                                        for (const emp of validEmps) {
                                            const nameKey = emp.name ? emp.name.trim().toLowerCase() : '';
                                            const pidMatch = emp.pipedrive_id ? mappedById.get(Number(emp.pipedrive_id)) : null;
                                            const existing = pidMatch || (nameKey && mappedByName.has(nameKey) ? mappedByName.get(nameKey) : null);
                                            
                                            if (existing) {
                                                if (!existing.profile_pic && (emp.profile_pic || emp.avatar)) {
                                                    existing.profile_pic = emp.profile_pic || emp.avatar;
                                                }
                                                if (!existing.job_title && (emp.role || emp.title)) {
                                                    existing.job_title = emp.role || emp.title;
                                                }
                                                if (!existing.name && emp.name) {
                                                    existing.name = emp.name;
                                                } else if (existing.name && emp.name && emp.name.length > existing.name.length) {
                                                    existing.name = emp.name;
                                                }
                                                // Merge local email and phone if available
                                                let hasPipedriveEmail = false;
                                                if (existing.email) {
                                                    if (Array.isArray(existing.email)) {
                                                        hasPipedriveEmail = existing.email.some((e: any) => e?.value && typeof e.value === 'string' && e.value.trim() !== '' && e.value.includes('@') && !e.value.includes('Sem dados'));
                                                    } else if (typeof existing.email === 'string') {
                                                        hasPipedriveEmail = existing.email.trim() !== '' && existing.email.includes('@') && !existing.email.includes('Sem dados');
                                                    }
                                                }
                                                if (emp.email && !hasPipedriveEmail) {
                                                    existing.email = [{ value: emp.email, primary: true }];
                                                }
                                                
                                                let hasPipedrivePhone = false;
                                                if (existing.phone) {
                                                    if (Array.isArray(existing.phone)) {
                                                        hasPipedrivePhone = existing.phone.some((p: any) => p?.value && typeof p.value === 'string' && p.value.trim() !== '' && /\d/.test(p.value) && !p.value.includes('Sem dados'));
                                                    } else if (typeof existing.phone === 'string') {
                                                        hasPipedrivePhone = existing.phone.trim() !== '' && /\d/.test(existing.phone) && !existing.phone.includes('Sem dados');
                                                    }
                                                }
                                                if (emp.phone && !hasPipedrivePhone) {
                                                    existing.phone = [{ value: emp.phone, primary: true }];
                                                }
                                                if (!existing.linkedin && emp.linkedin) {
                                                    existing.linkedin = emp.linkedin;
                                                }
                                                if (!existing.sources.includes('mapped')) {
                                                    existing.sources.push('mapped');
                                                }
                                            } else {
                                                merged.push({
                                                    id: `mapped_${emp.id}`,
                                                    name: emp.name,
                                                    job_title: emp.role || emp.title || 'Cargo não informado',
                                                    email: emp.email ? [{ value: emp.email, primary: true }] : undefined,
                                                    phone: emp.phone ? [{ value: emp.phone, primary: true }] : undefined,
                                                    sources: ['mapped'],
                                                    linkedin: emp.linkedin,
                                                    profile_pic: emp.profile_pic || emp.avatar,
                                                    emp_id: emp.id
                                                });
                                            }
                                        }
                                        return merged;
                                    })()}
                                    onEditPerson={onEditEmployee}
                                    onSaveToPipedrive={onSaveToPipedrive}
                                    onUpdateInPipedrive={onUpdateInPipedrive}
                                    onDeleteFromPipedrive={onDeleteFromPipedrive}
                                    onEmailDiscovered={onEmailDiscovered}
                                    onBatchValidateEmails={handleBatchValidateEmails}
                                    isBatchValidating={isBatchValidating}
                                />
                            )}

                            {activeTab === 'deals' && (
                                <div className={styles.dealList}>
                                    {orgDetails[expandedOrgId].deals.length === 0 && <div className={styles.emptyState}>Sem negócios.</div>}
                                    {(() => {
                                        const seen = new Set();
                                        return (orgDetails[expandedOrgId].deals || [])
                                            .filter((d: any) => {
                                                if (!d.id || seen.has(d.id)) return false;
                                                seen.add(d.id);
                                                return true;
                                            })
                                            .map((d: any) => (
                                                <div key={d.id} className={styles.dealItem}>
                                                    <div className={styles.dealTitle}>{d.title}</div>
                                                    <div className={styles.dealOwner} title="Responsável pelo negócio">
                                                        <Users size={10} style={{ marginRight: '4px', opacity: 0.5 }} />
                                                        {d.user_id?.name || d.owner_name || 'Sem responsável'}
                                                    </div>
                                                    <div className={styles.dealMeta}>
                                                        <span className={styles.dealValue}>
                                                            <DollarSign size={10} /> {d.formatted_value || 'R$ 0'}
                                                        </span>
                                                        <span className={`${styles.dealStatus} ${styles[d.status]}`}>
                                                            {d.status === 'open' ? 'Aberto' : d.status === 'won' ? 'Ganho' : 'Perdido'}
                                                        </span>
                                                    </div>
                                                </div>
                                            ));
                                    })()}
                                </div>
                            )}


                        </div>
                    </div>
                ) : null}
            </div>
        </div>
    );
};
