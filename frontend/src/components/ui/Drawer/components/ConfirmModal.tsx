import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Modal, Button } from '../../';

interface ConfirmModalProps {
    confirmKind: 'reset' | 'delete' | null;
    confirmBusy: boolean;
    setConfirmKind: (kind: 'reset' | 'delete' | null) => void;
    performDelete: (orgId: number) => Promise<void>;
    performReset: (orgId: number) => Promise<void>;
    expandedOrgId: number | null;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
    confirmKind,
    confirmBusy,
    setConfirmKind,
    performDelete,
    performReset,
    expandedOrgId,
}) => {
    return (
        <Modal
            isOpen={confirmKind !== null}
            onClose={() => !confirmBusy && setConfirmKind(null)}
            title={
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <AlertTriangle
                        size={18}
                        color={confirmKind === 'delete' ? '#ef4444' : '#f59e0b'}
                    />
                    <span>
                        {confirmKind === 'delete'
                            ? 'Excluir empresa definitivamente'
                            : 'Resetar dados da empresa'}
                    </span>
                </div>
            }
            width={460}
            closeOnOverlay={!confirmBusy}
            closeOnEsc={!confirmBusy}
            footer={
                <>
                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setConfirmKind(null)}
                        disabled={confirmBusy}
                    >
                        Cancelar
                    </Button>
                    <Button
                        variant={confirmKind === 'delete' ? 'danger' : 'warning'}
                        size="sm"
                        loading={confirmBusy}
                        onClick={() => {
                            if (!expandedOrgId || !confirmKind) return;
                            if (confirmKind === 'delete') void performDelete(expandedOrgId);
                            else void performReset(expandedOrgId);
                        }}
                    >
                        {confirmKind === 'delete' ? 'Excluir definitivamente' : 'Resetar tudo'}
                    </Button>
                </>
            }
        >
            {confirmKind === 'delete' ? (
                <p style={{ margin: 0, lineHeight: 1.5, color: 'var(--sw-text-subtle)' }}>
                    Esta ação <strong style={{ color: '#ef4444' }}>remove a empresa do Pipedrive</strong> e apaga
                    todos os dados locais (hierarquia, cache, logos, layouts). Operação irreversível.
                </p>
            ) : (
                <p style={{ margin: 0, lineHeight: 1.5, color: 'var(--sw-text-subtle)' }}>
                    Isso limpa o <strong>cache, hierarquia e layout</strong> salvos desta empresa, mantendo o
                    registro no Pipedrive. O próximo mapeamento partirá do zero.
                </p>
            )}
        </Modal>
    );
};
