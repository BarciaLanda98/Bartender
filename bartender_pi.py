import time
import threading
from flask import Flask, request, jsonify
import RPi.GPIO as GPIO

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE PINES GPIO
# ==========================================
# Motor DC (L298N)
# Conectados según lo indicado por el usuario
PIN_IN1 = 16
PIN_IN2 = 20
PIN_ENA = 21

# Relés de las Bombas (Ajusta según tu conexión)
# Usa los pines reales a los que conectaste cada relé
PUMPS = {
    "pump_1": 19,
    "pump_2": 6,
    "pump_3": 13,
    "pump_4": 5
}

# Configuración del motor DC
VELOCIDAD = 80        # 0-100 (duty cycle en %)
PWM_FREQ = 1000       # Frecuencia del PWM en Hz

# Las posiciones de las bombas (ver BOMBAS_CONFIG en config.py) están definidas
# directamente en SEGUNDOS de movimiento de motor (medidos empíricamente a VELOCIDAD=80),
# no en centímetros físicos. FACTOR_CALIBRACION es un multiplicador de ajuste fino:
# déjalo en 1.0 si tus tiempos medidos ya son exactos. Súbelo (ej. 1.05) si el riel
# se queda corto, o bájalo (ej. 0.95) si se pasa de la posición.
FACTOR_CALIBRACION = 1.0
pwm_motor = None

# ==========================================
# ESTADO GLOBAL
# ==========================================
is_busy = False      # Para evitar que sirva dos bebidas al mismo tiempo
current_position = 0 # Posición actual, expresada en SEGUNDOS de recorrido de motor desde el origen

# Inicialización de GPIO
def setup_gpio():
    global pwm_motor
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Motor DC
    GPIO.setup(PIN_IN1, GPIO.OUT)
    GPIO.setup(PIN_IN2, GPIO.OUT)
    GPIO.setup(PIN_ENA, GPIO.OUT)
    
    # Iniciar PWM
    pwm_motor = GPIO.PWM(PIN_ENA, PWM_FREQ)
    pwm_motor.start(0)
    
    # Bombas
    for pin in PUMPS.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH) # Asumiendo relés activos en LOW (ajustar si es necesario)

def detener_motor():
    GPIO.output(PIN_IN1, GPIO.LOW)
    GPIO.output(PIN_IN2, GPIO.LOW)
    pwm_motor.ChangeDutyCycle(0)

def mover_motor(target_seg):
    global current_position
    if target_seg == current_position:
        return
        
    distance = target_seg - current_position
    tiempo_movimiento = abs(distance) * FACTOR_CALIBRACION
    
    print(f"⚙️ [MOTOR] Moviendo a posición {target_seg}s (Tiempo estimado: {tiempo_movimiento:.2f}s)...")
    
    # Dirección
    if distance > 0:
        # Adelante (invertido físicamente)
        GPIO.output(PIN_IN1, GPIO.LOW)
        GPIO.output(PIN_IN2, GPIO.HIGH)
    else:
        # Atrás (invertido físicamente)
        GPIO.output(PIN_IN1, GPIO.HIGH)
        GPIO.output(PIN_IN2, GPIO.LOW)
        
    # Arrancar motor usando PWM
    pwm_motor.ChangeDutyCycle(VELOCIDAD)
    
    # Esperar el tiempo calculado
    time.sleep(tiempo_movimiento)
    
    # Detener motor
    detener_motor()
    
    current_position = target_seg
    print(f"⚙️ [MOTOR] Llegó a la posición calculada para {target_seg}s.")

def servir_bebida_multi_hilo(steps):
    global is_busy
    try:
        for i, step in enumerate(steps, 1):
            pump_key = step.get('pump')
            amount_ml = step.get('amount_ml', 0)
            target_seg = step.get('seg', step.get('cm', 0.0))  # 'seg' es la clave nueva; 'cm' se acepta por compatibilidad
            
            if amount_ml <= 0:
                continue
                
            print(f"🍹 [PASO {i}/{len(steps)}] Preparando {amount_ml}mL en {pump_key} a {target_seg}s...")
            
            # 1. Mover el vaso a la posición de la bomba (mover_motor calcula relativo a current_position)
            mover_motor(target_seg)
            time.sleep(0.5) # Pausa para estabilizar
            
            # 2. Encender bomba
            pump_pin = PUMPS.get(pump_key)
            if pump_pin:
                print(f"💧 [BOMBA] Encendiendo {pump_key} para servir {amount_ml}mL...")
                # Cálculo de tiempo (Bombas peristálticas pequeñas: ~1.5mL por segundo)
                tiempo_servido = amount_ml / 1.5 
                
                GPIO.output(pump_pin, GPIO.LOW) # RELÉ ON
                time.sleep(tiempo_servido)
                GPIO.output(pump_pin, GPIO.HIGH) # RELÉ OFF
                print(f"💧 [BOMBA] Apagada. Servido exitoso.")
                
            time.sleep(0.5) # Pausa corta antes de la siguiente posición para evitar goteo
            
        time.sleep(1) # Pausa final antes de regresar
        
        # 3. Regresar al origen (Posición 0)
        print("⚙️ [MOTOR] Regresando a la posición de origen (0s)...")
        mover_motor(0)
        
    except Exception as e:
        print(f"❌ [ERROR] Falló la secuencia de servido: {e}")
    finally:
        # Liberar la máquina
        is_busy = False
        print("✅ [FIN] Máquina lista para la siguiente bebida.")

# ==========================================
# RUTAS DEL SERVIDOR
# ==========================================
@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "ready", "busy": is_busy}), 200

@app.route('/prepare', methods=['POST'])
def prepare_drink():
    global is_busy
    if is_busy:
        return jsonify({"error": "La máquina está ocupada preparando otra bebida"}), 409
        
    data = request.get_json()
    steps = data.get('steps', [])
    
    # Retrocompatibilidad por si se recibe el formato viejo de un solo paso
    if not steps:
        pump_key = data.get('pump')
        amount_ml = data.get('amount_ml', 100)
        target_seg = data.get('seg', data.get('cm', 0))
        if pump_key:
            steps = [{"pump": pump_key, "amount_ml": amount_ml, "seg": target_seg}]
            
    if not steps:
        return jsonify({"error": "No se especificaron pasos o ingredientes"}), 400
        
    # Validar que las bombas existan
    for step in steps:
        pump_key = step.get('pump')
        if not pump_key or pump_key not in PUMPS:
            return jsonify({"error": f"Bomba no válida: {pump_key}"}), 400
            
    # Bloquear la máquina
    is_busy = True
    
    # Lanzar hilo en segundo plano (No bloquea la petición web)
    hilo = threading.Thread(target=servir_bebida_multi_hilo, args=(steps,))
    hilo.start()
    
    # Responder INMEDIATAMENTE a MIA (Laptop)
    return jsonify({
        "status": "processing",
        "message": f"Iniciando preparación secuencial con {len(steps)} ingredientes..."
    }), 200

if __name__ == '__main__':
    print("🍹 Iniciando Servidor Bartender en Raspberry Pi (MODO HILOS) 🍹")
    setup_gpio()
    try:
        app.run(host='0.0.0.0', port=5001)
    except KeyboardInterrupt:
        print("Apagando servidor...")
    finally:
        GPIO.cleanup()