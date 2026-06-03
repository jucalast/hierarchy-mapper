import pyaudiowpatch as pyaudio
import time
import threading
import queue
import logging
import audioop
import speech_recognition as sr

log = logging.getLogger(__name__)

# Configuração do SpeechRecognition para usar pyaudiowpatch (Loopback)
sr.Microphone.pyaudio_module = pyaudio

class CallAssistantManager:
    def __init__(self):
        self.transcription_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.is_running = False
        self.context_history = []
        self.speaker_thread = None

    def add_to_history(self, role: str, text: str):
        self.context_history.append(f"{role}: {text}")
        if len(self.context_history) > 20:
            self.context_history.pop(0)
            
        # Trigger insight a cada X mensagens
        if len(self.context_history) % 3 == 0:
            self.transcription_queue.put({
                "type": "trigger_insight",
                "history": "\n".join(self.context_history[-10:])
            })

    def _speaker_listener(self):
        p = pyaudio.PyAudio()
        try:
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            
            loopback_device = None
            if not default_speakers.get("isLoopbackDevice", False):
                for loopback in p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        loopback_device = loopback
                        break
            else:
                loopback_device = default_speakers
                
        except OSError:
            loopback_device = None

        if loopback_device is None:
            log.error("Não foi possível encontrar o Alto-falante padrão para escutar 'Os Outros'.")
            p.terminate()
            return

        sample_rate = int(loopback_device["defaultSampleRate"])
        channels = max(1, int(loopback_device.get("maxInputChannels", 2)))
        recognizer = sr.Recognizer()
        
        try:
            stream = p.open(format=pyaudio.paInt16,
                            channels=channels,
                            rate=sample_rate,
                            input=True,
                            input_device_index=loopback_device["index"],
                            frames_per_buffer=4000)
        except Exception as e:
            log.error(f"Erro ao abrir stream de áudio do sistema: {e}")
            p.terminate()
            return

        # VAD: parâmetros de detecção de fala
        CHUNK_SIZE = int(sample_rate * 0.1)  # chunks de 100ms
        RMS_THRESHOLD = 150                   # mínimo de volume para considerar fala
        SILENCE_LIMIT = 0.8                   # segundos de silêncio para fechar a frase
        MAX_PHRASE = 12.0                     # trava de segurança: frase máxima em segundos
        
        speech_buffer = b''
        silence_time = 0.0
        is_speaking = False
        
        while not self.stop_event.is_set():
            try:
                chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            except OSError:
                time.sleep(0.05)
                continue
            
            # Mix down para mono se necessário
            mono_chunk = audioop.tomono(chunk, 2, 0.5, 0.5) if channels == 2 else chunk
            rms = audioop.rms(mono_chunk, 2)
            
            # Atualiza o visualizador no frontend (barra de volume)
            self.transcription_queue.put({
                "type": "debug_audio", "source": "speaker",
                "rms": float(rms) / 32768.0, "is_speaking": rms > RMS_THRESHOLD
            })
            
            if rms > RMS_THRESHOLD:
                if not is_speaking:
                    is_speaking = True
                    self.transcription_queue.put({
                        "type": "status", "source": "speaker", "status": "Falando..."
                    })
                
                silence_time = 0.0
                speech_buffer += mono_chunk
                
                # STREAMING PARCIAL: a cada 1.5s enquanto fala, transcreve o buffer e mostra na tela
                secs_accumulated = len(speech_buffer) / (sample_rate * 2)
                if secs_accumulated >= 1.5 and (secs_accumulated % 1.5) < 0.12:
                    import threading
                    threading.Thread(
                        target=self._send_partial_to_google,
                        args=(bytes(speech_buffer), sample_rate, recognizer),
                        daemon=True
                    ).start()
                
                # Trava de segurança: máximo de 12s sem pausa
                if len(speech_buffer) >= sample_rate * 2 * MAX_PHRASE:
                    self._send_to_google(speech_buffer, sample_rate, recognizer)
                    speech_buffer = b''
                    is_speaking = False
            else:
                if is_speaking:
                    silence_time += 0.1  # cada chunk = 100ms
                    speech_buffer += mono_chunk  # acumula o silêncio para suavizar
                    
                    if silence_time >= SILENCE_LIMIT:
                        # Frase completa! Envia para o Google (resultado final)
                        self._send_to_google(speech_buffer, sample_rate, recognizer)
                        speech_buffer = b''
                        is_speaking = False
                        silence_time = 0.0
                        self.transcription_queue.put({
                            "type": "status", "source": "speaker", "status": "Aguardando Voz"
                        })

        stream.stop_stream()
        stream.close()
        p.terminate()

    def _send_partial_to_google(self, raw_audio: bytes, sample_rate: int, recognizer):
        """Transcreve o buffer atual e mostra como texto 'Digitando...' na tela."""
        import speech_recognition as sr
        audio_data = sr.AudioData(raw_audio, sample_rate, 2)
        try:
            texto = recognizer.recognize_google(audio_data, language='pt-BR')
            if texto.strip():
                self.transcription_queue.put({
                    "type": "partial_transcription",
                    "role": "Cliente",
                    "text": texto.strip()
                })
        except Exception:
            pass

    def _send_to_google(self, raw_audio: bytes, sample_rate: int, recognizer):
        """Envia o buffer de áudio para o Google Speech API e publica o resultado."""
        import speech_recognition as sr
        audio_data = sr.AudioData(raw_audio, sample_rate, 2)
        try:
            t_start = time.time()
            texto = recognizer.recognize_google(audio_data, language='pt-BR')
            t_end = time.time()
            if texto.strip():
                self.transcription_queue.put({
                    "type": "partial_transcription", "role": "Cliente", "text": ""
                })
                self.transcription_queue.put({
                    "type": "transcription",
                    "role": "Cliente",
                    "text": texto.strip(),
                    "latency_ms": int((t_end - t_start) * 1000),
                    "buffer_secs": round(len(raw_audio) / (sample_rate * 2), 1)
                })
                self.add_to_history("Cliente", texto.strip())
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            log.error(f"Erro na API do Google: {e}")
        finally:
            self.transcription_queue.put({
                "type": "partial_transcription", "role": "Cliente", "text": ""
            })

    def start(self):
        self.stop()
        time.sleep(0.5) 
        
        self.stop_event.clear()
        self.speaker_thread = threading.Thread(target=self._speaker_listener, daemon=True)
        self.speaker_thread.start()
        
        self.is_running = True
        return True

    def stop(self):
        self.stop_event.set()
        if self.speaker_thread and self.speaker_thread.is_alive():
            self.speaker_thread.join(timeout=2.0)
            
        self.is_running = False
        log.info("Call Assistant Manager parado.")

assistant_manager = CallAssistantManager()
