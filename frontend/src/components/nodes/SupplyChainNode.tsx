import React from 'react';
import { Handle, Position } from 'reactflow';
import styles from '../NetworkGraph.module.css';
import { PersonaCard } from '../PersonaCard';

export function SupplyChainNode({ data }: { data: any }) {
  const level = data.level !== undefined ? data.level : 5;

  return (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Top} className={styles.handle} style={{ zIndex: 10, top: '-5px' }} />
      <PersonaCard data={data} level={level} isNode={true} />
      <Handle type="source" position={Position.Bottom} className={styles.handle} style={{ zIndex: 10, bottom: '-5px' }} />
    </div>
  );
}

export const nodeTypes = {
  supplyChain: SupplyChainNode,
};

