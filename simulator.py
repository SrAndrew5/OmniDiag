# simulator.py
import random
import time

class OBDSimulator:
    """Simula un coche respondiendo a comandos OBD2 básicos."""

    def __init__(self):
        self.fallos_simulados = ["P0300", "P0171", "P0420"]

    def leer_fallos(self):
        """Simula lectura de DTCs (fallos)."""
        time.sleep(0.3)  # simula el retardo real de comunicación
        return self.fallos_simulados

    def borrar_fallos(self):
        """Simula borrado de fallos."""
        time.sleep(0.3)
        self.fallos_simulados = []
        return True

    def leer_rpm(self):
        """Simula lectura de RPM en vivo."""
        return random.randint(700, 3000)

    def leer_temp_refrigerante(self):
        """Simula temperatura del refrigerante en grados C."""
        return random.randint(80, 95)

    def leer_km(self):
        """Simula kilometraje (esto en la vida real depende del PID exacto)."""
        return 253400