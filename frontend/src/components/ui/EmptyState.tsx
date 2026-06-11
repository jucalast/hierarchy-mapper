/**
 * EmptyState — visual consistente para "sem dados" / erros vazios.
 */
import React from 'react';
import { Inbox } from 'lucide-react';

export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  compact?: boolean;
  style?: React.CSSProperties;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  compact = false,
  style,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        padding: compact ? '16px' : '32px',
        gap: compact ? 8 : 12,
        color: 'rgba(255,255,255,0.55)',
        ...style,
      }}
    >
      <div
        style={{
          width: compact ? 36 : 56,
          height: compact ? 36 : 56,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(255,255,255,0.04)',
          color: 'rgba(255,255,255,0.4)',
        }}
      >
        {icon || <Inbox size={compact ? 18 : 26} />}
      </div>
      <div style={{ fontSize: compact ? 13 : 15, fontWeight: 600, color: 'rgba(255,255,255,0.75)' }}>
        {title}
      </div>
      {description && (
        <div style={{ fontSize: 12, maxWidth: 320, lineHeight: 1.5 }}>{description}</div>
      )}
      {action && <div style={{ marginTop: 4 }}>{action}</div>}
    </div>
  );
};
