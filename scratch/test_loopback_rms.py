import pyaudiowpatch as pyaudio
import numpy as np

p = pyaudio.PyAudio()
wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
dev = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

if not dev["isLoopbackDevice"]:
    for loopback in p.get_loopback_device_info_generator():
        if dev["name"] in loopback["name"]:
            dev = loopback
            break

print(f"Testing loopback device: {dev['name']}")
stream = p.open(
    format=pyaudio.paInt16,
    channels=dev["maxInputChannels"],
    rate=int(dev["defaultSampleRate"]),
    input=True,
    frames_per_buffer=1024,
    input_device_index=dev["index"]
)

for i in range(10):
    raw = stream.read(1024, exception_on_overflow=False)
    arr = np.frombuffer(raw, dtype=np.int16)
    rms = np.sqrt(np.mean(arr.astype(np.float32)**2))
    print(f"Chunk {i} RMS: {rms}")

stream.stop_stream()
stream.close()
p.terminate()
