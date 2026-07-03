import pyaudiowpatch as pyaudio
import time
import threading
import numpy as np
from scipy import signal
from faster_whisper import WhisperModel
import queue
import sys

WHISPER_MODEL = "tiny"
SAMPLE_RATE = 16000
CHUNK_DURATION_SEC = 0.1 # <-- Reduzido para 100ms para captura imediata do hardware
SILENCE_THRESHOLD = 0.001
MAX_SILENCE_DURATION = 0.75

print(f"Loading Whisper model '{WHISPER_MODEL}'...")
model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

print("Warming up model to prevent first-run lag...")
dummy_audio = np.zeros(16000, dtype=np.float32)
model.transcribe(dummy_audio, beam_size=1, language="pt")
print("Whisper ready.")

audio_queue = queue.Queue()

def resample_audio(audio_data, orig_sr, target_sr):
    if orig_sr == target_sr:
        return audio_data
    num_samples = int(len(audio_data) * float(target_sr) / orig_sr)
    return signal.resample(audio_data, num_samples)

def capture_stream(p, device_info, stop_event, name):
    orig_sr = int(device_info["defaultSampleRate"])
    chunk_size = int(orig_sr * CHUNK_DURATION_SEC)
    channels = device_info["maxInputChannels"]
    
    print(f"Opening stream for {name}: {device_info['name']} at {orig_sr}Hz")
    
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=orig_sr,
            input=True,
            frames_per_buffer=chunk_size,
            input_device_index=device_info["index"]
        )
        print(f"Stream started for {name}")
        while not stop_event.is_set():
            try:
                # O timeout de read não bloqueia infinitamente
                raw_data = stream.read(chunk_size, exception_on_overflow=False)
                audio_np = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                
                if channels > 1:
                    audio_np = audio_np.reshape(-1, channels).mean(axis=1)
                
                if orig_sr != SAMPLE_RATE:
                    audio_np = resample_audio(audio_np, orig_sr, SAMPLE_RATE)
                
                # Timestamp de quando o áudio SAIU do hardware
                audio_queue.put((name, audio_np, time.time()))
            except Exception as e:
                break
                
        stream.stop_stream()
        stream.close()
    except Exception as e:
        print(f"Failed to open stream for {name}: {e}")

class SourceState:
    def __init__(self):
        self.is_speaking = False
        self.speech_buffer = np.array([], dtype=np.float32)
        self.silence_time = 0.0
        self.last_partial_time = 0.0

def transcription_worker(stop_event):
    states = {
        "mic": SourceState(),
        "speaker": SourceState()
    }
    
    while not stop_event.is_set():
        try:
            name, data, capture_time = audio_queue.get(timeout=0.05)
            state = states[name]
            
            rms = np.sqrt(np.mean(data**2))
            is_active = rms > SILENCE_THRESHOLD
            
            if is_active:
                if not state.is_speaking:
                    # DEBUG: Avisa exatamente o milissegundo que detectou som!
                    latency = time.time() - capture_time
                    sys.stdout.write(f"\r[DEBUG] Som do {name} detectado! Latencia do hardware: {latency*1000:.0f}ms\n")
                    sys.stdout.flush()
                
                state.is_speaking = True
                state.silence_time = 0.0
                state.speech_buffer = np.concatenate((state.speech_buffer, data))
                
                current_time = time.time()
                
                # Cortar com 15 segundos maximos
                if len(state.speech_buffer) >= SAMPLE_RATE * 15.0:
                    segments, _ = model.transcribe(state.speech_buffer, beam_size=3, language="pt", condition_on_previous_text=False)
                    text = " ".join([s.text for s in segments]).strip()
                    if text:
                        sys.stdout.write("\r" + " " * 100 + "\r")
                        print(f"[{name.upper()}]: {text}")
                    state.speech_buffer = np.array([], dtype=np.float32)
                    state.is_speaking = False
                
                # Transcrição parcial muito rapida
                elif len(state.speech_buffer) >= SAMPLE_RATE * 0.25 and (current_time - state.last_partial_time) >= 0.3:
                    t_start = time.time()
                    segments, _ = model.transcribe(state.speech_buffer, beam_size=1, language="pt", condition_on_previous_text=False)
                    text = " ".join([s.text for s in segments]).strip()
                    t_end = time.time()
                    if text:
                        # DEBUG: Mostra quanto tempo a IA demorou pra gerar o texto
                        sys.stdout.write(f"\r[{name.upper()}] (IA demorou {(t_end-t_start)*1000:.0f}ms): {text}")
                        sys.stdout.flush()
                    state.last_partial_time = current_time
                    
            else:
                if state.is_speaking:
                    state.speech_buffer = np.concatenate((state.speech_buffer, data))
                    state.silence_time += CHUNK_DURATION_SEC
                    
                    if state.silence_time >= MAX_SILENCE_DURATION:
                        state.is_speaking = False
                        if len(state.speech_buffer) > SAMPLE_RATE * 0.4:
                            segments, _ = model.transcribe(state.speech_buffer, beam_size=3, language="pt", condition_on_previous_text=False)
                            text = " ".join([s.text for s in segments]).strip()
                            if text:
                                sys.stdout.write("\r" + " " * 100 + "\r")
                                print(f"[{name.upper()}]: {text}")
                        state.speech_buffer = np.array([], dtype=np.float32)
        except queue.Empty:
            continue
        except Exception as e:
            pass

if __name__ == "__main__":
    stop_event = threading.Event()
    p = pyaudio.PyAudio()
    
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        print("Looks like WASAPI is not available on the system.")
        p.terminate()
        exit()

    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break
    
    default_mic = p.get_device_info_by_index(wasapi_info["defaultInputDevice"])

    print("\n=== Real-time Transcription Test (DIAGNOSTICO DE LATENCIA) ===")
    print("Press Ctrl+C to stop.\n")
    
    t_mic = threading.Thread(target=capture_stream, args=(p, default_mic, stop_event, "mic"))
    t_spkr = threading.Thread(target=capture_stream, args=(p, default_speakers, stop_event, "speaker"))
    t_transcribe = threading.Thread(target=transcription_worker, args=(stop_event,))

    t_mic.start()
    t_spkr.start()
    t_transcribe.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_event.set()
        t_mic.join()
        t_spkr.join()
        t_transcribe.join()
    p.terminate()
