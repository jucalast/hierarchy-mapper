import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import styles from '../../styles/NodeStyles.module.css';
import { PersonaCard } from '@/features/prospecting/components/PersonaCard';

function SupplyChainNodeBase({ data }: { data: any }) {
  const level = data.level !== undefined ? data.level : 5;

  return (
    <div style={{ position: 'relative' }}>
      <Handle
        type="target"
        position={Position.Top}
        className={styles.handle}
        style={{ zIndex: 10, top: '-5px' }}
      />
      <PersonaCard data={data} level={level} isNode={true} />
      <Handle
        type="source"
        position={Position.Bottom}
        className={styles.handle}
        style={{ zIndex: 10, bottom: '-5px' }}
      />
    </div>
  );
}

// React.memo evita re-render quando o objeto `data` referência igual.
// Como o ReactFlow recria nodes, a igualdade rasa ainda fala "diff"; usamos
// comparação custom em campos que realmente influenciam o render.
export const SupplyChainNode = memo(
  SupplyChainNodeBase,
  (prev, next) => {
    const a = prev.data || {};
    const b = next.data || {};
    return (
      a.id === b.id &&
      a.level === b.level &&
      a.name === b.name &&
      a.role === b.role &&
      a.matching_score === b.matching_score &&
      a.profile_pic === b.profile_pic &&
      a.evidence === b.evidence
    );
  },
);

export const nodeTypes = {
  supplyChain: SupplyChainNode,
};
