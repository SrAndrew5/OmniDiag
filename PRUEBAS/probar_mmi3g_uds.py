#!/usr/bin/env python3
"""
PRUEBAS/probar_mmi3g_uds.py
══════════════════════════════════════════════════════════════════════════════
Script de diagnóstico y lectura UDS / ISO-TP directa para MMI 3G (J794 / 0x5F)
en Audi A6 C6 Facelift (BNav / MMI 3G Basic).

En el Facelift 2009-2011 con MMI 3G (BNav_EU), la unidad central de información
J794 no se diagnostica por VW TP 2.0 (0xC0), sino mediante UDS (ISO 14229)
encapsulado en tramas ISO-TP (ISO 15765-2) en los IDs CAN dedicados:
  - TX (Tester -> MMI): 0x770 (o functional 0x7DF)
  - RX (MMI -> Tester): 0x7DA

Lee (100% MODO SOLO LECTURA):
  1. Sesión diagnóstica UDS (0x10 0x01 / 0x10 0x03).
  2. Número de pieza y Referencia VAG (DID 0xF187 / 0xF191).
  3. Versión exacta de Software (DID 0xF189 -> BNav_EU_...).
  4. Bastidor / VIN almacenado (DID 0xF190).
  5. Long Coding de la unidad multimedia (DID 0x0600 / 0xF18C).
  6. Códigos de avería (DTCs) activos o memorizados en la pantalla.

Uso:
    python PRUEBAS/probar_mmi3g_uds.py
    python PRUEBAS/probar_mmi3g_uds.py gs_usb
    python PRUEBAS/probar_mmi3g_uds.py virtual
══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time
from pathlib import Path

# Configurar stdout para evitar errores de codificación en consolas Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.can_manager import CANManager  # noqa: E402
from obd.isotp_uds import ISOTPClient, UDSClient, UDSError  # noqa: E402


def probar_mmi3g(pref_interfaz: str = "auto") -> None:
    print("=" * 76)
    print(" DIAGNÓSTICO UDS NATIVO: PANTALLA / UNIDAD MMI 3G J794 (5F)")
    print("=" * 76)
    print("Objetivo: Enviar tramas UDS / ISO-TP directas a la unidad BNav_EU de la pantalla.\n")

    can_mgr = CANManager(log_fn=lambda m: None)
    print(f"[*] Conectando con adaptador CAN ({pref_interfaz})...")
    if not can_mgr.conectar(interface_preference=pref_interfaz, bitrate=500000):
        print("[ERROR] No se pudo conectar con el adaptador CAN.")
        print("        Verifica que el cable USB esté conectado y los drivers instalados.")
        return

    interfaz_activa = getattr(can_mgr, "connected_interface", "desconocida")
    print(f"[OK] Conectado exitosamente vía {interfaz_activa} (500 kbps).\n")

    # Mapeo de IDs CAN para MMI 3G en plataforma VAG
    CANDIDATOS_IDS = [
        (0x770, 0x7DA, "MMI 3G Principal (J794) [TX 0x770 / RX 0x7DA]"),
        (0x76C, 0x7D6, "MMI 3G Secundario / Navegación [TX 0x76C / RX 0x7D6]"),
        (0x714, 0x77E, "Dashboard / Info Bus alternativo [TX 0x714 / RX 0x77E]"),
    ]

    uds_conectado = None
    info_canal = None

    print("-" * 76)
    print("[PASO 1] Estableciendo Sesión de Diagnóstico UDS...")
    print("-" * 76)

    for tx_id, rx_id, desc in CANDIDATOS_IDS:
        print(f"[*] Probando enlace con {desc}...")
        try:
            can_mgr.flush_rx()
            isotp = ISOTPClient(can_mgr, tx_id=tx_id, rx_id=rx_id, timeout=0.8)
            uds = UDSClient(isotp)

            # Enviar solicitud de sesión UDS Default (0x10 0x01)
            ok = uds.diagnostic_session_control(0x01)
            if ok:
                print(f"  [OK] ¡Conexión establecida con éxito en TX 0x{tx_id:03X} / RX 0x{rx_id:03X}!")
                uds_conectado = uds
                info_canal = desc
                break
            else:
                # Probar sesión extendida (0x10 0x03)
                ok = uds.diagnostic_session_control(0x03)
                if ok:
                    print(f"  [OK] ¡Sesión extendida UDS aceptada en TX 0x{tx_id:03X} / RX 0x{rx_id:03X}!")
                    uds_conectado = uds
                    info_canal = desc
                    break
                else:
                    print(f"      (Sin respuesta a la sesión en 0x{rx_id:03X})")
        except Exception as e:
            print(f"      (Error o timeout en este canal: {e})")
        time.sleep(0.05)

    if not uds_conectado:
        print("\n[ALERTA] Ninguno de los canales UDS directos respondió.")
        print("         Probando broadcast funcional OBD 0x7DF (Despertar UDS general)...")
        try:
            can_mgr.flush_rx()
            # Enviar Single Frame funcional 0x7DF [02 10 01 00 00 00 00 00]
            can_mgr.send_frame(0x7DF, bytes([0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]))
            t0 = time.perf_counter()
            respuestas_func = []
            while time.perf_counter() - t0 < 0.6:
                m = can_mgr.recv_frame(timeout=0.08)
                if m and len(m.data) >= 3 and m.data[1] == 0x50:
                    respuestas_func.append(m.arbitration_id)

            if respuestas_func:
                print(f"  [OK] Módulos UDS respondiendo al broadcast funcional: "
                      f"{', '.join(f'0x{i:03X}' for i in set(respuestas_func))}")
            else:
                print("  (Sin respuesta tampoco al broadcast funcional 0x7DF)")
        except Exception:
            pass

        print("\n[RESUMEN] No se pudo establecer sesión UDS con la pantalla en este intento.")
        print("          Recuerda: El motor debe estar arrancado o el contacto en posición II con la pantalla iluminada.")
        can_mgr.desconectar()
        return

    # Si conectó, leer todos los DIDs forenses
    try:
        print("\n" + "-" * 76)
        print(f"[PASO 2] Leyendo Identificación UDS de la Pantalla MMI ({info_canal})...")
        print("-" * 76)

        ident = uds_conectado.read_ecu_identification()
        print(f"  • Referencia VAG (DID 0xF187 / 0xF191): {ident.get('part_number', 'Desconocido')}")
        print(f"  • Versión Software (DID 0xF189):       {ident.get('sw_version', 'Desconocido')}")
        print(f"  • Número de Bastidor (VIN DID 0xF190):  {ident.get('vin', 'Desconocido')}")

        # Leer Long Coding del MMI 3G
        print("\n" + "-" * 76)
        print("[PASO 3] Leyendo Codificación Larga (Long Coding) del MMI 3G...")
        print("-" * 76)
        coding = uds_conectado.read_coding()
        if coding:
            hex_coding = " ".join(f"{b:02X}" for b in coding)
            print(f"  [OK] Long Coding leído con éxito ({len(coding)} bytes):")
            print(f"       {hex_coding}")
        else:
            print("  (La codificación larga requiere sesión extendida o acceso de seguridad)")

        # Leer Averías (DTCs) del MMI 3G
        print("\n" + "-" * 76)
        print("[PASO 4] Consultando Averías (DTCs) del MMI 3G...")
        print("-" * 76)
        dtcs = uds_conectado.read_dtcs()
        if dtcs:
            print(f"  [!] Averías registradas en la unidad MMI ({len(dtcs)}):")
            for d in dtcs:
                print(f"     → {d}")
        else:
            print("  [OK] Memoria de averías limpia (sin DTCs registrados en MMI).")

    except Exception as e:
        print(f"\n[ERROR] Anomalía durante la lectura UDS: {e}")
    finally:
        can_mgr.desconectar()
        print("\n[OK] Sesión UDS finalizada correctamente.\n")


def main():
    pref = "auto"
    if len(sys.argv) > 1:
        pref = sys.argv[1]
    probar_mmi3g(pref)


if __name__ == "__main__":
    main()
