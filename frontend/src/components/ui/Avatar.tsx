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
  data?: Record<string, unknown> | null;
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
  alt?: string;
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

  const fallback = `https://ui-avatars.com/api/?name=${encodeURIComponent(
    resolvedName,
  )}&background=${fallbackBg}&color=${fallbackColor}&bold=true&rounded=true&size=128`;

  const baseStyle: React.CSSProperties = {
    width: pxSize,
    height: pxSize,
    borderRadius: kind === 'company' ? '8px' : '50%',
    overflow: 'hidden',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    backgroundColor: kind === 'company' ? '#fff' : '#dfe5e7',
    ...style,
  };

  const showPlaceholder = !proxiedUrl || imgError;

  return (
    <span className={className} style={baseStyle} aria-label={alt || resolvedName}>
      {showPlaceholder ? (
        <img
          src={fallback}
          alt={alt || resolvedName}
          width={pxSize}
          height={pxSize}
          style={{ width: '100%', height: '100%', objectFit: defaultFit }}
          loading="lazy"
          decoding="async"
          onError={(e) => {
            // fallback final: ícone
            const tgt = e.currentTarget as HTMLImageElement;
            tgt.style.display = 'none';
          }}
        />
      ) : (
        <img
          src={proxiedUrl}
          alt={alt || resolvedName}
          width={pxSize}
          height={pxSize}
          style={{
            width: '100%',
            height: '100%',
            objectFit: defaultFit,
            background: kind === 'company' ? '#fff' : undefined,
          }}
          loading="lazy"
          decoding="async"
          onError={() => setImgError(true)}
        />
      )}
      {/* Ícone absoluto como último fallback se ambas imagens falharem */}
      {showPlaceholder && (
        <span
          aria-hidden
          style={{
            position: 'absolute',
            color: '#868686',
            pointerEvents: 'none',
          }}
        >
          {kind === 'company' ? <Building2 size={pxSize * 0.5} /> : <User2 size={pxSize * 0.5} />}
        </span>
      )}
    </span>
  );
}

export const Avatar = memo(AvatarBase);
