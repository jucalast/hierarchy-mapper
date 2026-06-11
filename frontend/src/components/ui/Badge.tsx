/**
 * Badge — Pills/labels consistentes para tier, status, seniority, temperatura, etc.
 */
import React, { memo } from 'react';

export type BadgeTone =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger'
  | 'primary'
  | 'purple';

export interface BadgeProps {
  tone?: BadgeTone;
  size?: 'sm' | 'md';
  icon?: React.ReactNode;
  children: React.ReactNode;
  title?: string;
  style?: React.CSSProperties;
  className?: string;
  outline?: boolean;
}

const TONE: Record<BadgeTone, { bg: string; fg: string; border: string }> = {
  neutral: { bg: 'rgba(255,255,255,0.06)', fg: 'rgba(255,255,255,0.85)', border: 'rgba(255,255,255,0.12)' },
  info:    { bg: 'rgba(96,165,250,0.15)', fg: '#60A5FA',                border: 'rgba(96,165,250,0.4)' },
  success: { bg: 'rgba(52,209,124,0.15)',   fg: '#34d17c',                border: 'rgba(52,209,124,0.4)' },
  warning: { bg: 'rgba(245,158,11,0.15)',  fg: '#f59e0b',                border: 'rgba(245,158,11,0.4)' },
  danger:  { bg: 'rgba(239,68,68,0.15)',   fg: '#ef4444',                border: 'rgba(239,68,68,0.4)' },
  primary: { bg: 'rgba(122,139,255,0.15)', fg: '#7A8BFF',                border: 'rgba(122,139,255,0.4)' },
  purple:  { bg: 'rgba(168,85,247,0.15)',  fg: '#a855f7',                border: 'rgba(168,85,247,0.4)' },
};

function BadgeBase({
  tone = 'neutral',
  size = 'sm',
  icon,
  children,
  title,
  style,
  className,
  outline,
}: BadgeProps) {
  const t = TONE[tone];
  const combined: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: size === 'sm' ? 4 : 6,
    padding: size === 'sm' ? '2px 8px' : '4px 10px',
    fontSize: size === 'sm' ? '0.68rem' : '0.78rem',
    fontWeight: 700,
    borderRadius: '999px',
    background: outline ? 'transparent' : t.bg,
    color: t.fg,
    border: `1px solid ${t.border}`,
    letterSpacing: '0.02em',
    whiteSpace: 'nowrap',
    ...style,
  };
  return (
    <span title={title} className={className} style={combined}>
      {icon && <span style={{ display: 'inline-flex' }}>{icon}</span>}
      {children}
    </span>
  );
}

export const Badge = memo(BadgeBase);

/**
 * Helper: derive BadgeTone a partir de um nível de seniority (0..6).
 */
export function toneForSeniority(level: number): BadgeTone {
  switch (level) {
    case 6: return 'primary';
    case 5: return 'info';
    case 4: return 'success';
    case 3: return 'success';
    case 2: return 'warning';
    case 1: return 'neutral';
    case 0: return 'purple';
    default: return 'neutral';
  }
}

/**
 * Helper: derive BadgeTone a partir de uma "temperatura" textual.
 */
export function toneForTemperature(temp: string | undefined): BadgeTone {
  if (!temp) return 'neutral';
  const t = temp.toLowerCase();
  if (t.includes('quente')) return 'danger';
  if (t.includes('morno')) return 'warning';
  if (t.includes('frio')) return 'info';
  return 'neutral';
}
