import pyaudiowpatch as pyaudio
import time
import io
import wave
import threading
import queue
import logging
import audioop
import os
import httpx

log = logging.getLogger(__name__)


def _pcm_to_wav(raw_audio: bytes, sample_rate: int) -> bytes:
    """Converte PCM mono 16-bit para WAV em memória."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_audio)
    return buf.getvalue()


def _transcribe_groq(wav_bytes: bytes, is_partial: bool = False) -> str:
    """Chama o Groq Whisper (~200ms) e retorna o texto transcrito."""
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return ""
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {groq_key}"},
            files={"file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
            data={
                "model": "whisper-large-v3-turbo",
                "language": "pt",
                "response_format": "text",
            },
            timeout=8.0,
        )
        if response.status_code == 200:
            return response.text.strip()
    except Exception as e:
        log.debug(f"Groq Whisper error: {e}")
    return ""


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
            log.error("Não foi possível encontrar o Alto-falante padrão.")
            p.terminate()
            return

        sample_rate = int(loopback_device["defaultSampleRate"])
        channels = max(1, int(loopback_device.get("maxInputChannels", 2)))

        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=loopback_device["index"],
                frames_per_buffer=int(sample_rate * 0.1),
            )
        except Exception as e:
            log.error(f"Erro ao abrir stream de áudio: {e}")
            p.terminate()
            return

        # VAD
        CHUNK_SIZE = int(sample_rate * 0.1)   # 100ms por chunk
        RMS_THRESHOLD = 150
        SILENCE_LIMIT = 0.75                  # segundos de silêncio para fechar frase
        PARTIAL_INTERVAL = 0.8               # envia parcial a cada 0.8s de fala
        MAX_PHRASE = 12.0

        speech_buffer = b''
        silence_time = 0.0
        is_speaking = False
        last_partial_secs = 0.0
        partial_lock = threading.Lock()

        def fire_partial(buf_snapshot: bytes):
            """Roda em thread separada para não bloquear o loop principal."""
            wav = _pcm_to_wav(buf_snapshot, sample_rate)
            text = _transcribe_groq(wav, is_partial=True)
            if text:
                with partial_lock:
                    self.transcription_queue.put({
                        "type": "partial_transcription",
                        "role": "Cliente",
                        "text": text,
                    })

        while not self.stop_event.is_set():
            try:
                chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            except OSError:
                time.sleep(0.05)
                continue

            mono = audioop.tomono(chunk, 2, 0.5, 0.5) if channels == 2 else chunk
            rms = audioop.rms(mono, 2)

            # Visualizador de volume
            self.transcription_queue.put({
                "type": "debug_audio", "source": "speaker",
                "rms": float(rms) / 32768.0, "is_speaking": rms > RMS_THRESHOLD
            })

            if rms > RMS_THRESHOLD:
                if not is_speaking:
                    is_speaking = True
                    last_partial_secs = 0.0
                    self.transcription_queue.put({
                        "type": "status", "source": "speaker", "status": "Falando..."
                    })

                silence_time = 0.0
                speech_buffer += mono
                secs = len(speech_buffer) / (sample_rate * 2)

                # Dispara parcial a cada PARTIAL_INTERVAL segundos de fala
                if secs - last_partial_secs >= PARTIAL_INTERVAL:
                    last_partial_secs = secs
                    threading.Thread(
                        target=fire_partial,
                        args=(bytes(speech_buffer),),
                        daemon=True
                    ).start()

                # Trava de segurança: 12s sem pausa
                if secs >= MAX_PHRASE:
                    self._finalize(speech_buffer, sample_rate)
                    speech_buffer = b''
                    is_speaking = False
            else:
                if is_speaking:
                    silence_time += 0.1
                    speech_buffer += mono

                    if silence_time >= SILENCE_LIMIT:
                        # Frase completa — transcrição final
                        self._finalize(speech_buffer, sample_rate)
                        speech_buffer = b''
                        is_speaking = False
                        silence_time = 0.0
                        last_partial_secs = 0.0
                        self.transcription_queue.put({
                            "type": "status", "source": "speaker", "status": "Aguardando Voz"
                        })

        stream.stop_stream()
        stream.close()
        p.terminate()

    def _finalize(self, raw_audio: bytes, sample_rate: int):
        """Transcrição final da frase (alta precisão) enviada como balão definitivo."""
        wav = _pcm_to_wav(raw_audio, sample_rate)
        t_start = time.time()
        text = _transcribe_groq(wav)
        t_end = time.time()
        if text:
            # Limpa o "Digitando..."
            self.transcription_queue.put({
                "type": "partial_transcription", "role": "Cliente", "text": ""
            })
            self.transcription_queue.put({
                "type": "transcription",
                "role": "Cliente",
                "text": text,
                "latency_ms": int((t_end - t_start) * 1000),
                "buffer_secs": round(len(raw_audio) / (sample_rate * 2), 1),
            })
            self.add_to_history("Cliente", text)
        else:
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
