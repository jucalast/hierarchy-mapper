import pyaudiowpatch as pyaudio
import audioop
import speech_recognition as sr
import time

sr.Microphone.pyaudio_module = pyaudio

p = pyaudio.PyAudio()
wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

loopback_device = None
for loopback in p.get_loopback_device_info_generator():
    if default_speakers["name"] in loopback["name"]:
        loopback_device = loopback
        break

sample_rate = int(loopback_device["defaultSampleRate"])
recognizer = sr.Recognizer()

stream = p.open(format=pyaudio.paInt16, channels=1, rate=sample_rate,
                input=True, input_device_index=loopback_device["index"], frames_per_buffer=4000)

print("Capturando 3 segundos... reproduza um audio agora!")
frames = []
target = 3 * sample_rate
read = 0
while read < target:
    data = stream.read(4000, exception_on_overflow=False)
    frames.append(data)
    read += 4000

raw = b''.join(frames)
rms = audioop.rms(raw, 2)
print(f"RMS: {rms}")

audio_data = sr.AudioData(raw, sample_rate, 2)
print("Enviando para o Google Speech API...")
try:
    t = time.time()
    texto = recognizer.recognize_google(audio_data, language='pt-BR')
    print(f"TRANSCRICAO ({int((time.time()-t)*1000)}ms): {texto}")
except sr.UnknownValueError:
    print("Google nao entendeu o audio (UnknownValueError)")
except sr.RequestError as e:
    print(f"Erro na API do Google: {e}")
except Exception as e:
    print(f"Erro inesperado: {type(e).__name__}: {e}")

stream.stop_stream()
stream.close()
p.terminate()
