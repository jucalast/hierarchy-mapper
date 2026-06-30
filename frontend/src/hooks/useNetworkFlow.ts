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
    isScanning?: boolean;
    discovering?: boolean;
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
    isScanning = false,
    discovering = false,
}: UseNetworkFlowProps) {
    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);
    const [shouldFitView, setShouldFitView] = useState(false);

    // 🔄 Transformação de dados e cálculo de Layout
    useEffect(() => {
        console.log(`[useNetworkFlow] 🛠️ Calculando layout para ${rawEmployees.length} funcionários. isScanning: ${isScanning}, discovering: ${discovering}`);
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
            // Apenas o nó com id literal 'root_company' é raiz — usar level===0 como
            // critério adicional causava que funcionários sem level (defaulting to 0)
            // fossem posicionados na mesma fileira do nó raiz e tratados como isRoot.
            const isRootNode = emp.id === 'root_company';
            return {
                id: emp.id.toString(),
                type: 'supplyChain',
                data: {
                    ...emp,
                    isRoot: isRootNode,
                    confirmedLogo: confirmedLogo,
                    onDelete: deleteEmployee,
                    onEdit: editEmployee,
                    isLoading: isRootNode && (isScanning || discovering),
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
                const cachedParent = cachedEdges![childStableId];
                // Só filtra a aresta do backend se houver um pai customizado válido na cache (diferente de "NONE")
                return !cachedParent || cachedParent === "NONE";
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
                            style: { stroke: 'var(--sw-graph-purple-edge)', strokeWidth: 3.0 },
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

        // 5. Anti-Overlap Global Absoluto (Força Bruta)
        // O usuário foi categórico: NUNCA permitir que cards se sobreponham, mesmo carregando do cache.
        const nodesByLevel: Record<number, Node[]> = {};
        finalNodes.forEach(node => {
            const lvl = node.data.level || 0;
            if (!nodesByLevel[lvl]) nodesByLevel[lvl] = [];
            nodesByLevel[lvl].push(node);
        });

        const NODE_WIDTH = 440;
        const MIN_GAP_X = 80;
        const SPACING_X = NODE_WIDTH + MIN_GAP_X;

        const NODE_HEIGHT = 450;
        const MIN_GAP_Y = 180; // Respiro vertical entre andares
        const SPACING_Y = NODE_HEIGHT + MIN_GAP_Y;

        // A. Prevenir Sobreposição Vertical (Entre Andares)
        // Ordem vertical: 0 (Raiz) no topo, seguido de 6, 5, 4, 3, 2, 1
        const sortedLevels = Object.keys(nodesByLevel).map(Number).sort((a, b) => {
            if (a === 0) return -1;
            if (b === 0) return 1;
            return b - a;
        });

        const levelY: Record<number, number> = {};
        sortedLevels.forEach((lvl, index) => {
            const rowNodes = nodesByLevel[lvl];
            // Tenta manter a posição média atual do andar (respeitando o cache se possível)
            let currentY = rowNodes.reduce((sum, n) => sum + n.position.y, 0) / rowNodes.length;
            
            // Trava de segurança: O andar atual NUNCA pode invadir o espaço do andar de cima
            if (index > 0) {
                const prevLvl = sortedLevels[index - 1];
                // Pega a altura real renderizada dos cards do andar de cima (se o React Flow já calculou), senão usa 700px de fallback gigante
                const maxPrevHeight = Math.max(...nodesByLevel[prevLvl].map(n => n.height || 700));
                const minY = levelY[prevLvl] + maxPrevHeight + 150; // 150px de respiro real obrigatório entre eles
                
                if (currentY < minY) {
                    currentY = minY; // Empurra o andar inteiro para baixo
                }
            }
            levelY[lvl] = currentY;

            // Alinha todos os cards deste andar no Y exato
            rowNodes.forEach(n => n.position.y = currentY);
        });

        // B. Prevenir Sobreposição Horizontal (Mesmo Andar)
        Object.values(nodesByLevel).forEach(rowNodes => {
            if (rowNodes.length <= 1) return;

            // Relaxamento magnético no eixo X
            for (let pass = 0; pass < 200; pass++) {
                let moved = false;
                rowNodes.sort((a, b) => a.position.x - b.position.x);

                for (let i = 0; i < rowNodes.length - 1; i++) {
                    const left = rowNodes[i];
                    const right = rowNodes[i + 1];
                    const overlap = SPACING_X - (right.position.x - left.position.x);
                    
                    if (overlap > 0.5) {
                        left.position.x -= overlap / 2;
                        right.position.x += overlap / 2;
                        moved = true;
                    }
                }
                
                if (!moved) break;
            }
        });

        // 6. Atualiza o State e também sobrescreve o Cache com as novas posições seguras
        finalNodes.forEach(node => {
            cachedPositions[getStableId(node)] = node.position;
        });
        localStorage.setItem(layoutCacheKey, JSON.stringify(cachedPositions));

        setNodes(finalNodes);
        
        // 🚀 OTIMIZAÇÃO: Força fitView se for a primeira vez carregando ou se só houver o root
        if (finalNodes.length === 1 && finalNodes[0].id === 'root_company') {
            setShouldFitView(true);
        }
    }, [rawEmployees, rawBackendEdges, currentOrgId, confirmedBrand, confirmedLogo, getStableId, deleteEmployee, editEmployee, isScanning, discovering]);

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
                    { ...params, animated: false, style: { stroke: 'var(--sw-graph-purple-edge)', strokeWidth: 3.0 } },
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
