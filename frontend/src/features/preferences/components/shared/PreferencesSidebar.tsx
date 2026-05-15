import React from 'react';
import { Sparkles, Briefcase, Package, Users, Flame, Target, GitFork, Database } from 'lucide-react';
import type { ActiveTab } from '../../types';
import styles from '../../styles/PreferencesView.module.css';

interface PreferencesSidebarProps {
    activeTab: ActiveTab;
    setActiveTab: (tab: ActiveTab) => void;
}

const NAV_ITEMS: Array<{ tab: ActiveTab; icon: React.ReactNode; label: string }> = [
    { tab: 'llm', icon: <Sparkles size={16} />, label: 'Preferências & Limites LLM' },
    { tab: 'profile', icon: <Briefcase size={16} />, label: 'Perfil Comercial' },
    { tab: 'products', icon: <Package size={16} />, label: 'Catálogo de Produtos' },
    { tab: 'references', icon: <Users size={16} />, label: 'Clientes de Referência' },
    { tab: 'value_props', icon: <Flame size={16} />, label: 'Dores & Propostas de Valor' },
    { tab: 'icp', icon: <Target size={16} />, label: 'Regras de ICP & Qualificação' },
    { tab: 'hierarchy', icon: <GitFork size={16} />, label: 'Regras de Hierarquia' },
    { tab: 'integrations', icon: <Database size={16} />, label: 'Conexões & Integrações' },
];

export const PreferencesSidebar: React.FC<PreferencesSidebarProps> = ({ activeTab, setActiveTab }) => (
    <aside className={styles.settingsSidebar}>
        <div className={styles.sidebarSectionTitle}>Categorias</div>
        <nav className={styles.sidebarMenu}>
            {NAV_ITEMS.map(({ tab, icon, label }) => (
                <div
                    key={tab}
                    className={`${styles.sidebarItem} ${activeTab === tab ? styles.sidebarItemActive : ''}`}
                    onClick={() => setActiveTab(tab)}
                >
                    {icon}
                    <span>{label}</span>
                </div>
            ))}
        </nav>
    </aside>
);
