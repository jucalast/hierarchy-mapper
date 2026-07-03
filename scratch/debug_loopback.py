import pyaudiowpatch as pyaudio
import audioop

p = pyaudio.PyAudio()
wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
print(f"Default Speakers: {default_speakers['name']}")

loopback_device = None
for loopback in p.get_loopback_device_info_generator():
    print(f"Checking Loopback: {loopback['name']}")
    if default_speakers["name"] in loopback["name"]:
        loopback_device = loopback
        break

if loopback_device:
    print(f"FOUND MATCHING LOOPBACK: {loopback_device['name']}")
else:
    print("NO MATCHING LOOPBACK FOUND! Attempting fallback...")
    for loopback in p.get_loopback_device_info_generator():
        loopback_device = loopback
        print(f"FALLBACK TO: {loopback_device['name']}")
        break
