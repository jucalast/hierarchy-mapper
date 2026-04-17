import { useState, useEffect, useCallback } from 'react';

export const useSpeechToText = () => {
    const [isListening, setIsListening] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [recognition, setRecognition] = useState<any>(null);

    useEffect(() => {
        const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            setError('Seu navegador não suporta reconhecimento de voz.');
            return;
        }

        const recognitionInstance = new SpeechRecognition();
        recognitionInstance.continuous = false;
        recognitionInstance.interimResults = false;
        recognitionInstance.lang = 'pt-BR';

        recognitionInstance.onstart = () => setIsListening(true);
        recognitionInstance.onend = () => setIsListening(false);
        recognitionInstance.onerror = (event: any) => {
            setError(event.error);
            setIsListening(false);
        };
        
        recognitionInstance.onresult = (event: any) => {
            const currentTranscript = event.results[0][0].transcript;
            setTranscript(currentTranscript);
        };

        setRecognition(recognitionInstance);
    }, []);

    const startListening = useCallback(() => {
        if (recognition) {
            setError(null);
            setTranscript('');
            try {
                recognition.start();
            } catch (e) {
                console.error("Speech recognition already started or error:", e);
            }
        }
    }, [recognition]);

    const stopListening = useCallback(() => {
        if (recognition) {
            recognition.stop();
        }
    }, [recognition]);

    return { isListening, transcript, error, startListening, stopListening };
};
