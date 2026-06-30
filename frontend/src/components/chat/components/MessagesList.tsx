import React from 'react';
import { AgentMessage } from '../AgentV2Message';
import { ChatMessage } from '../ChatMessage';
import { AIModel } from '../ModelSelector';
import { Message } from '../ChatInterfaces';
import styles from '../ChatPanel.module.css';

interface MessagesListProps {
    messages: Message[];
    activeRunningTask: any;
    scrollContainerRef: React.RefObject<HTMLDivElement | null>;
    handleScroll: (e: React.UIEvent<HTMLDivElement>) => void;
    agentStreaming: boolean;
    handleAgentConfirm: (actionId: string, approved: boolean) => Promise<void> | void;
    handleRegenerate: (messageId?: string) => Promise<void> | void;
    handleSendMessage: (text: string, selectedCompanies?: any[], isAgentAction?: boolean) => Promise<void> | void;
    approvedSuggestedActions: Record<string, 'pending' | 'streaming' | 'awaiting_confirm' | 'awaiting_mapping' | 'done' | 'rejected' | 'error' | 'cancelled'>;
    handleApproveSuggestedAction: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => Promise<void> | void;
    handleRetrySuggestedAction: (action: { label: string; prompt: string }, index: number, parentMessageId?: string) => Promise<void> | void;
    handleMainChatMappingDone: (contacts: any[]) => Promise<void> | void;
    model: AIModel;
    handleOpenTaskConsole: (action: any, index: number, parentMessageId?: string) => void;
    handleApproveAction: (id: string) => Promise<void> | void;
    handleRejectAction: (id: string) => Promise<void> | void;
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
    approvalStatuses: Record<string, 'pending' | 'approving' | 'approved' | 'rejected'>;
    messagesEndRef: React.RefObject<HTMLDivElement | null>;
    streamV2Url: string;
    confirmV2Url: string;
    activeOrgId: number | null;
    cleanOrgName: string;
    activeThreadId?: string;
    handleToggleBatch?: (messageId: string, actionIndex: number, action: { label: string; prompt: string; categoria?: string }) => void;
    batchQueue?: Array<{ messageId: string; actionIndex: number; action: any }>;
}

export const MessagesList: React.FC<MessagesListProps> = ({
    messages,
    activeRunningTask,
    scrollContainerRef,
    handleScroll,
    agentStreaming,
    handleAgentConfirm,
    handleRegenerate,
    handleSendMessage,
    approvedSuggestedActions,
    handleApproveSuggestedAction,
    handleRetrySuggestedAction,
    handleMainChatMappingDone,
    model,
    handleOpenTaskConsole,
    handleApproveAction,
    handleRejectAction,
    onOpenWhatsApp,
    approvalStatuses,
    messagesEndRef,
    streamV2Url,
    confirmV2Url,
    activeOrgId,
    cleanOrgName,
    activeThreadId,
    handleToggleBatch,
    batchQueue = [],
}) => {
    return (
        <div 
            className={styles.messagesContainer} 
            style={{
                paddingBottom: activeRunningTask?.isExpanded ? '440px' : undefined,
                opacity: activeRunningTask?.isExpanded ? 0.55 : 1,
                transition: 'opacity 0.3s ease, padding-bottom 0.3s ease',
            }}
            ref={scrollContainerRef} 
            onScroll={handleScroll}
        >
            {messages.map(message => {
                if (message.isAgent && message.role === 'assistant') {
                    return (
                        <AgentMessage
                            key={message.id}
                            messageId={message.id}
                            events={message.agentEvents || []}
                            isStreaming={message.agentStreaming !== false && agentStreaming}
                            onConfirm={handleAgentConfirm}
                            confirmedActions={message.agentConfirmedActions || {}}
                            onRegenerate={() => handleRegenerate(message.id)}
                            onAction={(prompt: string) => handleSendMessage(prompt, [], true)}
                            streamV2Url={streamV2Url}
                            confirmV2Url={confirmV2Url}
                            orgId={activeOrgId}
                            selectedOrgName={cleanOrgName}
                            threadId={activeThreadId}
                            approvedSuggestedActions={approvedSuggestedActions}
                            onApproveSuggestedAction={handleApproveSuggestedAction}
                            onRetrySuggestedAction={handleRetrySuggestedAction}
                            onHierarchyMappingDone={handleMainChatMappingDone}
                            model={model}
                            onOpenTaskConsole={handleOpenTaskConsole}
                            onToggleBatch={handleToggleBatch
                                ? (action, idx, parentMessageId) => handleToggleBatch(parentMessageId || message.id, idx, action)
                                : undefined}
                            batchQueue={batchQueue}
                        />
                    );
                }
                return (
                    <ChatMessage
                        key={message.id}
                        message={message}
                        onApprove={handleApproveAction}
                        onReject={handleRejectAction}
                        onOpenWhatsApp={onOpenWhatsApp}
                        approvalStatuses={approvalStatuses}
                        onRegenerate={handleRegenerate}
                        onSuggestedAction={(prompt) => handleSendMessage(prompt, [], true)}
                        model={model}
                    />
                );
            })}
            <div ref={messagesEndRef} />
        </div>
    );
};
