import React from 'react';
import { GitFork, Save, RefreshCw } from 'lucide-react';
import { StringListEditor } from '../shared/StringListEditor';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'forbiddenKeywords' | 'setForbiddenKeywords'
    | 'purchasingKeywords' | 'setPurchasingKeywords'
    | 'logisticsKeywords' | 'setLogisticsKeywords'
    | 'saving' | 'handleSaveHierarchy'
>;

export const HierarchyTab: React.FC<Props> = ({
    forbiddenKeywords, setForbiddenKeywords,
    purchasingKeywords, setPurchasingKeywords,
    logisticsKeywords, setLogisticsKeywords,
    saving, handleSaveHierarchy,
}) => (
    <div className={styles.card}>
        <h2 className={styles.cardTitle}>
            <span className={styles.cardTitleText}>
                <GitFork size={18} /> Filtros de Contato e Regras de Hierarquia
            </span>
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <span className={styles.label} style={{ fontSize: '12px' }}>Filtros de Veto Categórico (Para evitar cargos incorretos nos departamentos)</span>

            <StringListEditor
                list={forbiddenKeywords.compras || []}
                onChange={(newList) => setForbiddenKeywords({ ...forbiddenKeywords, compras: newList })}
                label="Keywords Proibidas em COMPRAS (Veto imediato)"
                placeholder="Ex: sales, comercial, marketing"
                description="Se o cargo do profissional contiver alguma dessas palavras, o sistema o desqualificará e vetará imediatamente do fluxo de Compras."
            />

            <StringListEditor
                list={forbiddenKeywords.logistica || []}
                onChange={(newList) => setForbiddenKeywords({ ...forbiddenKeywords, logistica: newList })}
                label="Keywords Proibidas em LOGÍSTICA & SUPPLY CHAIN (Veto imediato)"
                placeholder="Ex: financeiro, rh, vendas"
                description="Se o cargo do profissional contiver alguma dessas palavras, ele será descartado instantaneamente do fluxo de Logística."
            />
        </div>

        <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <span className={styles.label} style={{ fontSize: '12px' }}>Termos de Busca Utilizados no Crawler de Contatos</span>

            <StringListEditor
                list={purchasingKeywords}
                onChange={setPurchasingKeywords}
                label="Dicionário de Termos de Compras (Buscas Live LinkedIn)"
                placeholder="Ex: Comprador, Procurement, Buyer"
                description="Cargos e termos positivos que o robô de busca utilizará no LinkedIn para localizar e aprovar os tomadores de decisão em Compras."
            />

            <StringListEditor
                list={logisticsKeywords}
                onChange={setLogisticsKeywords}
                label="Dicionário de Termos de Logística (Buscas Live LinkedIn)"
                placeholder="Ex: Logística, Supply Chain, Almoxarifado"
                description="Cargos e termos positivos utilizados pelo robô para rastrear, encontrar e aprovar profissionais do departamento de Logística."
            />
        </div>

        <button className={styles.saveBtn} onClick={handleSaveHierarchy} disabled={saving} style={{ marginTop: '12px' }}>
            {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
            {saving ? "Salvando..." : "Salvar Regras de Hierarquia"}
        </button>
    </div>
);
