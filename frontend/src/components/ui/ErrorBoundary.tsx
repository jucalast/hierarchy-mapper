/**
 * ErrorBoundary — impede que um erro em um componente-filho mate toda a app.
 * Renderiza fallback (default: EmptyState estilo "quebrou" com botão de retry).
 */
import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { EmptyState } from './EmptyState';
import { Button } from './Button';

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode | ((err: Error, reset: () => void) => React.ReactNode);
  onError?: (error: Error, info: React.ErrorInfo) => void;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Evita import ciclíco; logamos no console
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] Componente quebrou:', error, info);
    this.props.onError?.(error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      const { fallback } = this.props;
      if (typeof fallback === 'function') {
        return (fallback as (e: Error, r: () => void) => React.ReactNode)(
          this.state.error,
          this.reset,
        );
      }
      if (fallback) return fallback;
      return (
        <EmptyState
          icon={<AlertTriangle size={26} />}
          title="Algo deu errado"
          description={this.state.error.message}
          action={
            <Button size="sm" variant="secondary" onClick={this.reset}>
              Tentar novamente
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
