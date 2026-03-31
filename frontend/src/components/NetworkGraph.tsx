"use client";

import React, { useEffect, useState, useMemo } from 'react';
import ReactFlow, { 
    Background, 
    Controls, 
    MiniMap,
    useNodesState,
    useEdgesState,
    Edge,
    Node,
    MarkerType,
    Position,
    Handle
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import styles from './NetworkGraph.module.css';

interface HierarchyEmployee {
    id: string;
    name: string;
    role: string;
    department: string;
    manager_id?: string | null;
    level: number;
    email?: string;
    linkedin?: string;
}

interface HierarchyResponse {
    company_name: string;
    identifier: string; // CNPJ now
    employees: HierarchyEmployee[];
}

// 1. Criação de um Node Customizado (resolve o aviso de memoização do React Flow)
const SupplyChainNode = ({ data, isConnectable }: any) => {
    const levelClass = styles[`level_${data.level || 5}`];
    
    const getLevelName = (level: number) => {
        if (level === 0) return 'Main Entity';
        if (level === 1) return 'Executive';
        if (level === 2) return 'Management';
        if (level === 3) return 'Tactical';
        if (level === 4) return 'Analytical';
        return 'Operational';
    };

    return (
        <div className={`${styles.customNode} ${levelClass}`}>
            <Handle type="target" position={Position.Top} isConnectable={isConnectable} className={styles.handle} />
            
            <div className={styles.nodeHeader}>
                <span>{getLevelName(data.level)}</span>
                {data.isRoot && <span style={{color: '#2ea043'}}>Target Base</span>}
            </div>

            <div className={styles.nodeBody}>
                <strong>{data.name}</strong>
                <span className={styles.role}>{data.role}</span>
                <div className={styles.nodeDepartment}>{data.department}</div>
            </div>

            <div className={styles.nodeFooter}>
                {data.email && <div className={styles.emailBadge}>{data.email}</div>}
                {data.linkedin && (
                    <a href={data.linkedin} target="_blank" rel="noopener noreferrer" className={styles.linkedinBtn}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
                        </svg>
                        LinkedIn Profile
                    </a>
                )}
            </div>
            
            <Handle type="source" position={Position.Bottom} isConnectable={isConnectable} className={styles.handle} />
        </div>
    );
};

const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'TB') => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    
    // Dimensões estimadas de CSS da carta para cálculos de árvore perfeitos
    const nodeWidth = 300;
    const nodeHeight = 150; 
  
    dagreGraph.setGraph({ rankdir: direction, nodesep: 60, edgesep: 20, ranksep: 120 });
  
    nodes.forEach((node) => {
        dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    });
  
    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });
  
    dagre.layout(dagreGraph);
  
    const layoutedNodes = nodes.map((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        
        // Dagre centraliza a coordenada, ReactFlow usa topo-esquerda
        return {
            ...node,
            position: {
                x: nodeWithPosition.x - nodeWidth / 2,
                y: nodeWithPosition.y - nodeHeight / 2,
            },
        };
    });
  
    return { layoutedNodes, layoutedEdges: edges };
};

// 2. Definido FORA do componente para evitar recriação e Warning #002 do React Flow
const nodeTypes = {
    supplyChain: SupplyChainNode,
};

export default function NetworkGraph({ defaultCnpj = "" }: { defaultCnpj?: string }) {

    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [cnpj, setCnpj] = useState(defaultCnpj);
    const [domainTarget, setDomainTarget] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const fetchHierarchy = (searchCnpj: string, explicitDomain: string = "") => {
        setLoading(true);
        setError("");
        
        const rawCnpj = searchCnpj.replace(/\D/g, "");
        if (!rawCnpj && !explicitDomain) {
            setError("Informe o CNPJ ou o Domínio.");
            setLoading(false);
            return;
        }

        let apiUrl = `http://localhost:8000/api/v1/hierarchy/stream?cnpj=${rawCnpj}`;
        if (explicitDomain.trim()) {
            apiUrl += `&domain=${encodeURIComponent(explicitDomain.trim())}`;
        }

        const sse = new EventSource(apiUrl);
        let accumulatedNodes: Node[] = [];
        let accumulatedEdges: Edge[] = [];

        sse.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'error') {
                setError(data.message);
                sse.close();
                setLoading(false);
                return;
            }
            
            if (data.type === 'done') {
                sse.close();
                setLoading(false);
                return;
            }
            
            if (data.type === 'initial' || data.type === 'batch') {
                const incomingNodes = data.nodes || [];
                
                incomingNodes.forEach((emp: any) => {
                    const isRoot = !emp.manager_id || emp.id === "root_company";
                    
                    accumulatedNodes.push({
                        id: emp.id,
                        type: 'supplyChain',
                        position: { x: 0, y: 0 },
                        data: { 
                            name: emp.name,
                            role: emp.role,
                            department: emp.department,
                            email: emp.email,
                            linkedin: emp.linkedin,
                            isRoot: isRoot,
                            level: emp.level,
                            company: emp.company
                        },
                    });

                    if (emp.manager_id && emp.id !== "root_company") {
                        accumulatedEdges.push({
                            id: `e-${emp.manager_id}-${emp.id}`,
                            source: emp.manager_id,
                            target: emp.id,
                            animated: true,
                            markerEnd: {
                                type: MarkerType.ArrowClosed,
                                color: '#30363d'
                            },
                            style: { stroke: '#30363d', strokeWidth: 2 },
                        });
                    }
                });

                const { layoutedNodes, layoutedEdges } = getLayoutedElements([...accumulatedNodes], [...accumulatedEdges]);
                setNodes(layoutedNodes);
                setEdges(layoutedEdges);
            }
        };

        sse.onerror = () => {
            sse.close();
            setLoading(false);
        };
    };

    useEffect(() => {
        if (defaultCnpj) {
            fetchHierarchy(defaultCnpj);
        }
    }, [defaultCnpj]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        fetchHierarchy(cnpj, domainTarget);
    };

    return (
        <div className={styles.container}>
            <div className={styles.topbar}>
                <h2>B2B Supply Chain Mapper</h2>
                <form onSubmit={handleSearch} className={styles.searchForm}>
                    <input 
                        type="text" 
                        value={cnpj}
                        onChange={(e) => setCnpj(e.target.value)}
                        placeholder="CNPJ..."
                        className={styles.input}
                    />
                    <input 
                        type="text" 
                        value={domainTarget}
                        onChange={(e) => setDomainTarget(e.target.value)}
                        placeholder="Domain (ex: toyota.com.br)"
                        className={styles.input}
                    />
                    <button type="submit" disabled={loading} className={styles.button}>
                        {loading ? 'Scanning...' : 'Build Pipeline'}
                    </button>
                    
                    {error && <span className={styles.error}>{error}</span>}
                </form>
            </div>
            
            <div className={styles.graphWrapper}>
                <div className={styles.legend}>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: 'var(--executive-border)'}}></div>
                        <span>Executive (CPO, Director)</span>
                    </div>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: 'var(--management-border)'}}></div>
                        <span>Management (Managers)</span>
                    </div>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: 'var(--tactical-border)'}}></div>
                        <span>Tactical (Coordinators)</span>
                    </div>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: 'var(--analytical-border)'}}></div>
                        <span>Analytical (Spec/Buyer/Planner)</span>
                    </div>
                    <div className={styles.legendItem}>
                        <div className={styles.legendColor} style={{background: 'var(--operational-border)'}}></div>
                        <span>Operational (Asst/Ops)</span>
                    </div>
                </div>

                <ReactFlow 
                    nodes={nodes} 
                    edges={edges} 
                    nodeTypes={nodeTypes}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    fitView
                    attributionPosition="bottom-right"
                >
                    <Controls />
                    <MiniMap nodeStrokeWidth={3} nodeColor="#0d1117" />
                    <Background gap={20} size={1} color="#30363d" />
                </ReactFlow>
            </div>
        </div>
    );
}
