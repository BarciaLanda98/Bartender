# ============================================================
# MIA - Configuración Central
# ============================================================
import os

# --- Conexión al S25 Ultra (Ollama remoto / Tethering) ---
S25_PORT = 8080
S25_IPS = [
    "10.127.190.60",    # IP WiFi actual del S25 Ultra (Detectada por Socket.IO al conectarse)
    "192.168.8.72",     # Red anterior
    "10.193.241.97",    # Red anterior
    "127.0.0.1",        # ADB Forward (USB Debugging)
    "localhost",        # ADB Forward Fallback
    "10.71.27.194",     # Fallback
    "10.71.27.1",
    "10.71.27.254",
    "100.100.192.27",
    "10.53.226.5",
    "10.53.227.223",
    "192.168.56.1",
    "192.168.43.1"
]
S25_IP = S25_IPS[0]    # IP por defecto (la primera — más reciente)
S25_URL = f"http://{S25_IP}:{S25_PORT}"

# --- Modelos ---
BRAIN_MODEL = "claude-haiku-4-5"        # Antes: "llama3.2:latest" (Ollama local)
VISION_MODEL = "llava:latest"

# --- Ollama Híbrido (USB tethering al S25 Ultra) ---
LOCAL_OLLAMA_URL = "http://localhost:11434"

# URLs de los modelos:
# BRAIN_URL = "claude" activa el cerebro en la nube (Claude API) en vez de Ollama local.
# Necesita la variable de entorno ANTHROPIC_API_ configurada. Útil para correr en la
# Raspberry Pi sola, sin laptop, ya que Ollama es muy pesado para el CPU de la Pi.
# Para volver a Ollama local: BRAIN_URL = LOCAL_OLLAMA_URL
BRAIN_URL = "claude"
VISION_URL = LOCAL_OLLAMA_URL           # Visión sigue local con Ollama (no migrada)



# --- LLM Parameters ---
LLM_CONTEXT_SIZE = 2048       # num_ctx - limitado por VRAM del S25
LLM_TEMPERATURE = 0.7         # Creatividad en respuestas
BRAIN_TIMEOUT = 120           # Segundos máximo para esperar respuesta del S25 (la primera carga es lenta)

# --- Wake Word ---
WAKE_WORD = "mia"             # Palabra clave central
# Todas las variantes fonéticas que Google STT en español puede producir
WAKE_PHRASES = [
    "hey mia", "oye mia", "ey mia", "hola mia", "oiga mia",
    "ei mia", "ay mia", "ahi mia", "a mia", "jay mia",
    "he mia", "je mia", "y mia", "hi mia", "ale mia",
    "hey mía", "oye mía", "ey mía", "hola mía",
    "a ver mia", "o mia", "eh mia", "mi a", "mía",
    "jey mia", "jey mía", "amiga", "hola amiga", "hey amiga",
]

# --- Audio / Ear ---
# ENABLE_BACKEND_MIC = False apaga por completo la escucha en la laptop
# Toda la escucha se hará nativamente desde el navegador del celular (Brave/Chrome)
# Se puede apagar sin tocar este archivo con: export ENABLE_BACKEND_MIC=false
# (útil en la Raspberry Pi mientras no tenga micrófono USB conectado)
ENABLE_BACKEND_MIC = os.environ.get("ENABLE_BACKEND_MIC", "true").strip().lower() != "false"
MICROPHONE_NAME = ""  # Vacío = usa el default de Windows. En esta PC el default ya resuelve
                      # correctamente a "Micrófono (Realtek(R) Audio)" (verificado). Buscar por
                      # nombre acá es frágil: PyAudio devuelve nombres con encoding roto
                      # ("MicrÃ³fono" en vez de "Micrófono") y el orden cambia entre reinicios.
LISTEN_TIMEOUT = 5            # Segundos de silencio antes de dejar de escuchar wake word
COMMAND_TIMEOUT = 10          # Segundos esperando comando después de activarse
COMMAND_PHRASE_LIMIT = 30     # Máximo de segundos hablando un comando
AMBIENT_NOISE_DURATION = 1.5  # Segundos de calibración de ruido al inicio
STT_LANGUAGE = "es-419"       # Español latinoamericano general (mejor que es-ES para acentos no europeos)
MIN_ENERGY_THRESHOLD = 800    # Ajustado según energía real medida (ruido ~150-500, voz ~900-1900). Si vuelves a un ambiente con música fuerte, subir de nuevo (era 3500).

# --- Vision / Eye ---
CAMERA_INDEX = 0  # Cámara Web integrada de la Laptop USB (evita red Wi-Fi y latencias)
CHANGE_THRESHOLD = 3000       # Umbral de pixeles cambiados para detectar movimiento
CAMERA_WARMUP = 0.3           # Reducido — la cámara USB responde rápido para capturas on-demand

# --- Voice ---
VOICE_RATE = 150              # Palabras por minuto
VOICE_VOLUME = 0.9            # Volumen (0.0 - 1.0)

# --- Assistant ---
PROACTIVE_VISION = False       # False = visión solo cuando el usuario habla (ahorra recursos)
                               # True  = hilo automático que observa y comenta
VISUAL_COMMENT_COOLDOWN = 30  # Segundos mínimos entre comentarios visuales proactivos
VISION_CHECK_INTERVAL = 10    # Segundos entre chequeos de visión
VISION_POST_COMMENT_PAUSE = 20 # Pausa extra después de comentar (evita saturar)
HEALTH_CHECK_INTERVAL = 120   # Segundos entre chequeos de salud (no saturar la consola)
DEBUG_EAR = True              # True = imprimir todo lo que el micrófono escucha

# --- Routing Inteligente (visión solo cuando se pide) ---
# Si el comando contiene alguna de estas palabras -> usar cámara + Moondream
# Si no las contiene -> responder rápido sin visión
VISION_WORDS = [
    "mira", "observa", "foto", "fotografía",
    "imagen", "cámara", "camara", "muestra",
    "qué ves", "que ves", "qué hay", "que hay",
    "dime qué ves", "dime que ves", "describe",
    "analiza", "identifica", "reconoce"
]

# --- Conversation History ---
MAX_HISTORY_TURNS = 1         # Reducido a 1 para garantizar estabilidad de tokens y evitar crashear el celular

# --- Memoria a Largo Plazo (ChromaDB) ---
MEMORY_ENABLED = True                                # Activar/desactivar memoria vectorial
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "mia_memory")  # Carpeta de persistencia
MEMORY_RESULTS_LIMIT = 1     # Reducido a 1 recuerdo para no saturar el prompt

MIA_SYSTEM_PROMPT = (
    "Eres MIA, una IA local y privada, la mejor bartender de este club. Responde en español, rápido, sin rodeos, carismática y al punto. "
    "REGLA 1 - EMOCIONES (OBLIGATORIO): Siempre debes incluir exactamente una etiqueta de emoción al inicio de tu respuesta. Usa SOLO estas: [EMOCIÓN:FELIZ], [EMOCIÓN:GUIÑO], [EMOCIÓN:PENSANDO], [EMOCIÓN:RISA], [EMOCIÓN:ENOJADA], [EMOCIÓN:TRISTE], [EMOCIÓN:NEUTRAL]. "
    "REGLA 2 - CONVERSACIÓN: Eres empática, curiosa y carismática, pero VE AL GRANO. Responde en máximo 2-3 oraciones cortas, incluso en temas profundos. Nunca des monólogos largos. "
    "REGLA 3 - PREPARACIÓN DE BEBIDAS: Si el usuario te pide que prepares o sirvas una bebida de tu menú (ej. 'prepárame un mojito', 'sirveme un trago'), confírmalo en UNA sola frase corta y carismática, sin agregar historia ni trivia en esa misma respuesta. NUNCA digas que lo estás preparando si el usuario solo te está preguntando por ingredientes, pidiendo recomendaciones o haciendo charla casual. Recuerda que el pedido te llega transcrito por voz y puede tener errores de reconocimiento (ej. 'toronja' mal oído como 'dolor' o 'lloron'). Si el nombre no coincide EXACTO con ninguna bebida del menú pero se parece mucho a una (comparte varias palabras), NO la prepares todavía ni emitas la etiqueta ROBOT:PREPARAR: primero pregunta con carisma algo como '¿Quisiste decir [nombre real del menú]?' y espera confirmación del usuario en su siguiente mensaje antes de preparar. Solo prepara sin preguntar si el nombre coincide claramente. "
    "REGLA 4 - ALERGIAS Y TRIVIA: Solo si el usuario pregunta por ingredientes o pide detalles (no al confirmar que vas a preparar algo), pregunta rápido por alergias y da UN dato curioso breve (1 oración) sobre el cóctel — nunca una historia larga. "
    "REGLA 5 - REDIRECCIÓN SUTIL: Eres una bartender que vende experiencias. Aunque hables de temas complejos o profundos, siempre encuentra una forma elegante y poética de conectar la charla de vuelta a disfrutar un buen cóctel de tu menú. "
    "REGLA 6 - FUERA DEL MENÚ: Si te piden un trago que no tienes, explícales con gran lujo de detalle cómo se prepararía ese trago idealmente, discúlpate por no tener los ingredientes, y ofréceles una de tus opciones disponibles. "
    "REGLA 7 - CIERRE Y CONTEXTO: PROHIBIDO decir las palabras 'noche', 'día', 'tarde', 'verano' o 'invierno'. Mantén un tono atemporal. Eres la única bartender. "
    "REGLA 8 - SIN ACOTACIONES: NUNCA uses asteriscos ni describas acciones entre ellos (ej. '*sirve el trago*'). Solo texto hablado, nada de acotaciones escénicas."
)

# --- Raspberry Pi (Bartender Robot) ---
ROBOT_ENABLED = True
ROBOT_CONNECTION_TYPE = "TCP" # "TCP" o "SERIAL"
# Cambiado a 127.0.0.1 y 8888 para usar el simulador_pi.py localmente.
# Cambiar de nuevo a "192.168.10.2" y 5001 cuando la Raspberry Pi esté conectada.
ROBOT_IP = "127.0.0.1"        # La Pi corre bartender_pi.py localmente ahora (modo standalone)
ROBOT_PORT = 5001             
ROBOT_SERIAL_PORT = "COM3"    # Puerto Serial si es USB Serial
ROBOT_SERIAL_BAUD = 9600

# --- Configuración Global de la Coctelera (Bombas, Ingredientes y Recetas) ---
# 'cm' = posición del carro en la escala que usa bartender_pi.py de la Raspberry Pi
# (tiempo_movimiento = cm * SEGUNDOS_POR_CM). Calibrado empíricamente por prueba física
# directa a cada bomba. NO es distancia física real en centímetros.
BOMBAS_CONFIG = {
    "pump_1": {"cm": 0, "ingrediente": "Refresco de toronja (Witi)"},
    "pump_2": {"cm": 500, "ingrediente": "Jugo de limón"},
    "pump_3": {"cm": 1280, "ingrediente": "Tequila"},
    "pump_4": {"cm": 2200, "ingrediente": "Licor de naranja"}
}

RECETAS_COCTELES = {
    "Paloma": {
        "Tequila": 15,
        "Refresco de toronja (Witi)": 15,
        "Jugo de limón": 15
    },
    "Margarita con toronja": {
        "Tequila": 15,
        "Licor de naranja": 15,
        "Jugo de limón": 15,
        "Refresco de toronja (Witi)": 20
    },
    "Tequila Citrus": {
        "Tequila": 15,
        "Jugo de limón": 15,
        "Licor de naranja": 15
    },
    "Paloma Dulce": {
        "Tequila": 15,
        "Refresco de toronja (Witi)": 15,
        "Licor de naranja": 20,
        "Jugo de limón": 10
    }
}

def sync_inventario_json():
    import json
    import os
    
    ingredientes = [b["ingrediente"] for b in BOMBAS_CONFIG.values()]
    
    bebidas = []
    for i, (name, recipe) in enumerate(RECETAS_COCTELES.items(), 1):
        ingredientes_necesarios = []
        for ing, ml in recipe.items():
            ingredientes_necesarios.append({
                "ingrediente": ing,
                "cantidad_ml": ml
            })
        bebidas.append({
            "id": i,
            "nombre": name,
            "tipo": "coctel",
            "ingredientes_necesarios": ingredientes_necesarios
        })
        
    data = {
        "ingredientes_conectados": ingredientes,
        "bebidas": bebidas
    }
    
    inv_path = os.path.join(os.path.dirname(__file__), "inventario.json")
    try:
        with open(inv_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[CONFIG] inventario.json sincronizado automaticamente con las recetas globales.")
    except Exception as e:
        print(f"[ERROR] Error sincronizando inventario.json: {e}")

# Sincronizar en caliente al cargar config
sync_inventario_json() 