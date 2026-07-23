import time
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

is_busy = False

def simular_hardware_multi(steps):
    global is_busy
    current_pos = 0.0
    try:
        for i, step in enumerate(steps, 1):
            pump_key = step.get("pump")
            amount_ml = step.get("amount_ml", 0)
            target_cm = step.get("cm", 0.0)
            
            # Distancia recorrida
            distance = target_cm - current_pos
            tiempo_viaje = max(0.2, abs(distance) / 2.0)
            
            print(f"\n[⚙️ MOTOR] Moviendo vaso de {current_pos}cm a {target_cm}cm (Tomará {tiempo_viaje:.2f}s)...")
            time.sleep(tiempo_viaje)
            current_pos = target_cm
            
            # Asumiendo una velocidad simulada de la bomba
            tiempo_bomba = amount_ml / 5.0
            print(f"[💧 BOMBA] Encendiendo bomba {pump_key} para servir {amount_ml}mL (Tomará {tiempo_bomba:.2f}s)...")
            time.sleep(tiempo_bomba)
            print(f"[💧 BOMBA] Apagada. Servido de {amount_ml}mL exitoso.")
            
        # Regresar al origen
        if current_pos > 0:
            tiempo_retorno = max(0.5, current_pos / 2.0)
            print(f"\n[⚙️ MOTOR] Regresando vaso de {current_pos}cm a 0cm (Tomará {tiempo_retorno:.2f}s)...")
            time.sleep(tiempo_retorno)
            
    except Exception as e:
        print(f"[!] Error simulando hardware: {e}")
    finally:
        is_busy = False
        print("[✅ ÉXITO] ¡Coctel preparado virtualmente! Máquina libre.\n")

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"status": "ready", "busy": is_busy}), 200

@app.route('/prepare', methods=['POST'])
def prepare():
    global is_busy
    if is_busy:
        return jsonify({"error": "Ocupado"}), 409
        
    data = request.get_json()
    steps = data.get('steps', [])
    
    if not steps:
        # Retrocompatibilidad
        pump_key = data.get('pump')
        amount_ml = data.get('amount_ml', 100)
        target_cm = data.get('cm', 0)
        if pump_key:
            steps = [{"pump": pump_key, "amount_ml": amount_ml, "cm": target_cm}]
            
    if not steps:
        return jsonify({"error": "No se especificaron pasos"}), 400
        
    is_busy = True
    print(f"\n==================================================")
    print(f"🍹 ORDEN RECIBIDA: Preparar {len(steps)} ingredientes")
    for step in steps:
        print(f"  - {step.get('pump')}: {step.get('amount_ml')}mL a {step.get('cm')}cm")
    print(f"==================================================")
    
    hilo = threading.Thread(target=simular_hardware_multi, args=(steps,))
    hilo.start()
    
    return jsonify({"status": "processing"}), 200

if __name__ == "__main__":
    print("==================================================")
    print("🍹 INICIANDO SIMULADOR VIRTUAL (HTTP FLASK) 🍹")
    print("Escuchando en http://127.0.0.1:8888...")
    print("==================================================")
    # IMPORTANTE: Desactivamos los logs de werkzeug para no ensuciar la consola
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='127.0.0.1', port=8888)