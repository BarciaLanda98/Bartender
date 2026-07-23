import sys
from assistant import VoiceAssistant

# Fix consola Windows UTF-8 (Método seguro para Python 3.7+)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════╗
    ║       🤖  MIA Voice Assistant       ║
    ║   Local AI with Vision & Sarcasm    ║
    ╠══════════════════════════════════════╣
    ║  Di 'Hola MIA' para activarme       ║
    ║  Escribe 'salir' para detener       ║
    ╚══════════════════════════════════════╝
    """)

    mia = VoiceAssistant()
    mia.run_interactive()