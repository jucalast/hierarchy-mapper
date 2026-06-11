"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import { Headset, Phone, PhoneOff, Zap, Mic, MicOff, Volume2, MessageSquare, AlertOctagon, Target, ChevronRight, Loader2, PhoneForwarded, Bug, X } from "lucide-react";
import { Avatar } from "../ui";
import styles from "./LigacaoView.module.css";
import { apiGet, API_BASE_URL } from "../../services/config";
import { getAvatarUrl, getProxiedUrl } from "../../utils/avatarUtils";

// ── Types ──────────────────────────────────────────────────────────────

interface TranscribedMessage {
  id: string;
  type: "transcription" | "insight";
  role: "Vendedor" | "Cliente" | "Agente";
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
  const companyLogo = initialData?.company_logo;
  
  useEffect(() => {
    console.log("[LigacaoView] Raw initialData received:", initialData);
  }, [initialData]);

  const [activeFlightPlan, setActiveFlightPlan] = useState<any>(null);
  const [isTransferred, setIsTransferred] = useState(false);
  const isCompanyPhone = activeFlightPlan?.is_company_phone === true || activeFlightPlan?.is_company_phone === "true";

  // Helper de parse e normalização de flight_plan
  const parseFlightPlan = useCallback((raw: any) => {
    if (!raw) return null;
    if (typeof raw === 'string') {
      try { raw = JSON.parse(raw); } catch (_) { return null; }
    }
    
    let stepsArr: any[] = [];
    if (Array.isArray(raw.steps)) stepsArr = raw.steps;
    else if (Array.isArray(raw.flight_plan?.steps)) stepsArr = raw.flight_plan.steps;
    else if (Array.isArray(raw.flight_plan)) stepsArr = raw.flight_plan;
    else if (Array.isArray(raw)) stepsArr = raw;

    if (stepsArr.length > 0) {
      const normalizedSteps = stepsArr.map(s => {
        if (typeof s === 'string') return { label: "Etapa", content: s };
        const label = s.label || s.action || s.name || s.title || s.step || "Etapa";
        const content = s.content || s.suggested_talk_track || s.intention || s.text || s.description || s.desc || s.value || "";
        const remainingKeys = Object.keys(s).filter(k => !['label', 'action', 'name', 'title', 'step'].includes(k));
        const finalContent = content || (remainingKeys.length > 0 ? s[remainingKeys[0]] : "");
        return { label, content: finalContent, is_lightning: s.is_lightning === true, suggestions: [], objections: [] };
      });
      let isCompanyPhoneFlag = false;
      if (raw.is_company_phone !== undefined) isCompanyPhoneFlag = raw.is_company_phone;
      else if (raw.flight_plan?.is_company_phone !== undefined) isCompanyPhoneFlag = raw.flight_plan.is_company_phone;

      return { steps: normalizedSteps, is_company_phone: isCompanyPhoneFlag };
    }
    return null;
  }, []);

  // Inicializa o plano de voo
  useEffect(() => {
    if (initialData?.flight_plan) {
      const parsed = parseFlightPlan(initialData.flight_plan);
      if (parsed) {
        // Se houver um insight recente persistido no DB, ele contém os passos já preenchidos
        if (initialData.latest_insight && Array.isArray(initialData.latest_insight.updated_steps)) {
          parsed.steps = initialData.latest_insight.updated_steps;
        }
        setActiveFlightPlan(parsed);
      }
    }
    if (initialData?.latest_insight) {
      setLatestInsight(initialData.latest_insight);
      if (initialData.latest_insight.transfer_detected) {
        setIsTransferred(true);
      }
    }
  }, [initialData, parseFlightPlan]);

  const [messages, setMessages] = useState<TranscribedMessage[]>([]);
  const [debugLogs, setDebugLogs] = useState<{timestamp: Date, role: string, text: string}[]>([]);
  const [partialMic, setPartialMic] = useState<PartialState | null>(null);
  const [partialSpeaker, setPartialSpeaker] = useState<PartialState | null>(null);
  const [latestInsight, setLatestInsight] = useState<LiveCoachingInsight | null>(null);
  const [isAudioConnected, setIsAudioConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [micMeter, setMicMeter] = useState<MeterState>({ rms: 0, speaking: false, status: "Aguardando" });
  const [speakerMeter, setSpeakerMeter] = useState<MeterState>({ rms: 0, speaking: false, status: "Aguardando" });
  const [vendorAvatarUrl, setVendorAvatarUrl] = useState<string | null>(null);
  const [hasHungUp, setHasHungUp] = useState(false);
  
  // Streaming state
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [streamingLabel, setStreamingLabel] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<any>(null);
  const isListeningRef = useRef(false);
  const clientScrollRef = useRef<HTMLDivElement>(null);
  const vendorScrollRef = useRef<HTMLDivElement>(null);
  const loggedAgentMessagesRef = useRef<Set<string>>(new Set());

  const speakerMeterRef = useRef<MeterState>(speakerMeter);
  useEffect(() => {
    speakerMeterRef.current = speakerMeter;
  }, [speakerMeter]);

  const lastClientMessageRef = useRef<{ text: string; timestamp: number | null }>({ text: "", timestamp: null });

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
    const loadVendorAvatar = async () => {
      try {
        const pipedriveUserStr = localStorage.getItem('pipedrive-current-user');
        if (pipedriveUserStr) {
          const parsed = JSON.parse(pipedriveUserStr);
          if (parsed?.avatar) {
            setVendorAvatarUrl(parsed.avatar);
            return;
          }
        }
        
        // Fallback: busca atualizada do backend usando apiGet para garantir headers de auth
        const data = await apiGet('/pipedrive/current-user');
        if (data && data.avatar) {
          setVendorAvatarUrl(data.avatar);
          localStorage.setItem('pipedrive-current-user', JSON.stringify(data));
        }
      } catch (e) {
        console.error("Error loading vendor avatar:", e);
      }
    };
    
    loadVendorAvatar();
  }, []);

  // Load saved session
  const hasLoadedSessionRef = useRef(false);

  useEffect(() => {
    const loadSession = async () => {
      if (hasLoadedSessionRef.current) return;
      hasLoadedSessionRef.current = true;
      
      try {
        // REGRA NOVA: Só carrega a última ligação se vier da aba /mensagens (tem id) ou se for explicitamente um recarregamento histórico.
        // Se a pessoa só clicou em "Ligar" no Grafo, vem o phone, mas NÃO queremos carregar o passado.
        if (!initialData?.id && !initialData?.isHistory) {
          return;
        }

        const queryParams = [];
        if (initialData?.id) queryParams.push(`session_id=${initialData.id}`);
        const queryString = queryParams.join('&');

        const data = await apiGet(`/calls/session?${queryString}`);
        if (data && data.ok) {
          if (data.messages && data.messages.length > 0) {
            setMessages(data.messages);
          }
          if (data.latest_insight) {
            setLatestInsight(data.latest_insight);
            if (data.latest_insight.transfer_detected) {
              setIsTransferred(true);
            }
            if (data.latest_insight.updated_steps) {
              setActiveFlightPlan({ steps: data.latest_insight.updated_steps });
            }
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
      
      // 1. Evita eco em tempo real: se o alto-falante estiver ativo (cliente falando), ignora captação do mic
      if (speakerMeterRef.current.speaking || speakerMeterRef.current.status === "Falando...") {
        console.log("[LigacaoView] Ignorando captação de mic: Cliente está falando no alto-falante.");
        return;
      }

      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) final += event.results[i][0].transcript;
        else interim += event.results[i][0].transcript;
      }

      if (final) {
        const text = final.trim();
        
        // 2. Previne vazamento de eco (echo leakage) por similaridade de texto com fala recente do cliente
        const lastClient = lastClientMessageRef.current;
        if (lastClient.timestamp && Date.now() - lastClient.timestamp < 4000) {
          const cleanText = (t: string) => 
            t.toLowerCase()
             .replace(/[.,\/#!$%\^&\*;:{}=\-_`~()?]/g, "")
             .replace(/\s+/g, " ")
             .trim()
             .split(" ")
             .filter(w => w.length > 2);
          
          const sellerWords = cleanText(text);
          const clientWords = cleanText(lastClient.text);
          
          if (sellerWords.length > 0 && clientWords.length > 0) {
            let matches = 0;
            for (const w of sellerWords) {
              if (clientWords.includes(w)) matches++;
            }
            const ratio = matches / sellerWords.length;
            if (ratio > 0.4 || matches >= 3) {
              console.log("[LigacaoView] Eco descartado com sucesso:", text);
              setPartialMic(null);
              return;
            }
          }
        }

        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "transcription", role: "Vendedor", text },
        ]);
        setDebugLogs((prev) => [...prev, { timestamp: new Date(), role: "Vendedor", text }]);
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
        alert("O acesso ao microfone foi bloqueado. Por favor, libere a permissão de uso do microfone no seu navegador (ícone de cadeado na URL) e tente novamente.");
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

    const queryParams = [];
    if (initialData?.activity_id) {
      queryParams.push(`activity_id=${initialData.activity_id}`);
    }
    if (initialData?.phone) {
      queryParams.push(`phone=${encodeURIComponent(initialData.phone)}`);
    }
    const queryString = queryParams.length > 0 ? `?${queryParams.join("&")}` : "";
    const wsBaseUrl = API_BASE_URL.replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBaseUrl}/api/v1/calls/ws${queryString}`);
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
            setDebugLogs((prev) => [...prev, { timestamp: new Date(), role: data.role, text: data.text }]);
            if (data.role === "Vendedor") setPartialMic(null);
            else {
              setPartialSpeaker(null);
              if (data.text) {
                lastClientMessageRef.current = { text: data.text, timestamp: Date.now() };
              }
            }
            break;

          case "partial_transcription":
            if (data.role === "Vendedor")
              setPartialMic(data.text ? { text: data.text, latency_ms: data.latency_ms, buffer_secs: data.buffer_secs } : null);
            else
              setPartialSpeaker(data.text ? { text: data.text, latency_ms: data.latency_ms, buffer_secs: data.buffer_secs } : null);
            break;

          case "insight_stream_start":
            setIsStreaming(true);
            setStreamingText("");
            setStreamingLabel("⚡ Roteirizando...");
            break;

          case "insight_metadata":
            if (data.data) {
              if (data.data.label) setStreamingLabel(data.data.label);
              if (data.data.transfer_detected) setIsTransferred(true);
            }
            break;

          case "insight_chunk":
            setStreamingText(prev => prev + data.chunk);
            if (data.label) setStreamingLabel(data.label);
            break;

          case "insight_stream_end":
            setIsStreaming(false);
            break;

          case "insight":
          case "live_coaching":
            const insightData = data.data || data.text;
            setLatestInsight(insightData);
            if (insightData && insightData.transfer_detected) {
              setIsTransferred(true);
            }
            if (insightData && Array.isArray(insightData.updated_steps)) {
              setActiveFlightPlan((prevPlan: any) => {
                if (!prevPlan || !prevPlan.steps) return { steps: insightData.updated_steps };
                
                const currentClean = (insightData.current_step || "").toLowerCase().trim();
                const mergedSteps = [...insightData.updated_steps];
                
                // Processa os passos que vieram do LLM
                for (let idx = 0; idx < mergedSteps.length; idx++) {
                  const newStep = mergedSteps[idx];
                  const oldStep = prevPlan.steps[idx];
                  if (!oldStep) continue;
                  
                  let finalContent = newStep.content;
                  const oldLower = (oldStep.content || "").toLowerCase();
                  const isOldReal = oldStep.content && oldStep.content !== "Pendente...";
                  
                  if (isOldReal) {
                     const newLower = (newStep.content || "").toLowerCase();
                     if (newLower.includes("concluíd") || newLower.includes("não se aplica") || newLower.includes("pendente")) {
                         if (isOldReal && !oldLower.includes("concluíd") && !oldLower.includes("não se aplica") && !oldLower.includes("pendente")) {
                             finalContent = oldStep.content;
                         }
                     }
                  }
                  
                  // Mesclar coaching history
                  let finalSuggestions = oldStep.suggestions || [];
                  let finalObjections = oldStep.objections || [];
                  
                  // Só adiciona se for O passo ativo AGORA
                  const labelClean = (newStep.label || "").toLowerCase().trim();
                  const isActiveNow = labelClean && currentClean && (labelClean.includes(currentClean) || currentClean.includes(labelClean));
                  
                  if (isActiveNow) {
                     if (insightData.suggestion && !finalSuggestions.includes(insightData.suggestion)) {
                         finalSuggestions = [...finalSuggestions, insightData.suggestion];
                     }
                     if (insightData.objection_handling && !finalObjections.includes(insightData.objection_handling)) {
                         finalObjections = [...finalObjections, insightData.objection_handling];
                     }
                  }
                  
                  mergedSteps[idx] = { ...newStep, content: finalContent, suggestions: finalSuggestions, objections: finalObjections };
                }

                // Se o LLM retornou menos passos do que tínhamos (truncou o final), preservamos os últimos intactos!
                if (prevPlan.steps.length > mergedSteps.length) {
                  for (let i = mergedSteps.length; i < prevPlan.steps.length; i++) {
                    mergedSteps.push(prevPlan.steps[i]);
                  }
                }
                
                return { ...prevPlan, steps: mergedSteps };
              });
            }

            // Separar os logs do Agente corretamente e persisti-los
            if (insightData) {
              const newAgentOutputs: { type: string, text: string }[] = [];

              if (insightData.suggestion && insightData.suggestion.trim() !== "") {
                newAgentOutputs.push({ type: "suggestion", text: `[SUGESTÃO] ${insightData.suggestion}` });
              }
              if (insightData.objection_handling && insightData.objection_handling.trim() !== "") {
                newAgentOutputs.push({ type: "objection", text: `[CONTORNO DE OBJEÇÃO] ${insightData.objection_handling}` });
              }
              if (Array.isArray(insightData.updated_steps)) {
                insightData.updated_steps.forEach((s: any) => {
                  if (s.content && s.content !== "Pendente..." && s.content.trim() !== "") {
                    const contentLower = s.content.toLowerCase();
                    const isPlaceholder = contentLower.includes("concluíd") || contentLower.includes("não se aplica") || s.content.length < 15;
                    if (!isPlaceholder) {
                      newAgentOutputs.push({ type: "step", text: `[${s.label || "ETAPA"}]\n${s.content}` });
                    }
                  }
                });
              }

              newAgentOutputs.forEach(output => {
                // Checa se já logamos exatamente este texto para evitar spam
                if (!loggedAgentMessagesRef.current.has(output.text)) {
                  loggedAgentMessagesRef.current.add(output.text);

                  // Persiste no state de messages para ir para o backend no final
                  setMessages((prev) => [
                    ...prev,
                    { id: crypto.randomUUID(), type: "insight", role: "Agente", text: output.text } as TranscribedMessage,
                  ]);

                  // Persiste no Debug Logs também
                  setDebugLogs((prev) => [...prev, { timestamp: new Date(), role: "Agente", text: output.text }]);
                }
              });
            }
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
            transcript: messages,
            transcriptCount: messages.length 
        } 
    }));

    setHasHungUp(true);
  }, [contactName, contactPhone, messages.length, stopAudio]);

  const toggleTranscription = () => {
    if (isAudioConnected) {
      stopAudio();
    } else {
      connect();
    }
  };

  // ── Handlers de Interface ────────────────────────────────────────────────
  const copyDebugLogs = () => {
    const logStr = debugLogs.map(l => {
      const time = l.timestamp.toLocaleTimeString("pt-BR", { hour12: false }) + ":" + String(l.timestamp.getMilliseconds()).padStart(3, '0');
      return `[${time}] ${l.role}:\n${l.text}\n`;
    }).join("\n");
    navigator.clipboard.writeText(logStr).then(() => alert("Log cronológico com segundos/milissegundos copiado para a área de transferência!"));
  };

  const copyTranscript = () => {
    const logStr = messages.map(l => {
      return `[${l.role}]:\n${l.text}\n`;
    }).join("\n");
    navigator.clipboard.writeText(logStr).then(() => alert("Log copiado para a área de transferência!"));
  };

  // ── Helpers ───────────────────────────────────────────────────────────
  const meterWidth = (rms: number) => Math.min(100, rms * 80000);

  const getActiveStepIndex = () => {
    if (!latestInsight?.current_step || !activeFlightPlan?.steps) return -1;
    const currentClean = latestInsight.current_step.toLowerCase().trim();
    
    // Tenta encontrar uma correspondência
    return activeFlightPlan.steps.findIndex((step: any) => {
      const labelClean = (step.label || '').toLowerCase().trim();
      return labelClean.includes(currentClean) || currentClean.includes(labelClean);
    });
  };
  const activeIdx = getActiveStepIndex();

  const clientAvatarRaw = getAvatarUrl(initialData);
  const clientAvatarUrl = clientAvatarRaw ? getProxiedUrl(clientAvatarRaw) : null;
  const clientFallbackUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(contactName || "Cliente")}&background=6366f1&color=fff&bold=true&rounded=true&size=120`;
  
  let resolvedClientUrl = clientAvatarUrl || clientFallbackUrl;
  let displayTitle = contactName || "Contato";
  let displaySubtitle = "Em Chamada";

  if (isCompanyPhone && !isTransferred) {
    if (companyLogo) {
      resolvedClientUrl = getProxiedUrl(companyLogo) || `https://ui-avatars.com/api/?name=PABX&background=6366f1&color=fff&bold=true&rounded=true&size=120`;
    } else {
      resolvedClientUrl = `https://ui-avatars.com/api/?name=PABX&background=6366f1&color=fff&bold=true&rounded=true&size=120`;
    }
    displayTitle = "Recepção / PABX";
    displaySubtitle = `Alvo: ${contactName}`;
  }

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
          {/* RENDERIZAÇÃO DO PLANO DE VOO (S.P.I.N) EM FORMATO DE PIPELINE/TIMELINE */}
          {activeFlightPlan && activeFlightPlan.steps && Array.isArray(activeFlightPlan.steps) && (
            <div className={styles.pipeline}>
              {activeFlightPlan.steps.map((step: any, idx: number) => {
                const isActive = idx === activeIdx;
                const isPast = idx < activeIdx;
                const isLightning = step.is_lightning === true;
                
                const isThisStepStreaming = isStreaming && streamingLabel && (
                  step.label.toLowerCase().includes(streamingLabel.toLowerCase()) || 
                  streamingLabel.toLowerCase().includes(step.label.toLowerCase())
                );
                
                // Se estivermos streamando exatamente esta etapa, mostramos a stream no lugar do content
                const displayContent = isThisStepStreaming ? streamingText : step.content;
                
                return (
                  <React.Fragment key={idx}>
                  
                  {/* FAKE ROW: Se estiver streamando uma Etapa Relâmpago ANTES desta etapa pendente */}
                  {isActive && isStreaming && !isThisStepStreaming && (
                    <div className={styles.pipelineRow}>
                      <div className={styles.pipelineSide}>
                        <div className={`${styles.pipelineDotLightning} ${styles.active}`}>
                          <Zap size={14} className={styles.zapIconLightning} style={{ animation: "pulse 1s infinite" }} />
                        </div>
                        <div className={`${styles.pipelineLine} ${styles.active}`} />
                      </div>
                      <div className={`${styles.pipelineCard} ${styles.pipelineCardLightning}`}>
                        <strong className={`${styles.pipelineStepLabel} ${styles.active} ${styles.lightningLabel}`}>
                          {streamingLabel || "⚡ Processando..."}
                        </strong>
                        <span className={`${styles.pipelineStepContent} ${styles.active}`}>
                          {streamingText}
                          <span className={styles.typingDots} style={{ marginLeft: 4 }}>
                            <span /><span /><span />
                          </span>
                        </span>
                      </div>
                    </div>
                  )}
                  
                    <div className={styles.pipelineRow}>
                    <div className={styles.pipelineSide}>
                      {isLightning ? (
                        <div className={`${styles.pipelineDotLightning} ${isActive ? styles.active : ''} ${isPast ? styles.past : ''}`}>
                          <Zap size={14} className={styles.zapIconLightning} />
                        </div>
                      ) : (
                        <div className={`${styles.pipelineDot} ${isActive ? styles.active : ''} ${isPast ? styles.past : ''}`} />
                      )}
                      
                      {idx < activeFlightPlan.steps.length - 1 && (
                        <div className={`${styles.pipelineLine} ${isPast ? styles.active : ''}`} />
                      )}
                    </div>
                    <div className={`${styles.pipelineCard} ${isLightning ? styles.pipelineCardLightning : ''}`}>
                      <strong className={`${styles.pipelineStepLabel} ${isActive ? styles.active : ''} ${isLightning ? styles.lightningLabel : ''}`}>
                        {step.label}
                      </strong>
                      <span className={`${styles.pipelineStepContent} ${isActive ? styles.active : ''}`}>
                        {displayContent}
                        {isThisStepStreaming && (
                          <span className={styles.typingDots} style={{ marginLeft: 4 }}>
                            <span /><span /><span />
                          </span>
                        )}
                      </span>
                      
                      {/* Histórico Persistido do Copiloto/Agent */}
                      {(step.suggestions?.length > 0 || step.objections?.length > 0) && (
                        <div className={styles.coachingInnerContainer} style={{ marginTop: 12 }}>
                          {step.suggestions?.map((sug: string, i: number) => (
                            <div key={`sug-${i}`} className={styles.suggestionTextOnly} style={{ opacity: isActive ? 1 : 0.7 }}>
                              <MessageSquare size={14} />
                              <p><em>{sug}</em></p>
                            </div>
                          ))}
                          {step.objections?.map((obj: string, i: number) => (
                            <div key={`obj-${i}`} className={styles.objectionTextOnly} style={{ opacity: isActive ? 1 : 0.7 }}>
                              <AlertOctagon size={14} />
                              <p><em>{obj}</em></p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  
                  </React.Fragment>
                );
              })}
            </div>
          )}

          {/* Caso não haja plano de voo ou o insight ativo não corresponda a nenhum passo */}
          {(!activeFlightPlan || !activeFlightPlan.steps || activeIdx === -1) && latestInsight && (
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
                <div className={styles.suggestionTextOnly}>
                  <MessageSquare size={14} />
                  <p><em>{latestInsight.suggestion}</em></p>
                </div>
              )}
              {latestInsight.objection_handling && (
                <div className={styles.objectionTextOnly}>
                  <AlertOctagon size={14} />
                  <p><em>{latestInsight.objection_handling}</em></p>
                </div>
              )}
            </div>
          )}

          {/* Caso não haja plano de voo ou o insight ativo não corresponda a nenhum passo */}
          {(!activeFlightPlan || !activeFlightPlan.steps || activeIdx === -1) && isStreaming && (
            <div className={styles.coachingCard}>
               <div className={styles.insightHeader}>
                 <Zap size={14} className={styles.zapIcon} style={{ animation: "pulse 1s infinite" }} />
                 <span>{streamingLabel || "⚡ Pensando..."}</span>
               </div>
               <div className={styles.suggestionTextOnly} style={{ opacity: 1 }}>
                 <p><em>{streamingText}<span className={styles.typingDots}><span /><span /><span /></span></em></p>
               </div>
            </div>
          )}

          {/* Estado vazio padrão */}
          {!activeFlightPlan && !latestInsight && !isStreaming && (
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
                  name={displayTitle} 
                  src={resolvedClientUrl}
                  size={120} 
                />
              </div>
              <h2 className={styles.sideName}>{displayTitle}</h2>
              <div className={styles.statusBadge} style={{ marginTop: 8 }}>
                <div className={`${styles.statusDot} ${styles.active}`} />
                <span>{displaySubtitle}</span>
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
          
          {!hasHungUp ? (
            <button className={`${styles.controlBtn} ${styles.hangup}`} onClick={handleHangup}>
              <PhoneOff size={20} />
              <span>Desligar</span>
            </button>
          ) : (
            <button className={`${styles.controlBtn} ${styles.hangup}`} style={{ background: '#4b5563' }} onClick={() => onBack && onBack()}>
              <X size={20} />
              <span>Sair da Ligação</span>
            </button>
          )}

          <button 
            className={styles.transcriptionToggleBtn} 
            onClick={copyDebugLogs} 
            title="Copiar Log de Debug" 
            style={{ background: "#333", color: "#fff" }}
          >
            <Bug size={20} />
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
