'use client';

import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { ProspectLead } from '@/hooks/useProspecting';
import { buildProxyImageUrl } from '@/services/config';

// Corrige o ícone padrão quebrado no webpack
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// ─── Ícones customizados por tier ─────────────────────────────────────────

function makeIcon(tier: 'A' | 'B', selected: boolean, status: string, zoom: number, proxiedLogo?: string | null) {
  const isApproved = status === 'created';
  const isRejected = status === 'rejected';
  
  // Cores: A=Verde, B=Laranja, Aprovado=Azul, Rejeitado=Cinza
  let color = tier === 'A' ? '#34d17c' : '#f59e0b';
  if (isApproved) color = '#3b82f6';
  if (isRejected) color = '#6b7280';

  // Tamanho base de 52px (mínimo)
  // O tamanho aumenta conforme o zoom aumenta a partir do nível 11
  const baseSize = 52;
  const zoomFactor = Math.max(1.0, Math.min(3.0, Math.pow(1.25, zoom - 11)));
  const size = Math.round(baseSize * zoomFactor * (selected ? 1.15 : 1.0));
  const logoSize = Math.round(size * 0.85);

  const content = proxiedLogo ? `
    <foreignObject x="${(size - logoSize) / 2}" y="${(size - logoSize) / 2}" width="${logoSize}" height="${logoSize}">
      <div style="
        width: 100%; 
        height: 100%; 
        background: #fff; 
        border-radius: ${Math.round(10 * zoomFactor)}px; 
        display: flex; 
        align-items: center; 
        justify-content: center;
        overflow: hidden;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        border: ${selected ? '3px solid #7A8BFF' : (isApproved ? '2px solid #3b82f6' : 'none')};
      ">
        <img src="${proxiedLogo}" style="width: 85%; height: 85%; object-fit: contain;" />
      </div>
    </foreignObject>
  ` : `
    <circle cx="${size / 2}" cy="${size / 2}" r="${size / 2 - 2}"
      fill="${color}" fill-opacity="${selected ? 1 : (isRejected ? 0.4 : 0.85)}"
      stroke="rgba(255,255,255,${selected ? 0.9 : 0.5})"
      stroke-width="${Math.round(3 * zoomFactor)}"/>
    <text x="${size / 2}" y="${size / 2 + (7 * zoomFactor)}" text-anchor="middle"
      font-family="system-ui,sans-serif"
      font-size="${Math.round(16 * zoomFactor)}" font-weight="900" fill="white">
      ${isApproved ? '✓' : tier}
    </text>
  `;

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      ${content}
    </svg>`;

  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

function makeCenterIcon() {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20">
      <circle cx="10" cy="10" r="8" fill="#7A8BFF" fill-opacity="0.9"
        stroke="white" stroke-width="2"/>
      <circle cx="10" cy="10" r="3" fill="white"/>
    </svg>`;
  return L.divIcon({ html: svg, className: '', iconSize: [20, 20], iconAnchor: [10, 10] });
}

// ─── Props ────────────────────────────────────────────────────────────────

interface ProspectMapProps {
  centerLat?: number;
  centerLng?: number;
  radiusKm: number;
  leads: ProspectLead[];
  selectedLeadId?: string;
  disabled?: boolean;
  onLeadClick: (lead: ProspectLead) => void;
  onLeadHover?: (lead: ProspectLead | null) => void;
  onMapClick: (coords: { lat: number; lng: number }) => void;
}

// ─── Componente ───────────────────────────────────────────────────────────

export default function ProspectMap({
  centerLat, centerLng, radiusKm,
  leads, selectedLeadId, disabled, onLeadClick, onLeadHover, onMapClick,
}: ProspectMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const centerMarkerRef = useRef<L.Marker | null>(null);
  const circleRef = useRef<L.Circle | null>(null);
  const markersRef = useRef<Record<string, L.Marker>>({});
  const hasFittedRef = useRef(false);
  const onMapClickRef = useRef(onMapClick);
  const [mapReady, setMapReady] = React.useState(false);
  const [zoom, setZoom] = React.useState(12);

  // Mantém a ref sempre atualizada sem precisar re-registrar o listener
  useEffect(() => { onMapClickRef.current = onMapClick; }, [onMapClick]);

  // ── Inicializa mapa ──────────────────────────────────────────────────

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const initialLat = centerLat ?? -23.55;
    const initialLng = centerLng ?? -46.63;
    const initialZoom = centerLat ? 12 : 10;
    setZoom(initialZoom);

    const map = L.map(containerRef.current, {
      center: [initialLat, initialLng],
      zoom: initialZoom,
      zoomControl: false,
      attributionControl: false,
    });

    // Detecta tema atual e escolhe os tiles correspondentes
    const isLight = document.documentElement.getAttribute('data-theme') === 'light' || document.body.getAttribute('data-theme') === 'light';
    const tileUrl = isLight 
      ? 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
      : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';

    L.tileLayer(
      tileUrl,
      { 
        maxZoom: 19,
        opacity: 0.85,
      }
    ).addTo(map);

    L.control.zoom({ position: 'topleft' }).addTo(map);

    map.on('click', (e: L.LeafletMouseEvent) => {
      onMapClickRef.current({ lat: e.latlng.lat, lng: e.latlng.lng });
    });

    map.on('zoomend', () => {
      setZoom(map.getZoom());
    });

    mapRef.current = map;
    setMapReady(true);
    // Força o Leaflet a recalcular o tamanho do container (resolve problemas de tiles cinzas ou mapa cortado)
    setTimeout(() => map.invalidateSize(), 100);
    return () => { map.remove(); mapRef.current = null; setMapReady(false); hasFittedRef.current = false; };
  }, []); // eslint-disable-line

  // ── Atualiza centro + círculo ────────────────────────────────────────

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || centerLat == null || centerLng == null) return;

    const latlng: L.LatLngExpression = [centerLat, centerLng];
    const radiusM = radiusKm * 1000;

    if (isNaN(centerLat) || isNaN(centerLng)) return;

    // Marcador do centro
    if (centerMarkerRef.current) {
      centerMarkerRef.current.setLatLng(latlng);
    } else {
      centerMarkerRef.current = L.marker(latlng, { icon: makeCenterIcon(), zIndexOffset: 1000 }).addTo(map);
    }

    // Círculo de raio
    if (circleRef.current) {
      circleRef.current.setLatLng(latlng).setRadius(radiusM);
    } else {
      circleRef.current = L.circle(latlng, {
        radius: radiusM,
        color: '#7A8BFF',
        fillColor: '#7A8BFF',
        fillOpacity: 0.25,
        weight: 3,
        dashArray: '8 5',
      }).addTo(map);
    }

    // Centralização assertiva: se o mapa estiver longe ou acabamos de receber coordenadas, voa pra lá
    const currentCenter = map.getCenter();
    const dist = map.distance(currentCenter, L.latLng(centerLat, centerLng));
    
    // Se a distância for maior que o raio ou o mapa estiver no centro padrão (SP), foca no CEP/clique
    if (dist > radiusM || (Math.abs(currentCenter.lat - (-23.55)) < 0.1)) {
       map.setView(latlng, 13, { animate: true });
    }
  }, [mapReady, centerLat, centerLng, radiusKm]);

  // ── Atualiza marcadores de leads ─────────────────────────────────────

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    // Nova busca iniciada — reseta o fit automático
    if (leads.length === 0) {
      hasFittedRef.current = false;
    }

    // Apenas leads pendentes ficam visíveis no mapa
    const visibleIds = new Set(
      leads.filter(l => l.status === 'pending').map(l => l.id)
    );

    // Remove marcadores de leads que saíram ou foram processados
    for (const id of Object.keys(markersRef.current)) {
      if (!visibleIds.has(id)) {
        markersRef.current[id].remove();
        delete markersRef.current[id];
      }
    }

    // Adiciona ou atualiza — só pendentes
    for (const lead of leads) {
      if (lead.status !== 'pending' || lead.icp_tier === 'C') continue;

      // Resolve coordenadas — fallback para o centro da busca se o lead não tiver posição
      let lat: number, lng: number;
      
      const leadLat = parseFloat(String(lead.lat));
      const leadLng = parseFloat(String(lead.lng));

      if (!isNaN(leadLat) && !isNaN(leadLng) && leadLat !== 0 && leadLng !== 0) {
        lat = leadLat;
        lng = leadLng;
      } else if (centerLat != null && centerLng != null) {
        // Jitter determinístico baseado no nome para não sobrepor tudo no mesmo ponto
        const h = (lead.name || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0);
        lat = centerLat + ((h % 200) - 100) / 250 * (radiusKm / 111);
        lng = centerLng + ((h % 150) - 75) / 250 * (radiusKm / 111);
      } else {
        continue;
      }

      try {
        const isSelected = lead.id === selectedLeadId;
        const tier = (lead.icp_tier as 'A' | 'B') ?? 'B';
        const tierColor = tier === 'A' ? '#34d17c' : '#f59e0b';
        const proxiedLogo = lead.logo_url ? buildProxyImageUrl(lead.logo_url) || lead.logo_url : null;
        const icon = makeIcon(tier, isSelected, lead.status, zoom, proxiedLogo);

        if (markersRef.current[lead.id]) {
          markersRef.current[lead.id].setIcon(icon);
          markersRef.current[lead.id].setLatLng([lat, lng]);
        } else {
          const marker = L.marker([lat, lng], { icon })
            .addTo(map)
            .on('click', (e) => {
                L.DomEvent.stopPropagation(e);
                onLeadClick(lead);
            })
            .on('mouseover', () => {
              onLeadHover?.(lead);
            })
            .on('mouseout', () => {
              onLeadHover?.(null);
            });

          const initials = (lead.name || 'E').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
          const avatarUrl = lead.logo_url ? buildProxyImageUrl(lead.logo_url) || lead.logo_url : `https://ui-avatars.com/api/?name=${encodeURIComponent(initials)}&background=6366f1&color=fff&bold=true`;

          marker.bindTooltip(
            `<div style="
              background: #141414; 
              border: 1px solid rgba(255,255,255,0.12); 
              border-radius: 8px; 
              padding: 8px 12px; 
              color: #fff; 
              box-shadow: 0 4px 12px rgba(0,0,0,0.4);
              min-width: 140px;
            ">
              <div style="font-weight: 800; font-size: var(--font-base); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;">
                ${lead.name}
              </div>
              <div style="display: flex; align-items: center; gap: 6px; margin-top: 2px;">
                <span style="font-size: var(--font-xs); font-weight: 900; color: ${tierColor}; text-transform: uppercase;">Tier ${tier}</span>
                <span style="font-size: var(--font-xs); color: rgba(255,255,255,0.4);">·</span>
                <span style="font-size: var(--font-sm); font-weight: 700; color: ${(lead.status as string) === 'created' ? '#3b82f6' : (tier === 'A' ? '#34d17c' : '#f59e0b')}">
                  ${(lead.status as string) === 'created' ? '✓ Aprovado' : lead.icp_score + ' pts'}
                </span>
              </div>
              ${lead.address ? `
                <div style="margin-top: 6px; font-size: var(--font-xs); color: rgba(255,255,255,0.5); line-height: 1.3; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 4px; max-width: 200px;">
                  ${lead.address}
                </div>
              ` : ''}
            </div>`,
            { direction: 'top', className: 'prospect-tooltip-rich', permanent: false, sticky: true, offset: [0, -10] }
          );

          markersRef.current[lead.id] = marker;
        }
      } catch (e) {
        console.warn("[ProspectMap] Erro ao renderizar lead:", lead.name, e);
      }
    }

    // Ajuste de zoom automático
    if (!hasFittedRef.current && Object.keys(markersRef.current).length > 0) {
      hasFittedRef.current = true;
      try {
        const positions = Object.values(markersRef.current).map(m => m.getLatLng());
        if (positions.length === 1) {
          map.setView(positions[0], 13, { animate: true });
        } else if (positions.length > 1) {
          map.fitBounds(L.latLngBounds(positions), { padding: [48, 48], maxZoom: 13, animate: true });
        }
      } catch { /* ignora */ }
    }
  }, [leads, selectedLeadId, onLeadClick, onLeadHover, mapReady, centerLat, centerLng, radiusKm, zoom]);

  // ── Centraliza no lead selecionado ───────────────────────────────────

  useEffect(() => {
    if (!mapReady || !selectedLeadId || !markersRef.current[selectedLeadId]) return;
    const marker = markersRef.current[selectedLeadId];
    mapRef.current?.setView(marker.getLatLng(), Math.max(mapRef.current?.getZoom() || 13, 15), { animate: true });
  }, [selectedLeadId, mapReady]);

  return (
    <>
      <div 
        ref={containerRef} 
        style={{ 
          width: '100%', 
          height: '100%', 
          background: 'var(--sw-graph-bg)',
          pointerEvents: disabled ? 'none' : 'auto',
          opacity: disabled ? 0.8 : 1
        }} 
      />
      <style>{`
        .leaflet-tooltip.prospect-tooltip-rich {
          background: transparent !important;
          border: none !important;
          box-shadow: none !important;
          padding: 0 !important;
        }
        .leaflet-tooltip.prospect-tooltip-rich:before {
          display: none !important;
        }
        .leaflet-container { background: var(--sw-graph-bg) !important; }
        .leaflet-tile { 
          filter: var(--sw-map-filter); 
        }
        .leaflet-bar,
        .leaflet-control-zoom {
          border: var(--sw-border-width) solid var(--sw-border) !important;
          border-radius: var(--radius-md) !important;
          box-shadow: var(--sw-shadow) !important;
          background: var(--sw-sidebar) !important;
          overflow: hidden !important;
          padding: 2px !important;
        }
        .leaflet-top .leaflet-control-zoom {
          margin-top: 16px !important;
          margin-left: 16px !important;
        }
        [data-theme='light'] .leaflet-bar,
        [data-theme='light'] .leaflet-control-zoom,
        html[data-theme='light'] .leaflet-bar,
        html[data-theme='light'] .leaflet-control-zoom {
          box-shadow: 0 8px 32px rgba(255, 255, 255, 0.3) !important;
        }
        .leaflet-bar a,
        .leaflet-control-zoom a { 
          background: transparent !important; 
          border: none !important;
          border-bottom: var(--sw-border-width) solid var(--sw-border) !important; 
          color: var(--sw-text-muted) !important; 
          transition: var(--transition-fast) !important;
          width: 30px !important;
          height: 30px !important;
          line-height: 30px !important;
        }
        .leaflet-bar a:last-child,
        .leaflet-control-zoom a:last-child {
          border-bottom: none !important;
        }
        .leaflet-bar a:hover,
        .leaflet-control-zoom a:hover { 
          background: var(--sw-hover) !important; 
          color: var(--sw-text-base) !important; 
        }
      `}</style>
    </>
  );
}
