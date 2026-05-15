import React from 'react';
import { Database, Save, RefreshCw } from 'lucide-react';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'pipedriveToken' | 'setPipedriveToken'
    | 'pipedriveUserId' | 'setPipedriveUserId'
    | 'whatsappServiceUrl' | 'setWhatsappServiceUrl'
    | 'emailUser' | 'setEmailUser'
    | 'emailPassword' | 'setEmailPassword'
    | 'emailPort' | 'setEmailPort'
    | 'saving' | 'handleSaveIntegrations'
>;

export const IntegrationsTab: React.FC<Props> = ({
    pipedriveToken, setPipedriveToken,
    pipedriveUserId, setPipedriveUserId,
    whatsappServiceUrl, setWhatsappServiceUrl,
    emailUser, setEmailUser,
    emailPassword, setEmailPassword,
    emailPort, setEmailPort,
    saving, handleSaveIntegrations,
}) => (
    <div className={styles.card}>
        <h2 className={styles.cardTitle}>
            <span className={styles.cardTitleText}>
                <Database size={18} /> Chaves de Conexão & Integrações SaaS
            </span>
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
            {/* Pipedrive */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <img src="/pipedrive.png" alt="Pipedrive" style={{ width: '20px', height: '20px', objectFit: 'contain', borderRadius: '4px' }} />
                    <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#38bdf8' }}>Integração CRM Pipedrive</h3>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Pipedrive API Token</label>
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                            Chave secreta usada para criar contatos e atualizar negócios direto no seu funil do Pipedrive CRM.
                        </span>
                        <input type="password" className={styles.select} value={pipedriveToken} onChange={(e) => setPipedriveToken(e.target.value)} placeholder="Insira o Token de API do seu Pipedrive..." />
                    </div>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Pipedrive Default User ID</label>
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                            ID numérico do proprietário no Pipedrive que será o responsável pelos contatos criados no CRM.
                        </span>
                        <input type="text" className={styles.select} value={pipedriveUserId} onChange={(e) => setPipedriveUserId(e.target.value)} placeholder="Ex: 24921888" />
                    </div>
                </div>
            </div>

            {/* WhatsApp */}
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <img src="/wppicon.png" alt="WhatsApp" style={{ width: '20px', height: '20px', objectFit: 'contain', borderRadius: '4px' }} />
                    <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#22c55e' }}>Integração WhatsApp Service</h3>
                </div>
                <div className={styles.formGroup}>
                    <label className={styles.label}>WhatsApp Service URL (API)</label>
                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                        URL de conexão do robô de WhatsApp responsável por disparar as abordagens e prospecções em lote.
                    </span>
                    <input type="text" className={styles.select} value={whatsappServiceUrl} onChange={(e) => setWhatsappServiceUrl(e.target.value)} placeholder="Ex: http://localhost:8001/api/v1/whatsapp" />
                </div>
            </div>

            {/* Outlook */}
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <img src="/outlook.png" alt="Outlook" style={{ width: '20px', height: '20px', objectFit: 'contain', borderRadius: '4px' }} />
                    <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f59e0b' }}>Conexão Email SMTP & IMAP (Outlook)</h3>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px' }}>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>E-mail de Envio (User)</label>
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                            Sua conta do Outlook. No Windows, o sistema se conecta diretamente ao seu aplicativo Outlook Desktop para enviar e ler e-mails.
                        </span>
                        <input type="email" className={styles.select} value={emailUser} onChange={(e) => setEmailUser(e.target.value)} placeholder="seu-usuario@outlook.com" />
                    </div>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Senha do E-mail</label>
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                            Senha normal ou Senha de Aplicativo para servidores SMTP de fallback.
                        </span>
                        <input type="password" className={styles.select} value={emailPassword} onChange={(e) => setEmailPassword(e.target.value)} placeholder="••••••••••••" />
                    </div>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Porta SMTP</label>
                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                            Porta segura do servidor SMTP (Office 365). O padrão TLS recomendado é 587.
                        </span>
                        <input type="text" className={styles.select} value={emailPort} onChange={(e) => setEmailPort(e.target.value)} placeholder="Ex: 587" />
                    </div>
                </div>
            </div>
        </div>

        <button className={styles.saveBtn} onClick={handleSaveIntegrations} disabled={saving} style={{ marginTop: '24px' }}>
            {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
            {saving ? "Salvando..." : "Salvar Chaves & Conexões"}
        </button>
    </div>
);
