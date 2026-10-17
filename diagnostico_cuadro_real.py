"""
diagnostico_cuadro_real.py
══════════════════════════════════════════════════════════════════════════════
Herramienta de diagnóstico e inspección forense para el Cuadro de Instrumentos
(Módulo 17 - 4F0 920 933 x) en Audi A6 C6 Facelift.

1. Abre canal TP 2.0 limpio con el Módulo 17.
2. Lee la identificación exacta: Referencia (HW/SW), letra de versión y componente.
3. Lee la memoria de codificación:
   - Si es Long Coding (Bytes): Analiza Byte 1 Bit 0 (Needle Sweep) y ofrece activación limpia.
   - Si es Soft Coding (7 dígitos): Muestra el desglose y confirma compatibilidad.
══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time

# Asegurar path raíz del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.can_manager import CANManager
from obd.tp20_can import TP20Transport, KWP2000NativeClient
from gestion.backup_manager import BackupManager


def print_header():
    print("=" * 68)
    print("   INSPECCIÓN FORENSE CUADRO DE INSTRUMENTOS AUDI A6 C6 (4F)")
    print("             Módulo 17 (J285) — CANable 2.0 / TP 2.0")
    print("=" * 68)


def ejecutar_diagnostico():
    print_header()

    can_mgr = CANManager()
    print("\n[1/4] Buscando y conectando adaptador CANable 2.0...")

    # Autodetectar puerto COM
    puerto = can_mgr.auto_detectar_puerto()
    if not puerto:
        print("\n[!] No se detectó CANable 2.0 conectado por USB.")
        print("    Verifica que el cable esté enchufado al portátil y al coche.")
        res = input("\n¿Quieres ejecutar en modo SIMULADO para probar la herramienta? (s/n): ").strip().lower()
        if res == "s":
            puerto = "SIMULADO"
        else:
            return

    if not can_mgr.conectar(port=puerto, bitrate=500000):
        print(f"\n[ERROR] No se pudo abrir conexión en {puerto} a 500 kbps.")
        return

    print(f"[OK] Conexión establecida con éxito en {puerto} (500 kbps).")
    print("[*] Asegúrate de que el contacto del coche esté encendido (IGN ON, motor apagado).")

    tp20 = TP20Transport(can_mgr, timeout=1.5)
    kwp = KWP2000NativeClient(tp20)

    try:
        can_mgr.flush_rx()
        print("\n[2/4] Abriendo canal de transporte privado TP 2.0 con Cuadro 17...")
        if not tp20.open_channel(0x17, retries=3):
            print("\n[FALLO] El Cuadro de Instrumentos (0x17) no responde al canal TP 2.0.")
            print("Posibles causas:")
            print(" - El contacto no está encendido.")
            print(" - El cuadro está en temporizador de castigo (espera 10 min con contacto quitado).")
            return

        print("[OK] Canal TP 2.0 abierto correctamente con Módulo 17.")

        print("\n[3/4] Estableciendo sesión de diagnóstico KWP2000...")
        kwp.start_diagnostic_session(0x86)
        time.sleep(0.08)

        # Leer Identificación del Cuadro (Service 0x1A 0x9B / 0x80)
        print("[*] Solicitando bloque de identificación de la centralita...")
        info = kwp.read_ecu_identification()
        part_number = info.get("part_number", "Desconocido")
        sw_ver = info.get("sw_version", "N/D")
        component = info.get("component", "N/D")

        print("\n" + "─" * 50)
        print(" DATOS OFICIALES DEL CUADRO DETECTADO:")
        print("─" * 50)
        print(f" ▸ Referencia / Part Number : {part_number}")
        print(f" ▸ Versión de Software (SW) : {sw_ver}")
        print(f" ▸ Identificación Componente: {component}")
        print("─" * 50)

        # Leer Codificación
        print("\n[4/4] Analizando arquitectura de memoria y codificación...")
        raw_coding = kwp.read_coding()

        if not raw_coding:
            print("\n[AVISO] No se pudo leer la codificación mediante los canales KWP estándar.")
            return

        coding_bytes = list(raw_coding)
        total_bytes = len(coding_bytes)
        hex_str = " ".join(f"{b:02X}" for b in coding_bytes)

        print(f" ▸ Longitud leída: {total_bytes} bytes")
        print(f" ▸ Volcado HEX   : {hex_str}")

        if total_bytes >= 3:
            # Cuadro con LONG CODING (Estructura de bytes)
            print("\n" + "★" * 55)
            print(" ¡CONFIRMADO! TU CUADRO TIENE ARQUITECTURA LONG CODING")
            print("★" * 55)

            byte_1 = coding_bytes[1]
            needle_activo = bool(byte_1 & 0x01)
            laptimer_activo = bool(byte_1 & 0x08)

            print(f"\n ▸ Byte 0: 0x{coding_bytes[0]:02X}")
            print(f" ▸ Byte 1: 0x{byte_1:02X} (Binario: {byte_1:08b})")
            print(f"    - Bit 0 [Needle Sweep / Staging]: {'[ACTIVO]' if needle_activo else '[INACTIVO]'}")
            print(f"    - Bit 3 [Lap Timer / Cronómetro]: {'[ACTIVO]' if laptimer_activo else '[INACTIVO]'}")

            if needle_activo:
                print("\n[✓] El Needle Sweep YA ESTÁ ACTIVADO en la memoria de este cuadro.")
                print("    Si quitas contacto 10 segundos y vuelves a dar contacto, las agujas deben barrer.")
            else:
                print("\n[!] El Needle Sweep está SOPORTADO pero actualmente está DESACTIVADO.")
                opcion = input("\n¿Deseas ACTIVAR el Needle Sweep ahora mismo de forma limpia? (s/n): ").strip().lower()

                if opcion == "s":
                    # Backup previo
                    bm = BackupManager()
                    bm.guardar_backup(
                        modulo="Cuadro Instrumentos (17)",
                        coche="AUDI_A6_C6_FACELIFT",
                        bytes_coding=hex_str,
                        etiqueta="PRE_NEEDLE_SWEEP_STANDALONE"
                    )
                    print("[OK] Copia de seguridad guardada en datos/backups/")

                    # Modificar Byte 1, Bit 0
                    coding_bytes[1] = byte_1 | 0x01
                    nuevo_hex = " ".join(f"{b:02X}" for b in coding_bytes)
                    print(f"[*] Nuevo Byte 1 calculado: 0x{coding_bytes[1]:02X}")
                    print(f"[*] Nueva codificación: {nuevo_hex}")

                    print("\n[*] Escribiendo en el cuadro mediante Service 0x3B (sin claves de seguridad falsas)...")
                    if kwp.write_coding(bytes(coding_bytes)):
                        time.sleep(0.15)
                        # Verificar
                        verif = kwp.read_coding()
                        if verif and len(verif) > 1 and (verif[1] & 0x01):
                            print("\n" + "=" * 60)
                            print(" ¡ÉXITO ROTUNDO! NEEDLE SWEEP GRABADO Y VERIFICADO")
                            print("=" * 60)
                            print("Próximo paso:")
                            print("1. Quita el contacto del coche y saca la llave 10 segundos.")
                            print("2. Vuelve a meter la llave y da contacto.")
                            print("3. ¡Disfruta del barrido de agujas completo!")
                        else:
                            print("\n[?] El comando se envió pero la verificación devolvió valor anterior.")
                    else:
                        print("\n[FALLO] El cuadro rechazó la escritura (NRC de servicio).")

        else:
            # Cuadro con SHORT CODING (Soft Coding decimal)
            print("\n" + "─" * 55)
            print(" DIAGNÓSTICO: TU CUADRO UTILIZA SOFT CODING TRADICIONAL")
            print("─" * 55)
            print(f"Volcado en memoria: {hex_str}")
            print("\nConclusión técnica definitiva:")
            print("Esta versión de software del cuadro 4F0 920 933 utiliza codificación")
            print("corta de opciones fijas. En esta revisión de fábrica, Audi no")
            print("incluyó la rutina de Needle Sweep por puerto de diagnosis OBD.")

    except Exception as e:
        print(f"\n[EXCEPCIÓN] Error durante el diagnóstico: {e}")

    finally:
        tp20.close_channel()
        can_mgr.desconectar()
        print("\n[*] Canal TP 2.0 cerrado y conexión liberada de forma segura.")


if __name__ == "__main__":
    ejecutar_diagnostico()
