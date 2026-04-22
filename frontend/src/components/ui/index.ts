/**
 * Biblioteca de primitivos UI reutilizáveis.
 *
 * Uso:
 *   import { Avatar, Button, Badge, Modal, Card, Spinner, EmptyState, ErrorBoundary } from '@/components/ui';
 */
export { Avatar } from './Avatar';
export type { AvatarKind, AvatarSize, AvatarProps } from './Avatar';

export { Button } from './Button';
export type { ButtonVariant, ButtonSize, ButtonProps } from './Button';

export { Badge, toneForSeniority, toneForTemperature } from './Badge';
export type { BadgeTone, BadgeProps } from './Badge';

export { Modal } from './Modal';
export type { ModalProps } from './Modal';

export { Spinner, LoadingSkeleton } from './Spinner';
export type { SpinnerProps } from './Spinner';

export { EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';

export { ErrorBoundary } from './ErrorBoundary';

export { Card } from './Card';
export type { CardVariant, CardProps } from './Card';
