import React from 'react';
import styles from '../ChatPanel.module.css';

interface EmptyWelcomeStateProps {
    isOrgLoading: boolean;
    activeOrgId: number | null;
    prospectingContext?: string | null;
    cleanOrgName: string;
    hasValidOrg: boolean;
    messages: any[];
    renderChatInput: () => React.ReactNode;
}

export const EmptyWelcomeState: React.FC<EmptyWelcomeStateProps> = ({
    isOrgLoading,
    activeOrgId,
    prospectingContext,
    cleanOrgName,
    hasValidOrg,
    messages,
    renderChatInput,
}) => {
    if (isOrgLoading && messages.length === 0) {
        return (
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
        );
    }

    if (activeOrgId && !prospectingContext && (messages.length === 0 || (messages.length === 1 && messages[0].id === 'welcome'))) {
        return (
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
        );
    }

    if (messages.length === 0) {
        return (
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
        );
    }

    if (messages.length === 1 && messages[0].id === 'welcome') {
        return (
            <div className={styles.emptyWelcomeContainer}>
                <h2 className={styles.emptyWelcomeText}>
                    {messages[0].content}
                </h2>
                <div className={styles.emptyInputWrapper}>
                    {renderChatInput()}
                </div>
            </div>
        );
    }

    return null;
};
