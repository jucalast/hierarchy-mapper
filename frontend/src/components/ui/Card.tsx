/**
 * Card — container de painel com variants (flat/elevated/outlined).
 * Usado por listagens, painéis de detalhes, tiles.
 */
import React from 'react';

export type CardVariant = 'flat' | 'elevated' | 'outlined' | 'ghost';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  padding?: number | string;
  interactive?: boolean;
}

const VARIANT: Record<CardVariant, React.CSSProperties> = {
  flat: {
    background: 'rgba(255,255,255,0.02)',
    border: '1px solid rgba(255,255,255,0.05)',
  },
  elevated: {
    background: '#171616',
    border: '1px solid rgba(255,255,255,0.06)',
    boxShadow: '0 6px 24px rgba(0,0,0,0.25)',
  },
  outlined: {
    background: 'transparent',
    border: '1px solid rgba(255,255,255,0.1)',
  },
  ghost: {
    background: 'transparent',
    border: '1px solid transparent',
  },
};

export const Card: React.FC<CardProps> = ({
  variant = 'flat',
  padding = 14,
  interactive = false,
  style,
  children,
  ...rest
}) => {
  return (
    <div
      {...rest}
      style={{
        ...VARIANT[variant],
        padding,
        borderRadius: 12,
        transition: interactive ? 'transform 0.15s ease, border-color 0.15s ease' : undefined,
        cursor: interactive ? 'pointer' : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
};
