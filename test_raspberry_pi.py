import socket
import sys
import time

# =====================================================================
# MIA AI Bartender - Servidor de Prueba para Raspberry Pi
# =====================================================================
# Ejecuta este script en tu Raspberry Pi para simular la coctelera y recibir
# los comandos de preparación enviados desde la laptop por cable Ethernet.
#
# Para una Raspberry Pi 3 B+ con 1GB de RAM, este script ligero en Python
# es ideal ya que consume menos de 10MB de memoria RAM.
# =====================================================================

HOST = '0.0.0.0'  # Escuchar en todas las interfaces de red de la RPi
PORT = 8888       # Mismo puerto configurado en config.py de la laptop

# Mapeo de bombas/ingredientes a pines GPIO de la Raspberry Pi
# Ajusta estos números a los pines reales donde conectaste tus relés.
GPIO_PUMPS = {
    "Ron": 17,            # GPIO 17
    "Limón": 27,          # GPIO 27
    "Menta": 22,          # GPIO 22
    "Coca-Cola": 23,      # GPIO 23
    "Vodka": 24,          # GPIO 24
    "Agua Tónica": 25,    # GPIO 25
    "Tequila": 5,         # GPIO 5
    "Jugo de Naranja": 6  # GPIO 6
}

# Inicializar GPIO si estamos en la Raspberry Pi real
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    for pump, pin in GPIO_PUMPS.items():
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH) # HIGH usualmente apaga relés optoacoplados activos en LOW
    HAS_GPIO = True
    print("🔌 [GPIO] Librería RPi.GPIO cargada y pines inicializados correctamente.")
except ImportError:
    HAS_GPIO = False
    print("💻 [SIMULACIÓN] No se detectó entorno Raspberry Pi. Ejecutando en modo SIMULADO.")

print("🍹 Servidor de Recepción de Coctelera Listo...")
print(f"📡 Escuchando en el puerto TCP: {PORT}...")

# Crear el socket de escucha TCP
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

try:
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)
except Exception as e:
    print(f"❌ Error al enlazar puerto {PORT}: {e}")
    sys.exit(1)

while True:
    print("\n⏳ Esperando conexión desde la laptop de MIA...")
    try:
        conn, addr = server_socket.accept()
        print(f"✅ Conexión establecida exitosamente desde: {addr}")
        
        while True:
            data = conn.recv(1024)
            if not data:
                print("🔌 La laptop se ha desconectado.")
                break
            
            command = data.decode('utf-8').strip()
            print(f"📩 Comando recibido de MIA: '{command}'")
            
            if command.startswith("PREPARE:"):
                drink_name = command.split(":", 1)[1]
                print(f"🍹 [COCTELERA] Preparando cóctel: {drink_name}...")
                
                # Simular/Activar bombas según la receta
                if HAS_GPIO:
                    # Ejemplo simple: prender bombas de forma consecutiva
                    print(f"🔌 [Relé] Activando GPIOs para {drink_name}...")
                    # Aquí puedes buscar los ingredientes de la bebida y activar sus pines correspondientes
                    # Por ejemplo, para Mojito prender bombas Ron (GPIO 17) y Limón (GPIO 27)
                    GPIO.output(17, GPIO.LOW) # Encender
                    GPIO.output(27, GPIO.LOW) # Encender
                    time.sleep(4.0)           # Servir por 4 segundos
                    GPIO.output(17, GPIO.HIGH) # Apagar
                    GPIO.output(27, GPIO.HIGH) # Apagar
                else:
                    # Modo simulación
                    print(f"💻 [Simulado] Encendiendo bombas de líquido para {drink_name}...")
                    time.sleep(3.0)
                    print(f"💻 [Simulado] Apagando bombas.")
                
                print(f"✅ [Coctelera] ¡{drink_name} terminado y servido!")
            else:
                print(f"⚠️ Comando no soportado: {command}")
                
    except KeyboardInterrupt:
        print("\n👋 Cerrando servidor de coctelera...")
        break
    except Exception as e:
        print(f"⚠️ Error en ejecución: {e}")

if HAS_GPIO:
    GPIO.cleanup()
server_socket.close()
