/**
 * Button — variantes consistentes com o tema, sem dependência de CSS module.
 * Padroniza o visual de todos os botões do app (primary/secondary/ghost/danger/success).
 */
import React, { forwardRef } from 'react';
import { Loader2 } from 'lucide-react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'warning';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}

const VARIANT_STYLE: Record<ButtonVariant, React.CSSProperties> = {
  primary: {
    background: 'linear-gradient(135deg, #7A8BFF 0%, #60A5FA 100%)',
    color: '#fff',
    border: '1px solid rgba(122, 139, 255, 0.4)',
  },
  secondary: {
    background: 'rgba(255,255,255,0.05)',
    color: 'rgba(255,255,255,0.85)',
    border: '1px solid rgba(255,255,255,0.10)',
  },
  ghost: {
    background: 'transparent',
    color: 'rgba(255,255,255,0.65)',
    border: '1px solid transparent',
  },
  danger: {
    background: '#ef4444',
    color: '#fff',
    border: '1px solid #dc2626',
  },
  success: {
    background: '#34d17c',
    color: '#fff',
    border: '1px solid #099272',
  },
  warning: {
    background: '#f59e0b',
    color: '#111',
    border: '1px solid #d97706',
  },
};

const SIZE_STYLE: Record<ButtonSize, React.CSSProperties> = {
  sm: { padding: '6px 10px', fontSize: '12px', borderRadius: '8px', gap: '6px' },
  md: { padding: '8px 14px', fontSize: '13px', borderRadius: '10px', gap: '8px' },
  lg: { padding: '10px 18px', fontSize: '14px', borderRadius: '12px', gap: '10px' },
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading,
    leftIcon,
    rightIcon,
    fullWidth,
    disabled,
    style,
    children,
    ...rest
  },
  ref,
) {
  const disabledFinal = disabled || loading;
  const combined: React.CSSProperties = {
    ...VARIANT_STYLE[variant],
    ...SIZE_STYLE[size],
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: disabledFinal ? 'not-allowed' : 'pointer',
    opacity: disabledFinal ? 0.55 : 1,
    fontWeight: 600,
    transition: 'transform 0.12s ease, opacity 0.12s ease, box-shadow 0.2s ease',
    width: fullWidth ? '100%' : undefined,
    whiteSpace: 'nowrap',
    ...style,
  };

  return (
    <button ref={ref} disabled={disabledFinal} style={combined} {...rest}>
      {loading ? (
        <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
      ) : (
        leftIcon
      )}
      {children}
      {!loading && rightIcon}
    </button>
  );
});
