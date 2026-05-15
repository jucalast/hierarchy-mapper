'use client';

import React, {
  useState, useEffect, useCallback, useRef,
} from 'react';
import dynamic from 'next/dynamic';
import {
  X, Loader2, CheckCircle, XCircle, MapPin, Radar,
  ChevronDown, ChevronUp, ExternalLink, Building2,
  TrendingUp, Tag, AlertCircle, Navigation,
} from 'lucide-react';
import { Badge, Button } from '@/components/ui';

// Leaflet importado dinamicamente (não roda no servidor)
const Map = dynamic(() => import('./ProspectMap'), { ssr: false, loading: () => <MapPlaceholder /> });

// ─── API ──────────────────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

async function post(path: string, body: object) {
  const r = await fetch(`${API}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText); }
  return r.json();
}

async function get(path: string) {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

// ─── Types ─────────────────────────────────────────────────────────────────

export interface ProspectLead {
  id: string;
  name: string;
  domain?: string;
  segment?: string;
  size_label?: string;
  employee_count?: string;
  exports: boolean;
  linkedin_url?: string;
  description?: string;
  icp_score: number;
  icp_tier: 'A' | 'B' | 'C';
  icp_reasons: string[];
  icp_penalties: string[];
  icp_recommendation: string;
  outreach_angle?: string;
  relevance_signal?: string;
  pipedrive_status: 'new' | 'lost_deal' | 'stale' | 'active';
  pipedrive_deal_info?: { days_inactive?: number; status?: string };
  lat?: string;
  lng?: string;
  status: 'pending' | 'approved' | 'rejected' | 'created';
  pipedrive_created_id?: number;
}

interface Session {
  id: string;
  status: 'running' | 'completed' | 'failed';
  city_name?: string;
  lat?: string;
  lng?: string;
  radius_km?: number;
  total_found: number;
  error_message?: string;
}

// ─── Map placeholder enquanto carrega ─────────────────────────────────────

function MapPlaceholder() {
  return (
    <div style={{
      flex: 1, background: 'var(--sw-bg-canvas)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
      color: 'var(--sw-text-muted)', fontSize: 13,
    }}>
      <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', marginRight: 8 }} />
      Carregando mapa...
    </div>
  );
}

// ─── Score ring ───────────────────────────────────────────────────────────

function ScoreRing({ score, tier }: { score: number; tier: string }) {
  const color = tier === 'A' ? 'var(--sw-success)' : 'var(--sw-warning)';
  const r = 18, circ = 2 * Math.PI * r;
  return (
    <div style={{ position: 'relative', width: 44, height: 44, flexShrink: 0 }}>
      <svg width={44} height={44} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={22} cy={22} r={r} fill="none" stroke="var(--sw-border)" strokeWidth={4} />
        <circle cx={22} cy={22} r={r} fill="none" stroke={color} strokeWidth={4}
          strokeDasharray={circ} strokeDashoffset={circ - (score / 100) * circ}
          strokeLinecap="round" />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, color, lineHeight: 1 }}>{score}</span>
        <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.35)', marginTop: 1 }}>{tier}</span>
      </div>
    </div>
  );
}

// ─── Lead card (bottom sheet) ─────────────────────────────────────────────

function LeadCard({
  lead, onApprove, onReject, onClose,
}: {
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
    try {
      if (action === 'approve') await onApprove(lead.id);
      else await onReject(lead.id);
    } finally { setBusy(null); }
  };

  const pdStatus = lead.pipedrive_status;
  const pdBadge = pdStatus === 'lost_deal'
    ? <Badge tone="danger">Deal perdido</Badge>
    : pdStatus === 'stale'
      ? <Badge tone="warning">{lead.pipedrive_deal_info?.days_inactive ? `Parado ${lead.pipedrive_deal_info.days_inactive}d` : 'Inativo'}</Badge>
      : <Badge tone="success">Novo lead</Badge>;

  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 1000,
      background: '#141414',
      borderTop: '1px solid rgba(255,255,255,0.08)',
      borderRadius: '16px 16px 0 0',
      padding: '4px 0 0',
    }}>
      {/* Drag handle */}
      <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0 4px' }}>
        <div style={{ width: 36, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.15)' }} />
      </div>

      <div style={{ padding: '0 16px 16px' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
          <ScoreRing score={lead.icp_score} tier={lead.icp_tier} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: '#fff' }}>{lead.name}</span>
              {lead.linkedin_url && (
                <a href={lead.linkedin_url} target="_blank" rel="noopener noreferrer"
                  style={{ color: '#60A5FA', display: 'inline-flex' }}>
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
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.3)', padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        {lead.description && (
          <p style={{
            fontSize: 11.5, color: 'rgba(255,255,255,0.5)', lineHeight: 1.5, marginBottom: 8,
            display: '-webkit-box', WebkitLineClamp: expanded ? 'unset' : 2,
            WebkitBoxOrient: 'vertical', overflow: 'hidden',
          }}>{lead.description}</p>
        )}

        {/* Expand toggle */}
        {(lead.icp_reasons.length > 0 || lead.outreach_angle) && (
          <button
            onClick={() => setExpanded(v => !v)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'rgba(255,255,255,0.4)', fontSize: 11, display: 'flex',
              alignItems: 'center', gap: 4, marginBottom: 8, padding: 0,
            }}>
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {expanded ? 'Menos detalhes' : 'Ver razões e ângulo de abordagem'}
          </button>
        )}

        {expanded && (
          <div style={{ marginBottom: 10 }}>
            {lead.icp_reasons.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                {lead.icp_reasons.map((r, i) => (
                  <div key={i} style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', display: 'flex', gap: 5, marginBottom: 2 }}>
                    <span style={{ color: '#34d17c' }}>✓</span> {r}
                  </div>
                ))}
              </div>
            )}
            {lead.outreach_angle && (
              <div style={{
                background: 'rgba(122,139,255,0.07)',
                border: '1px solid rgba(122,139,255,0.18)',
                borderRadius: 8, padding: '7px 10px',
                fontSize: 11, color: 'rgba(255,255,255,0.55)', lineHeight: 1.5,
              }}>
                <div style={{ fontSize: 9, fontWeight: 700, color: '#7A8BFF', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Abordagem sugerida
                </div>
                {lead.outreach_angle}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
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
          {!isDone && (
            <Button variant="success" size="sm" loading={busy === 'approving'}
              leftIcon={<CheckCircle size={12} />} onClick={() => handle('approve')} style={{ flex: 2 }}>
              Criar no Pipedrive
            </Button>
          )}
          {!isDone && (
            <Button variant="ghost" size="sm" loading={busy === 'rejecting'}
              leftIcon={<XCircle size={12} />} onClick={() => handle('reject')} style={{ flex: 1 }}>
              Rejeitar
            </Button>
          )}
          {isDone && (
            <div style={{ flex: 2, textAlign: 'center' }}>
              {lead.status === 'created'
                ? <Badge tone="success" icon={<CheckCircle size={10} />}>Criado no Pipedrive</Badge>
                : <Badge tone="neutral" icon={<XCircle size={10} />}>Rejeitado</Badge>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Painel principal ──────────────────────────────────────────────────────

interface Props { onClose: () => void; theme?: string; }

export const ProspectingPanel: React.FC<Props> = ({ onClose }) => {
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [radiusKm, setRadiusKm] = useState(50);
  const [geoLoading, setGeoLoading] = useState(false);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [leads, setLeads] = useState<ProspectLead[]>([]);
  const [selectedLead, setSelectedLead] = useState<ProspectLead | null>(null);

  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Geolocalização ────────────────────────────────────────────────────

  const requestLocation = () => {
    if (!navigator.geolocation) { setError('Geolocalização não disponível.'); return; }
    setGeoLoading(true);
    navigator.geolocation.getCurrentPosition(
      pos => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoLoading(false);
      },
      () => { setError('Não foi possível obter sua localização.'); setGeoLoading(false); },
      { timeout: 8000 },
    );
  };

  // Auto-solicita localização ao abrir
  useEffect(() => { requestLocation(); }, []);

  // ── Polling ───────────────────────────────────────────────────────────

  const fetchStatus = useCallback(async (id: string) => {
    try {
      const [sessData, leadsData] = await Promise.all([
        get(`/prospecting/sessions/${id}`),
        get(`/prospecting/sessions/${id}/leads`),
      ]);
      setSession(sessData);
      const incoming: ProspectLead[] = (leadsData.leads || []).sort(
        (a: ProspectLead, b: ProspectLead) => b.icp_score - a.icp_score,
      );
      setLeads(incoming);

      // Atualiza lead selecionado se ainda existir
      setSelectedLead(prev => prev ? incoming.find(l => l.id === prev.id) ?? prev : null);

      if (sessData.status !== 'running') {
        clearInterval(pollRef.current!);
        setSearching(false);
      }
    } catch (e: any) {
      setError(e.message);
      clearInterval(pollRef.current!);
      setSearching(false);
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    fetchStatus(sessionId);
    pollRef.current = setInterval(() => fetchStatus(sessionId), 5000);
    return () => clearInterval(pollRef.current!);
  }, [sessionId, fetchStatus]);

  // ── Iniciar busca ─────────────────────────────────────────────────────

  const handleSearch = async () => {
    if (!coords) { requestLocation(); return; }
    setError(null);
    setLeads([]);
    setSession(null);
    setSelectedLead(null);
    setSearching(true);
    try {
      const res = await post('/prospecting/search', {
        lat: coords.lat, lng: coords.lng, radius_km: radiusKm,
      });
      setSessionId(res.session_id);
    } catch (e: any) {
      setError(e.message);
      setSearching(false);
    }
  };

  // ── Ações de lead ─────────────────────────────────────────────────────

  const updateLeadStatus = (id: string, status: ProspectLead['status']) => {
    setLeads(prev => prev.map(l => l.id === id ? { ...l, status } : l));
    setSelectedLead(prev => prev?.id === id ? { ...prev, status } : prev);
  };

  const handleApprove = async (id: string) => {
    await post(`/prospecting/leads/${id}/approve`, {});
    updateLeadStatus(id, 'created');
  };

  const handleReject = async (id: string) => {
    await post(`/prospecting/leads/${id}/reject`, {});
    updateLeadStatus(id, 'rejected');
  };

  // ── Stats ─────────────────────────────────────────────────────────────

  const tierA = leads.filter(l => l.icp_tier === 'A').length;
  const pending = leads.filter(l => l.status === 'pending').length;
  const isRunning = session?.status === 'running';

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 500,
      background: '#0d0d0d',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* ── Top bar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 16px',
        borderBottom: '1px solid rgba(255,255,255,0.07)',
        background: 'rgba(20,20,20,0.95)',
        backdropFilter: 'blur(10px)',
        zIndex: 10,
      }}>
        <Radar size={16} color="#7A8BFF" />
        <span style={{ fontWeight: 600, fontSize: 13, color: '#fff' }}>Prospecção</span>

        {/* Localização */}
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', gap: 8,
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.09)',
          borderRadius: 8, padding: '5px 10px', cursor: 'pointer',
        }} onClick={requestLocation}>
          {geoLoading
            ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite', color: '#7A8BFF' }} />
            : <MapPin size={12} color={coords ? '#34d17c' : 'rgba(255,255,255,0.3)'} />}
          <span style={{ fontSize: 11.5, color: coords ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.3)' }}>
            {coords
              ? session?.city_name
                ? session.city_name
                : `${coords.lat.toFixed(3)}, ${coords.lng.toFixed(3)}`
              : 'Clique para usar localização atual'}
          </span>
        </div>

        {/* Radius */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', whiteSpace: 'nowrap' }}>
            {radiusKm} km
          </span>
          <input
            type="range" min={10} max={200} step={10} value={radiusKm}
            onChange={e => setRadiusKm(Number(e.target.value))}
            style={{ width: 72, accentColor: '#7A8BFF', cursor: 'pointer' }}
          />
        </div>

        {/* Search button */}
        <Button
          variant="primary" size="sm"
          loading={searching}
          leftIcon={<Navigation size={12} />}
          onClick={handleSearch}
          disabled={searching}
          style={{ flexShrink: 0 }}
        >
          {searching ? 'Buscando...' : 'Prospectar'}
        </Button>

        <button onClick={onClose} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'rgba(255,255,255,0.4)', padding: 4, flexShrink: 0,
        }}>
          <X size={16} />
        </button>
      </div>

      {/* ── Status bar ── */}
      {(session || error) && (
        <div style={{
          padding: '7px 16px',
          background: 'rgba(255,255,255,0.02)',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
          display: 'flex', alignItems: 'center', gap: 8, zIndex: 10,
        }}>
          {isRunning && <Loader2 size={12} color="#7A8BFF" style={{ animation: 'spin 1s linear infinite' }} />}
          {session?.status === 'completed' && <CheckCircle size={12} color="#34d17c" />}
          {session?.status === 'failed' && <AlertCircle size={12} color="#ef4444" />}
          {error && <AlertCircle size={12} color="#ef4444" />}

          <span style={{ fontSize: 11.5, color: 'rgba(255,255,255,0.45)', flex: 1 }}>
            {isRunning && `Buscando nos ${7} segmentos ICP em ${session?.city_name || 'sua região'}...`}
            {session?.status === 'completed' && `${leads.length} leads encontrados — ${tierA} Tier A, ${pending} aguardando aprovação`}
            {(session?.status === 'failed' || error) && (session?.error_message || error)}
          </span>

          {leads.length > 0 && (
            <div style={{ display: 'flex', gap: 6 }}>
              {tierA > 0 && <Badge tone="success">{tierA}× Tier A</Badge>}
              <Badge tone="neutral">{leads.length} total</Badge>
            </div>
          )}
        </div>
      )}

      {/* ── Mapa ── */}
      <div style={{ flex: 1, position: 'relative' }}>
        <Map
          disabled={searching}
          centerLat={coords?.lat}
          centerLng={coords?.lng}
          radiusKm={radiusKm}
          leads={leads}
          selectedLeadId={selectedLead?.id}
          onLeadClick={lead => setSelectedLead(prev => prev?.id === lead.id ? null : lead)}
          onMapClick={coords => {
            if (searching) return;
            setCoords(coords);
          }}
        />

        {/* Instrução inicial */}
        {!coords && !geoLoading && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%',
            transform: 'translate(-50%,-50%)',
            background: 'rgba(20,20,20,0.9)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 12, padding: '16px 20px',
            textAlign: 'center', pointerEvents: 'none',
          }}>
            <MapPin size={24} color="rgba(255,255,255,0.2)" style={{ margin: '0 auto 8px' }} />
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)' }}>
              Permita o acesso à localização<br />ou clique no mapa para definir o centro
            </div>
          </div>
        )}
      </div>

      {/* ── Card do lead selecionado (bottom sheet) ── */}
      {selectedLead && (
        <LeadCard
          lead={selectedLead}
          onApprove={handleApprove}
          onReject={handleReject}
          onClose={() => setSelectedLead(null)}
        />
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        input[type=range] { -webkit-appearance: none; height: 3px; border-radius: 2px; background: rgba(255,255,255,0.1); }
        input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 13px; height: 13px; border-radius: 50%; background: #7A8BFF; cursor: pointer; }
      `}</style>
    </div>
  );
};
