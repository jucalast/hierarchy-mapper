"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import { Headset, Phone, PhoneOff, Zap, Mic, MicOff, Volume2, MessageSquare, AlertOctagon, Target, ChevronRight, Loader2 } from "lucide-react";
import { Avatar } from "../ui";
import styles from "./LigacaoView.module.css";
import { apiGet } from "../../services/config";
import { getAvatarUrl, getProxiedUrl } from "../../utils/avatarUtils";

// ── Types ──────────────────────────────────────────────────────────────

interface TranscribedMessage {
  id: string;
  type: "transcription";
  role: "Vendedor" | "Cliente";
  text: string;
  latency_ms?: number;
  buffer_secs?: number;
}

interface PartialState {
  text: string;
  latency_ms?: number;
  buffer_secs?: number;
}

interface LiveCoachingInsight {
  current_step?: string;
  suggestion?: string;
  objection_detected?: boolean;
  objection_handling?: string;
}

interface MeterState {
  rms: number;
  speaking: boolean;
  status: string;
}

interface LigacaoViewProps {
  onBack?: () => void;
  initialData?: any;
}

// ── Component ──────────────────────────────────────────────────────────

export const LigacaoView: React.FC<LigacaoViewProps> = ({ onBack, initialData }) => {
  // 🚀 EXTRAÇÃO E PARSE DE DADOS 🚀
  const contactName = initialData?.contact_name;
  const contactPhone = initialData?.phone;
  
  useEffect(() => {
    console.log("[LigacaoView] Raw initialData received:", initialData);
  }, [initialData]);

  const flightPlan = (() => {
    let raw = initialData?.flight_plan;
    if (!raw) return null;
    
    // Se for string, tenta fazer o parse
    if (typeof raw === 'string') {
      try {
        raw = JSON.parse(raw);
      } catch (e) {
        console.error("[LigacaoView] Error parsing flight_plan string", e);
        return null;
      }
    }
    
    // Normalização agressiva para achar o array de passos
    let stepsArr: any[] = [];
    
    if (Array.isArray(raw.steps)) stepsArr = raw.steps;
    else if (Array.isArray(raw.flight_plan?.steps)) stepsArr = raw.flight_plan.steps;
    else if (Array.isArray(raw.flight_plan)) stepsArr = raw.flight_plan;
    else if (Array.isArray(raw)) stepsArr = raw;

    if (stepsArr.length > 0) {
        // Normaliza cada passo para garantir que tenha label e content
        const normalizedSteps = stepsArr.map(s => {
            if (typeof s === 'string') return { label: "Etapa", content: s };
            
            // Tenta achar qualquer chave que pareça um título ou conteúdo
            // Prioriza as novas chaves 'label' e 'content'
            const label = s.label || s.action || s.name || s.title || s.step || "Etapa";
            const content = s.content || s.suggested_talk_track || s.intention || s.text || s.description || s.desc || s.value || "";
            
            // Fallback total: se não achou nada acima, pega qualquer valor que sobrou
            const remainingKeys = Object.keys(s).filter(k => !['label', 'action', 'name', 'title', 'step'].includes(k));
            const finalContent = content || (remainingKeys.length > 0 ? s[remainingKeys[0]] : "");

            return { label, content: finalContent };
        });
        return { steps: normalizedSteps };
    }
    return null;
  })();

  const [messages, setMessages] = useState<TranscribedMessage[]>([]);
  const [partialMic, setPartialMic] = useState<PartialState | null>(null);
  const [partialSpeaker, setPartialSpeaker] = useState<PartialState | null>(null);
  const [latestInsight, setLatestInsight] = useState<LiveCoachingInsight | null>(null);
  const [isAudioConnected, setIsAudioConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [micMeter, setMicMeter] = useState<MeterState>({ rms: 0, speaking: false, status: "Aguardando" });
  const [speakerMeter, setSpeakerMeter] = useState<MeterState>({ rms: 0, speaking: false, status: "Aguardando" });
  const [vendorAvatarUrl, setVendorAvatarUrl] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<any>(null);
  const isListeningRef = useRef(false);
  const clientScrollRef = useRef<HTMLDivElement>(null);
  const vendorScrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll client transcription
  useEffect(() => {
    if (clientScrollRef.current) {
      clientScrollRef.current.scrollTo({
        top: clientScrollRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  }, [messages, partialSpeaker]);

  // Auto-scroll vendor transcription
  useEffect(() => {
    if (vendorScrollRef.current) {
      vendorScrollRef.current.scrollTo({
        top: vendorScrollRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  }, [messages, partialMic]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      console.log("[LigacaoView] Unmounting, cleaning up...");
      isListeningRef.current = false;
      wsRef.current?.close();
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (_) {}
        recognitionRef.current = null;
      }
    };
  }, []);

  // Load Vendor Avatar
  useEffect(() => {
    try {
      const pipedriveUserStr = localStorage.getItem('pipedrive-current-user');
      if (pipedriveUserStr) {
        const parsed = JSON.parse(pipedriveUserStr);
        if (parsed?.avatar) {
          setVendorAvatarUrl(parsed.avatar);
        }
      }
    } catch (e) {
      console.error("Error loading vendor avatar:", e);
    }
  }, []);

  // Load saved session (messages and latest coaching insights) from database
  useEffect(() => {
    const loadSession = async () => {
      const activityId = initialData?.activity_id;
      const phone = initialData?.phone;
      if (!activityId && !phone) return;

      try {
        const queryParams = [];
        if (activityId) queryParams.push(`activity_id=${activityId}`);
        if (phone) queryParams.push(`phone=${encodeURIComponent(phone)}`);
        const queryString = queryParams.join('&');

        const data = await apiGet(`/calls/session?${queryString}`);
        if (data && data.ok) {
          if (data.messages) {
            setMessages(data.messages);
          }
          if (data.latest_insight) {
            setLatestInsight(data.latest_insight);
          }
        }
      } catch (err) {
        console.error("Failed to load active call session from DB:", err);
      }
    };

    void loadSession();
  }, [initialData]);

  // ── Web Speech API (Vendedor / Mic) ──────────────────────────────────
  const startMicRecognition = useCallback(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("SpeechRecognition is not supported in this browser.");
      setMicMeter((p) => ({ ...p, status: "Não suportado" }));
      return;
    }

    if (recognitionRef.current) {
      console.log("[LigacaoView] previous recognition exists, aborting and waiting for browser to release microphone...");
      try {
        recognitionRef.current.abort();
      } catch (_) {}
      
      // Clear immediately to prevent onend from restarting it
      recognitionRef.current = null;

      setTimeout(() => {
        console.log("[LigacaoView] Retrying startMicRecognition after 300ms wait...");
        startMicRecognition();
      }, 300);
      return;
    }

    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;

    recognition.lang = "pt-BR";
    recognition.continuous = true;
    recognition.interimResults = true;

    let consecutiveErrors = 0;

    recognition.onstart = () => {
      if (recognition !== recognitionRef.current) return;
      console.log("[LigacaoView] Speech recognition started.");
      consecutiveErrors = 0;
      setMicMeter((p) => ({ ...p, speaking: true, status: "Ouvindo..." }));
    };

    recognition.onresult = (event: any) => {
      if (recognition !== recognitionRef.current) return;
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) final += event.results[i][0].transcript;
        else interim += event.results[i][0].transcript;
      }

      if (final) {
        const text = final.trim();
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "transcription", role: "Vendedor", text },
        ]);
        setPartialMic(null);
        wsRef.current?.readyState === WebSocket.OPEN &&
          wsRef.current.send(JSON.stringify({ type: "vendedor_transcription", text }));
      } else if (interim) {
        setPartialMic({ text: interim.trim() });
        setMicMeter((p) => ({ ...p, speaking: true }));
      }
    };

    recognition.onerror = (e: any) => {
      if (recognition !== recognitionRef.current) return;
      
      // Ignore programmatic aborts or normal no-speech events
      if (e.error === "aborted" || e.error === "no-speech") {
        console.log(`Speech recognition status event: ${e.error}`);
        return;
      }
      
      console.error("Speech recognition error:", e.error);
      
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        isListeningRef.current = false;
        setIsAudioConnected(false);
        wsRef.current?.close();
        setMicMeter((p) => ({ ...p, speaking: false, status: "Sem permissão ao microfone" }));
      } else {
        consecutiveErrors++;
        if (consecutiveErrors > 5) {
          console.warn("Too many consecutive speech recognition errors, stopping.");
          isListeningRef.current = false;
          setIsAudioConnected(false);
          wsRef.current?.close();
          setMicMeter((p) => ({ ...p, speaking: false, status: "Erro no microfone" }));
        }
      }
    };

    recognition.onend = () => {
      console.log("[LigacaoView] Speech recognition ended.");
      if (recognition !== recognitionRef.current) {
        return;
      }
      if (isListeningRef.current) {
        console.log("[LigacaoView] isListening is true, restarting recognition in 1s...");
        setTimeout(() => {
          if (recognition === recognitionRef.current && isListeningRef.current) {
            try {
              recognition.start();
            } catch (err) {
              console.error("Failed to restart speech recognition:", err);
            }
          }
        }, 1000);
      } else {
        setMicMeter((p) => ({ ...p, speaking: false, status: "Aguardando" }));
        recognitionRef.current = null; // Indicate to startMicRecognition that it's fully stopped!
      }
    };

    const tryStart = (retries = 3) => {
      try {
        recognition.start();
      } catch (err: any) {
        console.error("Error starting speech recognition:", err);
        const isAlreadyStarted = err.message?.includes("already started") || err.name === "InvalidStateError";
        if (retries > 0 && isAlreadyStarted) {
          console.log(`SpeechRecognition still stopping/active, retrying in 200ms... (${retries} retries left)`);
          setTimeout(() => {
            if (recognition === recognitionRef.current && isListeningRef.current) {
              tryStart(retries - 1);
            }
          }, 200);
        } else {
          setMicMeter((p) => ({ ...p, speaking: false, status: "Erro ao iniciar" }));
        }
      }
    };

    tryStart();
  }, []);

  // ── WebSocket ─────────────────────────────────────────────────────────
  const connect = useCallback(() => {
    console.log("[LigacaoView] Connecting WebSocket...");
    setIsConnecting(true);

    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (_) {}
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const queryParams = [];
    if (initialData?.activity_id) {
      queryParams.push(`activity_id=${initialData.activity_id}`);
    }
    if (initialData?.phone) {
      queryParams.push(`phone=${encodeURIComponent(initialData.phone)}`);
    }
    const queryString = queryParams.length > 0 ? `?${queryParams.join("&")}` : "";
    const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
    const ws = new WebSocket(`${protocol}//${host}:8000/api/v1/calls/ws${queryString}`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (ws !== wsRef.current) return;
      console.log("[LigacaoView] WebSocket opened.");
      setIsAudioConnected(true);
      setIsConnecting(false);
      isListeningRef.current = true;
      startMicRecognition();
    };

    ws.onmessage = (event) => {
      if (ws !== wsRef.current) return;
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case "transcription":
            setMessages((prev) => [
              ...prev,
              { id: crypto.randomUUID(), ...data } as TranscribedMessage,
            ]);
            if (data.role === "Vendedor") setPartialMic(null);
            else setPartialSpeaker(null);
            break;

          case "partial_transcription":
            if (data.role === "Vendedor")
              setPartialMic(data.text ? { text: data.text, latency_ms: data.latency_ms, buffer_secs: data.buffer_secs } : null);
            else
              setPartialSpeaker(data.text ? { text: data.text, latency_ms: data.latency_ms, buffer_secs: data.buffer_secs } : null);
            break;

          case "insight":
          case "live_coaching":
            setLatestInsight(data.data || data.text);
            break;

          case "debug_audio":
            if (data.source === "mic")
              setMicMeter((p) => ({ ...p, rms: data.rms, speaking: data.is_speaking }));
            else
              setSpeakerMeter((p) => ({ ...p, rms: data.rms, speaking: data.is_speaking }));
            break;

          case "status":
            if (data.source === "mic")
              setMicMeter((p) => ({ ...p, status: data.status }));
            else
              setSpeakerMeter((p) => ({ ...p, status: data.status }));
            break;

          case "error":
            console.error("Backend error:", data.message);
            break;
        }
      } catch (e) {
        console.error("WS parse error", e);
      }
    };

    ws.onclose = () => {
      if (ws !== wsRef.current) return;
      console.log("[LigacaoView] WebSocket closed.");
      setIsAudioConnected(false);
      setIsConnecting(false);
    };

    ws.onerror = () => {
      if (ws !== wsRef.current) return;
      console.error("[LigacaoView] WebSocket error.");
      setIsAudioConnected(false);
      setIsConnecting(false);
    };
  }, [startMicRecognition, initialData]);

  const stopAudio = useCallback(() => {
    console.log("[LigacaoView] Stopping audio...");
    isListeningRef.current = false;
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (_) {}
      wsRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch (_) {}
      // Clear immediately to prevent onend from restarting it
      recognitionRef.current = null;
    }
    setIsAudioConnected(false);
    setIsConnecting(false);
    setPartialMic(null);
    setPartialSpeaker(null);
    setMicMeter((p) => ({ ...p, speaking: false, status: "Aguardando" }));
    setSpeakerMeter((p) => ({ ...p, speaking: false, status: "Aguardando" }));
  }, []);

  const handleHangup = useCallback(() => {
    // Send FINALIZE signal so the backend knows the call was successfully completed and should be saved
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: "FINALIZE" }));
      } catch (err) {
        console.error("Failed to send FINALIZE message:", err);
      }
    }
    stopAudio();
    // Dispara evento para o agente saber que a ligação terminou e ele pode sugerir ações
    window.dispatchEvent(new CustomEvent('call_ended', { 
        detail: { 
            contactName, 
            phone: contactPhone,
            transcriptCount: messages.length 
        } 
    }));

    if (onBack) onBack();
  }, [contactName, contactPhone, messages.length, onBack, stopAudio]);

  const toggleTranscription = () => {
    if (isAudioConnected) {
      stopAudio();
    } else {
      connect();
    }
  };

  // ── Helpers ───────────────────────────────────────────────────────────
  const meterWidth = (rms: number) => Math.min(100, rms * 80000);

  const getActiveStepIndex = () => {
    if (!latestInsight?.current_step || !flightPlan?.steps) return -1;
    const currentClean = latestInsight.current_step.toLowerCase().trim();
    
    // Tenta encontrar uma correspondência
    return flightPlan.steps.findIndex((step: any) => {
      const labelClean = (step.label || '').toLowerCase().trim();
      return labelClean.includes(currentClean) || currentClean.includes(labelClean);
    });
  };
  const activeIdx = getActiveStepIndex();

  const clientAvatarRaw = getAvatarUrl(initialData);
  const clientAvatarUrl = clientAvatarRaw ? getProxiedUrl(clientAvatarRaw) : null;
  const clientFallbackUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(contactName || "Cliente")}&background=6366f1&color=fff&bold=true&rounded=true&size=120`;
  const resolvedClientUrl = clientAvatarUrl || clientFallbackUrl;

  const vendorAvatarProxied = vendorAvatarUrl ? getProxiedUrl(vendorAvatarUrl) : null;
  const vendorFallbackUrl = `https://ui-avatars.com/api/?name=Voc%C3%AA&background=10b981&color=fff&size=200&font-size=0.4&rounded=true`;
  const resolvedVendorUrl = vendorAvatarProxied || vendorFallbackUrl;

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className={styles.root}>
      {/* ── Sidebar ── */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarBody}>
          {/* RENDERIZAÇÃO DO PLANO DE VOO (S.P.I.N) EM FORMATO DE PIPELINE/TIMELINE */}
          {flightPlan && flightPlan.steps && Array.isArray(flightPlan.steps) && (
            <div className={styles.pipeline}>
              {flightPlan.steps.map((step: any, idx: number) => {
                const isActive = idx === activeIdx;
                const isPast = idx < activeIdx;
                return (
                  <div key={idx} className={styles.pipelineRow}>
                    <div className={styles.pipelineSide}>
                      <div className={`${styles.pipelineDot} ${isActive ? styles.active : ''} ${isPast ? styles.past : ''}`} />
                      {idx < flightPlan.steps.length - 1 && (
                        <div className={`${styles.pipelineLine} ${isPast ? styles.active : ''}`} />
                      )}
                    </div>
                    <div className={styles.pipelineCard}>
                      <strong className={`${styles.pipelineStepLabel} ${isActive ? styles.active : ''}`}>
                        {step.label}
                      </strong>
                      <span className={`${styles.pipelineStepContent} ${isActive ? styles.active : ''}`}>
                        {step.content}
                      </span>
                      
                      {/* Se for a etapa ativa, aninhamos o Copiloto/Agent diretamente dentro dela */}
                      {isActive && latestInsight && (
                        <div className={styles.coachingInnerContainer} style={{ marginTop: 12 }}>
                          {latestInsight.suggestion && (
                            <div className={styles.suggestionBox}>
                              <div className={styles.suggestionHeader}>
                                <MessageSquare size={14} />
                                <span>Sugestão</span>
                              </div>
                              <p>{latestInsight.suggestion}</p>
                            </div>
                          )}
                          {latestInsight.objection_handling && (
                            <div className={styles.objectionBox} style={{ marginTop: 8 }}>
                              <div className={styles.objectionHeader}>
                                <AlertOctagon size={14} />
                                <span>Objeção Detectada!</span>
                              </div>
                              <p>{latestInsight.objection_handling}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Caso não haja plano de voo ou o insight ativo não corresponda a nenhum passo */}
          {(!flightPlan || !flightPlan.steps || activeIdx === -1) && latestInsight && (
            <div className={styles.coachingCard}>
              <div className={styles.insightHeader}>
                <Zap size={14} className={styles.zapIcon} />
                <span>Copiloto Ativo</span>
              </div>
              {latestInsight.current_step && (
                <div className={styles.stepIndicator}>
                  <ChevronRight size={14} />
                  <span>Etapa: {latestInsight.current_step}</span>
                </div>
              )}
              {latestInsight.suggestion && (
                <div className={styles.suggestionBox}>
                  <div className={styles.suggestionHeader}>
                    <MessageSquare size={14} />
                    <span>Sugestão</span>
                  </div>
                  <p>{latestInsight.suggestion}</p>
                </div>
              )}
              {latestInsight.objection_handling && (
                <div className={styles.objectionBox}>
                  <div className={styles.objectionHeader}>
                    <AlertOctagon size={14} />
                    <span>Objeção Detectada!</span>
                  </div>
                  <p>{latestInsight.objection_handling}</p>
                </div>
              )}
            </div>
          )}

          {/* Estado vazio padrão */}
          {!flightPlan && !latestInsight && (
            <div className={styles.emptySidebar}>
              <Headset size={32} strokeWidth={1.2} />
              <p>O Copiloto analisará o áudio em tempo real para sugerir gatilhos do SPIN Selling.</p>
            </div>
          )}
        </div>
      </aside>

      {/* ── Main View (Split Layout) ── */}
      <main className={styles.main}>
        <div className={styles.splitView}>
          
          {/* Left Column: Client */}
          <div className={styles.sideColumn}>
            <div 
              className={styles.columnBg} 
              style={{ backgroundImage: `url(${resolvedClientUrl})` }}
            />
            <div className={styles.avatarSection}>
              <div style={{ position: 'relative' }}>
                <div 
                  className={styles.avatarGlow} 
                  style={{ backgroundImage: `url(${resolvedClientUrl})` }}
                />
                <div className={`${styles.avatarRing} ${speakerMeter.speaking ? styles.speaking : ""}`} />
                <Avatar 
                  kind="person" 
                  name={contactName || "Cliente"} 
                  data={initialData}
                  size={120} 
                />
              </div>
              <h2 className={styles.sideName}>{contactName || "Contato"}</h2>
              <div className={styles.statusBadge} style={{ marginTop: 8 }}>
                <div className={`${styles.statusDot} ${styles.active}`} />
                <span>Em Chamada</span>
              </div>
            </div>

            <div className={styles.transcriptionArea} ref={clientScrollRef}>
                {messages.filter(m => m.role === "Cliente").map((msg) => (
                  <div key={msg.id} className={`${styles.bubbleRow} ${styles.cliente}`}>
                    <div className={styles.bubble}>
                      <p className={styles.bubbleText}>{msg.text}</p>
                      {msg.latency_ms != null && (
                        <span className={styles.bubbleMeta}>
                          IA: {msg.latency_ms}ms · {msg.buffer_secs}s
                        </span>
                      )}
                    </div>
                  </div>
                ))}
                
                {partialSpeaker && (
                  <div className={`${styles.bubbleRow} ${styles.cliente} ${styles.partial}`}>
                    <div className={styles.bubble}>
                      <p className={styles.bubbleText}>
                        {partialSpeaker.text || (
                          <span className={styles.typingDots}>
                            <span /><span /><span />
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                )}
                
              </div>
          </div>

          {/* Right Column: Vendor (User) */}
          <div className={styles.sideColumn}>
            <div 
              className={styles.columnBg} 
              style={{ backgroundImage: `url(${resolvedVendorUrl})` }}
            />
            <div className={styles.avatarSection}>
              <div style={{ position: 'relative' }}>
                <div 
                  className={styles.avatarGlow} 
                  style={{ backgroundImage: `url(${resolvedVendorUrl})` }}
                />
                <div className={`${styles.avatarRing} ${micMeter.speaking ? styles.speaking : ""}`} />
                <Avatar 
                  kind="person" 
                  name="Você"
                  src={vendorAvatarUrl || `https://ui-avatars.com/api/?name=Voc%C3%AA&background=10b981&color=fff&size=200&font-size=0.4&rounded=true`}
                  size={120} 
                />
              </div>
              <h2 className={styles.sideName}>Você</h2>
              <div 
                className={styles.statusBadge} 
                style={{ 
                  marginTop: 8, 
                  opacity: (micMeter.status && micMeter.status !== "Aguardando" && !micMeter.speaking) ? 1 : 0,
                  transition: 'opacity 0.3s'
                }}
              >
                <div className={`${styles.statusDot} ${micMeter.status.includes('Erro') || micMeter.status.includes('Sem permissão') ? styles.error : styles.active}`} />
                <span>{micMeter.status}</span>
              </div>
            </div>

            <div className={styles.transcriptionArea} ref={vendorScrollRef}>
                {messages.filter(m => m.role === "Vendedor").map((msg) => (
                  <div key={msg.id} className={`${styles.bubbleRow} ${styles.vendedor}`}>
                    <div className={styles.bubble}>
                      <p className={styles.bubbleText}>{msg.text}</p>
                    </div>
                  </div>
                ))}
                
                {partialMic && (
                  <div className={`${styles.bubbleRow} ${styles.vendedor} ${styles.partial}`}>
                    <div className={styles.bubble}>
                      <p className={styles.bubbleText}>
                        {partialMic.text || (
                          <span className={styles.typingDots}>
                            <span /><span /><span />
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                )}


              </div>
          </div>
        </div>

        {/* Call control buttons directly on screen */}
        <div style={{ position: 'absolute', bottom: 32, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 16, alignItems: 'center', zIndex: 10 }}>
          <button className={`${styles.controlBtn} ${styles.hangup}`} onClick={handleHangup}>
            <PhoneOff size={20} />
            <span>Desligar</span>
          </button>

          <button 
            className={`${styles.transcriptionToggleBtn} ${isAudioConnected ? styles.active : ''} ${isConnecting ? styles.connecting : ''}`}
            onClick={toggleTranscription}
            disabled={isConnecting}
            title={isAudioConnected ? "Desativar Transcrição" : "Ativar Transcrição"}
          >
            {isConnecting ? (
              <Loader2 size={20} className={styles.spin} />
            ) : isAudioConnected ? (
              <Mic size={20} />
            ) : (
              <MicOff size={20} />
            )}
          </button>
        </div>
      </main>
    </div>
  );
};
