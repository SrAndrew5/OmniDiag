# modo_exploracion.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.connection import Connection
from obd.vin_reader import leer_vin
from datetime import datetime
import time
import config

def generar_pids_modo(modo_hex):
    pids = []
    for numero in range(0x00, 0xC9):
        pid_hex = f"{numero:02X}"
        comando = f"{modo_hex}{pid_hex}"
        pids.append(comando)
    return pids

def explorar():
    conexion = Connection()
    if not conexion.conectar():
        print("No se pudo conectar, abortando exploración.")
        return

    conexion.enviar_comando("0902")
    time.sleep(0.1)
    respuesta_vin = conexion.leer_respuesta()
    vin = leer_vin(respuesta_vin)
    print(f"VIN detectado: {vin}")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if not os.path.exists(config.EXPLORACIONES_FOLDER):
        os.makedirs(config.EXPLORACIONES_FOLDER)

    nombre_fichero = f"{config.EXPLORACIONES_FOLDER}exploracion_{vin}_{timestamp}.txt"

    modos_a_explorar = {
        "01": "Datos en vivo actuales",
        "02": "Freeze frame",
        "06": "Resultados de test de monitores",
        "09": "Información del vehículo",
    }

    con_respuesta_total = 0
    sin_respuesta_total = 0

    with open(nombre_fichero, "w") as f:
        f.write(f"Exploración completa - Coche: {vin} - Fecha: {timestamp}\n")
        f.write("=" * 70 + "\n\n")

        for modo_hex, descripcion in modos_a_explorar.items():
            print(f"\n=== Explorando modo {modo_hex} ({descripcion}) ===")
            f.write(f"\n--- MODO {modo_hex}: {descripcion} ---\n\n")

            pids = generar_pids_modo(modo_hex)

            for comando in pids:
                conexion.enviar_comando(comando)
                time.sleep(0.1)
                respuesta = conexion.leer_respuesta()

                if respuesta:
                    linea = f"Comando: {comando} | Respuesta: {respuesta}\n"
                    con_respuesta_total += 1
                else:
                    linea = f"Comando: {comando} | Sin respuesta\n"
                    sin_respuesta_total += 1

                print(linea.strip())
                f.write(linea)

    conexion.desconectar()

    print(f"\n--- Resumen total ---")
    print(f"PIDs con respuesta: {con_respuesta_total}")
    print(f"PIDs sin respuesta: {sin_respuesta_total}")
    print(f"Exploración guardada en: {nombre_fichero}")

if __name__ == "__main__":
    explorar()