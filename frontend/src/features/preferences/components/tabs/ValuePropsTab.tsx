import React from 'react';
import { Flame, Save, RefreshCw } from 'lucide-react';
import { StringListEditor } from '../shared/StringListEditor';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'painPoints' | 'setPainPoints'
    | 'valueProps' | 'setValueProps'
    | 'saving' | 'handleSaveValueProps'
>;

const VALUE_PROP_FIELDS = [
    {
        key: 'plano_b',
        label: 'Abordagem 1: Plano B / Mitigação de Risco',
        description: 'Texto focado em posicionar sua empresa como fornecedora alternativa ou reserva estratégica (Plano B) para garantir a segurança da operação do lead.',
        placeholder: 'Argumento de vendas focando em servir como alternativa confiável...',
    },
    {
        key: 'kanban_stock',
        label: 'Abordagem 2: Modelo Kanban / Estoque em Fábrica',
        description: 'Mensagem destacando soluções de entregas programadas sob demanda (Kanban) e estoque de segurança dedicado para evitar rupturas de fábrica.',
        placeholder: 'Argumento sobre modelo Kanban e segurança just-in-time...',
    },
    {
        key: 'custom_manufacturing',
        label: 'Abordagem 3: Embalagens Manuais / Alta Customização',
        description: 'Mensagem direcionada para soluções sob medida, embalagens complexas ou pequenos lotes altamente customizados que grandes fornecedores não atendem.',
        placeholder: 'Argumento sobre customização e o que concorrentes grandes não fazem...',
    },
    {
        key: 'ckd_export',
        label: 'Abordagem 4: Especialistas em CKD / Exportação',
        description: 'Texto voltado especificamente para indústrias exportadoras ou que utilizam sistemas de CKD exigindo alta resistência estrutural.',
        placeholder: 'Argumento para indústrias exportadoras que usam embalagens CKD...',
    },
    {
        key: 'just_in_time',
        label: 'Abordagem 5: Just-In-Time / Agilidade Extrema',
        description: 'Discurso ressaltando flexibilidade operacional, velocidade de resposta rápida, lead times curtos e entregas ágeis no modelo Just-In-Time.',
        placeholder: 'Argumento sobre agilidade, lead time curto e entrega garantida...',
    },
];

export const ValuePropsTab: React.FC<Props> = ({
    painPoints, setPainPoints,
    valueProps, setValueProps,
    saving, handleSaveValueProps,
}) => (
    <div className={styles.card}>
        <h2 className={styles.cardTitle}>
            <span className={styles.cardTitleText}>
                <Flame size={18} /> Argumentos de Venda, Dores e Propostas de Valor
            </span>
        </h2>

        <StringListEditor
            list={painPoints}
            onChange={setPainPoints}
            label="Dores Críticas que Resolvemos (Dores do Lead)"
            placeholder="Ex: Fornecedor atual atrasa ou tem rupturas de estoque frequentes"
            description="Lista de problemas que os clientes costumam vivenciar. O robô usará esses tópicos de forma consultiva para criar ganchos de dor hiper-relevantes nas abordagens."
        />

        <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <span className={styles.label} style={{ fontSize: '12px' }}>Textos de Propostas de Valor (Ângulos de Abordagem)</span>
            {VALUE_PROP_FIELDS.map(({ key, label, description, placeholder }) => (
                <div key={key} className={styles.formGroup}>
                    <label className={styles.label} style={{ fontSize: '10px' }}>{label}</label>
                    <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginTop: '-4px', marginBottom: '2px', lineHeight: '1.4' }}>
                        {description}
                    </span>
                    <textarea
                        className={styles.select}
                        rows={3}
                        value={valueProps[key] || ''}
                        onChange={(e) => setValueProps({ ...valueProps, [key]: e.target.value })}
                        placeholder={placeholder}
                        style={{ fontFamily: 'inherit', resize: 'vertical' }}
                    />
                </div>
            ))}
        </div>

        <button className={styles.saveBtn} onClick={handleSaveValueProps} disabled={saving} style={{ marginTop: '12px' }}>
            {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
            {saving ? "Salvando..." : "Salvar Dores e Propostas"}
        </button>
    </div>
);
