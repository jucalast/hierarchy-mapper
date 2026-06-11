import pyaudiowpatch as pyaudio
import time
import threading

# Configuration
CHUNK_SIZE = 1024

def capture_stream(p, device_info, data_list, stop_event, name):
    print(f"Opening stream for {name}: {device_info['name']}")
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=device_info["maxInputChannels"],
            rate=int(device_info["defaultSampleRate"]),
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            input_device_index=device_info["index"]
        )
        print(f"Stream started for {name}")
        while not stop_event.is_set():
            try:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                data_list.append((name, data))
            except Exception as e:
                print(f"Error reading {name}: {e}")
                break
                
        stream.stop_stream()
        stream.close()
    except Exception as e:
        print(f"Failed to open stream for {name}: {e}")

if __name__ == "__main__":
    audio_events = []
    stop_event = threading.Event()
    
    p = pyaudio.PyAudio()
    
    # Get WASAPI Host API
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        print("Looks like WASAPI is not available on the system.")
        p.terminate()
        exit()

    # Get default speaker
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break
    
    # Get default microphone
    default_mic = p.get_device_info_by_index(wasapi_info["defaultInputDevice"])

    print("=== Audio Loopback Test (PyAudioWPatch) ===")
    print(f"Mic: {default_mic['name']}")
    print(f"Speaker Loopback: {default_speakers['name']}")
    
    t1 = threading.Thread(target=capture_stream, args=(p, default_mic, audio_events, stop_event, "mic"))
    t2 = threading.Thread(target=capture_stream, args=(p, default_speakers, audio_events, stop_event, "speaker"))

    t1.start()
    t2.start()

    try:
        for i in range(5):
            time.sleep(1)
            print(f"Recording... {5-i}s remaining. Current chunks: {len(audio_events)}")
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_event.set()
        t1.join()
        t2.join()

    p.terminate()

    mic_chunks = [d for src, d in audio_events if src == "mic"]
    spkr_chunks = [d for src, d in audio_events if src == "speaker"]

    print(f"\n--- Results ---")
    print(f"Captured {len(mic_chunks)} mic chunks.")
    print(f"Captured {len(spkr_chunks)} speaker chunks.")
    
    if mic_chunks and spkr_chunks:
        print("SUCCESS! Both microphone and speaker audio were captured.")
    else:
        print("FAILED to capture one or both audio sources.")
