// Barrel do subsistema de mensagens do agente (chat).
// Reúne tipos, helpers, cards e componentes de stream em um único ponto de import.

export type {
    AgentEvent,
    AgentMessageProps,
    MappedContact,
    MappingStatus,
    TaskStatus,
    TaskCategory,
} from './types';

export { classifyFailure } from './classifyFailure';
export { parseMarkdownToHTML, renderInline, renderMarkdown } from './markdown';
export {
    WRITE_TOOLS,
    TOOL_COLORS,
    CONTEXT_TOOLS,
    detectTaskCategory,
    CATEGORY_CONFIG,
} from './constants';

export { ConfirmationCard } from './cards/ConfirmationCard';
export { HierarchyMappingCard } from './cards/HierarchyMappingCard';
export { ProspectingPlanCard } from './cards/ProspectingPlanCard';

export { InlineEventStream } from './InlineEventStream';
export { SuggestedActionTask } from './SuggestedActionTask';
export { AgentMessage } from './AgentMessage';
