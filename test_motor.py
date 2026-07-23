import RPi.GPIO as GPIO
import time

# Usa numeración BCM (¡NO los números físicos del conector!)
# GPIO 17 = Pin Físico 11
# GPIO 27 = Pin Físico 13
# GPIO 22 = Pin Físico 15

IN1 = 17
IN2 = 27
ENA = 22

print("Iniciando prueba del motor DC con L298N...")
print(f"Verifica tus conexiones físicas:")
print(f" - IN1 conectado a GPIO {IN1} (Pin Físico 11)")
print(f" - IN2 conectado a GPIO {IN2} (Pin Físico 13)")
print(f" - ENA conectado a GPIO {ENA} (Pin Físico 15)")
print(f" - Tierra (GND) del L298N conectada a un pin GND de la Raspberry Pi")

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)
GPIO.setup(ENA, GPIO.OUT)

print("\nGirando ADELANTE por 2 segundos...")
GPIO.output(IN1, GPIO.HIGH)
GPIO.output(IN2, GPIO.LOW)
GPIO.output(ENA, GPIO.HIGH)
time.sleep(2)

print("Deteniendo...")
GPIO.output(IN1, GPIO.LOW)
GPIO.output(IN2, GPIO.LOW)
GPIO.output(ENA, GPIO.LOW)
time.sleep(1)

print("Girando ATRÁS por 2 segundos...")
GPIO.output(IN1, GPIO.LOW)
GPIO.output(IN2, GPIO.HIGH)
GPIO.output(ENA, GPIO.HIGH)
time.sleep(2)

print("Prueba finalizada. Limpiando pines...")
GPIO.cleanup()
