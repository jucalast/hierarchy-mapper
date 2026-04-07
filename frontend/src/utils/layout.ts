import dagre from 'dagre';
import { Node, Edge, Position, MarkerType } from 'reactflow';

export const calculateEdges = (nodes: Node[], backendEdges: any[]): Edge[] => {
  if (backendEdges && backendEdges.length > 0) {
    return backendEdges.map((e, index) => ({
      id: `e-${e.source}-${e.target}-${index}`,
      source: e.source,
      target: e.target,
      animated: true,
      style: { stroke: '#6e7681', strokeWidth: 1.5 },
    }));
  }

  const implicitEdges: Edge[] = [];
  const rootEntity = nodes.find(n => n.data.level === 0);

  nodes.forEach(child => {
    const childLevel = child.data.level || 1;
    if (childLevel === 0) return; // A própria empresa não tem pai

    // Tenta encontrar o melhor pai (nível maior que o dele, ex: 1 busca 2,3,4,5,6)
    // Exceto o root (level 0) que é sempre uma opção de fallback
    const potentialParents = nodes
      .filter(p => (p.data.level || 0) > childLevel)
      .sort((a, b) => (a.data.level || 0) - (b.data.level || 0));

    let bestParent = null;

    // 1. Prioridade: Mesmo Departamento + Nível mais próximo
    bestParent = potentialParents.find(p => p.data.department === child.data.department);

    // 2. Fallback: Qualquer autoridade disponível acima dele
    if (!bestParent && potentialParents.length > 0) {
      bestParent = potentialParents[0];
    }

    // 3. Fallback de Segurança Máxima: Conecta na Empresa (Root 0) para evitar colisão/empilhamento
    if (!bestParent && rootEntity && child.id !== rootEntity.id) {
       bestParent = rootEntity;
    }

    if (bestParent) {
      implicitEdges.push({
        id: `e-${bestParent.id}-${child.id}`,
        source: bestParent.id,
        target: child.id,
        animated: true,
        style: { stroke: '#8b949e', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#8b949e' },
      });
    }
  });

  return implicitEdges;
};

export const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 320; // Aumentado para garantir zona de exclusão
  const nodeHeight = 220; 

  // nodesep: 150 garante que os cards tenham respiro lateral mesmo com muitos itens no mesmo nível
  dagreGraph.setGraph({ rankdir: direction, ranksep: 200, nodesep: 150 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  // ... (resto da lógica de ranks permanece igual)

  // 1. Identificar quais níveis (Tiers) realmente existem na tela
  const uniqueLevels = Array.from(new Set(nodes.map(n => n.data.level || 0)));
  
  // 2. Ordenar para que a Empresa (0) seja topo, seguido por 6, 5, 4, 3, 2, 1
  uniqueLevels.sort((a, b) => {
    if (a === 0) return -1;
    if (b === 0) return 1;
    return b - a; // 6, 5, 4...
  });

  // 3. Criar o mapa de Ranks (Mapeia Level -> Sequência Vertical)
  const levelToRank: { [key: number]: number } = {};
  uniqueLevels.forEach((lvl, idx) => {
    levelToRank[lvl] = idx;
  });

  // 4. Calcular a Altura Máxima por Nível e Posicionamento Acumulado
  const rankHeights: { [key: number]: number } = {};
  const verticalMargin = 160; 

  const defaultCardHeight = 220; 
  
  uniqueLevels.forEach((lvl, idx) => {
    rankHeights[idx] = lvl === 0 ? 100 : defaultCardHeight;
  });

  // 5. Calcular o Y acumulado
  const rankToY: { [key: number]: number } = {};
  let currentY = 0;
  uniqueLevels.forEach((lvl, idx) => {
    rankToY[idx] = currentY;
    currentY += rankHeights[idx] + verticalMargin;
  });

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const nodeLevel = node.data.level || 0;
    const rank = levelToRank[nodeLevel] !== undefined ? levelToRank[nodeLevel] : 0;

    const newNode = {
      ...node,
      targetPosition: Position.Top,
      sourcePosition: Position.Bottom,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: rankToY[rank],
      },
    };

    return newNode;
  });

  return { layoutedNodes, layoutedEdges: edges };
};