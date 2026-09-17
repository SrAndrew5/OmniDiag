# prueba_conexion.py
from core.connection import Connection
from obd.obd_parser import OBDParser
from obd.utils import extraer_byte
from obd.dtc_manager import DTCManager
from obd.pid_discovery import detectar_pids_soportados
from obd.vin_reader import leer_vin
from gestion.backup_manager import BackupManager
from gestion.historial_lecturas import HistorialLecturas
import time

conexion = Connection()

if not conexion.conectar():
    print("Error al conectar, no se puede continuar.")
    exit()

parser = OBDParser()

# --- Leer el VIN del coche PRIMERO, para poder usarlo en todo lo demás ---
conexion.enviar_comando("0902")
time.sleep(0.1)
respuesta_vin = conexion.leer_respuesta()
vin = leer_vin(respuesta_vin)
print(f"VIN detectado: {vin}")
historial = HistorialLecturas(coche=vin)

# Lista de pruebas: (comando, función del parser a usar, nombre para mostrar, unidad)
pruebas = [
    ("0105", parser.parsear_temp_refrigerante, "Temp. refrigerante", "°C"),
    ("010C", parser.parsear_rpm, "RPM", "rpm"),
    ("010D", parser.parsear_velocidad, "Velocidad", "km/h"),
    ("010B", parser.parsear_presion_admision, "Presión admisión", "kPa"),
    ("015C", parser.parsear_temp_aceite, "Temp. aceite", "°C"),
]

for comando, funcion_parser, nombre, unidad in pruebas:
    conexion.enviar_comando(comando)
    time.sleep(0.1)
    respuesta = conexion.leer_respuesta()

    if comando == "010C":
        byte_a = extraer_byte(respuesta, 2)
        byte_b = extraer_byte(respuesta, 3)
        if byte_a is None or byte_b is None:
            print(f"{nombre}: no se pudo leer (sin respuesta del coche).")
            continue
        resultado = funcion_parser(byte_a, byte_b)
    else:
        byte_a = extraer_byte(respuesta, 2)
        if byte_a is None:
            print(f"{nombre}: no se pudo leer (sin respuesta del coche).")
            continue
        resultado = funcion_parser(byte_a)
    historial.registrar_lectura(nombre,resultado,unidad)
    print(f"{nombre}: {resultado} {unidad}")

# --- Prueba de borrado de fallos, usando el VIN real ---
dtc_mgr = DTCManager()
fallos_actuales = ["P0300", "P0171", "P0420"]
dtc_mgr.borrar_fallos(conexion, fallos_actuales, coche=vin)

# --- Prueba del sistema de backup, usando el VIN real ---
backup_mgr = BackupManager()
bytes_ejemplo = [0x01, 0x0A, 0x3F, 0x00, 0x12]
backup_mgr.guardar_backup(modulo="BCM", coche=vin, bytes_coding=bytes_ejemplo)

# --- Detección completa de PIDs soportados ---
pids_totales = detectar_pids_soportados(conexion, parser)
print(f"\nTotal de PIDs soportados detectados: {len(pids_totales)}")
print(f"Lista completa: {pids_totales}")

# Desconectamos al final de todo, cuando ya no necesitamos más la conexión
conexion.desconectar()