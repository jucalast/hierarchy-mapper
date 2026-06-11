/**
 * Avatar — wrapper inteligente com fallback em cascata.
 *
 * Em ordem de prioridade:
 * 1. URL explícita (prop `src`)
 * 2. getAvatarUrl(data) — procura avatar_url, avatar, profile_pic, photo, image, linkedin
 * 3. getCompanyLogoUrl(data) — quando `kind="company"`
 * 4. ui-avatars.com — fallback final com iniciais
 *
 * Nunca quebra: sempre retorna algo visível.
 */
import React, { memo, useMemo, useState } from 'react';
import { User2, Building2 } from 'lucide-react';
import { getAvatarUrl, getCompanyLogoUrl, getProxiedUrl } from '@/utils/avatarUtils';

export type AvatarKind = 'person' | 'company';
export type AvatarSize = number | 'xs' | 'sm' | 'md' | 'lg' | 'xl';

export interface AvatarProps {
  /** Dados do funcionário/empresa para derivar URL automaticamente */
  data?: any;
  /** Forçar URL específica (tem prioridade sobre `data`) */
  src?: string | null;
  /** Nome para derivar iniciais no fallback ui-avatars */
  name?: string;
  /** Pessoa (circular, User2 como placeholder) vs. Empresa (quadrado arredondado, Building2) */
  kind?: AvatarKind;
  /** Tamanho em px ou preset */
  size?: AvatarSize;
  /** Cor de fundo do fallback ui-avatars (sem #) */
  fallbackBg?: string;
  /** Cor do texto do fallback ui-avatars (sem #) */
  fallbackColor?: string;
  /** object-fit — contain p/ logos de empresa, cover p/ foto */
  fit?: 'cover' | 'contain';
  /** Classe CSS extra p/ composição (ex.: borda animada) */
  className?: string;
  /** Estilo inline extra */
  style?: React.CSSProperties;
  /** alt text acessível */
  /** alt text acessível */
  alt?: string;
  /** Não mostrar iniciais (ui-avatars) se não houver imagem */
  noInitialFallback?: boolean;
}

const SIZE_MAP: Record<Exclude<AvatarSize, number>, number> = {
  xs: 20,
  sm: 28,
  md: 36,
  lg: 48,
  xl: 64,
};

function resolveSize(size?: AvatarSize): number {
  if (!size) return 36;
  if (typeof size === 'number') return size;
  return SIZE_MAP[size] ?? 36;
}

function AvatarBase({
  data,
  src,
  name,
  kind = 'person',
  size = 'md',
  fallbackBg = '6366f1',
  fallbackColor = 'fff',
  fit,
  className,
  style,
  alt,
  noInitialFallback = false,
}: AvatarProps) {
  const pxSize = resolveSize(size);
  const defaultFit: 'cover' | 'contain' = fit || (kind === 'company' ? 'contain' : 'cover');

  const rawUrl = useMemo(() => {
    if (src) return src;
    if (!data) return null;
    return kind === 'company' ? getCompanyLogoUrl(data) : getAvatarUrl(data);
  }, [src, data, kind]);

  const proxiedUrl = useMemo(() => getProxiedUrl(rawUrl || ''), [rawUrl]);

  const resolvedName =
    name ||
    (data && (data.name as string)) ||
    (kind === 'company' ? 'C' : 'P');

  const [imgError, setImgError] = useState(false);
  const [retryUrl, setRetryUrl] = useState<string | null>(null);

  // Reset error state when URL changes
  React.useEffect(() => {
    setImgError(false);
    setRetryUrl(null);
  }, [proxiedUrl]);

  // Imagem de silhueta genérica e elegante
  const genericPersonFallback = "/imagem_linkedin.png";

  const fallback = (kind === 'person' && !noInitialFallback && resolvedName !== 'P')
    ? `https://ui-avatars.com/api/?name=${encodeURIComponent(resolvedName)}&background=${fallbackBg}&color=${fallbackColor}&bold=true&rounded=true&size=${size}`
    : genericPersonFallback;

  const showPlaceholder = (!proxiedUrl && !retryUrl) || imgError;

  const baseStyle: React.CSSProperties = {
    width: pxSize,
    height: pxSize,
    borderRadius: kind === 'company' ? '8px' : '50%',
    overflow: 'hidden',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    backgroundColor: showPlaceholder
      ? 'rgba(255, 255, 255, 0.05)'
      : (kind === 'company' ? 'transparent' : 'rgba(255, 255, 255, 0.05)'),
    position: 'relative',
    ...style,
  };

  return (
    <span className={className} style={baseStyle} aria-label={alt || resolvedName}>
      {/* Ícone absoluto como último fallback se ambas imagens falharem */}
      {showPlaceholder && (
        <span
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'rgba(255, 255, 255, 0.35)',
            pointerEvents: 'none',
          }}
        >
          {kind === 'company' ? (
            <Building2 size={pxSize * 0.5} />
          ) : (
            <User2 size={pxSize * 0.5} />
          )}
        </span>
      )}

      {(showPlaceholder && !noInitialFallback && kind !== 'company') ? (
        <img
          src={fallback}
          alt={alt || resolvedName}
          width={pxSize}
          height={pxSize}
          style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'relative', zIndex: 1, backgroundColor: 'transparent', transform: 'scale(1.2)' }}
          loading="lazy"
          decoding="async"
          onError={(e) => {
            // fallback final: ícone
            const tgt = e.currentTarget as HTMLImageElement;
            tgt.style.display = 'none';
          }}
        />
      ) : !showPlaceholder ? (
        <img
          src={retryUrl || proxiedUrl}
          alt={alt || resolvedName}
          width={pxSize}
          height={pxSize}
          style={{
            width: '100%',
            height: '100%',
            objectFit: defaultFit,
            background: 'transparent',
            position: 'relative',
            zIndex: 1
          }}
          loading="lazy"
          decoding="async"
          onError={() => {
            // Se falhou a principal e temos um domínio, tenta unavatar.io como retry
            const domain = data?.domain || data?.company_domain;
            if (!retryUrl && kind === 'company' && domain) {
               setRetryUrl(`https://unavatar.io/${domain}`);
            } else {
               setImgError(true);
            }
          }}
        />
      ) : null}
    </span>
  );
}

export const Avatar = memo(AvatarBase);
