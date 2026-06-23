import React from 'react';
import { Clock, Plus } from 'lucide-react';
import styles from './ChatPanel.module.css';

import { Modal, Button } from '../ui';
import { ChatInput } from './ChatInput';
import { ChatTabs } from './ChatTabs';
import { ConversationContextAccordion } from './ConversationContextAccordion';
import { ThreadList } from './ThreadList';

// Micro Components Imports
import { CollapsedChatHandle } from './components/CollapsedChatHandle';
import { ChatPanelHeader } from './components/ChatPanelHeader';
import { EmptyWelcomeState } from './components/EmptyWelcomeState';
import { MessagesList } from './components/MessagesList';

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
    // Se não for mostrar o chat, mantemos montado para a transição CSS, 
    // mas também exibimos o handle
    const handleNode = !showChat ? <CollapsedChatHandle onClick={() => setShowChat(true)} theme={theme} /> : null;

    if (view === 'list') {
        return (
            <>
                {handleNode}
                <div className={`${styles.chatPanelWrapper} ${showChat ? styles.chatPanelWrapperOpen : styles.chatPanelWrapperClosed}`}>
                <div className={styles.chatPanelInner} data-theme={theme}>
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
            </div>
            </>
        );
    }

    // ═══════════════════════════════════════════
    // RENDER: Chat view
    // ═══════════════════════════════════════════
    return (
        <>
            {handleNode}
            <div className={`${styles.chatPanelWrapper} ${showChat ? styles.chatPanelWrapperOpen : styles.chatPanelWrapperClosed}`}>
            <div className={styles.chatPanelInner} data-theme={theme}>

            {/* Chat sub-header: back + thread title + activities toggle */}
            <ChatPanelHeader 
                logo={currentOrgInfo.logo}
                orgName={hasValidOrg ? cleanOrgName : 'Geral'}
                title={activeThread?.title || 'Nova conversa'}
                onNewThread={handleNewThread}
                onBackToList={handleBackToList}
                onCloseChat={() => setShowChat(false)}
            />

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
                {messages.length === 0 || (messages.length === 1 && messages[0].id === 'welcome') ? (
                    <EmptyWelcomeState 
                        isOrgLoading={!!isOrgLoading}
                        activeOrgId={activeOrgId}
                        prospectingContext={prospectingContext}
                        cleanOrgName={cleanOrgName}
                        hasValidOrg={hasValidOrg}
                        messages={messages}
                        renderChatInput={renderChatInput}
                    />
                ) : (
                    <>
                        <MessagesList 
                            messages={messages}
                            activeRunningTask={activeRunningTask}
                            scrollContainerRef={scrollContainerRef}
                            handleScroll={handleScroll}
                            agentStreaming={agentStreaming}
                            handleAgentConfirm={handleAgentConfirm}
                            handleRegenerate={handleRegenerate}
                            handleSendMessage={handleSendMessage}
                            approvedSuggestedActions={approvedSuggestedActions}
                            handleApproveSuggestedAction={handleApproveSuggestedAction}
                            handleMainChatMappingDone={handleMainChatMappingDone}
                            model={model}
                            handleOpenTaskConsole={handleOpenTaskConsole}
                            handleApproveAction={handleApproveAction}
                            handleRejectAction={handleRejectAction}
                            onOpenWhatsApp={onOpenWhatsApp}
                            approvalStatuses={approvalStatuses}
                            messagesEndRef={messagesEndRef}
                            streamV2Url={AGENT_STREAM_URL}
                            confirmV2Url={AGENT_CONFIRM_URL}
                            activeOrgId={activeOrgId}
                            cleanOrgName={cleanOrgName}
                            activeThreadId={activeThread?.id}
                        />
                        {renderChatInput()}
                    </>
                )}
            </div>
            {renderActiveTaskConsoleOverlay()}
        </div>
        </div>
        </>
    );
};
