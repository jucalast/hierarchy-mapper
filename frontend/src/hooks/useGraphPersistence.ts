import { useCallback, useRef } from 'react';
import { Node, Edge } from 'reactflow';

export function useGraphPersistence() {
    const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const getCacheId = useCallback(() => {
        let cacheId = "default";
        try {
            const raw = localStorage.getItem('last-viewed-org');
            if (raw && raw !== "NaN" && raw !== "undefined") {
                const lObj = JSON.parse(raw);
                if (lObj.id) cacheId = lObj.id.toString();
                else if (lObj.name) cacheId = lObj.name;
            }
        } catch (e) {
            console.error("Error getting cache ID:", e);
        }
        return cacheId;
    }, []);

    const getStableId = useCallback((n: any) => n?.data?.linkedin || n?.data?.name || n?.id, []);

    const saveGraphState = useCallback((nodes: Node[], edges: Edge[]) => {
        // Debounce para não salvar a cada pixel de movimento
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);

        saveTimeoutRef.current = setTimeout(() => {
            const cacheId = getCacheId();
            
            // 1. Salvar Posições
            const positionsCacheKey = `layout-cache-${cacheId}`;
            let cachedPositions: Record<string, { x: number, y: number }> = {};
            try {
                const cached = localStorage.getItem(positionsCacheKey);
                if (cached) cachedPositions = JSON.parse(cached);
            } catch (e) {}

            nodes.forEach(node => {
                cachedPositions[getStableId(node)] = { x: node.position.x, y: node.position.y };
            });
            localStorage.setItem(positionsCacheKey, JSON.stringify(cachedPositions));

            // 2. Salvar Edges (Conexões customizadas)
            const edgesCacheKey = `edges-cache-${cacheId}`;
            const customEdges: Record<string, string> = {};
            
            nodes.forEach(node => {
                const incomingEdge = edges.find(e => e.target === node.id);
                if (incomingEdge) {
                    const parentNode = nodes.find(n => n.id === incomingEdge.source);
                    customEdges[getStableId(node)] = parentNode ? getStableId(parentNode) : incomingEdge.source;
                } else {
                    customEdges[getStableId(node)] = "NONE";
                }
            });
            localStorage.setItem(edgesCacheKey, JSON.stringify(customEdges));

            console.log(`[Persistence] Saved state for ${cacheId}`);
        }, 200);
    }, [getCacheId]);

    return {
        saveGraphState,
        getCacheId,
        getStableId
    };
}
