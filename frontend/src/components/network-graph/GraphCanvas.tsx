import React, { memo } from 'react';
import ReactFlow, { Controls } from 'reactflow';
import 'reactflow/dist/style.css';
import { SupplyChainNode } from './nodes/SupplyChainNode';

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
}

export const GraphCanvas = memo(({
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    fitViewHandler,
    smartBackground
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
                fitViewOptions={{ padding: 0.2 }}
                deleteKeyCode={['Backspace', 'Delete']}
                multiSelectionKeyCode="Control"
                selectionKeyCode="Shift"
            >
                {smartBackground}
                <Controls 
                    showInteractive={false} 
                    className="custom-flow-controls"
                />
                {fitViewHandler}
            </ReactFlow>
        </div>
    );
});

GraphCanvas.displayName = 'GraphCanvas';
