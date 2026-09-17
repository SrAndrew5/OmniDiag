# pid_discovery.py
"""
Detecta automáticamente qué PIDs soporta el coche conectado,
preguntando los PIDs 'supported' (00, 20, 40, 60, 80) de golpe.
"""
import time
from obd.utils import extraer_byte

# Cada entrada: (comando a mandar, pid_base para la función de parseo)
RANGOS_A_PREGUNTAR = [
    ("0100", 0x00),
    ("0120", 0x20),
    ("0140", 0x40),
    ("0160", 0x60),
    ("0180", 0x80),
]

def detectar_pids_soportados(conexion, parser):
    """
    Pregunta al coche qué PIDs soporta en total, recorriendo todos los rangos.
    Devuelve una lista completa con todos los PIDs confirmados como soportados.
    """
    todos_los_soportados = []

    for comando, pid_base in RANGOS_A_PREGUNTAR:
        conexion.enviar_comando(comando)
        time.sleep(0.1)
        respuesta = conexion.leer_respuesta()

        if not respuesta:
            print(f"Sin respuesta para {comando}, dejamos de preguntar rangos superiores.")
            break

        byte_a = extraer_byte(respuesta, 2)
        byte_b = extraer_byte(respuesta, 3)
        byte_c = extraer_byte(respuesta, 4)
        byte_d = extraer_byte(respuesta, 5)

        soportados_en_este_rango = parser.parsear_pids_soportados(
            [byte_a, byte_b, byte_c, byte_d], pid_base
        )
        todos_los_soportados.extend(soportados_en_este_rango)

    return todos_los_soportados