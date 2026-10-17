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
from obd.audi_a6_actions import AudiA6Actions
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
            print(" DIAGNÓSTICO: FORMATO LONG CODING DETECTADO")
            print("★" * 55)

            byte_1 = coding_bytes[1]
            needle_activo = bool(byte_1 & 0x01)
            laptimer_activo = bool(byte_1 & 0x08)

            print(f"\n ▸ Byte 0: 0x{coding_bytes[0]:02X}")
            print(f" ▸ Byte 1: 0x{byte_1:02X} (Binario: {byte_1:08b})")
            print(f"    - Bit 0 [Needle Sweep / Staging]: {'[ACTIVO]' if needle_activo else '[INACTIVO]'}")
            print(f"    - Bit 3 [Lap Timer / Cronómetro]: {'[ACTIVO]' if laptimer_activo else '[INACTIVO]'}")

            if needle_activo:
                print("\n[✓] El Needle Sweep YA ESTÁ ACTIVADO en la codificación de este cuadro.")
            else:
                print("\n[!] El Needle Sweep está actualmente DESACTIVADO (Bit 0 Byte 1 en 0).")
                opcion = input("\n¿Deseas activar el Needle Sweep mediante el protocolo seguro unificado? (s/n): ").strip().lower()

                if opcion == "s":
                    tp20.close_channel()
                    actions = AudiA6Actions(can_mgr, log_fn=print, vin="AUDI_A6_C6_FACELIFT")
                    ok, msg = actions.activar_needle_sweep()
                    if ok:
                        print("\n" + "=" * 60)
                        print(" ¡ÉXITO! NEEDLE SWEEP GRABADO Y VERIFICADO AL 100%")
                        print("=" * 60)
                    else:
                        print(f"\n[AVISO] {msg}")

        else:
            # Cuadro con SHORT CODING (Soft Coding decimal)
            print("\n" + "─" * 55)
            print(" DIAGNÓSTICO: LONGITUD INFERIOR A 3 BYTES (SOFT CODING TRADICIONAL)")
            print("─" * 55)
            print(f"Volcado en memoria: {hex_str}")
            print("\nInformación técnica:")
            print("La codificación leída tiene menos de 3 bytes. En cuadros con codificación")
            print("corta tradicional, el Needle Sweep habitualmente no está documentado")
            print("por este canal de codificación.")

    except Exception as e:
        print(f"\n[EXCEPCIÓN] Error durante el diagnóstico: {e}")

    finally:
        tp20.close_channel()
        can_mgr.desconectar()
        print("\n[*] Canal TP 2.0 cerrado y conexión liberada de forma segura.")


if __name__ == "__main__":
    ejecutar_diagnostico()
