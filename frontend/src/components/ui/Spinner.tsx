/**
 * Spinner — Loader2 animado com tamanho e label consistentes.
 */
import React from 'react';
import { Loader2 } from 'lucide-react';

export interface SpinnerProps {
  size?: number;
  label?: string;
  color?: string;
  inline?: boolean;
  style?: React.CSSProperties;
  className?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({
  size = 16,
  label,
  color = 'rgba(255,255,255,0.75)',
  inline = false,
  style,
  className,
}) => (
  <span
    className={className}
    style={{
      display: inline ? 'inline-flex' : 'flex',
      alignItems: 'center',
      gap: label ? 8 : 0,
      color,
      ...style,
    }}
  >
    <Loader2 size={size} style={{ animation: 'spin 1s linear infinite' }} />
    {label && <span style={{ fontSize: 12 }}>{label}</span>}
  </span>
);

/**
 * LoadingSkeleton — bloco pulsante para placeholders.
 */
export const LoadingSkeleton: React.FC<{
  width?: number | string;
  height?: number | string;
  rounded?: number | string;
  style?: React.CSSProperties;
}> = ({ width = '100%', height = 16, rounded = 6, style }) => (
  <div
    style={{
      width,
      height,
      borderRadius: rounded,
      background:
        'linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 100%)',
      backgroundSize: '200% 100%',
      animation: 'shimmer 1.2s linear infinite',
      ...style,
    }}
  />
);
