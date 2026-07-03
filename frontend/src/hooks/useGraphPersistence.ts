import { useCallback, useRef } from 'react';
import { Node, Edge } from 'reactflow';

/**
 * Deriva a chave canônica de cache do grafo (posições + arestas manuais).
 *
 * REGRA CRÍTICA: esta é a ÚNICA fonte de verdade da chave. Tanto o caminho de
 * leitura (useNetworkFlow) quanto o de escrita (saveGraphState) DEVEM usá-la,
 * senão as posições são salvas numa chave e lidas de outra — que era a causa de
 * o layout manual "não voltar" após arrastar nós / recarregar.
 *
 * Prioriza o orgId (numérico, estável e alinhado com o restante do app:
 * chatStore, Drawer, limpeza de cache). Só cai para o nome da marca quando ainda
 * não há org integrada (empresa nova antes do confirmIntelligence).
 */
export function getGraphCacheId(
    currentOrgId?: number | null,
    confirmedBrand?: string | null,
): string {
    if (currentOrgId) return String(currentOrgId);
    if (confirmedBrand && confirmedBrand.trim()) return confirmedBrand.trim();
    return 'default';
}

/**
 * Identidade estável de um nó para fins de cache de posição/aresta.
 *
 * Precisa sobreviver à migração de id provisório → id do banco que o
 * connectionManager faz durante o mapeamento (partner_x / node_x → id numérico).
 * Por isso prioriza o LinkedIn (imutável) e depois o nome; o id cru é o último
 * recurso, justamente porque ele é o que muda.
 */
export function getStableNodeId(n: any): string {
    const d = n?.data ?? n;
    return (
        d?.linkedin ||
        d?.linkedin_url ||
        d?.name ||
        n?.id ||
        d?.id ||
        ''
    ).toString();
}

/**
 * Remove APENAS o cache de layout (posições) e arestas manuais de UMA empresa.
 *
 * Usado após o refino de IA, que reordena a hierarquia e portanto invalida as posições
 * daquela empresa. É crítico ser escopado: a versão antiga varria todo o localStorage e
 * apagava o layout manual de TODAS as empresas a cada mapeamento.
 */
export function clearGraphCache(...cacheIds: Array<string | number | null | undefined>): void {
    for (const raw of cacheIds) {
        if (raw === null || raw === undefined || String(raw).trim() === '') continue;
        const id = String(raw).trim();
        try {
            localStorage.removeItem(`layout-cache-${id}`);
            localStorage.removeItem(`edges-cache-${id}`);
        } catch { /* ignore */ }
    }
}

export function useGraphPersistence() {
    const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    // Mantido por retrocompatibilidade: deriva a chave a partir do último org visto.
    // Preferir SEMPRE passar o cacheId explícito para saveGraphState.
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

    const getStableId = useCallback((n: any) => getStableNodeId(n), []);

    const saveGraphState = useCallback((nodes: Node[], edges: Edge[], cacheId?: string) => {
        // Debounce para não salvar a cada pixel de movimento
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);

        saveTimeoutRef.current = setTimeout(() => {
            // Usa o cacheId canônico passado pelo componente; só cai no fallback legado
            // (last-viewed-org) se nenhum for fornecido, para não regredir chamadores antigos.
            const resolvedCacheId = cacheId || getCacheId();

            // 1. Salvar Posições
            const positionsCacheKey = `layout-cache-${resolvedCacheId}`;
            let cachedPositions: Record<string, { x: number, y: number }> = {};
            try {
                const cached = localStorage.getItem(positionsCacheKey);
                if (cached) cachedPositions = JSON.parse(cached);
            } catch (e) {}

            nodes.forEach(node => {
                cachedPositions[getStableNodeId(node)] = { x: node.position.x, y: node.position.y };
            });
            localStorage.setItem(positionsCacheKey, JSON.stringify(cachedPositions));

            // 2. Salvar Edges (Conexões customizadas)
            const edgesCacheKey = `edges-cache-${resolvedCacheId}`;
            const customEdges: Record<string, string> = {};

            nodes.forEach(node => {
                const incomingEdge = edges.find(e => e.target === node.id);
                if (incomingEdge) {
                    const parentNode = nodes.find(n => n.id === incomingEdge.source);
                    customEdges[getStableNodeId(node)] = parentNode ? getStableNodeId(parentNode) : incomingEdge.source;
                } else {
                    customEdges[getStableNodeId(node)] = "NONE";
                }
            });
            localStorage.setItem(edgesCacheKey, JSON.stringify(customEdges));

            console.log(`[Persistence] Saved state for ${resolvedCacheId}`);
        }, 200);
    }, [getCacheId]);

    return {
        saveGraphState,
        getCacheId,
        getStableId
    };
}
