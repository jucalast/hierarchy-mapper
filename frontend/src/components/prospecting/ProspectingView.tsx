'use client';

import React, { useState } from 'react';
import dynamic from 'next/dynamic';
import {
  Loader2, CheckCircle, XCircle, ExternalLink,
  Building2, TrendingUp, Tag, ChevronDown, ChevronUp, X,
} from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import type { ProspectLead, ProspectSession } from '@/hooks/useProspecting';
import { buildProxyImageUrl } from '@/services/config';

const ProspectMap = dynamic(() => import('./ProspectMap'), {
  ssr: false,
  loading: () => (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.15)', gap: 8 }}>
      <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
      <span style={{ fontSize: 12 }}>Carregando mapa…</span>
    </div>
  ),
});

// ─── Score ring ───────────────────────────────────────────────────────────

function ScoreRing({ score, tier }: { score: number; tier: string }) {
  const color = tier === 'A' ? '#34d17c' : '#f59e0b';
  const r = 18, circ = 2 * Math.PI * r;
  return (
    <div style={{ position: 'relative', width: 44, height: 44, flexShrink: 0 }}>
      <svg width={44} height={44} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={22} cy={22} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={4} />
        <circle cx={22} cy={22} r={r} fill="none" stroke={color} strokeWidth={4}
          strokeDasharray={circ} strokeDashoffset={circ - (score / 100) * circ} strokeLinecap="round" />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color, lineHeight: 1 }}>{score}</span>
        <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.35)', marginTop: 1 }}>{tier}</span>
      </div>
    </div>
  );
}

// ─── Bottom sheet do lead selecionado ────────────────────────────────────

function LeadSheet({ lead, onApprove, onReject, onClose }: {
  lead: ProspectLead;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
  onClose: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState<'approving' | 'rejecting' | null>(null);
  const isDone = lead.status !== 'pending';

  const handle = async (action: 'approve' | 'reject') => {
    setBusy(action === 'approve' ? 'approving' : 'rejecting');
    try { action === 'approve' ? await onApprove(lead.id) : await onReject(lead.id); }
    finally { setBusy(null); }
  };

  const pdBadge = lead.pipedrive_status === 'lost_deal'
    ? <Badge tone="danger">Deal perdido</Badge>
    : lead.pipedrive_status === 'stale'
      ? <Badge tone="warning">{lead.pipedrive_deal_info?.days_inactive ? `Parado ${lead.pipedrive_deal_info.days_inactive}d` : 'Inativo'}</Badge>
      : <Badge tone="success">Novo lead</Badge>;

  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 20,
      background: 'rgba(16,16,16,0.97)',
      backdropFilter: 'blur(14px)',
      borderTop: '1px solid rgba(255,255,255,0.08)',
      borderRadius: '14px 14px 0 0',
    }}>
      <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0 2px' }}>
        <div style={{ width: 32, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.1)' }} />
      </div>

      <div style={{ padding: '4px 16px 16px' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 8 }}>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
             <ScoreRing score={lead.icp_score} tier={lead.icp_tier} />
             {lead.logo_url && (
               <div style={{
                 position: 'absolute', bottom: -2, right: -2,
                 width: 22, height: 22, borderRadius: 6, overflow: 'hidden',
                 border: '2px solid rgba(16,16,16,0.97)', background: '#1d1d1d',
                 boxShadow: '0 2px 4px rgba(0,0,0,0.5)'
               }}>
                 <img
                   src={buildProxyImageUrl(lead.logo_url) || lead.logo_url}
                   alt={lead.name}
                   style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                   onError={(e) => {
                     const initials = (lead.name || 'E').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
                     e.currentTarget.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(initials)}&background=6366f1&color=fff&bold=true&rounded=true&size=128`;
                   }}
                 />
               </div>
             )}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontWeight: 700, fontSize: 15, color: '#fff' }}>{lead.name}</span>
              {lead.linkedin_url && (
                <a href={lead.linkedin_url} target="_blank" rel="noopener noreferrer" style={{ color: '#60A5FA', display: 'inline-flex' }}>
                  <ExternalLink size={11} />
                </a>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 5 }}>
              {lead.segment && <Badge tone="info" icon={<Tag size={8} />}>{lead.segment}</Badge>}
              {lead.exports && <Badge tone="purple" icon={<TrendingUp size={8} />}>Exporta</Badge>}
              {lead.size_label && <Badge tone="neutral" icon={<Building2 size={8} />}>{lead.size_label}</Badge>}
              {pdBadge}
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.3)', padding: 4, flexShrink: 0 }}>
            <X size={15} />
          </button>
        </div>

        {lead.description && (
          <p style={{
            fontSize: 11.5, color: 'rgba(255,255,255,0.5)', lineHeight: 1.5, marginBottom: 8,
            display: '-webkit-box', WebkitLineClamp: expanded ? 'unset' : 2,
            WebkitBoxOrient: 'vertical', overflow: 'hidden',
          }}>{lead.description}</p>
        )}

        {(lead.icp_reasons.length > 0 || lead.outreach_angle) && (
          <button onClick={() => setExpanded(v => !v)} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.35)',
            fontSize: 11, display: 'flex', alignItems: 'center', gap: 4, marginBottom: 8, padding: 0,
          }}>
            {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            {expanded ? 'Menos' : 'Por que este lead · Ângulo de abordagem'}
          </button>
        )}

        {expanded && (
          <div style={{ marginBottom: 10 }}>
            {lead.icp_reasons.map((r, i) => (
              <div key={i} style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', display: 'flex', gap: 5, marginBottom: 2 }}>
                <span style={{ color: '#34d17c' }}>✓</span>{r}
              </div>
            ))}
            {lead.outreach_angle && (
              <div style={{
                background: 'rgba(122,139,255,0.07)', border: '1px solid rgba(122,139,255,0.15)',
                borderRadius: 8, padding: '7px 10px', fontSize: 11,
                color: 'rgba(255,255,255,0.5)', lineHeight: 1.5, marginTop: 8,
              }}>
                <div style={{ fontSize: 9, fontWeight: 700, color: '#7A8BFF', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Abordagem sugerida
                </div>
                {lead.outreach_angle}
              </div>
            )}
          </div>
        )}

        {!isDone ? (
          <div style={{ display: 'flex', gap: 8 }}>
            {lead.linkedin_url && (
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<img src="/linkedin.png" alt="" style={{ width: 12, height: 12, borderRadius: 2 }} />}
                onClick={() => window.open(lead.linkedin_url, '_blank')}
                style={{ flex: 1, background: '#0077B5', color: '#fff', border: 'none' }}
              >
                LinkedIn
              </Button>
            )}
            <Button variant="success" size="sm" loading={busy === 'approving'}
              leftIcon={<CheckCircle size={12} />} onClick={() => handle('approve')} style={{ flex: 2 }}>
              Criar no Pipedrive
            </Button>
            <Button variant="ghost" size="sm" loading={busy === 'rejecting'}
              leftIcon={<XCircle size={12} />} onClick={() => handle('reject')} style={{ flex: 1 }}>
              Rejeitar
            </Button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 8 }}>
            {lead.linkedin_url && (
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<img src="/linkedin.png" alt="" style={{ width: 12, height: 12, borderRadius: 2 }} />}
                onClick={() => window.open(lead.linkedin_url, '_blank')}
                style={{ flex: 1, background: '#0077B5', color: '#fff', border: 'none' }}
              >
                LinkedIn
              </Button>
            )}
            <div style={{ flex: 2, textAlign: 'center' }}>
              {lead.status === 'created'
                ? <Badge tone="success" icon={<CheckCircle size={10} />}>Criado no Pipedrive</Badge>
                : <Badge tone="neutral" icon={<XCircle size={10} />}>Rejeitado</Badge>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── View principal (só mapa + bottom sheet) ──────────────────────────────

interface ProspectingViewProps {
  coords: { lat: number; lng: number } | null;
  onMapClick: (coords: { lat: number; lng: number }) => void;
  radiusKm: number;
  leads: ProspectLead[];
  selectedLead: ProspectLead | null;
  onLeadClick: (lead: ProspectLead) => void;
  onLeadClose: () => void;
  onApproveLead: (id: string) => Promise<void>;
  onRejectLead: (id: string) => Promise<void>;
  onLeadHover?: (lead: ProspectLead | null) => void;
  session: ProspectSession | null;
}

export function ProspectingView({
  coords, onMapClick, radiusKm,
  leads, selectedLead, onLeadClick, onLeadClose,
  onApproveLead, onRejectLead, onLeadHover,
  session,
}: ProspectingViewProps) {
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: '#1d1d1d' }}>
      <ProspectMap
        centerLat={coords?.lat}
        centerLng={coords?.lng}
        radiusKm={radiusKm}
        leads={leads}
        selectedLeadId={selectedLead?.id}
        onLeadClick={lead => onLeadClick(lead)}
        onLeadHover={onLeadHover}
        onMapClick={onMapClick}
      />

      {!coords && (
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center', pointerEvents: 'none', color: 'rgba(255,255,255,0.2)',
        }}>
          <div style={{ fontSize: 12, lineHeight: 1.7 }}>
            Permita acesso à localização<br />ou clique no mapa para definir o centro
          </div>
        </div>
      )}

      {/* LeadSheet agora está integrado no FloatingToolbar */}
      {/* {selectedLead && (
        <LeadSheet
          lead={selectedLead}
          onApprove={onApproveLead}
          onReject={onRejectLead}
          onClose={onLeadClose}
        />
      )} */}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
