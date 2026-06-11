/**
 * Modal — overlay genérico. Suporta ESC p/ fechar, click no overlay, trap de foco básico.
 * O ConfirmModal existente vira uma especialização fina sobre este.
 */
import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: number | string;
  closeOnOverlay?: boolean;
  closeOnEsc?: boolean;
  showCloseBtn?: boolean;
  ariaLabel?: string;
}

import { createPortal } from 'react-dom';

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  footer,
  width = 440,
  closeOnOverlay = true,
  closeOnEsc = true,
  showCloseBtn = true,
  ariaLabel,
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = React.useState(false);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  useEffect(() => {
    if (!isOpen || !closeOnEsc) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, closeOnEsc, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    // Foca o modal para acessibilidade básica
    ref.current?.focus();
  }, [isOpen]);

  if (!isOpen || !mounted) return null;

  return createPortal(
    <div
      onClick={closeOnOverlay ? onClose : undefined}
      role="dialog"
      aria-modal="true"
      aria-label={typeof title === 'string' ? title : ariaLabel}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 99999, // Ensure it's above everything
        padding: '24px',
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--sw-sidebar)',
          color: 'var(--sw-text-base)',
          width,
          maxWidth: '100%',
          maxHeight: '90vh',
          borderRadius: '12px',
          border: 'var(--sw-border-width) solid var(--sw-border)',
          boxShadow: 'var(--sw-shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {(title || showCloseBtn) && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '20px 24px',
              borderBottom: 'var(--sw-border-width) solid var(--sw-border)',
            }}
          >
            {typeof title === 'string' ? (
              <h3 style={{ margin: 0, fontSize: 'var(--font-lg)', fontWeight: 600 }}>{title}</h3>
            ) : (
              title ?? <span />
            )}
            {showCloseBtn && (
              <button
                aria-label="Fechar"
                onClick={onClose}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--sw-text-muted)',
                  cursor: 'pointer',
                  borderRadius: '6px',
                  padding: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'background 0.2s, color 0.2s',
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.background = 'var(--sw-hover)';
                  e.currentTarget.style.color = 'var(--sw-text-base)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = 'var(--sw-text-muted)';
                }}
              >
                <X size={18} />
              </button>
            )}
          </div>
        )}
        <div style={{ padding: '24px', overflow: 'auto' }}>{children}</div>
        {footer && (
          <div
            style={{
              padding: '16px 24px',
              borderTop: 'var(--sw-border-width) solid var(--sw-border)',
              display: 'flex',
              gap: '12px',
              justifyContent: 'flex-end',
              background: 'transparent',
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};
