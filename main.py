import sys
import time
from core.connection import Connection
from obd.obd_parser import OBDParser
from obd.utils import extraer_byte
from obd.dtc_manager import DTCManager
from obd.pid_discovery import detectar_pids_soportados
from obd.vin_reader import leer_vin
from gestion.backup_manager import BackupManager
from gestion.historial_lecturas import HistorialLecturas

class Menu:
    def __init__(self):
        self.conexion = Connection()
        self.parser = OBDParser()
        self.vin = None
        self.historial = None
        self.dtc_mgr = DTCManager()
        self.backup_mgr = BackupManager()

    def mostrar_menu(self):
        print("\n--- MENÚ PRINCIPAL AUDI DIAG ---")
        print("1. Conectar y leer VIN")
        print("2. Leer Sensores")
        print("3. Gestionar Fallos (DTC)")
        print("4. Detectar PIDs soportados")
        print("5. Hacer Backup de un Módulo")
        print("0. Salir")
        return input("Elige una opción: ")

    def conectar(self):
        print("\nConectando...")
        if not self.conexion.conectar():
            print("Error al conectar.")
            return False
        
        self.conexion.enviar_comando("0902")
        time.sleep(0.1)
        respuesta_vin = self.conexion.leer_respuesta()
        self.vin = leer_vin(respuesta_vin)
        print(f"Conexión exitosa. VIN detectado: {self.vin}")
        self.historial = HistorialLecturas(coche=self.vin)
        return True

    def leer_sensores(self):
        if not self.vin:
            print("Primero debes conectarte (Opción 1).")
            return

        pruebas = [
            ("0105", self.parser.parsear_temp_refrigerante, "Temp. refrigerante", "°C"),
            ("010C", self.parser.parsear_rpm, "RPM", "rpm"),
            ("010D", self.parser.parsear_velocidad, "Velocidad", "km/h"),
            ("010B", self.parser.parsear_presion_admision, "Presión admisión", "kPa"),
            ("015C", self.parser.parsear_temp_aceite, "Temp. aceite", "°C"),
        ]

        print("\n--- LEYENDO SENSORES ---")
        for comando, funcion_parser, nombre, unidad in pruebas:
            self.conexion.enviar_comando(comando)
            time.sleep(0.1)
            respuesta = self.conexion.leer_respuesta()

            if comando == "010C": # RPM necesita 2 bytes
                byte_a = extraer_byte(respuesta, 2)
                byte_b = extraer_byte(respuesta, 3)
                if byte_a is None or byte_b is None:
                    print(f"{nombre}: no se pudo leer.")
                    continue
                resultado = funcion_parser(byte_a, byte_b)
            else:
                byte_a = extraer_byte(respuesta, 2)
                if byte_a is None:
                    print(f"{nombre}: no se pudo leer.")
                    continue
                resultado = funcion_parser(byte_a)
                
            self.historial.registrar_lectura(nombre, resultado, unidad)
            print(f"{nombre}: {resultado} {unidad}")

    def gestionar_fallos(self):
        if not self.vin:
            print("Primero debes conectarte (Opción 1).")
            return
            
        print("\n--- GESTIÓN DE FALLOS ---")
        # Aquí puedes añadir la lógica de leer fallos cuando la tengas.
        # Por ahora, usamos el ejemplo de borrado.
        fallos_actuales = ["P0300", "P0171", "P0420"]
        print(f"Fallos detectados (simulados): {fallos_actuales}")
        borrar = input("¿Deseas borrarlos? (s/n): ")
        if borrar.lower() == 's':
            self.dtc_mgr.borrar_fallos(self.conexion, fallos_actuales, coche=self.vin)

    def detectar_pids(self):
        if not self.vin:
            print("Primero debes conectarte (Opción 1).")
            return
            
        print("\n--- DETECTANDO PIDs SOPORTADOS ---")
        pids_totales = detectar_pids_soportados(self.conexion, self.parser)
        print(f"Total de PIDs soportados detectados: {len(pids_totales)}")
        print(f"Lista completa: {pids_totales}")

    def hacer_backup(self):
        if not self.vin:
            print("Primero debes conectarte (Opción 1).")
            return
            
        print("\n--- BACKUP DE MÓDULO ---")
        modulo = input("Introduce el nombre del módulo (ej. BCM): ")
        # Aquí leerías los bytes reales del coche, usando un ejemplo por ahora
        bytes_ejemplo = [0x01, 0x0A, 0x3F, 0x00, 0x12]
        self.backup_mgr.guardar_backup(modulo=modulo, coche=self.vin, bytes_coding=bytes_ejemplo)
        print(f"Backup guardado para el módulo {modulo}.")

    def ejecutar(self):
        while True:
            opcion = self.mostrar_menu()
            if opcion == '1':
                self.conectar()
            elif opcion == '2':
                self.leer_sensores()
            elif opcion == '3':
                self.gestionar_fallos()
            elif opcion == '4':
                self.detectar_pids()
            elif opcion == '5':
                self.hacer_backup()
            elif opcion == '0':
                print("Desconectando y saliendo...")
                if self.conexion:
                    self.conexion.desconectar()
                sys.exit(0)
            else:
                print("Opción no válida. Inténtalo de nuevo.")

if __name__ == "__main__":
    menu = Menu()
    menu.ejecutar()
