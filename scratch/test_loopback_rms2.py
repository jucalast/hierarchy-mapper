import pyaudiowpatch as pyaudio
import audioop
import time

p = pyaudio.PyAudio()
wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
print(f"Default Speakers: {default_speakers['name']}")

loopback_device = None
for loopback in p.get_loopback_device_info_generator():
    if default_speakers["name"] in loopback["name"]:
        loopback_device = loopback
        break

if not loopback_device:
    print("No loopback found")
    exit(1)

sample_rate = int(loopback_device["defaultSampleRate"])
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=sample_rate,
                input=True,
                input_device_index=loopback_device["index"],
                frames_per_buffer=4000)

print("Listening... Play a video and look at the RMS values!")
for _ in range(20):
    try:
        data = stream.read(4000, exception_on_overflow=False)
        rms = audioop.rms(data, 2)
        print(f"RMS: {rms} | > 100: {rms > 100}")
    except OSError:
        pass
    time.sleep(0.1)

stream.stop_stream()
stream.close()
p.terminate()
