import React, { memo } from 'react';
import styles from './DrawerStageTabs.module.css';

interface Stage {
    name: string;
    count: number;
}

interface DrawerStageTabsProps {
    stages: Stage[];
    activeStage: string | null;
    onSelect: (stage: string | null) => void;
    totalCount: number;
}

function DrawerStageTabsBase({
    stages,
    activeStage,
    onSelect,
    totalCount,
}: DrawerStageTabsProps) {
    if (stages.length === 0) return null;

    return (
        <div className={styles.tabsWrapper}>
            <div className={styles.tabsScroll}>
                {/* Aba "Todos" */}
                <button
                    id="drawer-stage-tab-all"
                    className={`${styles.tab} ${activeStage === null ? styles.tabActive : ''}`}
                    onClick={() => onSelect(null)}
                    title="Ver todas as empresas"
                >
                    Todos
                    <span className={styles.count}>{totalCount}</span>
                </button>

                {stages.map((stage) => (
                    <button
                        key={stage.name}
                        id={`drawer-stage-tab-${stage.name.toLowerCase().replace(/\s+/g, '-')}`}
                        className={`${styles.tab} ${activeStage === stage.name ? styles.tabActive : ''}`}
                        onClick={() => onSelect(stage.name)}
                        title={`Filtrar por: ${stage.name}`}
                    >
                        {stage.name}
                        <span className={styles.count}>{stage.count}</span>
                    </button>
                ))}
            </div>
        </div>
    );
}

export const DrawerStageTabs = memo(DrawerStageTabsBase);
