import threading
import time
from queue import Empty, Queue
from eye import Eye
from ear import Ear
from voice import Voice
from brain import Brain
from robot_control import RobotControl
from config import (
    VISUAL_COMMENT_COOLDOWN, VISION_CHECK_INTERVAL,
    VISION_POST_COMMENT_PAUSE, HEALTH_CHECK_INTERVAL,
    PROACTIVE_VISION, VISION_WORDS, ENABLE_BACKEND_MIC
)


class VoiceAssistant:
    """Orquesta visión, audio y respuestas de MIA.

    Flujo:
    - Thread de audio: escucha 'Hey MIA' → captura comando → responde
    - Thread de visión (opcional): detecta cambios visuales → comenta
    - Thread de salud: monitorea conexión al S25 Ultra

    Anti-eco: El oído se silencia mientras MIA habla.
    Cámara on-demand: Solo se enciende cuando se necesita.
    """

    def __init__(self, socketio=None):
        print("=" * 50)
        print("🤖 Inicializando MIA...")
        print("=" * 50)

        self.socketio = socketio
        self.audio_queue = Queue()  # Cola principal si el Ear está apagado
        
        self.eye = Eye()
        
        self.ear = Ear(socketio=self.socketio) if ENABLE_BACKEND_MIC else None
        if not ENABLE_BACKEND_MIC:
            print("🎧 Sistema de escucha backend (laptop) DESACTIVADO. Usando S25 Ultra nativo.")
            
        self.voice = Voice()
        self.brain = Brain()
        self.robot = RobotControl()

        # Compartir la URL activa del S25 Ultra auto-detectada con el sistema de visión
        self.eye.active_url = self.brain.active_url.replace("/chat", "/vision")

        self.is_running = False
        self._last_visual_comment = 0
        self._threads = []

        # Estado del sistema (para la UI Web)
        self.state = "idle"
        self.on_state_change = None

        # Lock para evitar que MIA hable de visión mientras responde al usuario
        self._speaking_lock = threading.Lock()

        # Sincronización con el frontend
        self.audio_playback_done = threading.Event()
        self.latest_frontend_image = None

        # Anti-eco y prevención de conflictos de audio:
        if self.ear:
            self.ear.set_mute_check(lambda: self._speaking_lock.locked() or self.voice.is_speaking)

        # Confirmación auditiva: cuando detecta "Hey MIA", dice "¿Sí?"
        # para que el usuario sepa que debe hablar
        if self.ear:
            self.ear.set_wake_callback(lambda: self.voice.speak_async("¿Sí?"))

        print("=" * 50)
        print("✅ MIA lista para funcionar")
        print("=" * 50)

    # ------------------------------------------------------------------
    # Thread: Visión proactiva (OPCIONAL)
    # ------------------------------------------------------------------

    def _react_to_vision(self):
        """Monitorea cambios visuales y comenta automáticamente.
        Solo se ejecuta si PROACTIVE_VISION = True en config.
        """
        print("👁️ Thread de visión proactiva iniciado")

        while self.is_running:
            try:
                time.sleep(VISION_CHECK_INTERVAL)

                if not self.is_running:
                    break

                # No comentar si está en cooldown
                if time.time() - self._last_visual_comment < VISUAL_COMMENT_COOLDOWN:
                    continue

                # No comentar si está atendiendo al usuario o hablando
                if self._speaking_lock.locked() or self.voice.is_speaking:
                    continue

                # Detectar cambio visual
                if not self.eye.detect_change():
                    continue

                # Capturar y describir lo que ve
                image_base64 = self.eye.capture_image()
                if not image_base64:
                    continue

                visual_desc = self.eye.describe_image(image_base64)
                if not visual_desc:
                    continue

                # Generar comentario sarcástico
                with self._speaking_lock:
                    mia_comment = self.brain.think_about_vision(visual_desc)
                    if mia_comment:
                        self.voice.speak_async(mia_comment)
                        self._last_visual_comment = time.time()
                        # Pausa larga después de comentar para no saturar
                        time.sleep(VISION_POST_COMMENT_PAUSE)

            except Exception as e:
                print(f"❌ Error en thread de visión: {e}")
                time.sleep(10)  # Pausa larga tras error

    def _needs_vision(self, text):
        """Determina si el comando requiere usar la cámara.

        'Hey MIA di hola' → False (solo hablar, rápido)
        'Hey MIA mira esto' → True (usar cámara + Moondream)
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in VISION_WORDS)

    def set_state(self, new_state, data=None):
        """Actualiza el estado de MIA y notifica a los listeners (servidor web)"""
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(new_state, data)

    def _listen_for_commands(self):
        """Escucha comandos del usuario activados por wake word 'Hey MIA' o desde PTT/Web

        Routing inteligente:
        - Comando con palabra visual (mira, observa, etc.) → cámara + cerebro
        - Comando normal (di hola, cuéntame, etc.) → solo cerebro (rápido)
        """
        print("🎤 Thread de procesamiento de comandos iniciado")

        if self.ear:
            # Configurar callback cuando Ear.py entra en modo activo "escuchando"
            self.ear.set_wake_callback(lambda: [
                self.set_state("listening"), 
                self.voice.speak_async("¿Sí?")
            ])

            # Iniciar escucha continua pasiva en Windows
            self.ear.start_listening_thread()
            print("🎧 Sistema Híbrido Activado: Escuchando micrófono Windows y Web PTT simultáneamente.")
        else:
            print("🎧 Escucha pasiva de Windows desactivada. MIA solo responderá a Web PTT o Auto-Escucha Web.")

        while self.is_running:
            try:
                # Esperar comando transcrito (de PTT Web o de Ear.py)
                # Si ear no existe, leemos de self.audio_queue directamente
                queue_to_read = self.ear.audio_queue if self.ear else self.audio_queue
                user_input = queue_to_read.get(timeout=1)

                print(f"👤 Usuario dice: {user_input}")

                with self._speaking_lock:
                    visual_context = ""
                    image_base64 = None

                    # Solo usar cámara si el usuario lo pide explícitamente
                    if self._needs_vision(user_input):
                        self.set_state("vision", data=user_input)
                        print("👁️ Modo VISIÓN activado")
                        
                        if self.latest_frontend_image:
                            image_base64 = self.latest_frontend_image
                            self.latest_frontend_image = None
                            print("📸 Usando la imagen enviada por el Frontend")
                        else:
                            print("📸 Usando cámara local de la Laptop...")
                            image_base64 = self.eye.capture_image()
                            
                        if image_base64:
                            visual_context = self.eye.describe_image(image_base64)
                            if "error" in visual_context.lower() or "no se pudo" in visual_context.lower():
                                # Interceptar error técnico para evitar alucinaciones
                                visual_context = "ERROR: El sistema de visión no está respondiendo. Dile al usuario de forma muy amigable que no puedes ver en este momento por problemas de conexión."
                    else:
                        print("⚡ Modo RÁPIDO (sin cámara)")

                    # Generar respuesta (ahora devuelve un Generador)
                    self.set_state("thinking", data=user_input)
                    raw_response_gen = self.brain.respond_to_user(
                        user_input, visual_context=visual_context
                    )

                    # Filtrar comandos del robot y etiquetas <think> en caliente (con soporte JSON)
                    import re
                    import json
                    robot_command = None
                    buffered_text = ""
                    is_json_response = False
                    full_response_buffer = ""

                    def clean_generator():
                        nonlocal buffered_text, robot_command, is_json_response, full_response_buffer
                        if not raw_response_gen:
                            return
                        
                        inside_think = False
                        think_buffer = ""
                        is_first_non_think_char = True
                        
                        def process_clean_text(text):
                            nonlocal buffered_text, robot_command, is_json_response, full_response_buffer
                            
                            # Si detectamos que la respuesta es JSON (empieza con '{' o '```json')
                            if is_first_non_think_char:
                                stripped = text.strip()
                                if stripped.startswith('{') or stripped.startswith('```'):
                                    is_json_response = True
                            
                            if is_json_response:
                                # Acumular el JSON completo
                                full_response_buffer += text
                                return
                                
                            combined = buffered_text + text
                            if '[' in combined and ']' not in combined:
                                buffered_text = combined
                                return

                            # Capturar emoción explícita (con o sin corchetes perfectos)
                            match_emotion = re.search(r'\[?EMOCI[OÓ]N:\s*([a-zA-ZáéíóúÁÉÍÓÚñÑ]+)\]?', combined, re.IGNORECASE)
                            if match_emotion:
                                emotion_val = match_emotion.group(1).strip().lower()
                                self.socketio.emit('emotion_update', {'emotion': emotion_val})
                                print(f"🎭 Emoción detectada: {emotion_val}")
                                combined = re.sub(r'\[?EMOCI[OÓ]N:\s*[a-zA-ZáéíóúÁÉÍÓÚñÑ]+\]?', '', combined, flags=re.IGNORECASE)

                            # Capturar comando del robot (con o sin corchetes)
                            match_robot = re.search(r'\[?ROBOT:PREPARAR:?\s*([^\]\.\-]+?)(?=\]|\.|\-|$)', combined, re.IGNORECASE)
                            if match_robot:
                                drink_name = match_robot.group(1).strip()
                                robot_command = f"PREPARAR:{drink_name}"
                                print(f"🔧 [DEBUG] robot_command capturado en assistant.py: {robot_command!r}")
                                combined = re.sub(r'\[?ROBOT:PREPARAR:?\s*[^\]\.\-]+\]?', '', combined, flags=re.IGNORECASE)

                            # Separar por signos de puntuación finales
                            import re as regex
                            # Buscamos puntos, signos de exclamación/interrogación seguidos opcionalmente de un espacio
                            sentences = regex.split(r'(?<=[.!?\n])\s*', combined)
                            
                            # Todas las oraciones completas (excepto la última si no termina en puntuación)
                            for i in range(len(sentences) - 1):
                                clean_text = sentences[i].strip()
                                if clean_text:
                                    yield clean_text
                            
                            # La última parte queda en el buffer esperando más texto
                            buffered_text = sentences[-1]

                        for chunk in raw_response_gen:
                            # Si estamos dentro de un bloque <think>
                            if inside_think:
                                think_buffer += chunk
                                if "</think>" in think_buffer:
                                    parts = think_buffer.split("</think>", 1)
                                    inside_think = False
                                    chunk = parts[1]  # Continuar procesando lo que esté después de </think>
                                    think_buffer = ""
                                else:
                                    continue  # Omitir contenido de pensamiento
                            
                            # Si estamos fuera del bloque <think>
                            if not inside_think:
                                if "<think>" in chunk:
                                    parts = chunk.split("<think>", 1)
                                    chunk_before = parts[0]
                                    if chunk_before.strip():
                                        if is_first_non_think_char:
                                            is_first_non_think_char = False
                                        yield from process_clean_text(chunk_before)
                                    inside_think = True
                                    think_buffer = parts[1]
                                    if "</think>" in think_buffer:
                                        subparts = think_buffer.split("</think>", 1)
                                        inside_think = False
                                        chunk = subparts[1]
                                        think_buffer = ""
                                    else:
                                        continue
                                
                                if chunk.strip() and is_first_non_think_char:
                                    # Peek at the chunk to see if it's JSON before clearing the flag
                                    stripped = chunk.strip()
                                    if stripped.startswith('{') or stripped.startswith('```'):
                                        is_json_response = True
                                    is_first_non_think_char = False
                                    
                                yield from process_clean_text(chunk)
                                
                        # Vaciar cualquier texto restante en el buffer si no es JSON
                        if not is_json_response and buffered_text.strip():
                            yield buffered_text.strip()
                            buffered_text = ""
                            
                        # Si era JSON, procesarlo todo al final y yield el texto
                        if is_json_response and full_response_buffer.strip():
                            clean_res = full_response_buffer.strip()
                            if clean_res.startswith("```json"):
                                clean_res = clean_res[7:]
                            if clean_res.endswith("```"):
                                clean_res = clean_res[:-3]
                            clean_res = clean_res.strip()
                            
                            try:
                                data = json.loads(clean_res)
                                spoken_text = data.get("texto") or data.get("response") or data.get("respuesta") or data.get("message")
                                if "preparar" in data and data["preparar"]:
                                    robot_command = data["preparar"]
                                if spoken_text:
                                    yield spoken_text
                            except Exception as e:
                                print(f"⚠️ Error al parsear JSON de respuesta: {e}")
                                # Fallback: yield el buffer crudo si no se pudo parsear
                                yield full_response_buffer
                                
                        elif buffered_text:
                            yield buffered_text

                    response_gen = clean_generator()

                    # Reproducir respuesta chunk por chunk
                    if response_gen:
                        self.audio_playback_done.clear()
                        
                        is_first = True
                        for chunk_text in response_gen:
                            if is_first:
                                self.set_state("speaking", data={"text": chunk_text})
                                is_first = False
                            
                            # Callback en-sitio que el generador de Audio llama cuando tiene el pedazo mp3
                            def push_audio_chunk(text_resp, b64_audio):
                                self.set_state("audio_payload_chunk", {"text": text_resp, "audio": b64_audio})
                                
                            self.voice.on_audio_ready = push_audio_chunk
                            self.voice.speak_async(chunk_text)

                        if is_first:
                            fallback_text = (
                                f"Claro, voy a preparar {robot_command}."
                                if robot_command else
                                "Perdon, no pude construir una respuesta clara. Intentalo de nuevo."
                            )
                            self.set_state("speaking", data={"text": fallback_text})

                            def push_audio_chunk(text_resp, b64_audio):
                                self.set_state("audio_payload_chunk", {"text": text_resp, "audio": b64_audio})

                            self.voice.on_audio_ready = push_audio_chunk
                            self.voice.speak_async(fallback_text)
                            is_first = False
                            
                        # Si hay comando de robot, enviarlo YA (en paralelo con lo que MIA sigue
                        # hablando/sintetizando) en vez de esperar a que termine toda la charla —
                        # así el trago se empieza a preparar mientras MIA todavía habla, como un
                        # bartender real, y no se siente lento cuando la respuesta es larga.
                        thanks_text = None
                        if robot_command:
                            if robot_command.startswith("PREPARAR:"):
                                readable_name = robot_command.replace("PREPARAR:", "", 1).strip()
                                thanks_text = f"Tu {readable_name} está listo. ¡Muchas gracias por tu preferencia y vuelve pronto!"
                            elif robot_command.startswith("MEZCLAR:"):
                                readable_name = "mezcla especial"
                                thanks_text = f"Tu {readable_name} está lista. ¡Espero que disfrutes esta creación única!"
                            else:
                                readable_name = robot_command
                                thanks_text = f"Tu bebida está lista. ¡Disfrútala!"

                            self.set_state("preparing_drink", data=readable_name)
                            print(f"⚙️ Acción de Robot: {robot_command} ({readable_name})")
                            self.robot.send_drink_command(robot_command)

                        # El backend ya procesó e inyectó todo el texto a Edge-TTS.
                        # Esperamos a que el VoiceWorker termine de sintetizar y emitir todos los chunks
                        self.voice.wait_until_done()
                        self.set_state("all_audio_sent")

                        # Ahora bloqueamos la reactivación de listening local del orquestador
                        # hasta que el celular confirme que la COLA EN JavaScript terminó de sonar.
                        # Si el audio se reprodujo localmente (Pi standalone, sin navegador
                        # escuchando), esa confirmación nunca llega — no hay por qué esperarla.
                        if self.voice.last_used_browser:
                            self.audio_playback_done.wait(timeout=60.0)
                        
                        # Si hay comando de robot, esperar a que termine y agradecer
                        if robot_command:
                            # MIA espera dinámicamente hasta que la Raspberry Pi diga que terminó
                            self.robot.wait_for_drink_ready(timeout=120)
                            
                            # MIA habla automáticamente al terminar de preparar la bebida
                            self.set_state("speaking", data={"text": thanks_text})
                            
                            self.audio_playback_done.clear()
                            def push_audio_chunk(text_resp, b64_audio):
                                self.set_state("audio_payload_chunk", {"text": text_resp, "audio": b64_audio})
                            
                            self.voice.on_audio_ready = push_audio_chunk
                            self.voice.speak_async(thanks_text)
                            self.voice.wait_until_done()
                            self.set_state("all_audio_sent")
                            
                            # Esperar a que termine de reproducir el agradecimiento en el navegador
                            # (solo aplica si de verdad se mandó ahí, ver nota arriba)
                            if self.voice.last_used_browser:
                                self.audio_playback_done.wait(timeout=10.0)
                        
                        self.set_state("idle")

            except Empty:
                # Si estamos escuchando, no hay comando en la cola, y el micro de Windows está inactivo, volver a dormir.
                if self.state == "listening" and not self.ear.is_activated:
                    self.set_state("idle")
                continue
            except Exception as e:
                print(f"❌ Error en thread de audio: {e}")
                time.sleep(1)


    # Control del asistente
    # ------------------------------------------------------------------

    def start(self):
        """Inicia todos los threads de MIA"""
        if self.is_running:
            print("⚠️ MIA ya está en ejecución")
            return

        self.is_running = True
        print("\n🟢 MIA activada — Di 'Hola MIA' para hablarme\n")

        # Crear y lanzar threads
        thread_targets = [
            ("Audio", self._listen_for_commands),
        ]

        # Visión proactiva solo si está habilitada
        if PROACTIVE_VISION:
            thread_targets.insert(0, ("Vision", self._react_to_vision))
            print("👁️ Visión proactiva ACTIVADA")
        else:
            print("👁️ Visión en modo ON-DEMAND (solo cuando hablas)")

        for name, target in thread_targets:
            t = threading.Thread(target=target, daemon=True, name=f"MIA-{name}")
            t.start()
            self._threads.append(t)

    def stop(self):
        """Detiene MIA y libera todos los recursos"""
        print("\n🔴 Deteniendo MIA...")
        self.is_running = False

        # Detener subsistemas
        self.ear.stop_listening()
        self.voice.stop()
        self.eye.cleanup()

        # Esperar a que terminen threads
        for t in self._threads:
            t.join(timeout=3)

        self._threads.clear()
        print("✅ MIA desactivada\n")

    def run_interactive(self):
        """Ejecución interactiva con control por teclado"""
        self.start()

        try:
            while self.is_running:
                cmd = input(
                    "\n📋 Comandos: 'salir' | 'estado' | 'historial' | 'memoria' | 'enseñar' | 'recuerdos'\n> "
                ).strip().lower()

                if cmd == "salir":
                    self.stop()
                    break
                elif cmd == "estado":
                    connected = self.brain.is_connected()
                    active = len([t for t in self._threads if t.is_alive()])
                    mem_stats = self.brain.get_memory_stats()
                    print(f"  🧠 S25 Ultra: {'Conectado' if connected else 'Desconectado'}")
                    print(f"  🧵 Hilos activos: {active}/{len(self._threads)}")
                    print(f"  📷 Cámara: On-demand ({'proactiva' if PROACTIVE_VISION else 'solo al hablar'})")
                    ear_status = 'esperando' if self.ear else 'DESACTIVADO (usando S25/Web)'
                    print(f"  🎤 Wake word: {ear_status}")
                    print(f"  🔇 Anti-eco: {'MUTED (MIA hablando)' if self.voice.is_speaking else 'escuchando'}")
                    print(f"  🧬 Memoria: {'Activa' if mem_stats['enabled'] else 'Desactivada'}"
                          f" — {mem_stats['conversations']} conversaciones, {mem_stats['knowledge']} conocimientos")
                elif cmd == "historial":
                    history = self.brain._format_history()
                    if history:
                        print(f"\n📜 Historial de sesión:\n{history}")
                    else:
                        print("📜 Sin historial en esta sesión")
                elif cmd == "memoria":
                    stats = self.brain.get_memory_stats()
                    if stats["enabled"]:
                        print(f"\n🧬 Memoria a largo plazo (ChromaDB):")
                        print(f"  📝 Conversaciones almacenadas: {stats['conversations']}")
                        print(f"  📚 Conocimientos almacenados: {stats['knowledge']}")
                    else:
                        print("⚠️ Memoria a largo plazo desactivada")
                elif cmd.startswith("enseñar") or cmd.startswith("ensenar"):
                    fact = input("📚 ¿Qué quieres que MIA recuerde? > ").strip()
                    if fact:
                        category = input("📂 Categoría (preferencia/dato_personal/general/instruccion) [general] > ").strip() or "general"
                        if self.brain.learn_fact(fact, category):
                            print("✅ MIA recordará esto permanentemente")
                        else:
                            print("❌ No se pudo guardar")
                elif cmd.startswith("recuerdos"):
                    query = input("🔍 ¿Qué quieres buscar en la memoria? > ").strip()
                    if query and self.brain.memory:
                        memories = self.brain.memory.recall_conversations(query, n_results=5)
                        if memories:
                            print(f"\n🧬 {len(memories)} recuerdos encontrados:")
                            for i, mem in enumerate(memories, 1):
                                print(f"  {i}. Fernando: \"{mem['user_message']}\"")
                                print(f"     MIA: \"{mem['mia_response']}\"")
                        else:
                            print("🧬 No encontré recuerdos relacionados")
                    elif not self.brain.memory:
                        print("⚠️ Memoria no disponible")
                elif cmd:
                    print("❓ Comando no reconocido")

        except KeyboardInterrupt:
            print("\n⏹️ Interrupción del usuario")
            self.stop()
