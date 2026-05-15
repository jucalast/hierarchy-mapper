import React from 'react';
import { Briefcase, Save, RefreshCw } from 'lucide-react';
import { StringListEditor } from '../shared/StringListEditor';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'companyName' | 'setCompanyName'
    | 'companySegment' | 'setCompanySegment'
    | 'sellerName' | 'setSellerName'
    | 'sellerRole' | 'setSellerRole'
    | 'companyDifferentials' | 'setCompanyDifferentials'
    | 'saving' | 'handleSaveProfile'
>;

export const ProfileTab: React.FC<Props> = ({
    companyName, setCompanyName,
    companySegment, setCompanySegment,
    sellerName, setSellerName,
    sellerRole, setSellerRole,
    companyDifferentials, setCompanyDifferentials,
    saving, handleSaveProfile,
}) => (
    <div className={styles.card}>
        <h2 className={styles.cardTitle}>
            <span className={styles.cardTitleText}>
                <Briefcase size={18} /> Identidade & Perfil Comercial da Empresa
            </span>
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div className={styles.formGroup}>
                <label className={styles.label}>Nome da Empresa</label>
                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                    O nome oficial ou fantasia que a inteligência artificial mencionará nas mensagens ao falar em nome da sua empresa.
                </span>
                <input type="text" className={styles.select} value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Nome fantasia da sua empresa (Ex: J.Ferres)" />
            </div>
            <div className={styles.formGroup}>
                <label className={styles.label}>Segmento / Atuação</label>
                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                    O nicho específico de mercado que descreve a sua operação para dar contexto ao robô na prospecção.
                </span>
                <input type="text" className={styles.select} value={companySegment} onChange={(e) => setCompanySegment(e.target.value)} placeholder="Setor detalhado (Ex: Embalagens de Papelão Ondulado)" />
            </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div className={styles.formGroup}>
                <label className={styles.label}>Nome do Vendedor Principal</label>
                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                    Nome de quem assinará as mensagens de prospecção fria enviadas por e-mail ou WhatsApp.
                </span>
                <input type="text" className={styles.select} value={sellerName} onChange={(e) => setSellerName(e.target.value)} placeholder="Ex: João Luccas" />
            </div>
            <div className={styles.formGroup}>
                <label className={styles.label}>Cargo do Vendedor</label>
                <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                    Cargo institucional do remetente para assinar os e-mails.
                </span>
                <input type="text" className={styles.select} value={sellerRole} onChange={(e) => setSellerRole(e.target.value)} placeholder="Ex: Representante Comercial" />
            </div>
        </div>

        <StringListEditor
            list={companyDifferentials}
            onChange={setCompanyDifferentials}
            label="Diferenciais Competitivos da Empresa"
            placeholder="Insira um diferencial e aperte Enter"
            description="Destaques exclusivos, prêmios ou diferenciais da sua empresa que a IA lerá para gerar argumentos de autoridade e convencimento."
        />

        <button className={styles.saveBtn} onClick={handleSaveProfile} disabled={saving} style={{ marginTop: '12px' }}>
            {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
            {saving ? "Salvando..." : "Salvar Perfil Comercial"}
        </button>
    </div>
);
