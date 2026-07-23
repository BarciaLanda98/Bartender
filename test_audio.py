import speech_recognition as sr
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def test_microphone(device_index=None):
    device_name = "Predeterminado"
    if device_index is not None:
        try:
            mics = sr.Microphone.list_microphone_names()
            device_name = mics[device_index]
        except IndexError:
            print(f"[ERROR] Indice {device_index} fuera de rango.")
            return False

    print(f"\nProbando Micrófono: {device_name} (Indice: {device_index})")
    try:
        m = sr.Microphone(device_index=device_index)
        r = sr.Recognizer()
        with m as source:
            print("Calibrando ruido ambiental por 2 segundos...")
            r.adjust_for_ambient_noise(source, duration=2)
            print(f"Umbral de energía calibrado: {r.energy_threshold:.2f}")
            print("Escuchando... Di algo ahora (tienes 5 segundos)...")
            try:
                audio = r.listen(source, timeout=5, phrase_time_limit=5)
                print(f"Audio capturado! Longitud: {len(audio.frame_data)} bytes")
                print("Intentando transcribir con Google Speech Recognition...")
                text = r.recognize_google(audio, language="es-ES")
                print(f"Transcripción: \"{text}\"")
                return True
            except sr.WaitTimeoutError:
                print("[INFO] Timeout: No se detectó voz o sonido.")
            except sr.UnknownValueError:
                print("[INFO] No se pudo entender el audio (Google STT no pudo transcribir nada).")
            except sr.RequestError as e:
                print(f"[ERROR] Error al conectar con el servicio de Google STT: {e}")
    except Exception as e:
        print(f"[ERROR] Error al inicializar/usar el dispositivo: {e}")
    return False

if __name__ == "__main__":
    print("=== Herramienta de Diagnóstico de Micrófono MIA ===")
    
    # Listar micrófonos
    mics = sr.Microphone.list_microphone_names()
    print("\nMicrófonos detectados en el sistema:")
    for i, name in enumerate(mics):
        try:
            print(f"  [{i}]: {name}")
        except Exception:
            # Fallback si el nombre contiene caracteres extraños
            print(f"  [{i}]: Dispositivo de Audio {i}")
    
    # Comprobar argumento CLI
    target_idx = None
    if len(sys.argv) > 1:
        try:
            target_idx = int(sys.argv[1])
            print(f"\nUso de índice especificado por argumento: {target_idx}")
        except ValueError:
            print(f"\nArgumento no válido '{sys.argv[1]}'. Se usará el micrófono predeterminado.")
            
    test_microphone(target_idx)


