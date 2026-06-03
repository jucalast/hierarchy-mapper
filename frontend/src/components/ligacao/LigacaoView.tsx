"use client";

import React, { useEffect, useState, useRef } from "react";
import { Headset, PhoneOff, Zap } from "lucide-react";

interface TranscribedMessage {
  type: "transcription";
  role: "Vendedor" | "Cliente";
  text: string;
  latency_ms?: number;
  buffer_secs?: number;
}

interface InsightMessage {
  type: "insight";
  text: string;
}

interface LigacaoViewProps {
  onBack: () => void;
}

interface DebugMessage {
  type: "debug_audio";
  source: "mic" | "speaker";
  rms: number;
  is_speaking: boolean;
}

interface StatusMessage {
  type: "status";
  source: "mic" | "speaker";
  status: string;
}

export const LigacaoView: React.FC<LigacaoViewProps> = ({ onBack }) => {
  const [messages, setMessages] = useState<TranscribedMessage[]>([]);
  const [latestInsight, setLatestInsight] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [micDebug, setMicDebug] = useState({ rms: 0, speaking: false, status: 'Aguardando Voz' });
  const [speakerDebug, setSpeakerDebug] = useState({ rms: 0, speaking: false, status: 'Aguardando Voz' });
  const [partialMic, setPartialMic] = useState<{text: string, latency_ms?: number, buffer_secs?: number} | null>(null);
  const [partialSpeaker, setPartialSpeaker] = useState<{text: string, latency_ms?: number, buffer_secs?: number} | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const recognitionRef = useRef<any>(null);
  const isListeningRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const connectWebSocket = () => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.hostname}:8000/api/v1/calls/ws`;
    
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      setIsConnected(true);
      isListeningRef.current = true;
      console.log("WebSocket connected");
      startMicRecognition();
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "transcription") {
          setMessages((prev) => [...prev, data as TranscribedMessage]);
          if (data.role === "Vendedor") setPartialMic(null);
          else setPartialSpeaker(null);
        } else if (data.type === "partial_transcription") {
          if (data.role === "Vendedor") setPartialMic(data.text ? { text: data.text, latency_ms: data.latency_ms, buffer_secs: data.buffer_secs } : null);
          else setPartialSpeaker(data.text ? { text: data.text, latency_ms: data.latency_ms, buffer_secs: data.buffer_secs } : null);
        } else if (data.type === "insight") {
          setLatestInsight((data as InsightMessage).text);
        } else if (data.type === "error") {
          console.error("Backend Error:", data.message);
          alert(`Erro: ${data.message}`);
        } else if (data.type === "debug_audio") {
          const debugData = data as DebugMessage;
          if (debugData.source === "mic") {
            setMicDebug(prev => ({ ...prev, rms: debugData.rms, speaking: debugData.is_speaking }));
          } else {
            setSpeakerDebug(prev => ({ ...prev, rms: debugData.rms, speaking: debugData.is_speaking }));
          }
        } else if (data.type === "status") {
          const statusData = data as StatusMessage;
          if (statusData.source === "mic") {
            setMicDebug(prev => ({ ...prev, status: statusData.status }));
          } else {
            setSpeakerDebug(prev => ({ ...prev, status: statusData.status }));
          }
        }
      } catch (err) {
        console.error("Failed to parse WS message", err);
      }
    };

    wsRef.current.onclose = () => {
      setIsConnected(false);
      console.log("WebSocket disconnected");
    };

    wsRef.current.onerror = (err) => {
      console.error("WebSocket error", err);
      setIsConnected(false);
    };
  };

  const disconnectWebSocket = () => {
    isListeningRef.current = false;
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ type: "STOP" }));
      wsRef.current.close();
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  };

  const startMicRecognition = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Seu navegador não suporta Web Speech API. Use o Chrome ou Edge.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = true;
    recognition.interimResults = true;

    recognition.onstart = () => {
      setMicDebug(prev => ({ ...prev, speaking: true, status: 'Ouvindo...' }));
    };

    recognition.onresult = (event: any) => {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }

      if (finalTranscript) {
        const text = finalTranscript.trim();
        const msg: TranscribedMessage = { type: "transcription", role: "Vendedor", text };
        setMessages((prev) => [...prev, msg]);
        setPartialMic(null);
        
        // Envia para o backend salvar no histórico
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "vendedor_transcription", text }));
        }
      } else if (interimTranscript) {
        setPartialMic({ text: interimTranscript.trim() });
        setMicDebug(prev => ({ ...prev, speaking: true }));
      }
    };

    recognition.onerror = (event: any) => {
      console.error("Erro no reconhecimento de voz:", event.error);
    };

    recognition.onend = () => {
      if (isListeningRef.current) {
        // Reinicia automaticamente se ainda estiver escutando
        try { recognition.start(); } catch(e){}
      } else {
        setMicDebug(prev => ({ ...prev, speaking: false, status: 'Aguardando Voz' }));
      }
    };

    recognition.start();
    recognitionRef.current = recognition;
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return (
    <div style={{
      display: 'flex',
      height: '100%',
      width: '100%',
      backgroundColor: 'var(--sw-bg)',
      color: 'var(--sw-text-base)',
      fontFamily: 'var(--font-primary)'
    }}>
      {/* Sidebar: AI Insights */}
      <div style={{
        width: '350px',
        backgroundColor: 'var(--sw-sidebar)',
        borderRight: '1px solid var(--sw-border)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px',
        boxSizing: 'border-box'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '32px' }}>
          <div style={{
            backgroundColor: 'var(--sw-primary)',
            color: '#fff',
            padding: '8px',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Zap size={24} />
          </div>
          <h2 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--sw-text-base)', margin: 0 }}>
            Copiloto de Vendas
          </h2>
        </div>
        
        <div style={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          {latestInsight ? (
            <div style={{
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              borderRadius: '12px',
              padding: '20px',
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
              transition: 'all 0.5s ease'
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px',
                color: 'var(--sw-primary)', fontWeight: 600, fontSize: '14px'
              }}>
                <Zap size={18} />
                Dica em Tempo Real
              </div>
              <p style={{
                color: 'var(--sw-text-base)',
                lineHeight: 1.6,
                fontSize: '16px',
                margin: 0
              }}>
                {latestInsight}
              </p>
            </div>
          ) : (
            <div style={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--sw-text-muted)',
              opacity: 0.7,
              textAlign: 'center'
            }}>
              <Headset size={64} style={{ marginBottom: '16px' }} />
              <p style={{ fontWeight: 500, margin: '0 0 8px 0' }}>Aguardando a conversa...</p>
              <p style={{ fontSize: '13px', margin: 0 }}>A IA analisará o diálogo e fornecerá dicas estratégicas aqui.</p>
            </div>
          )}
        </div>

        <div style={{ marginTop: '24px' }}>
          {!isConnected ? (
            <button
              onClick={connectWebSocket}
              style={{
                width: '100%',
                backgroundColor: '#10b981',
                color: 'white',
                fontWeight: 600,
                padding: '16px',
                borderRadius: '12px',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                fontSize: '15px',
                boxShadow: '0 4px 6px -1px rgba(16, 185, 129, 0.2)'
              }}
            >
              <Headset size={20} />
              Iniciar Escuta da Ligação
            </button>
          ) : (
            <button
              onClick={disconnectWebSocket}
              style={{
                width: '100%',
                backgroundColor: '#ef4444',
                color: 'white',
                fontWeight: 600,
                padding: '16px',
                borderRadius: '12px',
                border: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                fontSize: '15px',
                boxShadow: '0 4px 6px -1px rgba(239, 68, 68, 0.2)'
              }}
            >
              <PhoneOff size={20} />
              Encerrar Escuta
            </button>
          )}
        </div>
      </div>

      {/* Main Content: Transcription */}
      <div style={{
        flexGrow: 1,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--sw-bg)',
      }}>
        <header style={{
          backgroundColor: 'var(--sw-sidebar)',
          borderBottom: '1px solid var(--sw-border)',
          padding: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h1 style={{
              fontSize: '20px',
              fontWeight: 600,
              color: 'var(--sw-text-base)',
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              Transcrição ao Vivo
              {isConnected && (
                <div style={{
                  width: '12px',
                  height: '12px',
                  backgroundColor: '#10b981',
                  borderRadius: '50%',
                  boxShadow: '0 0 8px #10b981'
                }} />
              )}
            </h1>
          </div>
          
          {/* Debug Visualizer */}
          {isConnected && (
            <div style={{ display: 'flex', gap: '24px', fontSize: '12px', color: 'var(--sw-text-muted)' }}>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Microfone (Vendedor): {micDebug.status}</span>
                  <span>{Math.round(micDebug.rms * 10000)}</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--sw-border)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${Math.min(100, micDebug.rms * 100000)}%`, backgroundColor: micDebug.speaking ? '#10b981' : 'var(--sw-text-muted)', transition: 'width 0.1s' }} />
                </div>
              </div>
              
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Alto-falante (Cliente): {speakerDebug.status}</span>
                  <span>{Math.round(speakerDebug.rms * 10000)}</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--sw-border)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${Math.min(100, speakerDebug.rms * 100000)}%`, backgroundColor: speakerDebug.speaking ? '#3b82f6' : 'var(--sw-text-muted)', transition: 'width 0.1s' }} />
                </div>
              </div>
            </div>
          )}
        </header>

        <main style={{
          flexGrow: 1,
          padding: '32px',
          overflowY: 'auto',
          backgroundColor: 'var(--sw-bg)',
        }}>
          {messages.length === 0 && !partialMic && !partialSpeaker ? (
            <div style={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--sw-text-muted)',
            }}>
              <p>Nenhuma fala detectada ainda.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {messages.map((msg, index) => (
                <div
                  key={index}
                  style={{
                    display: 'flex',
                    justifyContent: msg.role === "Vendedor" ? "flex-end" : "flex-start",
                    width: '100%'
                  }}
                >
                  <div style={{
                    maxWidth: '70%',
                    padding: '16px',
                    borderRadius: '16px',
                    borderBottomRightRadius: msg.role === "Vendedor" ? '4px' : '16px',
                    borderBottomLeftRadius: msg.role === "Vendedor" ? '16px' : '4px',
                    backgroundColor: msg.role === "Vendedor" ? 'var(--sw-primary)' : 'var(--sw-sidebar)',
                    color: msg.role === "Vendedor" ? '#fff' : 'var(--sw-text-base)',
                    boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
                    border: msg.role === "Vendedor" ? 'none' : '1px solid var(--sw-border)'
                  }}>
                    <span style={{
                      fontSize: '12px',
                      fontWeight: 600,
                      marginBottom: '8px',
                      display: 'block',
                      opacity: msg.role === "Vendedor" ? 0.8 : 0.6,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>
                      {msg.role} {msg.latency_ms ? `(IA: ${msg.latency_ms}ms p/ ${msg.buffer_secs}s)` : ''}
                    </span>
                    <p style={{ margin: 0, fontSize: '15px', lineHeight: 1.5 }}>
                      {msg.text}
                    </p>
                  </div>
                </div>
              ))}
              
              {/* Partial Mic (Vendedor) */}
              {partialMic && (
                <div style={{ display: 'flex', justifyContent: "flex-end", width: '100%' }}>
                  <div style={{
                    maxWidth: '70%', padding: '16px', borderRadius: '16px', borderBottomRightRadius: '4px',
                    backgroundColor: 'var(--sw-primary)', color: '#fff', opacity: 0.7, fontStyle: 'italic'
                  }}>
                    <span style={{ fontSize: '12px', fontWeight: 600, marginBottom: '8px', display: 'block', opacity: 0.8 }}>
                      VENDEDOR (Digitando... {partialMic.latency_ms ? `IA: ${partialMic.latency_ms}ms p/ ${partialMic.buffer_secs}s` : ''})
                    </span>
                    <p style={{ margin: 0, fontSize: '15px', lineHeight: 1.5 }}>{partialMic.text}</p>
                  </div>
                </div>
              )}

              {/* Partial Speaker (Cliente) */}
              {partialSpeaker && (
                <div style={{ display: 'flex', justifyContent: "flex-start", width: '100%' }}>
                  <div style={{
                    maxWidth: '70%', padding: '16px', borderRadius: '16px', borderBottomLeftRadius: '4px',
                    backgroundColor: 'var(--sw-sidebar)', color: 'var(--sw-text-base)', opacity: 0.7, fontStyle: 'italic',
                    border: '1px solid var(--sw-border)'
                  }}>
                    <span style={{ fontSize: '12px', fontWeight: 600, marginBottom: '8px', display: 'block', opacity: 0.6 }}>
                      CLIENTE (Digitando... {partialSpeaker.latency_ms ? `IA: ${partialSpeaker.latency_ms}ms p/ ${partialSpeaker.buffer_secs}s` : ''})
                    </span>
                    <p style={{ margin: 0, fontSize: '15px', lineHeight: 1.5 }}>{partialSpeaker.text}</p>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
