import requests
import time

from config import (
    ROBOT_ENABLED, ROBOT_IP, ROBOT_PORT,
    BOMBAS_CONFIG, RECETAS_COCTELES
)

class RobotControl:
    """Controla la comunicación con la Raspberry Pi (brazo robot y bombas) vía HTTP.
    
    Ahora MIA (Windows) es el orquestador maestro y la Raspberry Pi es un esclavo
    que solo obedece /move y /dispense.
    """
    def __init__(self):
        self.connected = False
        
        # Menú de recetas cargado desde la configuración centralizada
        self.drinks_menu = RECETAS_COCTELES
        
        if not ROBOT_ENABLED:
            print("🤖 [ROBOT] Integración con Raspberry Pi desactivada en la configuración.")
            return

        self.connect()

    def connect(self):
        self.connected = False
        url = f"http://{ROBOT_IP}:{ROBOT_PORT}/status"
        try:
            print(f"[ROBOT] Verificando conexion HTTP con Raspberry Pi en {url}...")
            res = requests.get(url, timeout=3.0)
            if res.status_code == 200:
                self.connected = True
                print("[ROBOT] [SUCCESS] Conexion establecida con Raspberry Pi (HTTP). Modo Maestro-Esclavo.")
            else:
                print(f"[ROBOT] [WARNING] La Raspberry Pi respondio con codigo {res.status_code}.")
        except Exception as e:
            print(f"[ROBOT] [WARNING] No se pudo conectar a la Raspberry Pi en {url}.")
            print("   MIA funcionara normalmente, pero el hardware no se activara.")

    def send_drink_command(self, robot_command):
        """Orquesta la preparación secuencial multibomba desde Windows hacia el esclavo Pi."""
        if not self.connected:
            self.connect()
            if not self.connected:
                return False
            
        drink_name = robot_command
        if robot_command.startswith("PREPARAR:"):
            drink_name = robot_command.replace("PREPARAR:", "", 1).strip()
            
        # Buscar el trago en el recetario (ignorando mayúsculas)
        match_name = None
        match_recipe = None
        for name, recipe in self.drinks_menu.items():
            if name.lower() in drink_name.lower():
                match_recipe = recipe
                match_name = name
                break
                
        if not match_recipe:
            print(f"[ROBOT] [ERROR] El trago '{drink_name}' no esta configurado en las recetas.")
            return False
            
        # Construir pasos por ingrediente
        steps = []
        for ingrediente, amount_ml in match_recipe.items():
            # Encontrar la bomba asignada a este ingrediente
            found_pump = None
            target_cm = None
            for pump_id, pump_info in BOMBAS_CONFIG.items():
                if pump_info["ingrediente"].lower() == ingrediente.lower():
                    found_pump = pump_id
                    target_cm = pump_info["cm"]
                    break
            
            if found_pump:
                steps.append({
                    "pump": found_pump,
                    "amount_ml": amount_ml,
                    "cm": target_cm
                })
            else:
                print(f"[ROBOT] [WARNING] El ingrediente '{ingrediente}' no esta asignado a ninguna bomba.")
                
        if not steps:
            print(f"[ROBOT] [ERROR] No hay ingredientes configurados en las bombas para preparar '{match_name}'.")
            return False
            
        # Ordenar pasos de manera lineal por posición cm (de izquierda a derecha)
        steps.sort(key=lambda x: x["cm"])
        
        print(f"[ROBOT] Enviando orden de preparación de {match_name} ({len(steps)} pasos) a Raspberry Pi...")
        url = f"http://{ROBOT_IP}:{ROBOT_PORT}/prepare"
        
        try:
            res = requests.post(url, json={"steps": steps}, timeout=5.0)
            if res.status_code == 200:
                print(f"[ROBOT] [SUCCESS] Orden recibida. Raspberry Pi preparara la bebida en segundo plano.")
                return True
            else:
                print(f"[ROBOT] [WARNING] Raspberry Pi rechazo la orden. Codigo: {res.status_code}")
                return False
        except Exception as e:
            print(f"[ROBOT] [ERROR] Error enviando comando a Raspberry Pi: {e}")
            return False


    def wait_for_drink_ready(self, timeout=120):
        if not self.connected: return True
        
        print("[ROBOT] Esperando a que la Raspberry Pi termine fisicamente...")
        url = f"http://{ROBOT_IP}:{ROBOT_PORT}/status"
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                res = requests.get(url, timeout=2.0)
                if res.status_code == 200:
                    data = res.json()
                    if not data.get("busy", False):
                        print("[ROBOT] [SUCCESS] La Raspberry Pi ha finalizado la preparacion.")
                        return True
            except:
                pass
            time.sleep(2)
            
        print("[ROBOT] [WARNING] Timeout esperando a que la maquina termine.")
        return True
