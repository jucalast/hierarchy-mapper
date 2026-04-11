import dagre from 'dagre';
import { Node, Edge, Position, MarkerType } from 'reactflow';

export const calculateEdges = (nodes: Node[], backendEdges: any[]): Edge[] => {
  const finalEdges: Edge[] = [];
  const processedTargets = new Set<string>();

  // 1. Prioridade: Conexões explícitas do Backend (Manager IDs)
  if (backendEdges && backendEdges.length > 0) {
    backendEdges.forEach((e, index) => {
      finalEdges.push({
        id: `e-${e.source}-${e.target}-${index}`,
        source: e.source,
        target: e.target,
        animated: false,
        style: { stroke: '#6e7681', strokeWidth: 1.5 },
      });
      processedTargets.add(e.target);
    });
  }

  // 2. Fallback: Conexões Implícitas para quem está órfão
  const rootEntity = nodes.find(n => n.data.level === 0);

  nodes.forEach(child => {
    // Se o nó já tem pai ou é a raiz, não precisa de conexão implícita
    if (processedTargets.has(child.id) || child.data.level === 0) return;

    const childLevel = child.data.level || 1;

    // Tenta encontrar o melhor pai (nível maior que o dele)
    const potentialParents = nodes
      .filter(p => (p.data.level || 0) > childLevel)
      .sort((a, b) => (a.data.level || 0) - (b.data.level || 0));

    let bestParent = null;

    // A. Prioridade: Mesmo Departamento + Nível mais próximo
    bestParent = potentialParents.find(p => p.data.department === child.data.department);

    // B. Fallback: Qualquer autoridade disponível acima dele
    if (!bestParent && potentialParents.length > 0) {
      bestParent = potentialParents[0];
    }

    // B2. Se o nó é Nível 6 (Sócio/C-Level), ele deve reportar à Empresa Raiz se estiver sozinho no topo
    if (childLevel === 6 && !bestParent) {
        bestParent = rootEntity;
    }

    // C. Fallback de Segurança Máxima: Conecta na Empresa (Root 0)
    if (!bestParent && rootEntity && child.id !== rootEntity.id) {
       bestParent = rootEntity;
    }

    if (bestParent) {
      finalEdges.push({
        id: `e-impl-${bestParent.id}-${child.id}`,
        source: bestParent.id,
        target: child.id,
        animated: false,
        style: { stroke: '#8b949e', strokeWidth: 1.5 },
      });
      processedTargets.add(child.id);
    }
  });

  return finalEdges;
};

export const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 440; // Synchronized with CSS width
  const nodeHeight = 450; // Increased to accommodate Bio + Metadata

  // ranksep 250: Increased separation between levels
  // nodesep 180: Clearer horizontal distance between departments
  dagreGraph.setGraph({ rankdir: direction, ranksep: 250, nodesep: 180 });

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
  const verticalMargin = 180; // Gap between card tiers

  const defaultCardHeight = 450; 
  
  uniqueLevels.forEach((lvl, idx) => {
    // Ensuring the root level (company) also has enough space for its title/logo
    // and matches the visual rhythm of the hierarchy
    rankHeights[idx] = defaultCardHeight;
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