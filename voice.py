import threading
import asyncio
import edge_tts
import base64
import os
from queue import Queue

class Voice:
    """Síntesis de voz usando Edge-TTS — Genera MP3 y emite a la UI"""

    def __init__(self):
        self._speech_queue = Queue()
        self.is_speaking = False
        self._running = True
        
        # Callback para emitir el audio Base64 hacia el navegador
        self.on_audio_ready = None

        self._worker = threading.Thread(
            target=self._process_queue, daemon=True, name="VoiceWorker"
        )
        self._worker.start()

    def _speak_sync(self, text):
        """Genera el MP3 con Edge-TTS sincrónicamente en memoria (dentro del worker)"""
        if not text or not text.strip():
            return

        self.is_speaking = True
        print(f"🔊 MIA dice: {text}")

        try:
            communicate = edge_tts.Communicate(text, "es-MX-DaliaNeural")
            audio_bytes = b""
            
            # Streaming en memoria directo de edge-tts
            async def get_bytes():
                nonlocal audio_bytes
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]
            
            asyncio.run(get_bytes())
            
            if audio_bytes:
                audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                # Emitir a la UI (UI se encarga de cambiar los estados del avatar)
                if self.on_audio_ready:
                    self.on_audio_ready(text, audio_b64)
            else:
                print("⚠️ No se generaron bytes de audio de Edge-TTS.")
                
        except Exception as e:
            print(f"❌ Error en síntesis de Edge-TTS: {e}")
        finally:
            self.is_speaking = False

    def speak_async(self, text):
        """Encola el texto para ser procesado sin bloquear"""
        self._speech_queue.put(text)
        
    def clear_queue(self):
        """Vacía la cola de voz para interrupciones"""
        with self._speech_queue.mutex:
            self._speech_queue.queue.clear()


    def wait_until_done(self):
        """Bloquea hasta que todos los elementos en la cola hayan sido procesados por el worker"""
        self._speech_queue.join()

    def _process_queue(self):
        """Thread eterno que procesa la cola"""
        while self._running:
            try:
                text = self._speech_queue.get(timeout=1)
            except Exception:
                continue

            if text is None:
                break

            self._speak_sync(text)
            self._speech_queue.task_done()

    def stop(self):
        """Detiene el worker"""
        self._running = False
        self._speech_queue.put(None)