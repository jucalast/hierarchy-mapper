import React, { memo } from 'react';
import ReactFlow, { Controls, ControlButton } from 'reactflow';
import 'reactflow/dist/style.css';
import { SupplyChainNode } from './nodes/SupplyChainNode';
import { Bug, Workflow, Loader2 } from 'lucide-react';
import styles from './styles/Graph.module.css';

const nodeTypes = {
    supplyChain: SupplyChainNode
};

const edgeTypes = {};

interface GraphCanvasProps {
    nodes: any[];
    edges: any[];
    onNodesChange: any;
    onEdgesChange: any;
    onConnect: any;
    fitViewHandler: React.ReactNode;
    smartBackground: React.ReactNode;
    onCopyData?: () => void;
    onRefine?: () => void;
    refining?: boolean;
}

export const GraphCanvas = memo(({
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    fitViewHandler,
    smartBackground,
    onCopyData,
    onRefine,
    refining
}: GraphCanvasProps) => {
    return (
        <div style={{ width: '100%', height: '100%', position: 'relative' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                minZoom={0.05}
                maxZoom={2}
                fitViewOptions={{ padding: 0.45 }}
                deleteKeyCode={['Backspace', 'Delete']}
                multiSelectionKeyCode="Control"
                selectionKeyCode="Shift"
            >
                {smartBackground}
                <Controls 
                    showInteractive={false} 
                    className="custom-flow-controls"
                >
                    {onRefine && (
                        <ControlButton
                            onClick={onRefine}
                            disabled={refining}
                            className={refining ? styles.aiAnalyzing : undefined}
                            title="Analista de IA"
                        >
                            {refining ? <Loader2 size={14} className={styles.loadingAnim} /> : <Workflow size={14} />}
                        </ControlButton>
                    )}
                    {onCopyData && (
                        <ControlButton onClick={onCopyData} title="Copiar Dados (Debug)">
                            <Bug size={14} />
                        </ControlButton>
                    )}
                </Controls>
                {fitViewHandler}
            </ReactFlow>
        </div>
    );
});

GraphCanvas.displayName = 'GraphCanvas';
