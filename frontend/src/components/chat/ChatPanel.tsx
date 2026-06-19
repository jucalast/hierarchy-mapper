import React from 'react';
import { PanelRightOpen, Clock, Plus } from 'lucide-react';
import styles from './ChatPanel.module.css';

import { Avatar, Modal, Button } from '../ui';
import { ChatInput } from './ChatInput';
import { ChatMessage } from './ChatMessage';
import { AgentMessage } from './AgentV2Message';
import { ChatTabs } from './ChatTabs';
import { ConversationContextAccordion } from './ConversationContextAccordion';
import { ThreadList } from './ThreadList';

import { ai } from '@/services/api';
import { useChatPanel } from './useChatPanel';

const AGENT_STREAM_URL = ai.getAgentChatStreamUrl();
const AGENT_CONFIRM_URL = ai.getAgentConfirmStreamUrl();

interface ChatPanelProps {
    showChat: boolean;
    setShowChat: (show: boolean) => void;
    selectedOrgId?: number | null;
    selectedOrgName?: string;
    theme?: string;
    onToggleTheme?: () => void;
    onOpenWhatsApp?: (info: { name: string, id?: string }) => void;
    selectedOrgLogo?: string;
    prospectingContext?: string | null;
    isOrgLoading?: boolean;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
    showChat,
    setShowChat,
    selectedOrgId,
    selectedOrgName = 'Organização',
    theme = 'light',
    onOpenWhatsApp,
    selectedOrgLogo,
    prospectingContext,
    isOrgLoading,
}) => {
    const {
        isListening,
        isTranscribing,
        voiceError,
        startListening,
        stopListening,
        voiceSupported,
        analyserNode,
        view,
        setView,
        activeThread,
        threads,
        isLoadingThreads,
        isCreatingThread,
        currentOrgInfo,
        hasValidOrg,
        cleanOrgName,
        messages,
        inputValue,
        isLoading,
        selectedCompanies,
        approvalStatuses,
        liveModel,
        modelActivity,
        agentStreaming,
        activeRunningTask,
        approvedSuggestedActions,
        taskInlineConfirmed,
        setInputValue,
        setSelectedCompanies,
        setShowAutocomplete,
        model,
        setModel,
        strictMode,
        setStrictMode,
        pipedriveCooldown,
        showAutocomplete,
        isSearching,
        searchingCategory,
        searchTerm,
        companies,
        threadsToDelete,
        setThreadsToDelete,
        messagesEndRef,
        scrollContainerRef,
        handleStopStreaming,
        handleCancelActiveTask,
        handleApproveSuggestedAction,
        handleOpenTaskConsole,
        handleTaskInlineConfirm,
        handleTaskMappingComplete,
        handleScroll,
        handleInputChange,
        handleSendMessage,
        handleNewThread,
        handleBackToList,
        confirmDeleteThread,
        openThread,
        handleRegenerate,
        handleApproveAction,
        handleRejectAction,
        handleMainChatMappingDone,
        handleAgentConfirm,
        setActiveRunningTask,
    } = useChatPanel({
        selectedOrgId,
        selectedOrgName,
        selectedOrgLogo,
        prospectingContext,
        isOrgLoading,
    });

    const activeOrgId = selectedOrgId || null;

    const renderActiveTaskConsoleOverlay = () => {
        return null;
    };

    const renderChatInput = () => (
        <ChatInput
            inputValue={inputValue}
            setInputValue={handleInputChange}
            isLoading={isLoading || activeRunningTask?.status === 'streaming'}
            onSend={handleSendMessage}
            selectedCompanies={selectedCompanies}
            setSelectedCompanies={setSelectedCompanies}
            model={model}
            setModel={setModel}
            strictMode={strictMode}
            setStrictMode={setStrictMode}
            liveModel={liveModel}
            modelActivity={modelActivity}
            isStreamingActivity={isLoading}
            showAutocomplete={showAutocomplete}
            isSearching={isSearching}
            searchingCategory={searchingCategory}
            searchTerm={searchTerm}
            companies={companies}
            selectSearchResult={item => {
                if (!selectedCompanies.find(c => c.id === item.id)) {
                    setSelectedCompanies([...selectedCompanies, item]);
                }
                const lastAt = inputValue.lastIndexOf('@');
                if (lastAt !== -1) setInputValue(inputValue.substring(0, lastAt) + '@' + item.name + ' ');
                setShowAutocomplete(false);
            }}
            isListening={isListening}
            isTranscribing={isTranscribing}
            startListening={startListening}
            stopListening={stopListening}
            voiceError={voiceError}
            voiceSupported={voiceSupported}
            analyserNode={analyserNode}
            theme={theme}
            pipedriveCooldown={pipedriveCooldown}
            onStop={handleStopStreaming}
            activeRunningTask={activeRunningTask}
            setActiveRunningTask={setActiveRunningTask}
            taskInlineConfirmed={taskInlineConfirmed}
            onTaskInlineConfirm={handleTaskInlineConfirm}
            onTaskMappingComplete={handleTaskMappingComplete}
            onCancelActiveTask={handleCancelActiveTask}
        />
    );

    // ═══════════════════════════════════════════
    // RENDER: Collapsed handle view
    // ═══════════════════════════════════════════
    if (!showChat) {
        return (
            <div 
                style={{
                    width: '56px',
                    height: '100%',
                    backgroundColor: '#131313',
                    borderLeft: '1px solid rgba(255, 255, 255, 0.04)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    paddingTop: '16px',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    flexShrink: 0
                }}
                onClick={() => setShowChat(true)}
                title="Abrir Assistente de IA"
            >
                <button 
                    style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--sw-text-muted)',
                        cursor: 'pointer',
                        padding: '8px',
                        borderRadius: '8px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        transition: 'color 0.2s',
                    }}
                >
                    <PanelRightOpen size={20} />
                </button>
            </div>
        );
    }

    if (view === 'list') {
        return (
            <div className={styles.chatPanel} data-theme={theme}>
                <ThreadList
                    orgName={hasValidOrg ? cleanOrgName : 'Geral'}
                    threads={threads}
                    isLoading={isLoadingThreads}
                    onSelectThread={openThread}
                    onNewThread={handleNewThread}
                    isCreating={isCreatingThread}
                    selectedOrgLogo={currentOrgInfo.logo}
                    onDeleteThread={(t) => setThreadsToDelete([t])}
                    onDeleteThreadsBulk={setThreadsToDelete}
                    onCloseChat={() => setShowChat(false)}
                    onBackToChat={() => {
                        setView('chat');
                        if (typeof window !== 'undefined') {
                            window.localStorage.setItem('chat-panel-view', 'chat');
                            const targetOrgId = activeOrgId || 0;
                            const savedThreadId = window.localStorage.getItem(`active-thread-id-${targetOrgId}`);
                            if (savedThreadId) {
                                const matched = threads.find(t => t.id === savedThreadId);
                                if (matched) {
                                    void openThread(matched);
                                }
                            }
                        }
                    }}
                />

                <Modal
                    isOpen={threadsToDelete.length > 0}
                    onClose={() => setThreadsToDelete([])}
                    title={threadsToDelete.length > 1 ? "Excluir Conversas" : "Excluir Conversa"}
                    width={400}
                    footer={
                        <>
                            <Button variant="secondary" size="sm" onClick={() => setThreadsToDelete([])}>
                                Cancelar
                            </Button>
                            <Button variant="danger" size="sm" onClick={confirmDeleteThread}>
                                Excluir {threadsToDelete.length > 1 ? `(${threadsToDelete.length})` : ''}
                            </Button>
                        </>
                    }
                >
                    <p style={{ margin: 0, color: 'var(--chat-text-secondary)', fontSize: '14px', lineHeight: '1.5' }}>
                        {threadsToDelete.length > 1 
                            ? `Tem certeza que deseja excluir as ${threadsToDelete.length} conversas selecionadas? Esta ação não poderá ser desfeita.`
                            : 'Tem certeza que deseja excluir esta conversa? Esta ação removerá permanentemente todo o histórico e não poderá ser desfeita.'}
                    </p>
                </Modal>
            </div>
        );
    }

    // ═══════════════════════════════════════════
    // RENDER: Chat view
    // ═══════════════════════════════════════════
    return (
        <div className={styles.chatPanel} data-theme={theme}>

            {/* Chat sub-header: back + thread title + activities toggle */}
            <div className={styles.chatHeader} style={{ paddingLeft: '16px', gap: '12px' }}>
                <Avatar 
                    kind="company"
                    src={currentOrgInfo.logo}
                    name={currentOrgInfo.name}
                    size={32}
                    style={{ border: currentOrgInfo.logo ? '3px solid var(--sw-border-strong)' : 'none' }}
                />
                <div className={styles.chatHeaderInfo} style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '8px', flex: '0 1 auto', minWidth: 0 }}>
                    <span style={{ color: 'var(--sw-text-muted)', fontWeight: 600, fontSize: '0.88rem', flexShrink: 0 }}>
                        {activeThread?.title || 'Nova conversa'}
                    </span>
                    <span style={{ color: 'var(--sw-border)', fontWeight: 300, fontSize: '0.88rem', flexShrink: 0 }}>/</span>
                    <span 
                        style={{ 
                            color: 'var(--sw-text-base)', 
                            fontWeight: 600, 
                            fontSize: '0.88rem', 
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            maxWidth: '180px',
                            flexShrink: 1
                        }}
                        title={hasValidOrg ? cleanOrgName : 'Geral'}
                    >
                        {hasValidOrg ? cleanOrgName : 'Geral'}
                    </span>
                </div>
                <div style={{ flex: 1 }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginRight: '12px' }}>
                    <button
                        className={styles.tlNewBtn}
                        onClick={handleNewThread}
                        title="Nova conversa"
                        style={{ height: '32px', padding: '0 12px', fontSize: '12px' }}
                    >
                        <Plus size={13} />
                        <span>Nova</span>
                    </button>
                    <button
                        className={styles.chatHeaderIconBtn}
                        onClick={handleBackToList}
                        title="Histórico de conversas"
                    >
                        <Clock size={20} />
                    </button>
                </div>
            </div>

            {/* Abas dinâmicas para multi-chat */}
            <ChatTabs />

            {/* Accordion de Contexto da Investigação */}
            <ConversationContextAccordion 
                messages={messages} 
                orgId={activeOrgId}
                orgName={cleanOrgName}
                dealId={activeThread?.meta?.deal_id}
            />

            {/* Body: messages + optional sidebar */}
            <div className={`${styles.chatBody} ${messages.length === 0 || (messages.length === 1 && messages[0].id === 'welcome') ? styles.emptyChatBody : ''}`}>
                {isOrgLoading && messages.length === 0 ? (
                    <div className={styles.emptyWelcomeContainer} style={{ opacity: 0.7 }}>
                        <h2 className={styles.emptyWelcomeText}>
                            Carregando contexto da{' '}
                            <span className={styles.highlightPurple}>
                                @{cleanOrgName}
                            </span>
                            ...
                        </h2>
                    </div>
                ) : activeOrgId && !prospectingContext && (messages.length === 0 || (messages.length === 1 && messages[0].id === 'welcome')) ? (
                    <div className={styles.emptyWelcomeContainer}>
                        <h2 className={styles.emptyWelcomeText}>
                            A{' '}
                            <span className={styles.highlightPurple}>
                                @{cleanOrgName}
                            </span>
                            {' '}ainda não possui um plano de prospecção.
                        </h2>
                        <div className={styles.emptyInputWrapper}>
                            {renderChatInput()}
                        </div>
                    </div>
                ) : messages.length === 0 ? (
                    <div className={styles.emptyWelcomeContainer}>
                        <h2 className={styles.emptyWelcomeText}>
                            {hasValidOrg ? (
                                <>
                                    Como posso te ajudar com a{' '}
                                    <span className={styles.highlightPurple}>
                                        @{cleanOrgName}
                                    </span>
                                    ?
                                </>
                            ) : (
                                "Como posso te ajudar hoje?"
                            )}
                        </h2>
                        <div className={styles.emptyInputWrapper}>
                            {renderChatInput()}
                        </div>
                    </div>
                ) : messages.length === 1 && messages[0].id === 'welcome' ? (
                    <div className={styles.emptyWelcomeContainer}>
                        <h2 className={styles.emptyWelcomeText}>
                            {messages[0].content}
                        </h2>
                        <div className={styles.emptyInputWrapper}>
                            {renderChatInput()}
                        </div>
                    </div>
                ) : (
                    <>
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
                                            streamV2Url={AGENT_STREAM_URL}
                                            confirmV2Url={AGENT_CONFIRM_URL}
                                            orgId={activeOrgId}
                                            selectedOrgName={cleanOrgName}
                                            threadId={activeThread?.id}
                                            approvedSuggestedActions={approvedSuggestedActions}
                                            onApproveSuggestedAction={handleApproveSuggestedAction}
                                            onHierarchyMappingDone={handleMainChatMappingDone}
                                            model={model}
                                            onOpenTaskConsole={handleOpenTaskConsole}
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
                        {renderChatInput()}
                    </>
                )}
            </div>
            {renderActiveTaskConsoleOverlay()}
        </div>
    );
};
