import { useState, useCallback, useEffect } from 'react';
import {
    Node,
    Edge,
    NodeChange,
    EdgeChange,
    Connection,
    applyNodeChanges,
    applyEdgeChanges,
    addEdge,
} from 'reactflow';
import { getLayoutedElements, calculateEdges } from '@/utils/layout';

interface UseNetworkFlowProps {
    rawEmployees: any[];
    rawBackendEdges: any[];
    currentOrgId: number | null;
    confirmedBrand: string;
    confirmedLogo: string;
    getStableId: (n: any) => string;
    deleteEmployee?: (id: string) => void;
    editEmployee?: (id: string) => void;
}

export function useNetworkFlow({
    rawEmployees,
    rawBackendEdges,
    currentOrgId,
    confirmedBrand,
    confirmedLogo,
    getStableId,
    deleteEmployee,
    editEmployee,
}: UseNetworkFlowProps) {
    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);
    const [shouldFitView, setShouldFitView] = useState(false);

    // 🔄 Transformação de dados e cálculo de Layout
    useEffect(() => {
        if (rawEmployees.length === 0) {
            setNodes([]);
            setEdges([]);
            return;
        }

        // 🕵️ Filtrar 'Análise Humana' e 'Reprovados' do grafo principal com segurança (impede crash se emp ou emp.id for undefined/null)
        const visibleEmployees = rawEmployees.filter(emp => 
            emp && 
            emp.id &&
            (!emp.role || !emp.role.toLowerCase().includes('humana')) && 
            emp.role !== "Reprovado" && 
            emp.department !== "Reprovado"
        );

        // 1. Criar nós base
        const uiNodes: Node[] = visibleEmployees.map((emp) => {
            const isRootNode = emp.id === 'root_company' || emp.level === 0;
            return {
                id: emp.id.toString(),
                type: 'supplyChain',
                data: {
                    ...emp,
                    isRoot: isRootNode,
                    confirmedLogo: confirmedLogo,
                    onDelete: deleteEmployee,
                    onEdit: editEmployee,
                },
                position: { x: 0, y: 0 }, // Dagre vai calcular
            };
        });

        // 2. Criar arestas base (backend) usando calculateEdges util para manter paridade
        let finalEdges = calculateEdges(uiNodes, rawBackendEdges);

        // 3. Aplicar Cache de Edges (Conexões customizadas)
        const cacheId = currentOrgId || confirmedBrand || "default";
        const edgesCacheKey = `edges-cache-${cacheId}`;
        let cachedEdges: Record<string, string> | null = null;
        try {
            const cacheRaw = localStorage.getItem(edgesCacheKey);
            if (cacheRaw) cachedEdges = JSON.parse(cacheRaw);
        } catch (e) { }

        if (cachedEdges) {
            finalEdges = finalEdges.filter(e => {
                const childNode = uiNodes.find(n => n.id === e.target);
                const childStableId = childNode ? getStableId(childNode) : e.target;
                return !(childStableId in cachedEdges!);
            });

            Object.entries(cachedEdges).forEach(([childStableId, parentStableId]) => {
                if (parentStableId !== "NONE") {
                    const childNode = uiNodes.find(n => getStableId(n) === childStableId);
                    const parentNode = uiNodes.find(n => getStableId(n) === parentStableId);

                    if (childNode && parentNode) {
                        finalEdges.push({
                            id: `e-${parentNode.id}-${childNode.id}`,
                            source: parentNode.id,
                            target: childNode.id,
                            animated: false,
                            style: { stroke: 'var(--sw-graph-purple-edge)', strokeWidth: 1.5 },
                        });
                    }
                }
            });
        }

        // 4. Aplicar Cache de Posições e Layout Dagre
        const layoutCacheKey = `layout-cache-${cacheId}`;
        let cachedPositions: Record<string, { x: number, y: number }> = {};
        try {
            const cacheRaw = localStorage.getItem(layoutCacheKey);
            if (cacheRaw) cachedPositions = JSON.parse(cacheRaw);
        } catch (e) { }

        const nodesSemCache = uiNodes.filter(n => !cachedPositions[getStableId(n)]);
        
        let finalNodes: Node[] = [];
        if (nodesSemCache.length > 0) {
            const { layoutedNodes, layoutedEdges } = getLayoutedElements(uiNodes, finalEdges);
            finalNodes = layoutedNodes.map(node => {
                const stableId = getStableId(node);
                if (cachedPositions[stableId]) {
                    return { ...node, position: cachedPositions[stableId] };
                }
                return node;
            });
            setEdges(layoutedEdges);
        } else {
            finalNodes = uiNodes.map(n => ({ ...n, position: cachedPositions[getStableId(n)] }));
            setEdges(finalEdges);
        }

        setNodes(finalNodes);
    }, [rawEmployees, rawBackendEdges, currentOrgId, confirmedBrand, confirmedLogo, getStableId]);

    const onNodesChange = useCallback(
        (changes: NodeChange[]) => {
            setNodes((nds) => applyNodeChanges(changes, nds));
        },
        []
    );

    const onEdgesChange = useCallback(
        (changes: EdgeChange[]) => {
            setEdges((eds) => applyEdgeChanges(changes, eds));
        },
        []
    );

    const onConnect = useCallback(
        (params: Connection) => {
            setEdges((eds) => {
                const filteredEdges = eds.filter((e) => e.target !== params.target);
                return addEdge(
                    { ...params, animated: false, style: { stroke: 'var(--sw-graph-purple-edge)', strokeWidth: 1.5 } },
                    filteredEdges
                );
            });
        },
        []
    );

    return {
        nodes,
        setNodes,
        edges,
        setEdges,
        onNodesChange,
        onEdgesChange,
        onConnect,
        shouldFitView,
        setShouldFitView,
    };
}
