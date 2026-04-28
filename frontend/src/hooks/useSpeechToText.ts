import { useState, useEffect, useCallback } from 'react';

export const useSpeechToText = () => {
    const [isListening, setIsListening] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [recognition, setRecognition] = useState<any>(null);

    useEffect(() => {
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            console.error('Speech recognition not supported in this browser');
            setError('Seu navegador não suporta reconhecimento de voz.');
            return;
        }

        const recognitionInstance = new SpeechRecognition();
        recognitionInstance.continuous = false;
        recognitionInstance.interimResults = false;
        recognitionInstance.lang = 'pt-BR';

        recognitionInstance.onstart = () => {
            console.log('Speech recognition started');
            setIsListening(true);
        };
        recognitionInstance.onend = () => {
            console.log('Speech recognition ended');
            setIsListening(false);
        };
        recognitionInstance.onerror = (event: any) => {
            const err = event.error;
            // 'not-allowed' = sem permissão de microfone — erro esperado, não precisa poluir o console
            if (err === 'not-allowed' || err === 'permission-denied') {
                setError('Permissão de microfone negada. Habilite nas configurações do navegador.');
            } else if (err === 'no-speech') {
                setError(null); // silêncio não é erro
            } else {
                setError(err);
            }
            setIsListening(false);
        };
        
        recognitionInstance.onresult = (event: any) => {
            const currentTranscript = event.results[0][0].transcript;
            console.log('Speech recognition result:', currentTranscript);
            setTranscript(currentTranscript);
        };

        setRecognition(recognitionInstance);
    }, []);

    const startListening = useCallback(async () => {
        if (!recognition) {
            setError('Reconhecimento de voz não disponível');
            return;
        }
        // Solicita permissão explicitamente antes de iniciar
        try {
            await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch {
            setError('Permissão de microfone negada. Habilite nas configurações do navegador.');
            return;
        }
        setError(null);
        setTranscript('');
        try {
            recognition.start();
        } catch {
            // já estava rodando — ignora silenciosamente
        }
    }, [recognition]);

    const stopListening = useCallback(() => {
        if (recognition) {
            console.log('Stopping speech recognition...');
            recognition.stop();
        }
    }, [recognition]);

    return { isListening, transcript, error, startListening, stopListening };
};
