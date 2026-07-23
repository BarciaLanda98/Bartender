from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import threading
import time
import sys
import io
from assistant import VoiceAssistant

# Fix consola Windows UTF-8 (Método seguro para Python 3.7+)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

app = Flask(__name__)
# Inicializar SocketIO usando threading estándar para evitar alertas de obsolescencia
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

mia = None

# Sincronización de audio manejada dentro de la instancia de mia

def start_mia_backend():
    """Inicia MIA en un hilo separado"""
    global mia
    mia = VoiceAssistant(socketio)

    # Conectar el audio de Voice al frontend DESDE EL INICIO (no solo dentro de un
    # comando completo) — si no, el "¿Sí?" del wake word solo nunca llega al navegador
    # la primera vez que se usa (on_audio_ready seguía en None hasta el primer comando).
    def push_audio_chunk(text_resp, b64_audio):
        mia.set_state("audio_payload_chunk", {"text": text_resp, "audio": b64_audio})
    mia.voice.on_audio_ready = push_audio_chunk

    # Cada vez que MIA cambia de estado, se emite al Socket
    def on_mia_state_change(new_state, data=None):
        if new_state == "audio_payload_chunk":
            # Hemos recibido un MP3 en base64 de Edge-TTS (Stream chunk)
            socketio.emit('play_audio_chunk', {
                'text': data['text'],
                'audio_b64': data['audio']
            })
            # IMPORTANTE: No bloqueamos aquí para permitir que los chunks fluyan asíncronamente a la UI
            
        else:
            socketio.emit('state_update', {
                "state": new_state,
                "text": data if data else ""
            })
            
    mia.on_state_change = on_mia_state_change
    mia.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/command', methods=['POST'])
def handle_api_command():
    """Recibe comandos de texto directamente desde la App Android Nativa (C:/MIA)"""
    if mia:
        data = request.get_json()
        
        # --- APRENDIZAJE DINÁMICO DE IP ---
        # Si la IP del celular cambia (ej. al cambiar de WiFi a datos móviles),
        # la aprendemos automáticamente cuando el celular nos manda el primer comando.
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', ''))
        if client_ip and not client_ip.startswith('127.') and not client_ip.startswith('::1'):
            if hasattr(mia, 'brain') and mia.brain:
                new_chat_url = f"http://{client_ip}:8080/chat"
                new_vision_url = f"http://{client_ip}:8080/vision"
                if mia.brain.active_url != new_chat_url:
                    mia.brain.active_url = new_chat_url
                    if hasattr(mia, 'eye') and mia.eye:
                        mia.eye.active_url = new_vision_url
                    print(f"📡 ¡IP del Celular actualizada automáticamente a {client_ip}!")
        # ----------------------------------

        if data and "text" in data:
            text = data["text"].strip()
            if text:
                print(f"📱 Comando Nativo Android recibido: {text}")
                
                # LIMPIEZA: Remover muletillas o wake words del inicio para no ensuciar el prompt
                import re
                text = re.sub(r'^(hey mia|ey mia|m mia|oye mia|hola mia|mia)\b\s*,?\s*', '', text, flags=re.IGNORECASE)
                text = text.strip() or "Hola" # Si solo dijo "MIA", lo cambiamos a "Hola"
                
                # INTERRUPCIÓN: Si MIA estaba hablando, la silenciamos y abortamos audio pendiente
                if hasattr(mia, 'voice') and mia.voice:
                    mia.voice.clear_queue()
                socketio.emit('stop_audio')
                
                queue = mia.ear.audio_queue if mia.ear else mia.audio_queue
                queue.put(text)
                mia.set_state("listening")
                return jsonify({"status": "success", "message": "Command received"}), 200
    return jsonify({"status": "error", "message": "Invalid request or MIA offline"}), 400

@socketio.on('audio_finished')
def handle_audio_finished():
    """El navegador web avisa que terminó de reproducir toda la cola de audios"""
    if mia:
        mia.audio_playback_done.set()

@socketio.on('request_state')
def handle_request_state():
    """El cliente pide el estado actual de MIA (al conectar o reconectar)"""
    if mia:
        socketio.emit('state_update', {'state': mia.state, 'text': ''})
    else:
        socketio.emit('state_update', {'state': 'idle', 'text': ''})

@socketio.on('connect')
def handle_connect():
    """Cuando un cliente se conecta, captura su IP y actualiza el cerebro si es el S25 Ultra."""
    global mia
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', ''))
    # Filtrar loopback
    if client_ip and not client_ip.startswith('127.') and not client_ip.startswith('::1'):
        print(f"🔗 Cliente conectado desde: {client_ip}")
        if mia and hasattr(mia, 'brain') and mia.brain:
            new_chat_url = f"http://{client_ip}:8080/chat"
            new_vision_url = f"http://{client_ip}:8080/vision"
            import socket as _sock
            # TCP check rápido: si el puerto 8080 está abierto, es el S25
            port_open = False
            try:
                with _sock.create_connection((client_ip, 8080), timeout=2.0):
                    port_open = True
            except Exception:
                pass
            
            if port_open:
                old_url = mia.brain.active_url
                mia.brain.active_ip = client_ip
                mia.brain.active_url = new_chat_url
                # Actualizar también el sistema de visión
                if hasattr(mia, 'eye') and mia.eye:
                    mia.eye.active_url = new_vision_url
                print(f"🧠✅ Cerebro actualizado automáticamente: {old_url} → {new_chat_url}")
            else:
                print(f"   (Puerto 8080 no activo en {client_ip} — no es el S25 o Ktor está apagado)")


@socketio.on('user_command')
def handle_text_command(data):
    """Comandos enviados desde el PTT de la página web nativa"""
    if mia:
        text = data.get("text", "").strip()
        if text:
            print(f"🎧 Recibido PTT Web: {text}")
            
            # LIMPIEZA: Remover muletillas o wake words del inicio para no ensuciar el prompt
            import re
            text = re.sub(r'^(hey mia|ey mia|m mia|oye mia|hola mia|mia)\b\s*,?\s*', '', text, flags=re.IGNORECASE)
            text = text.strip() or "Hola" # Si solo dijo "MIA", lo cambiamos a "Hola"
            
            # INTERRUPCIÓN: Si MIA estaba hablando, la silenciamos y abortamos audio pendiente
            if hasattr(mia, 'voice') and mia.voice:
                mia.voice.clear_queue()
            socketio.emit('stop_audio')
            
            queue = mia.ear.audio_queue if mia.ear else mia.audio_queue
            queue.put(text)
            mia.set_state("listening")

@socketio.on('request_vision')
def handle_request_vision(data=None):
    """Botón explícito de 'Analizar Entorno' desde el navegador"""
    if mia and mia.ear:
        print("🌐 Solicitud Manual de Visión recibida")
        if data and isinstance(data, dict) and "image" in data:
            mia.latest_frontend_image = data["image"]
            print("📸 Recibida imagen en Base64 desde el Frontend")
        else:
            mia.latest_frontend_image = None
            print("📸 No se recibió imagen desde el Frontend. Se usará la cámara local/IP.")
            
        # Inyectar un comando simulado que tiene las palabras clave de visión
        mia.ear.audio_queue.put("mira esto y dime qué ves")
        mia.set_state("listening")

# ------------------------------------------------------------------
# 🚧 HOLDER / STUB: RASPBERRY PI INTEGRATION (BARTENDER 3.0)
# ------------------------------------------------------------------
# Futuro: Añade aquí la lógica de PySerial o Paho-MQTT para conectar con 
# el puerto COM o IP de la Raspberry Pi que controla los servomotores / brazo.
# Ejemplo:
# def send_to_robot(command_id):
#     try:
#         import serial
#         ser = serial.Serial('COM3', 9600)
#         ser.write(b'MOVE_ARM\n')
#         ser.close()
#     except Exception as e:
#         print("Fallo brazo:", e)
# ------------------------------------------------------------------

if __name__ == '__main__':
    # NOTA: socketio.run() (Werkzeug) corre en un hilo aparte, y VoiceAssistant()
    # se crea en el hilo principal. En este entorno, calibrar el mic en un hilo
    # secundario mientras Werkzeug sirve en el principal se cuelga indefinidamente
    # (probablemente por inicialización de COM/WASAPI atada al hilo principal).
    def run_flask():
        print("\n" + "="*50)
        print("🌐 SERVIDOR SOCKET.IO INICIADO")
        print("👉 Abre http://[IP_DE_TU_LAPTOP]:5000 en tu celular o ingresa en localhost:5000 en el navegador")
        print("="*50 + "\n")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    time.sleep(1)

    start_mia_backend()

    flask_thread.join()
