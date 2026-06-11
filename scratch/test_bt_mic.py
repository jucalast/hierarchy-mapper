import pyaudiowpatch as pyaudio
import numpy as np
import time

p = pyaudio.PyAudio()
wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
dev = p.get_device_info_by_index(wasapi_info["defaultInputDevice"])

print(f"=== TESTE DE MICROFONE ===")
print(f"Usando: {dev['name']}")
print("Fale alguma coisa no fone agora!\n")

stream = p.open(
    format=pyaudio.paInt16,
    channels=dev["maxInputChannels"],
    rate=int(dev["defaultSampleRate"]),
    input=True,
    frames_per_buffer=1024,
    input_device_index=dev["index"]
)

try:
    for i in range(50): # Roda por ~2.5 segundos
        raw = stream.read(1024, exception_on_overflow=False)
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(arr**2))
        
        # Converter para uma escala visual fácil de ler
        visual_bar = "#" * int(rms * 1000)
        print(f"Volume RMS: {rms:.6f} | {visual_bar}")
        time.sleep(0.05)
except KeyboardInterrupt:
    pass

stream.stop_stream()
stream.close()
p.terminate()
