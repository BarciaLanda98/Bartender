import cv2
import base64
import numpy as np
import time
from config import (
    S25_IP, CAMERA_INDEX,
    CHANGE_THRESHOLD, CAMERA_WARMUP
)


class Eye:
    """Responsable de captura de imágenes y análisis visual via webcam + Gemma-3n.

    Modo on-demand: la cámara se abre solo cuando se necesita y se cierra después.
    Esto evita que la luz de la cámara se quede encendida permanentemente.
    """

    def __init__(self):
        self.active_url = f"http://{S25_IP}:8080/vision"

        # Frame anterior para detección de cambios
        self._previous_frame_gray = None

        # Cámara on-demand (NO se abre al iniciar)
        self._cap = None
        print("📷 Cámara en modo on-demand (se activa solo cuando se necesita)")

    # ------------------------------------------------------------------
    # Cámara on-demand
    # ------------------------------------------------------------------

    def _open_camera(self):
        """Abre webcam local y configura exposición para evitar flash/blancos"""
        if str(CAMERA_INDEX).isdigit():
            if self._cap is not None and self._cap.isOpened():
                return True
            self._cap = cv2.VideoCapture(int(CAMERA_INDEX))
            if not self._cap.isOpened():
                return False
            
            # Intentar desactivar auto-exposición y bajar el brillo para que no se quemen las fotos
            try:
                # 0.25 suele apagar el auto exposure en Windows DirectShow
                self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25) 
                self._cap.set(cv2.CAP_PROP_EXPOSURE, -5) # Forzar exposición más oscura
            except:
                pass
                
            time.sleep(CAMERA_WARMUP)
            return True
        return False

    def _close_camera(self):
        if self._cap is not None and self._cap.isOpened():
            self._cap.release()
        self._cap = None

    def capture_frame(self):
        """Captura un frame. Para IP Webcam, es infinitamente mejor usar /shot.jpg"""
        import urllib.request
        url_str = str(CAMERA_INDEX)

        if url_str.startswith("http"):
            # Reemplazar /video por /shot.jpg para capturas instantáneas sin cargar streams TCP
            cache_busting = f"?t={int(time.time())}"
            if "/video" in url_str:
                shot_url = url_str.replace("/video", "/shot.jpg") + cache_busting
            else:
                shot_url = url_str + cache_busting
                
            try:
                print(f"📷 Descargando Snapshot HTTP de la cámara...")
                req = urllib.request.urlopen(shot_url, timeout=6.0)
                arr = np.asarray(bytearray(req.read()), dtype=np.uint8)
                frame = cv2.imdecode(arr, -1)
                return frame
            except Exception as e:
                print(f"❌ Error descargando Snapshot Red: {e}")
                return None
        else:
            # Cámara USB Local (Fallback)
            if not self._open_camera():
                return None
            ret, frame = self._cap.read()
            return frame if ret else None

    def capture_image(self):
        """Captura una imagen, la guarda en disco y la convierte a base64."""
        frame = self.capture_frame()
        if frame is None:
            return None

        # --- NUEVO: REDIMENSIONAR PARA EVITAR FATIGA Y CORRUPCIÓN DE MOONDREAM (!!!IMAGE!!!) ---
        max_size = 800
        height, width = frame.shape[:2]
        if max(height, width) > max_size:
            scale = max_size / max(height, width)
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)))

        # --- RECOMENDACIÓN APLICADA: GUARDAR EN DISCO ---
        try:
            cv2.imwrite("temp_vision.jpg", frame)
            print("💾 Foto física guardada como temp_vision.jpg a buena resolución.")
        except Exception as e:
            print("Fallo menor al guardar temp_vision.jpg:", e)
            
        _, buffer = cv2.imencode('.jpg', frame)
        image_b64 = base64.b64encode(buffer).decode('utf-8')

        # Cerrar cámara después de capturar (apaga la luz)
        self._close_camera()

        return image_b64

    # ------------------------------------------------------------------
    # Detección de cambios
    # ------------------------------------------------------------------

    def detect_change(self, threshold=None):
        """Detecta si hubo un cambio visual significativo entre el frame actual y el anterior"""
        if threshold is None:
            threshold = CHANGE_THRESHOLD

        frame = self.capture_frame()
        if frame is None:
            return False

        # Convertir a escala de grises para comparación eficiente
        current_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Primera captura: guardar referencia y retornar False
        if self._previous_frame_gray is None:
            self._previous_frame_gray = current_gray
            self._close_camera()
            return False

        # Calcular diferencia absoluta entre frames
        diff = cv2.absdiff(self._previous_frame_gray, current_gray)
        change_magnitude = cv2.countNonZero(diff)

        # Actualizar frame de referencia DESPUÉS de comparar
        self._previous_frame_gray = current_gray

        # Cerrar cámara después de comparar
        self._close_camera()

        return change_magnitude > threshold

    # ------------------------------------------------------------------
    # Análisis visual con Moondream
    # ------------------------------------------------------------------

    def describe_image(self, image_base64):
        """Usa el servidor Ktor de visión en el S25 Ultra para describir la imagen"""
        import requests
        import base64
        print("👁️ S25 Ultra analizando imagen...")

        if not image_base64:
            return "(No se recibió imagen para analizar)"

        try:
            # Decodificar la imagen Base64 que viene del `capture_image`
            img_bytes = base64.b64decode(image_base64)

            # Enviar los bytes crudos directamente en el cuerpo (evita errores de parseo multipart de Ktor)
            headers = {
                "Content-Type": "application/octet-stream",
                "X-Prompt": "Describe la imagen de forma concisa y directa."
            }
            response = requests.post(
                self.active_url,
                data=img_bytes,
                headers=headers,
                timeout=25.0
            )

            response.raise_for_status()  # Lanza un error para códigos HTTP 4xx/5xx
            
            description = response.text.strip()
            
            if not description:
                description = "(El sistema de visión devolvió una respuesta vacía.)"
                
            print(f"👁️ El S25 Ultra ve: {description}")
            return description
            
        except requests.exceptions.HTTPError as http_err:
            # Errores específicos del servidor (4xx, 5xx)
            print(f"❌ Error HTTP en el sistema de visión Ktor: {http_err}")
            print(f"   Respuesta del servidor: {http_err.response.text[:500]}")
            return f"(Hubo un error en el servidor de visión: {http_err.response.status_code})"
        except Exception as e:
            # Otros errores (timeouts, conexión, etc.)
            print(f"❌ Error Crítico en el sistema de visión Ktor: {e}")
            return "(No se pudo usar la cámara debido a un problema de conexión con el S25)"

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Libera la cámara de forma segura"""
        self._close_camera()
        print("📷 Cámara liberada")
