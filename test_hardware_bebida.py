#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MIA - Programa de Prueba de Hardware (Flujo Manual Adaptado)
============================================================
Este script permite probar el hardware (motor y bombas) de la coctelera MIA.
Puedes configurar los ingredientes en las bombas, ver qué tragos están listos,
ejecutar secuencias completas, purgar de limpieza o hacer diagnósticos individuales.

Funciona en 2 modos:
1. MODO REMOTO (HTTP): Se ejecuta desde la Laptop (Windows) y envía comandos 
   a la Raspberry Pi por red HTTP (sin pasar por el flujo de voz o IA).
2. MODO LOCAL (GPIO): Se ejecuta directamente en la Raspberry Pi y controla
   los pines físicos (GPIO) usando el mismo flujo que bartender_pi.py.
"""

import sys
import os
import json
import time

# Asegurar que el directorio de trabajo actual esté en el PATH de Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Intentar cargar la configuración centralizada de MIA
try:
    from config import BOMBAS_CONFIG, RECETAS_COCTELES, ROBOT_IP, ROBOT_PORT
    CONFIG_LOADED = True
except ImportError:
    CONFIG_LOADED = False
    # Configuraciones por defecto si se ejecuta de forma aislada
    ROBOT_IP = "192.168.25.60"
    ROBOT_PORT = 5001
    BOMBAS_CONFIG = {
        "pump_1": {"cm": 0.01, "ingrediente": "Refresco de toronja (Witi)"},
        "pump_2": {"cm": 0.50, "ingrediente": "Jugo de limón"},
        "pump_3": {"cm": 1.25, "ingrediente": "Tequila"},
        "pump_4": {"cm": 1.85, "ingrediente": "Licor de naranja"}
    }
    RECETAS_COCTELES = {
        "Paloma": {
            "Tequila": 45,
            "Refresco de toronja (Witi)": 90,
            "Jugo de limón": 15
        },
        "Margarita con toronja": {
            "Tequila": 45,
            "Licor de naranja": 30,
            "Jugo de limón": 30,
            "Refresco de toronja (Witi)": 30
        },
        "Tequila Citrus": {
            "Tequila": 45,
            "Jugo de limón": 30,
            "Licor de naranja": 30
        },
        "Paloma Dulce": {
            "Tequila": 30,
            "Refresco de toronja (Witi)": 90,
            "Licor de naranja": 20,
            "Jugo de limón": 10
        }
    }

# Verificar disponibilidad de RPi.GPIO para Modo Local
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False

# Intentar importar requests para Modo Remoto
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ==========================================
# CONFIGURACIÓN LOCAL GPIO (Raspberry Pi)
# ==========================================
# Mapeo de configuraciones de motores físicos (Pines BCM)
MOTORES = {
    "1": {
        "nombre": "Motor Principal (Pines de bartender_pi.py: IN1=16, IN2=20, ENA=21)",
        "IN1": 16,
        "IN2": 20,
        "ENA": 21
    },
    "2": {
        "nombre": "Motor de Pruebas (Pines de test_motor.py: IN1=17, IN2=27, ENA=22)",
        "IN1": 17,
        "IN2": 27,
        "ENA": 22
    }
}

# Motor activo por defecto
motor_activo_key = "1"

PUMPS_PINS = {
    "pump_1": 19,
    "pump_2": 6,
    "pump_3": 13,
    "pump_4": 5
}

VELOCIDAD = 80         # 0-100%
PWM_FREQ = 1000        # Hz
SEGUNDOS_POR_CM = 0.001 # Ajustar según calibración física
FLOW_RATE = 1.5        # mL servidos por segundo en las bombas

pwm_motor = None
current_position = 0.0
active_bombas_config = {}

# ==========================================
# CARGA Y GUARDADO DE CONFIGURACIÓN DE BOMBAS
# ==========================================
def load_bombas_config():
    global active_bombas_config
    if os.path.exists("pump_config.json"):
        try:
            with open("pump_config.json", "r", encoding="utf-8") as f:
                active_bombas_config = json.load(f)
            # Validar claves
            for k in ["pump_1", "pump_2", "pump_3", "pump_4"]:
                if k not in active_bombas_config:
                    raise KeyError()
            return
        except Exception:
            pass
            
    # Copia inicial si no existe archivo
    active_bombas_config = {}
    for k, v in BOMBAS_CONFIG.items():
        active_bombas_config[k] = {
            "cm": v["cm"],
            "ingrediente": v["ingrediente"]
        }

def save_bombas_config():
    try:
        with open("pump_config.json", "w", encoding="utf-8") as f:
            json.dump(active_bombas_config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Error al guardar config: {e}")

# ==========================================
# RESOLUCIÓN DE MOTORES Y MOVIMIENTO
# ==========================================
def obtener_pines_motor():
    """Retorna los pines del motor activo actualmente"""
    config = MOTORES[motor_activo_key]
    return config["IN1"], config["IN2"], config["ENA"]

def setup_local_gpio():
    """Inicializa los pines en la Raspberry Pi"""
    global pwm_motor
    if not HAS_GPIO:
        return False
    
    in1, in2, ena = obtener_pines_motor()
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Configurar motor DC activo
    GPIO.setup(in1, GPIO.OUT)
    GPIO.setup(in2, GPIO.OUT)
    GPIO.setup(ena, GPIO.OUT)
    
    pwm_motor = GPIO.PWM(ena, PWM_FREQ)
    pwm_motor.start(0)
    
    # Configurar relés de bombas (Activos en LOW por defecto)
    for pin in PUMPS_PINS.values():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)
        
    return True

def detener_motor_local():
    if not HAS_GPIO: return
    in1, in2, ena = obtener_pines_motor()
    GPIO.output(in1, GPIO.LOW)
    GPIO.output(in2, GPIO.LOW)
    if pwm_motor:
        pwm_motor.ChangeDutyCycle(0)

def mover_motor_local(target_cm):
    global current_position
    if not HAS_GPIO: return
    
    if target_cm == current_position:
        return
        
    in1, in2, ena = obtener_pines_motor()
    distance = target_cm - current_position
    tiempo_movimiento = abs(distance) * SEGUNDOS_POR_CM
    
    print(f"⚙️ [MOTOR] Moviendo de {current_position:.2f}cm a {target_cm:.2f}cm (Tiempo: {tiempo_movimiento:.3f}s)...")
    
    if distance > 0:
        # Adelante
        GPIO.output(in1, GPIO.LOW)
        GPIO.output(in2, GPIO.HIGH)
    else:
        # Atrás
        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.LOW)
        
    pwm_motor.ChangeDutyCycle(VELOCIDAD)
    time.sleep(tiempo_movimiento)
    detener_motor_local()
    
    current_position = target_cm
    print(f"⚙️ [MOTOR] Llegó a la posición {target_cm}cm.")

def ejecutar_secuencia_local(steps):
    """Ejecuta los pasos de preparación controlando GPIO directamente"""
    global current_position
    if not HAS_GPIO:
        print("❌ RPi.GPIO no disponible en esta máquina.")
        return False
        
    try:
        setup_local_gpio()
        print(f"\n🍹 [PREPARACIÓN LOCAL] Iniciando secuencia con {len(steps)} ingredientes...")
        
        for i, step in enumerate(steps, 1):
            pump_key = step["pump"]
            amount_ml = step["amount_ml"]
            target_cm = step["cm"]
            ingrediente = step.get("ingrediente", "Ingrediente")
            
            if amount_ml <= 0:
                continue
                
            print(f"\n🔸 [PASO {i}/{len(steps)}] Servir {amount_ml}mL de '{ingrediente}' en {pump_key} ({target_cm}cm)")
            
            # 1. Mover motor a la posición
            mover_motor_local(target_cm)
            time.sleep(0.5)
            
            # 2. Encender bomba
            pump_pin = PUMPS_PINS.get(pump_key)
            if pump_pin:
                tiempo_servido = amount_ml / FLOW_RATE
                print(f"💧 [BOMBA] Activando Pin GPIO {pump_pin} por {tiempo_servido:.2f}s...")
                GPIO.output(pump_pin, GPIO.LOW) # Encender relé (Activo en LOW)
                time.sleep(tiempo_servido)
                GPIO.output(pump_pin, GPIO.HIGH) # Apagar relé
                print("💧 [BOMBA] Apagada.")
            else:
                print(f"⚠️ Bomba {pump_key} no configurada en PUMPS_PINS.")
                
            time.sleep(0.5)
            
        # Regresar a origen
        print("\n⚙️ [MOTOR] Retornando al origen (0cm)...")
        mover_motor_local(0.0)
        print("✅ [PREPARACIÓN LOCAL] ¡Proceso completado con éxito!")
        return True
        
    except KeyboardInterrupt:
        print("\n🛑 [PARADA DE EMERGENCIA] Cancelado por el usuario.")
        detener_motor_local()
        # Apagar todas las bombas
        for pin in PUMPS_PINS.values():
            GPIO.output(pin, GPIO.HIGH)
        return False
    finally:
        GPIO.cleanup()

# ==========================================
# MODO CLIENTE HTTP (Orquestación remota)
# ==========================================
def ejecutar_secuencia_remota(steps, drink_name):
    """Envía los comandos por HTTP a la Raspberry Pi"""
    if not HAS_REQUESTS:
        print("❌ La librería 'requests' no está instalada. Ejecuta 'pip install requests'.")
        return False
        
    url_prepare = f"http://{ROBOT_IP}:{ROBOT_PORT}/prepare"
    url_status = f"http://{ROBOT_IP}:{ROBOT_PORT}/status"
    
    print(f"\n📡 [REMOTO] Conectando con Raspberry Pi en http://{ROBOT_IP}:{ROBOT_PORT}...")
    try:
        # Verificar estado del robot
        status_res = requests.get(url_status, timeout=3.0)
        if status_res.status_code != 200:
            print(f"❌ La Raspberry Pi respondió con código: {status_res.status_code}")
            return False
            
        status_data = status_res.json()
        if status_data.get("busy", False):
            print("⚠️ La Raspberry Pi está ocupada preparando otra bebida.")
            return False
            
        print(f"📡 [REMOTO] Enviando orden de preparación de '{drink_name}' ({len(steps)} pasos)...")
        res = requests.post(url_prepare, json={"steps": steps}, timeout=5.0)
        
        if res.status_code == 200:
            print("✅ [REMOTO] ¡Orden aceptada por la Raspberry Pi!")
            
            # Monitorear hasta que termine
            print("⏳ Monitoreando estado de preparación (Ctrl+C para salir del monitoreo)...")
            while True:
                time.sleep(2)
                check = requests.get(url_status, timeout=2.0)
                if check.status_code == 200:
                    data = check.json()
                    if not data.get("busy", False):
                        print("\n🎉 [REMOTO] ¡La Raspberry Pi ha finalizado la preparación!")
                        break
                    else:
                        print(".", end="", flush=True)
                else:
                    print(f"\n⚠️ Error al consultar estado: {check.status_code}")
            return True
        else:
            print(f"❌ La Raspberry Pi rechazó la orden. Código: {res.status_code}, Detalle: {res.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ No se pudo conectar con la Raspberry Pi: {e}")
        print("   Asegúrate de que 'bartender_pi.py' esté corriendo en la Raspberry Pi.")
        return False

# ==========================================
# FLUX INTERACTIVO ADAPTADO
# ==========================================
def print_header():
    print("=" * 65)
    print("          PRUEBA MANUAL DE FLUJO - SMART BARTENDER")
    print("=" * 65)

def show_pump_config():
    print("\n--- Distribución de Ingredientes en las Bombas ---")
    for key in sorted(active_bombas_config.keys()):
        data = active_bombas_config[key]
        val = data.get("ingrediente")
        val_str = f"\033[92m{val}\033[0m" if val else "\033[90m[Vacío]\033[0m"
        pos = data.get("cm", 0.0)
        pin = PUMPS_PINS.get(key, "N/A")
        print(f"  * Bomba {key[-1]} (GPIO Pin {pin}) en {pos:.2f} cm: {val_str}")

def configure_pumps():
    print("\n--- Configuración de Bombas ---")
    show_pump_config()
    try:
        pump_num = input("\nSeleccione el número de bomba a cambiar (1-4) o 'm' para menú principal: ").strip()
        if pump_num.lower() == 'm':
            return
        if pump_num not in ["1", "2", "3", "4"]:
            print("⚠️ Número de bomba inválido.")
            return
        
        pump_key = f"pump_{pump_num}"
        
        # Obtener los ingredientes únicos de RECETAS_COCTELES
        drink_options = sorted(list(set(
            ing for recipe in RECETAS_COCTELES.values() for ing in recipe.keys()
        )))
        
        print("\nIngredientes disponibles:")
        for idx, opt in enumerate(drink_options, 1):
            print(f"  {idx}. {opt}")
        print("  0. Vaciar bomba (Ninguno)")
        
        ing_idx = input("\nSeleccione el número de ingrediente: ").strip()
        if not ing_idx.isdigit():
            print("⚠️ Opción inválida.")
            return
            
        ing_idx = int(ing_idx)
        if ing_idx == 0:
            active_bombas_config[pump_key]["ingrediente"] = None
        elif 1 <= ing_idx <= len(drink_options):
            selected_ing = drink_options[ing_idx - 1]
            active_bombas_config[pump_key]["ingrediente"] = selected_ing
        else:
            print("⚠️ Opción inválida.")
            return
            
        # Guardar la nueva configuración
        save_bombas_config()
        print(f"✅ ¡Bomba {pump_num} actualizada exitosamente!")
    except Exception as e:
        print(f"⚠️ Error al configurar: {e}")

def get_connected_ingredients():
    return [info["ingrediente"] for info in active_bombas_config.values() if info.get("ingrediente")]

def is_recipe_preparable(recipe):
    connected = get_connected_ingredients()
    connected_lower = [c.lower() for c in connected]
    for ingrediente in recipe.keys():
        if ingrediente.lower() not in connected_lower:
            return False
    return True

def obtener_pasos_bebida(drink_name):
    """Busca la receta y arma los pasos correspondientes usando active_bombas_config"""
    recipe = None
    matched_name = None
    
    # Búsqueda difusa simple
    for name, r in RECETAS_COCTELES.items():
        if name.lower() == drink_name.lower() or name.lower() in drink_name.lower() or drink_name.lower() in name.lower():
            recipe = r
            matched_name = name
            break
            
    if not recipe:
        return None, None
        
    steps = []
    for ingrediente, amount_ml in recipe.items():
        # Encontrar la bomba asignada
        found_pump = None
        target_cm = None
        for pump_id, pump_info in active_bombas_config.items():
            if pump_info.get("ingrediente") and pump_info["ingrediente"].lower() == ingrediente.lower():
                found_pump = pump_id
                target_cm = pump_info["cm"]
                break
                
        if found_pump:
            steps.append({
                "pump": found_pump,
                "amount_ml": amount_ml,
                "cm": target_cm,
                "ingrediente": ingrediente
            })
            
    # Ordenar por posición cm (de izquierda a derecha)
    steps.sort(key=lambda x: x["cm"])
    return matched_name, steps

def make_drink_interactive(modo):
    print("\n--- Preparar Bebida ---")
    
    # Obtener bebidas preparables ahora
    available = []
    for name, recipe in RECETAS_COCTELES.items():
        if is_recipe_preparable(recipe):
            available.append(name)
            
    print("\n[+] Bebidas preparables AHORA con las botellas conectadas:")
    if not available:
        print("  \033[91mNinguna (¡Asigna ingredientes a las bombas en la opción 2 primero!)\033[0m")
    else:
        for idx, d in enumerate(available, 1):
            print(f"  {idx}. {d}")
        
    print("\n[+] Lista completa de recetas disponibles en el sistema:")
    recetas_list = list(RECETAS_COCTELES.keys())
    for idx, name in enumerate(recetas_list, 1):
        recipe = RECETAS_COCTELES[name]
        is_ready = is_recipe_preparable(recipe)
        status = "\033[92m[Listo]\033[0m" if is_ready else "\033[91m[Faltan botellas]\033[0m"
        print(f"  {idx + 100}. {name} {status}")
        
    choice = input("\nEscribe el NOMBRE del cóctel o el NÚMERO correspondiente: ").strip()
    if not choice:
        return
        
    drink_name = ""
    # Comprobar si se ingresó un número
    if choice.isdigit():
        val = int(choice)
        if val <= len(available):
            drink_name = available[val - 1]
        elif 101 <= val <= 100 + len(recetas_list):
            drink_name = recetas_list[val - 101]
        else:
            print("⚠️ Número fuera de rango.")
            return
    else:
        # Búsqueda insensible a mayúsculas
        match = next((name for name in RECETAS_COCTELES.keys() if name.lower() == choice.lower()), None)
        if match:
            drink_name = match
        else:
            print(f"⚠️ Cóctel '{choice}' no encontrado en las recetas.")
            return
            
    matched_name, steps = obtener_pasos_bebida(drink_name)
    if not matched_name or not steps:
        print(f"❌ No se puede preparar '{drink_name}' porque faltan bombas configuradas para sus ingredientes.")
        return
        
    print(f"\n🚀 Iniciando preparación de: {matched_name}")
    print("Pasos secuenciales a ejecutar:")
    for s in steps:
        print(f"  -> Ir a {s['cm']:.2f}cm y servir {s['amount_ml']}mL de '{s['ingrediente']}' usando {s['pump']}")
        
    confirm = input("\n¿Estás seguro de que deseas iniciar el hardware físico? (s/n): ").strip().lower()
    if confirm != 's':
        print("❌ Operación cancelada.")
        return
        
    if modo == "local":
        success = ejecutar_secuencia_local(steps)
    else:
        success = ejecutar_secuencia_remota(steps, matched_name)
        
    if success:
        print(f"\n🎉 \033[92m¡{matched_name} preparado exitosamente!\033[0m")
    else:
        print(f"\n❌ \033[91mError al preparar {matched_name}\033[0m")

# ==========================================
# DIAGNÓSTICOS DE HARDWARE
# ==========================================
def test_individual_pump(modo):
    """Permite encender una bomba específica por un volumen determinado"""
    print("\n--- PRUEBA INDIVIDUAL DE BOMBA ---")
    for pump_id, pump_info in active_bombas_config.items():
        print(f" - {pump_id}: {pump_info['ingrediente']} (Posición: {pump_info['cm']} cm)")
        
    bomba = input("\nEscribe el ID de la bomba a probar (ej: pump_1): ").strip()
    if bomba not in active_bombas_config:
        print("❌ Bomba inválida.")
        return
        
    try:
        ml = float(input("Cantidad de mL a servir (ej: 30): "))
    except ValueError:
        print("❌ Cantidad inválida.")
        return
        
    step = [{
        "pump": bomba,
        "amount_ml": ml,
        "cm": active_bombas_config[bomba]["cm"],
        "ingrediente": active_bombas_config[bomba].get("ingrediente") or "Prueba"
    }]
    
    if modo == "local":
        ejecutar_secuencia_local(step)
    else:
        ejecutar_secuencia_remota(step, f"Prueba Bomba {bomba}")

def test_individual_motor(modo):
    """Permite mover el motor a una posición específica"""
    print("\n--- PRUEBA INDIVIDUAL DE MOTOR ---")
    try:
        target = float(input("Introduce la posición a la que deseas mover el vaso (en CM): "))
    except ValueError:
        print("❌ Posición inválida.")
        return
        
    if modo == "local":
        try:
            setup_local_gpio()
            mover_motor_local(target)
            detener_motor_local()
        except KeyboardInterrupt:
            detener_motor_local()
        finally:
            GPIO.cleanup()
    else:
        print("💡 Para el modo HTTP, se enviará un comando de movimiento remoto a la Pi.")
        confirm = input("¿Deseas enviar comando de movimiento remoto a la Pi? (s/n): ").strip().lower()
        if confirm == 's':
            step = [{
                "pump": "pump_1",
                "amount_ml": 0.1,  # Cantidad casi nula para no activar bomba
                "cm": target,
                "ingrediente": "Prueba Posicionamiento Motor"
            }]
            ejecutar_secuencia_remota(step, f"Prueba Motor a {target}cm")

def cambiar_motor_activo():
    global motor_activo_key
    print("\n--- SELECCIONAR CONFIGURACIÓN DE MOTOR ---")
    for key, info in MOTORES.items():
        print(f"  {key}. {info['nombre']}")
    opc = input("Selecciona una opción (ENTER para cancelar): ").strip()
    if opc in MOTORES:
        motor_activo_key = opc
        print(f"✅ Configuración de motor seleccionada: {MOTORES[motor_activo_key]['nombre']}")
    else:
        print("❌ Opción no válida. Manteniendo motor actual.")

def ejecutar_menu_diagnostico(modo):
    while True:
        print("\n" + "="*50)
        print("MÓDULO DE PRUEBAS DE DIAGNÓSTICO:")
        print("  1. Probar una Bomba Individual (Servir mL específicos)")
        print("  2. Probar Motor Individual (Desplazar a CM específicos)")
        if modo == "local":
            print(f"  3. Cambiar Motor Activo (Actual: Motor {motor_activo_key})")
        print("  0. Regresar al Menú Principal")
        print("="*50)
        
        opc = input("Seleccione una opción: ").strip()
        if opc == "0":
            break
        elif opc == "1":
            test_individual_pump(modo)
        elif opc == "2":
            test_individual_motor(modo)
        elif opc == "3" and modo == "local":
            cambiar_motor_activo()
        else:
            print("⚠️ Opción inválida.")

# ==========================================
# MENÚ Y FLUJO PRINCIPAL
# ==========================================
def main():
    global motor_activo_key
    # Evitar problemas de codificación de emojis en Windows
    os.environ["PYTHONIOENCODING"] = "utf-8"
    
    # Cargar la configuración de las bombas
    load_bombas_config()
    
    print("="*65)
    print("      MIA BARTENDER - ADAPTACIÓN DE FLUJO MANUAL DE PRUEBAS")
    print("="*65)
    if CONFIG_LOADED:
        print("✅ Configuración central de MIA cargada correctamente.")
    else:
        print("⚠️ No se encontró config.py. Usando configuración interna de respaldo.")
        
    print(f"📌 IP de Raspberry Pi: {ROBOT_IP}:{ROBOT_PORT}")
    print(f"📌 Detección de GPIO Local: {'SI' if HAS_GPIO else 'NO (Corriendo en Laptop/PC)'}")
    print("="*65)
    
    # Determinar modo de ejecución por defecto
    modo_defecto = "local" if HAS_GPIO else "remoto"
    print(f"Modo seleccionado por defecto: {modo_defecto.upper()}")
    modo_input = input("¿Deseas cambiar el modo? (presiona ENTER para mantener o escribe 'local' / 'remoto'): ").strip().lower()
    
    if modo_input in ["local", "remoto"]:
        modo = modo_input
    else:
        modo = modo_defecto
        
    print(f"🚀 Iniciando en MODO: {modo.upper()}")
    
    # Si corre en local, permitir elegir motor al inicio
    if modo == "local" and HAS_GPIO:
        print("\nConfiguración del motor para prueba local:")
        for key, info in MOTORES.items():
            print(f"  {key}. {info['nombre']}")
        sel_mot = input(f"Selecciona motor [Por defecto {motor_activo_key}]: ").strip()
        if sel_mot in MOTORES:
            motor_activo_key = sel_mot
        print(f"🤖 Motor activo: {MOTORES[motor_activo_key]['nombre']}")
        
    while True:
        # Limpiar consola
        os.system('cls' if os.name == 'nt' else 'clear')
        print_header()
        show_pump_config()
        
        print("\nOpciones de Prueba:")
        print("  1. Preparar un cóctel (Ver flujo del vaso y bombas)")
        print("  2. Configurar ingredientes de las bombas")
        print("  3. Ejecutar secuencia de limpieza (Purga de 50mL)")
        print("  4. Diagnósticos individuales (Motores y bombas)")
        print("  5. Salir")
        
        opcion = input("\nSeleccione una opción (1-5): ").strip()
        if opcion == "1":
            make_drink_interactive(modo)
        elif opcion == "2":
            configure_pumps()
        elif opcion == "3":
            print("\n💧 Iniciando purgado de limpieza de 50mL en todas las bombas de manera secuencial...")
            steps = []
            for pump_key, pump_info in active_bombas_config.items():
                steps.append({
                    "pump": pump_key,
                    "amount_ml": 50.0,
                    "cm": pump_info["cm"],
                    "ingrediente": pump_info.get("ingrediente") or "Limpieza"
                })
            # Ordenar por cm de menor a mayor
            steps.sort(key=lambda x: x["cm"])
            
            if modo == "local":
                ejecutar_secuencia_local(steps)
            else:
                ejecutar_secuencia_remota(steps, "Purga de Limpieza")
            print("✅ Limpieza completada.")
        elif opcion == "4":
            ejecutar_menu_diagnostico(modo)
        elif opcion == "5" or opcion.lower() == "salir":
            print("¡Pruebas finalizadas!")
            break
        else:
            print("⚠️ Opción inválida.")
            
        input("\nPresione Enter para continuar...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Ejecución finalizada por el usuario.")
