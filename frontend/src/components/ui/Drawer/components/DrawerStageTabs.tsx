import React, { memo, useEffect, useRef } from 'react';
import styles from './DrawerStageTabs.module.css';

interface Stage {
    name: string;
    count: number;
    order_nr?: number;
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
    const scrollRef = useRef<HTMLDivElement>(null);

    // A ordem das abas nunca muda — apenas o scroll do carrossel se move para deixar
    // a aba selecionada em evidência (primeira visível), tanto avançando quanto voltando.
    useEffect(() => {
        const container = scrollRef.current;
        if (!container) return;

        const targetId = activeStage === null
            ? 'drawer-stage-tab-all'
            : `drawer-stage-tab-${activeStage.toLowerCase().replace(/\s+/g, '-')}`;
        const el = document.getElementById(targetId);
        if (!el || !container.contains(el)) return;

        // scrollIntoView com inline:'center' centraliza o elemento no contêiner em
        // qualquer direção — não há necessidade de calcular o delta manualmente.
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }, [activeStage, stages]);

    if (stages.length === 0) return null;

    return (
        <div className={styles.tabsWrapper}>
            <div className={styles.tabsScroll} ref={scrollRef}>
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
