import { AgentEvent } from './types';
import { WRITE_TOOLS } from './constants';

/**
 * Classifica o desfecho de uma execução a partir dos eventos coletados:
 * 'error' (falha real e não recuperada de alguma tool, ou evento de erro fatal),
 * 'cancelled' (toda falha presente foi uma confirmação recusada pelo usuário) ou
 * null (sem falhas, ou falhas que o próprio agente conseguiu contornar).
 */
export function classifyFailure(events: AgentEvent[]): 'error' | 'cancelled' | null {
    // Lista vazia = resultado desconhecido (race condition de subscrição Redis ou stream
    // sem eventos). NÃO interpretar como erro — o deal pode ter sido atualizado com sucesso.
    if (events.length === 0) return null;

    // Erro genérico (loop do agente quebrou) é sempre fatal, não importa o que veio depois.
    const hasGenericError = events.some(e => e.type === 'error');
    if (hasGenericError) return 'error';

    const failedResults = events.filter(e => e.type === 'tool_result' && e.ok === false);

    // Verifica se alguma ferramenta de escrita falhou e não teve sucesso posterior na mesma execução.
    // Isso garante que erros em ferramentas cruciais não sejam mascarados,
    // consertando inclusive estados retroativos onde o agente emitiu suggested_actions após errar.
    const hasUnrecoveredWriteFailure = failedResults.some(failedEvent => {
        if (failedEvent.cancelled || !WRITE_TOOLS.has(failedEvent.tool as string)) return false;

        const failedIndex = events.indexOf(failedEvent);
        const hasSuccessAfter = events.slice(failedIndex + 1).some(e =>
            e.type === 'tool_result' && e.tool === failedEvent.tool && (e as any).ok === true
        );
        return !hasSuccessAfter;
    });

    if (hasUnrecoveredWriteFailure) return 'error';

    // Para outras tools (leitura): se o agente chegou a uma conclusão real (resposta final ou
    // suggested_actions) ele teve chance de se recuperar de falhas intermediárias.
    const reachedConclusion = events.some(e => e.type === 'suggested_actions' || e.type === 'final');
    const hasRealFailure = failedResults.some(e => !e.cancelled);

    if (hasRealFailure && !reachedConclusion) return 'error';
    if (failedResults.some(e => e.cancelled) && !reachedConclusion) return 'cancelled';
    return null;
}
