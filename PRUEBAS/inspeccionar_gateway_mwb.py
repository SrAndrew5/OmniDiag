#!/usr/bin/env python3
"""
PRUEBAS/inspeccionar_gateway_mwb.py
══════════════════════════════════════════════════════════════════════════════
Script de diagnóstico forense de la Pasarela CAN Gateway (J533)
y Gestor de Energía de Batería (BEM J644) (100% SOLO LECTURA).

Funcionalidades:
  1. Abre canal TP 2.0 con la Pasarela (0x19).
  2. Lee la identificación exacta de la ECU (Referencia SW, HW, Componente).
  3. Lee los Códigos de Avería (DTCs) de comunicación almacenados.
  4. Lee los Bloques de Valores de Medición (MWB vía Servicio KWP 0x21):
     - Grupo 125: Estado de comunicación del Cuadro J285, Motor, ABS.
     - Grupo 126: Estado de comunicación de Puertas J386/J387, Clima, J519.
     - Grupo 127: Estado de comunicación de Centralita Confort J393.
     - Grupo 001/002: Tensión de borne 30/15 y Etapa de Desconexión BEM (Load Shedding).

Uso:
    python PRUEBAS/inspeccionar_gateway_mwb.py
    python PRUEBAS/inspeccionar_gateway_mwb.py gs_usb
    python PRUEBAS/inspeccionar_gateway_mwb.py virtual
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
from obd.tp20_can import TP20Transport, KWP2000NativeClient  # noqa: E402


def decodificar_bloque_mwb(grupo: int, raw_bytes: bytes) -> str:
    """Decodifica texto o campos estándar VAG de un bloque de medición."""
    if not raw_bytes:
        return "Sin datos"
    # Mostrar hex formateado y texto ASCII imprimible
    hex_str = " ".join(f"{b:02X}" for b in raw_bytes)
    ascii_chars = [chr(b) if 32 <= b <= 126 else "." for b in raw_bytes]
    ascii_str = "".join(ascii_chars).strip()
    return f"Hex: [{hex_str}] | ASCII: '{ascii_str}'"


def inspeccionar_gateway(pref_interfaz: str = "auto") -> None:
    print("=" * 72)
    print(" INSPECCIÓN FORENSE DE PASARELA CAN GATEWAY J533 / BEM (SOLO LECTURA)")
    print("=" * 72)
    print("Objetivo: Comprobar qué módulos ve el Gateway y si hay Load Shedding activo.\n")

    can_mgr = CANManager(log_fn=lambda m: None)
    print(f"[*] Conectando con adaptador CAN ({pref_interfaz})...")
    if not can_mgr.conectar(interface_preference=pref_interfaz, bitrate=500000):
        print("[ERROR] No se pudo conectar con el adaptador CAN.")
        print("        Verifica que el cable USB esté conectado y los drivers instalados.")
        return

    interfaz_activa = getattr(can_mgr, "connected_interface", "desconocida")
    print(f"[OK] Conectado exitosamente vía {interfaz_activa} (500 kbps).\n")

    tp20 = TP20Transport(
        can_mgr,
        timeout=1.2,
        debug=False,
        progress_fn=lambda m: print(f"   {m}"),
    )
    kwp = KWP2000NativeClient(tp20)

    # 1. Intentar abrir canal con la Gateway (0x19)
    print("-" * 72)
    print("[PASO 1] Abriendo canal TP 2.0 con Dirección 0x19 (CAN Gateway)...")
    print("-" * 72)

    canal_ok = tp20.open_channel(0x19, attempts=3, setup_timeout=1.5)
    if not canal_ok:
        print("\n[ALERTA] No se pudo abrir canal TP 2.0 con 0x19.")
        print("         Probando dirección alternativa 0x13 (19 dec)...")
        canal_ok = tp20.open_channel(0x13, attempts=2, setup_timeout=1.5)

    if not canal_ok:
        print("[ERROR] El Gateway no respondió al Channel Setup TP 2.0 en 0x19 ni 0x13.")
        print("        Asegúrate de que el contacto esté puesto o el motor en marcha.")
        can_mgr.desconectar()
        return

    print(f"[OK] Canal TP 2.0 establecido (TX 0x{tp20.tx_addr:03X} / RX 0x{tp20.rx_addr:03X}).\n")

    try:
        # 2. Identificación del módulo
        print("-" * 72)
        print("[PASO 2] Leyendo Identificación del Módulo...")
        print("-" * 72)
        ident = kwp.read_ecu_identification()
        part_num = ident.get("part_number", "Desconocido")
        comp = ident.get("component", "Desconocido")
        sw = ident.get("sw_version", "Desconocido")
        hw = ident.get("hw_version", "Desconocido")

        print(f"  • Referencia SW:    {part_num}")
        print(f"  • Componente / Sis: {comp}")
        print(f"  • Versión SW:       {sw}")
        print(f"  • Versión HW:       {hw}")

        if "EPB" in comp or "801" in part_num:
            print("\n  [NOTA TÉCNICA RELEVANTE]")
            print("  El módulo que respondió en 0x19 se identifica como Freno de Mano Eléctrico (EPB).")
        elif "GW" in comp or "468" in part_num:
            print("\n  [OK] El módulo responde como CAN Gateway J533 auténtico.")

        # 3. Lectura de DTCs (Códigos de avería de comunicación)
        print("\n" + "-" * 72)
        print("[PASO 3] Consultando Memoria de Averías (DTCs)...")
        print("-" * 72)
        dtcs = kwp.read_dtcs()
        if dtcs:
            print(f"  [!] Averías encontradas ({len(dtcs)}):")
            for d in dtcs:
                print(f"     → {d}")
        else:
            print("  [OK] No hay códigos de avería registrados (o memoria limpia).")

        # 4. Lectura de Bloques de Medición (MWB) de Comunicación
        print("\n" + "-" * 72)
        print("[PASO 4] Lectura de Bloques de Medición de Comunicación (MWB)...")
        print("-" * 72)

        bloques = [
            (125, "0x7D", "Estado Bus Tracción / Cuadro (Motor, ABS, Cuadro J285, Airbag)"),
            (126, "0x7E", "Estado Bus Confort (Clima J255, Puerta Conductor J386, Puerta Copiloto J387)"),
            (127, "0x7F", "Estado Bus Confort Extendido (Centralita Confort J393)"),
            (1, "0x01", "Tensiones Borne 30 / Borne 15 / Generador"),
            (2, "0x02", "Etapa de Desconexión de Carga BEM (Abschaltstufen)"),
        ]

        for num_bloque, hex_label, desc in bloques:
            print(f"\n[*] Solicitando Grupo {num_bloque} ({hex_label}): {desc}...")
            try:
                # Servicio KWP2000 0x21: ReadDataByLocalIdentifier
                resp = kwp.execute_service(0x21, subfunction=num_bloque)
                interpretacion = decodificar_bloque_mwb(num_bloque, resp)
                print(f"    Respuesta ECU: {interpretacion}")
            except Exception as e:
                print(f"    (Sin respuesta o grupo no soportado: {e})")
            time.sleep(0.08)

    except Exception as e:
        print(f"\n[ERROR] Ocurrió una anomalía durante la inspección: {e}")
    finally:
        print("\n[*] Cerrando canal TP 2.0 y liberando bus CAN...")
        tp20.close_channel()
        can_mgr.desconectar()
        print("[OK] Sesión finalizada con seguridad.\n")


def main():
    pref = "auto"
    if len(sys.argv) > 1:
        pref = sys.argv[1]
    inspeccionar_gateway(pref)


if __name__ == "__main__":
    main()
