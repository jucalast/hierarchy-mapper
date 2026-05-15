import React from 'react';
import { Target, Save, RefreshCw } from 'lucide-react';
import { StringListEditor } from '../shared/StringListEditor';
import type { UsePreferencesReturn } from '../../hooks/usePreferences';
import styles from '../../styles/PreferencesView.module.css';

type Props = Pick<UsePreferencesReturn,
    | 'icpSegments' | 'setIcpSegments'
    | 'targetIndustries' | 'setTargetIndustries'
    | 'companyProfiles' | 'setCompanyProfiles'
    | 'decisionMakers' | 'setDecisionMakers'
    | 'disqualifiers' | 'setDisqualifiers'
    | 'highFitKeywords' | 'setHighFitKeywords'
    | 'mediumFitKeywords' | 'setMediumFitKeywords'
    | 'lowFitKeywords' | 'setLowFitKeywords'
    | 'saving' | 'handleSaveICP'
>;

export const ICPTab: React.FC<Props> = ({
    icpSegments, setIcpSegments,
    targetIndustries, setTargetIndustries,
    companyProfiles, setCompanyProfiles,
    decisionMakers, setDecisionMakers,
    disqualifiers, setDisqualifiers,
    highFitKeywords, setHighFitKeywords,
    mediumFitKeywords, setMediumFitKeywords,
    lowFitKeywords, setLowFitKeywords,
    saving, handleSaveICP,
}) => (
    <div className={styles.card}>
        <h2 className={styles.cardTitle}>
            <span className={styles.cardTitleText}>
                <Target size={18} /> Parametrizadores de ICP e Pontuação de Leads (0-100)
            </span>
        </h2>

        <StringListEditor
            list={icpSegments}
            onChange={setIcpSegments}
            label="Segmentos de Mercado Pesquisados (Prospecção Ativa)"
            placeholder="Ex: autopeças"
            description="Termos e nichos principais que orientarão as buscas ativas do crawler no Google Maps e LinkedIn para descobrir novas empresas."
        />

        <StringListEditor
            list={targetIndustries}
            onChange={setTargetIndustries}
            label="Indústrias Alvo (Foco Principal)"
            placeholder="Ex: Autopeças e montadoras"
            description="Indústrias ou setores de atuação prioritários do seu público-alvo (ICP) para as quais a sua proposta se adapta melhor."
        />

        <StringListEditor
            list={companyProfiles}
            onChange={setCompanyProfiles}
            label="Perfil Ideais de Empresa (Mapeamento)"
            placeholder="Ex: Empresas de médio e grande porte (100+ funcionários)"
            description="Características ideais das empresas (ex: faturamento, número de funcionários, plantas industriais) para filtragem cognitiva da IA."
        />

        <StringListEditor
            list={decisionMakers}
            onChange={setDecisionMakers}
            label="Cargos de Decisores Mapeados (Mapeamento)"
            placeholder="Ex: Gerente / Analista de Compras"
            description="Cargos e títulos de tomadores de decisão que o crawler tentará encontrar e mapear."
        />

        <StringListEditor
            list={disqualifiers}
            onChange={setDisqualifiers}
            label="Critérios de Desqualificação Categorizados"
            placeholder="Ex: Empresas de varejo ou food/beverage"
            description="Regras claras e restritivas que desqualificam um lead de forma automática, economizando o tempo de vendas com perfis indesejados."
        />

        <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <span className={styles.label} style={{ fontSize: '12px' }}>Pontuação de Lead (Keywords para Matching de Segmento)</span>

            <StringListEditor
                list={highFitKeywords}
                onChange={setHighFitKeywords}
                label="Keywords de Alto Encaixe (Ganho de +40 pontos no Lead)"
                placeholder="Ex: autopeça"
                description="Termos de altíssimo alinhamento que, se encontrados na descrição da empresa ou CNAE, garantem +40 pontos na qualificação do lead."
            />

            <StringListEditor
                list={mediumFitKeywords}
                onChange={setMediumFitKeywords}
                label="Keywords de Encaixe Médio (Ganho de +20 pontos no Lead)"
                placeholder="Ex: plástico"
                description="Termos relevantes que somam +20 pontos na nota de qualificação de ICP se encontrados no perfil ou segmento da empresa."
            />

            <StringListEditor
                list={lowFitKeywords}
                onChange={setLowFitKeywords}
                label="Keywords Rejeitadas / Baixo Encaixe (Perda de -20 pontos no Lead)"
                placeholder="Ex: varejo"
                description="Palavras-chave de baixo alinhamento ou setores indesejados que reduzem a pontuação do lead em -20 pontos para evitar falso-positivos."
            />
        </div>

        <button className={styles.saveBtn} onClick={handleSaveICP} disabled={saving} style={{ marginTop: '12px' }}>
            {saving ? <RefreshCw size={16} className={styles.spin} /> : <Save size={16} />}
            {saving ? "Salvando..." : "Salvar Configurações de ICP"}
        </button>
    </div>
);
