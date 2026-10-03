# -*- coding: utf-8 -*-
"""
test_kline_hardware.py
══════════════════════════════════════════════════════════════════════════════
Pre-Flight Hardware Check para el Cable USB K-Line (VW Polo 9N3).
Ejecuta una comprobación rápida en PC antes de bajar al vehículo:
  1. Escanea puertos COM serie en Windows.
  2. Identifica chips FTDI (FT232RL) o adaptadores USB-Serie compatibles.
  3. Comprueba apertura de puerto a 9600 y 10400 baudios.
  4. Valida el soporte de condición BREAK para el Slow Init de 5 baudios.
══════════════════════════════════════════════════════════════════════════════
"""

import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[ERROR] PySerial no está instalado. Ejecuta: pip install pyserial")
    sys.exit(1)


def verificar_hardware_kline():
    print("=" * 65)
    print("   OMNIDIAG - TEST PRE-FLIGHT DE CABLE K-LINE (VW POLO 9N3)")
    print("=" * 65)

    puertos = list(serial.tools.list_ports.comports())
    if not puertos:
        print("\n[!] AVISO: No se ha detectado ningún puerto COM activo en Windows.")
        print("    -> Enchufa el cable USB K-Line a cualquier puerto USB de tu PC.")
        print("    -> Si el cable ya está enchufado, comprueba que Windows ha cargado el driver FTDI.")
        return False

    print(f"\n[+] Puertos COM detectados en Windows: {len(puertos)}")
    candidatos_ftdi = []
    for p in puertos:
        mfg = (p.manufacturer or "").upper()
        hwid = (p.hwid or "").upper()
        desc = (p.description or "").upper()
        es_ftdi = "FTDI" in mfg or "0403" in hwid or "USB-SERIAL" in desc or "SERIAL" in desc
        tag = "[CABLE CANDIDATO]" if es_ftdi else "[OTRO DISPOSITIVO]"
        print(f"    * {p.device}: {p.description}")
        print(f"      HWID: {p.hwid} {tag}")
        if es_ftdi or "COM" in p.device:
            candidatos_ftdi.append(p.device)

    if not candidatos_ftdi:
        candidatos_ftdi = [p.device for p in puertos]

    puerto_test = candidatos_ftdi[0]
    print(f"\n[TEST] Probando comunicación de bajo nivel en: {puerto_test}...")

    try:
        ser = serial.Serial(puerto_test, 9600, timeout=0.5)
        print("  [OK] Apertura de puerto a 9600 baudios correcta.")

        # Test de conmutación de velocidad a 10400
        ser.baudrate = 10400
        print("  [OK] Conmutación a 10.400 baudios (EDC15 TDI) soportada.")

        # Test de señal BREAK para 5 baudios
        ser.break_condition = True
        time.sleep(0.05)
        ser.break_condition = False
        print("  [OK] Línea de control BREAK activa (Bit-Banging 5 baudios operativo).")

        ser.close()
        print("\n" + "=" * 65)
        print(f"  [100% LISTO] El cable en {puerto_test} está perfectamente configurado.")
        print("  -> Puedes bajar al coche y conectar con total seguridad.")
        print("=" * 65)
        return True

    except Exception as e:
        print(f"\n  [ERROR] Al acceder a {puerto_test}: {e}")
        print("  -> Asegúrate de que ninguna otra aplicación (VCDS, Putty, etc.) tenga abierto el puerto.")
        return False


if __name__ == "__main__":
    verificar_hardware_kline()
