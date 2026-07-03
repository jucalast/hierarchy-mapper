import { useState, useEffect, useCallback, useRef } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function apiPost(path: string, body: object) {
  const r = await fetch(`${API}/api/v1${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.statusText); }
  return r.json();
}
async function apiGet(path: string) {
  const r = await fetch(`${API}/api/v1${path}`);
  if (!r.ok) throw new Error(r.statusText);
  return r.json();
}

export interface ProspectLead {
  id: string;
  name: string;
  domain?: string;
  logo_url?: string;
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
  address?: string;
}

export interface ProspectSession {
  id: string;
  status: 'running' | 'completed' | 'failed';
  city_name?: string;
  lat?: string;
  lng?: string;
  radius_km?: number;
  total_found: number;
  error_message?: string;
}

export function useProspecting() {
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(() => {
    if (typeof window !== 'undefined') {
        const saved = localStorage.getItem('prospect_coords');
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                if (parsed && typeof parsed.lat === 'number' && typeof parsed.lng === 'number' && !isNaN(parsed.lat) && !isNaN(parsed.lng)) {
                    return parsed;
                }
            } catch (e) {
                console.error("[useProspecting] Erro ao carregar coords:", e);
            }
        }
    }
    return null;
  });
  const [radiusKm, setRadiusKm] = useState(() => {
    if (typeof window !== 'undefined') {
        const saved = localStorage.getItem('prospect_radius');
        return saved ? Number(saved) : 50;
    }
    return 50;
  });
  const [geoLoading, setGeoLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<ProspectSession | null>(null);
  const [leads, setLeads] = useState<ProspectLead[]>([]);
  const [selectedLead, setSelectedLead] = useState<ProspectLead | null>(null);

  // Sync selectedLead ID to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
        if (selectedLead) {
            localStorage.setItem('prospect_selected_lead_id', selectedLead.id);
        } else {
            localStorage.removeItem('prospect_selected_lead_id');
        }
    }
  }, [selectedLead]);

  // Restore selectedLead from leads once leads are loaded/updated
  useEffect(() => {
    if (typeof window !== 'undefined' && !selectedLead && leads.length > 0) {
        const savedId = localStorage.getItem('prospect_selected_lead_id');
        if (savedId) {
            const matched = leads.find(l => l.id === savedId);
            if (matched) {
                setSelectedLead(matched);
            }
        }
    }
  }, [leads, selectedLead]);
  const [cityName, setCityName] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
        return localStorage.getItem('prospect_city') || null;
    }
    return null;
  });
  const [cep, setCep] = useState(() => {
    if (typeof window !== 'undefined') {
        return localStorage.getItem('prospect_cep') || '';
    }
    return '';
  });
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const failedCepRef = useRef<string | null>(null);

  // ── Busca por CEP ────────────────────────────────────────────────────

  const lookupCep = useCallback(async (cep: string) => {
    const clean = cep.replace(/\D/g, '');
    if (clean.length !== 8) { 
        const msg = 'CEP inválido — use 8 dígitos.';
        setError(msg);
        throw new Error(msg); 
    }
    setGeoLoading(true);
    setError(null);
    try {
      // BrasilAPI retorna coordenadas diretas na v2
      const res = await fetch(`https://brasilapi.com.br/api/cep/v2/${clean}`);
      if (!res.ok) throw new Error('CEP não encontrado.');
      const data = await res.json();

      const hasValidCoords = data.location?.coordinates && 
                           typeof data.location.coordinates.latitude === 'string' && 
                           typeof data.location.coordinates.longitude === 'string';

      if (hasValidCoords) {
        const { longitude, latitude } = data.location.coordinates;
        const lat = parseFloat(latitude);
        const lng = parseFloat(longitude);
        if (!isNaN(lat) && !isNaN(lng)) {
            setCoords({ lat, lng });
            setCityName(data.city);
            failedCepRef.current = null;
            return;
        }
      }
      
      // Fallback: geocodifica a cidade via Nominatim com tentativas progressivas
      setCityName(data.city); // Seta logo a cidade pra dar feedback

      const queries = [
        [data.street, data.neighborhood, data.city, data.state, 'Brasil'].filter(Boolean).join(', '),
        [data.street, data.city, data.state, 'Brasil'].filter(Boolean).join(', '),
        [data.city, data.state, 'Brasil'].filter(Boolean).join(', ')
      ];

      let found = false;
      for (const query of queries) {
        try {
          const geoRes = await fetch(
            `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1&countrycodes=br`,
            { headers: { 'User-Agent': 'LINKB2B-ProspectingModule/1.0' } }
          );
          if (!geoRes.ok) continue;
          const geo = await geoRes.json();
          if (geo[0]) {
            const lat = parseFloat(geo[0].lat);
            const lng = parseFloat(geo[0].lon);
            if (!isNaN(lat) && !isNaN(lng)) {
                setCoords({ lat, lng });
                found = true;
                failedCepRef.current = null;
                break;
            }
          }
        } catch (err) {
          console.warn("Falha no fallback Nominatim para query:", query, err);
          continue;
        }
      }

      if (!found) {
        failedCepRef.current = clean;
        const msg = 'CEP encontrado mas não conseguimos localizar no mapa. Clique no mapa para definir.';
        setError(msg);
        throw new Error(msg);
      }
    } catch (e: any) {
      failedCepRef.current = clean;
      setError(e.message || 'Erro ao buscar CEP.');
      throw e; // Re-throw to be caught by the component
    } finally {
      setGeoLoading(false);
    }
  }, []);

  // Salva no localStorage quando muda
  useEffect(() => {
    if (typeof window !== 'undefined') {
        localStorage.setItem('prospect_radius', radiusKm.toString());
        
        if (cityName) localStorage.setItem('prospect_city', cityName);
        else localStorage.removeItem('prospect_city');

        if (cep) localStorage.setItem('prospect_cep', cep);
        else localStorage.removeItem('prospect_cep');

        if (coords) localStorage.setItem('prospect_coords', JSON.stringify(coords));
        else localStorage.removeItem('prospect_coords');
    }
  }, [radiusKm, cityName, cep, coords]);

  // Auto-recovery: Se tem CEP mas não tem coords, tenta buscar
  useEffect(() => {
    const clean = cep.replace(/\D/g, '');
    if (clean.length === 8 && !coords && !geoLoading && failedCepRef.current !== clean) {
      console.log(`[useProspecting] CEP detectado (${clean}) sem coordenadas. Recuperando...`);
      lookupCep(clean).catch(() => {});
    }
  }, [cep, coords, geoLoading, lookupCep]);

  // ── Carregar Pendentes ────────────────────────────────────────────────

  const fetchPendingLeads = useCallback(async () => {
    try {
      const data = await apiGet('/prospecting/leads/pending');
      if (data && data.leads) {
        setLeads(prev => {
          const existingIds = new Set(prev.map(l => l.id));
          const newLeads = data.leads.filter((l: ProspectLead) => !existingIds.has(l.id));
          const result = [...prev, ...newLeads];
          result.sort((a, b) => b.icp_score - a.icp_score);
          return result;
        });
      }

      // Restaura a localização/status da última sessão
      const sessionsData = await apiGet('/prospecting/sessions?limit=1');
      if (sessionsData && sessionsData.length > 0) {
        const lastSession = sessionsData[0];
        setSessionId(lastSession.id);
        setSession(lastSession);
        if (lastSession.lat !== undefined && lastSession.lng !== undefined) {
            setCoords({ lat: Number(lastSession.lat), lng: Number(lastSession.lng) });
        }
        if (lastSession.radius_km !== undefined) {
            setRadiusKm(Number(lastSession.radius_km));
        }
        if (lastSession.city_name) {
            setCityName(lastSession.city_name);
        }
      }
    } catch (e: any) {
      // Falha silenciosa para não poluir o console do usuário durante o boot do backend
      // Se for um erro real após o boot, ele aparecerá em tentativas subsequentes ou ações do usuário
    }
  }, []);

  useEffect(() => {
    fetchPendingLeads();
  }, [fetchPendingLeads]);

  // ── Geolocalização ────────────────────────────────────────────────────

  const geolocate = useCallback(async () => {
    if (!navigator.geolocation) {
      setError('Geolocalização não suportada neste navegador.');
      return;
    }

    // Checa permissão antes de solicitar para evitar erros de Permissions Policy
    if (navigator.permissions) {
      try {
        const perm = await navigator.permissions.query({ name: 'geolocation' });
        if (perm.state === 'denied') {
          setError('Permissão de localização negada. Clique no mapa para definir o ponto central.');
          return;
        }
      } catch {
        // permissions API pode não estar disponível em alguns browsers — prossegue
      }
    }

    setGeoLoading(true);
    try {
      navigator.geolocation.getCurrentPosition(
        p => { setCoords({ lat: p.coords.latitude, lng: p.coords.longitude }); setGeoLoading(false); },
        err => {
          const msg = err.code === 1
            ? 'Permissão negada. Clique no mapa para definir o ponto central.'
            : 'Não foi possível obter a localização.';
          setError(msg);
          setGeoLoading(false);
        },
        { timeout: 8000, enableHighAccuracy: false },
      );
    } catch {
      // Permissions Policy bloqueou a chamada (iframe, HTTP sem HTTPS, etc.)
      setError('Localização bloqueada pelo navegador. Clique no mapa para definir o ponto central.');
      setGeoLoading(false);
    }
  }, []);

  // ── Polling ───────────────────────────────────────────────────────────

  const fetchStatus = useCallback(async (id: string) => {
    try {
      const [sessData, leadsData] = await Promise.all([
        apiGet(`/prospecting/sessions/${id}`),
        apiGet(`/prospecting/sessions/${id}/leads`),
      ]);
      setSession(sessData);
      if (sessData.city_name) setCityName(sessData.city_name);
      const incoming: ProspectLead[] = (leadsData.leads || []);
      setLeads(prev => {
        // Preserva leads pendentes ou já criados de outras sessões/fontes que não estão no pacote atual
        const otherLeads = prev.filter(l => 
          (l.status === 'pending' || l.status === 'created') && 
          l.id && 
          !incoming.find(il => il.id === l.id)
        );
        const merged = [...otherLeads, ...incoming];
        merged.sort((a, b) => b.icp_score - a.icp_score);
        return merged;
      });
      setSelectedLead(prev => prev ? (incoming.find(l => l.id === prev.id) ?? prev) : null);
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

  // ── Search / Stop ─────────────────────────────────────────────────────

  const startSearch = useCallback(async () => {
    if (!coords) return; // botão já fica disabled sem coords — fallback: clique no mapa
    setError(null);
    setLeads([]);
    setSession(null);
    setSelectedLead(null);
    setSearching(true);
    try {
      const res = await apiPost('/prospecting/search', { lat: coords.lat, lng: coords.lng, radius_km: radiusKm });
      setSessionId(res.session_id);
    } catch (e: any) {
      setError(e.message);
      setSearching(false);
    }
  }, [coords, radiusKm, geolocate]);

  const stopSearch = useCallback(async () => {
    if (sessionId) {
      try {
        await apiPost(`/prospecting/sessions/${sessionId}/stop`, {});
      } catch (e) {
        console.warn("Erro ao parar no backend:", e);
        // A chamada de stop pode não ter chegado ao servidor (falha de rede) —
        // avisa o usuário em vez de só fingir que a busca parou.
        setError("Não foi possível confirmar a parada no servidor; a busca pode continuar em segundo plano.");
      }
    }
    clearInterval(pollRef.current!);
    setSearching(false);
    setSession(prev => prev ? { ...prev, status: 'failed' } : null);
  }, [sessionId]);

  // ── Lead actions ──────────────────────────────────────────────────────

  const updateLead = useCallback((id: string, status: ProspectLead['status']) => {
    setLeads(prev => prev.map(l => l.id === id ? { ...l, status } : l));
    setSelectedLead(prev => prev?.id === id ? { ...prev, status } : prev);
  }, []);

  const approveLead = useCallback(async (id: string) => {
    await apiPost(`/prospecting/leads/${id}/approve`, {});
    updateLead(id, 'created');
  }, [updateLead]);

  const rejectLead = useCallback(async (id: string) => {
    await apiPost(`/prospecting/leads/${id}/reject`, {});
    updateLead(id, 'rejected');
  }, [updateLead]);

  return {
    coords, setCoords,
    radiusKm, setRadiusKm,
    geoLoading,
    cityName,
    session,
    leads,
    selectedLead, setSelectedLead,
    searching,
    error,
    geolocate,
    lookupCep,
    cep, setCep,
    startSearch,
    stopSearch,
    approveLead,
    rejectLead,
    refreshPendingLeads: fetchPendingLeads,
  };
}
