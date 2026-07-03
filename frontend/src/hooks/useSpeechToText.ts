import { useState, useRef, useCallback, useEffect } from 'react';
import { API_V1_URL } from '../services/config';

/**
 * Hook de voz cross-browser.
 * Usa MediaRecorder para gravar áudio e envia ao backend (Groq Whisper)
 * para transcrição — funciona em Chrome, Firefox, Safari e Edge.
 */
export const useSpeechToText = () => {
    const [isListening, setIsListening] = useState(false);
    const [isTranscribing, setIsTranscribing] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [finalTranscript, setFinalTranscript] = useState('');
    const [error, setError] = useState<string | null>(null);

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const chunksRef = useRef<Blob[]>([]);
    const streamRef = useRef<MediaStream | null>(null);
    const audioCtxRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);

    const [isSupported, setIsSupported] = useState(false);

    useEffect(() => {
        setIsSupported(typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia);
    }, []);

    const startListening = useCallback(async () => {
        if (!navigator.mediaDevices?.getUserMedia) {
            setError('Seu navegador não suporta captura de áudio.');
            return;
        }

        // Verifica o estado atual da permissão antes de tentar
        try {
            const perm = await navigator.permissions.query({ name: 'microphone' as PermissionName });
            if (perm.state === 'denied') {
                setError('blocked');
                return;
            }
        } catch (_) {
            // Permissions API não disponível em alguns browsers — segue tentando normalmente
        }

        setError(null);
        setTranscript('');
        setFinalTranscript('');
        chunksRef.current = [];

        let stream: MediaStream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e: any) {
            const name = e?.name ?? '';
            if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
                setError('blocked');
            } else {
                setError(`Não foi possível acessar o microfone: ${e?.message ?? name}`);
            }
            return;
        }

        streamRef.current = stream;

        // Cria o AnalyserNode para visualização de ondas
        try {
            const audioCtx = new AudioContext();
            const source = audioCtx.createMediaStreamSource(stream);
            const analyser = audioCtx.createAnalyser();
            analyser.fftSize = 64;
            analyser.smoothingTimeConstant = 0.8;
            source.connect(analyser);
            audioCtxRef.current = audioCtx;
            analyserRef.current = analyser;
        } catch (_) {}

        // Escolhe o melhor formato suportado pelo browser
        const mimeType = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
        ].find(t => MediaRecorder.isTypeSupported(t)) ?? '';

        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        mediaRecorderRef.current = recorder;

        recorder.ondataavailable = (e) => {
            if (e.data.size > 0) chunksRef.current.push(e.data);
        };

        recorder.onstop = async () => {
            // Libera o microfone e fecha o AudioContext
            streamRef.current?.getTracks().forEach(t => t.stop());
            streamRef.current = null;
            analyserRef.current = null;
            audioCtxRef.current?.close().catch(() => {});
            audioCtxRef.current = null;
            setIsListening(false);

            const blob = new Blob(chunksRef.current, {
                type: mimeType || 'audio/webm',
            });
            chunksRef.current = [];

            if (blob.size < 1000) {
                // Áudio muito curto ou vazio — ignora silenciosamente
                return;
            }

            setIsTranscribing(true);
            try {
                const ext = (mimeType.includes('ogg') ? 'ogg' : mimeType.includes('mp4') ? 'mp4' : 'webm');
                const form = new FormData();
                form.append('audio', blob, `recording.${ext}`);

                const resp = await fetch(`${API_V1_URL}/ai/transcribe`, {
                    method: 'POST',
                    body: form,
                });

                if (!resp.ok) {
                    const detail = await resp.text();
                    throw new Error(`Erro ${resp.status}: ${detail.slice(0, 120)}`);
                }

                const { transcript: text } = await resp.json();
                if (text) {
                    setTranscript(text);
                    setFinalTranscript(text);
                }
            } catch (e: any) {
                setError(`Falha na transcrição: ${e?.message ?? 'erro desconhecido'}`);
            } finally {
                setIsTranscribing(false);
            }
        };

        recorder.start();
        setIsListening(true);
    }, []);

    const stopListening = useCallback(() => {
        if (mediaRecorderRef.current?.state === 'recording') {
            mediaRecorderRef.current.stop();
        } else {
            // Garante limpeza mesmo se stop for chamado fora de gravação
            streamRef.current?.getTracks().forEach(t => t.stop());
            streamRef.current = null;
            setIsListening(false);
        }
    }, []);

    const clearTranscript = useCallback(() => {
        setTranscript('');
        setFinalTranscript('');
    }, []);

    return {
        isListening,
        isTranscribing,
        transcript,
        finalTranscript,
        error,
        startListening,
        stopListening,
        clearTranscript,
        isSupported,
        analyserNode: analyserRef,
    };
};
