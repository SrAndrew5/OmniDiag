#!/usr/bin/env python3
"""
PRUEBAS/inspeccionar_gateway_mwb.py
══════════════════════════════════════════════════════════════════════════════
Script de diagnóstico forense EXHAUSTIVO de la Pasarela CAN Gateway (J533)
y Gestor de Energía de Batería (BEM J644) (100% SOLO LECTURA).

Inspecciona TODO lo que la pasarela tiene disponible:
  1. Identificación Completa (Referencia SW, HW, Componente, Codificación).
  2. Todos los Códigos de Avería de Comunicación (DTCs).
  3. Bloques de Medición del Sistema Eléctrico y BEM (Grupos 001 al 006):
     - Tensiones (Borne 30 / Borne 15 / Alternador).
     - Etapa de Desconexión de Carga (Abschaltstufen 0 a 6: Load Shedding).
     - Corrientes de reposo y estado de carga de la batería.
  4. Bloques de Medición de Comunicación de TODOS los Módulos (Grupos 125 al 135):
     - Grupo 125: Motor (01), Transmisión (02), ABS (03), Cuadro J285 (17).
     - Grupo 126: Climatizador (08), Airbag (15), Volante (16), Freno Mano (53).
     - Grupo 127: Puerta Conductor (42), Puerta Copiloto (52), Traseras (62/72).
     - Grupo 128: Centralita Confort (46), Red de a Bordo (09), Inmovilizador (25).
     - Grupo 129: Infotainment, Radio, Teléfono, MMI.
     - Grupo 130: ESTADO FÍSICO DEL BUS (2 hilos OK vs 1 hilo / Monocable Eindraht).
     - Grupo 131-135: Enrutamiento CAN-Diagnóstico y fuentes de despertar (Wake-up).

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


# ── DICCIONARIO OFICIAL DE BLOQUES DE MEDICIÓN VAG GATEWAY J533 ───────────────
GRUPOS_GATEWAY_VAG = {
    # ── GESTIÓN DE ENERGÍA Y BATERÍA (BEM J644) ──
    1: "Tensiones del Sistema (Borne 30, Borne 15, Generador)",
    2: "Etapa de Desconexión BEM (Abschaltstufe: 0=Normal, 1..6=Load Shedding Activo)",
    3: "Batería BEM: Capacidad de arranque, Estado de Carga (SOC) y Salud (SOH)",
    4: "Consumos de Reposo y Pérdidas de Energía Parásitas",
    5: "Historial BEM: Últimas etapas de corte de corriente activadas",
    6: "Historial BEM: Corrientes de reposo máximas registradas",

    # ── ESTADO DE COMUNICACIÓN DE TODAS LAS CENTRALITAS ──
    125: "CAN-Tracción y Cuadro: [1] Motor (01) | [2] Cambio (02) | [3] ABS (03) | [4] Cuadro J285 (17)",
    126: "CAN-Seguridad y Chasis: [1] Climatronic (08) | [2] Airbag (15) | [3] Volante (16) | [4] EPB Freno (53)",
    127: "CAN-Confort Puertas: [1] Puerta Conductor J386 (42) | [2] Puerta Copiloto J387 (52) | [3] Puerta Tras Izq (62) | [4] Puerta Tras Der (72)",
    128: "CAN-Confort Central: [1] Confort J393 (46) | [2] Red de a Bordo J519 (09) | [3] Inmovilizador (25) | [4] Memoria Asientos (36)",
    129: "CAN-Infotainment: [1] Radio / Sonido | [2] Navegación MMI | [3] Teléfono / BT | [4] Cuadro MMI",
    130: "ESTADO FÍSICO DEL BUS CAN: [1] CAN-Tracción | [2] CAN-Confort (2-wire vs 1-wire Monocable!) | [3] CAN-Kombi | [4] Estado Bus-Off",
    131: "CAN-Diagnóstico: Estado de enlace entre Conector OBD (T16) y Pasarela J533",
    132: "Fuentes de Despertar de Bus (Wake-up Bus): Qué módulo despertó el coche",
    133: "Estado de Reposo de Centralitas de Confort (Bus Ruhe)",
    134: "Estado de Reposo de Centralitas de Tracción",
    135: "Supervisión de Alimentación de Transceptores CAN",
}


def formatear_campo_vag(scaler: int, a: int, b: int) -> str:
    """Interpreta el escalador estándar KWP2000 según las fórmulas del Grupo VAG."""
    # Escalador 0x24: Típico indicador binario/estado booleano en pasarelas VAG
    if scaler == 0x24:
        val = (a * 256) + b
        if val == 1 or a == 1:
            return "1 (COMUNICANDO / ACTIVO)"
        elif val == 0:
            return "0 (SIN SEÑAL / OFFLINE)"
        return f"{val}"
    # Escalador 0x01: Conteo crudo / Etapa
    elif scaler == 0x01:
        return f"{a * 256 + b}"
    # Escalador 0x02: Porcentaje
    elif scaler == 0x02:
        return f"{a * 0.4:.1f} %"
    # Escalador 0x07: Voltaje típico (0.01V o 0.05V)
    elif scaler == 0x07:
        v = (a * 256 + b) * 0.01
        return f"{v:.2f} V"
    # Escalador 0x08: Amperios
    elif scaler == 0x08:
        amp = (a * 256 + b) * 0.1 - 100.0
        return f"{amp:.1f} A"
    # Escalador 0x21 / 0x24 para km
    elif scaler in (0x21, 0x24) and ((a * 256 + b) > 1000):
        return f"{(a * 256 + b):,} km"
    else:
        return f"Raw: [0x{scaler:02X} {a:02X} {b:02X}]"


def decodificar_bloque_mwb(grupo: int, raw_bytes: bytes) -> str:
    """Decodifica los 4 campos VAG KWP2000 o el volcado hex/ASCII."""
    if not raw_bytes or len(raw_bytes) < 2:
        return "Sin datos devueltos"

    datos = raw_bytes[1:] if raw_bytes[0] in (0x61, grupo) else raw_bytes

    # Formato estándar VAG KWP2000: 4 campos de 3 bytes = 12 bytes [scaler, a, b]
    campos_interpretados = []
    if len(datos) >= 3:
        for idx in range(0, min(len(datos) - 2, 12), 3):
            scaler = datos[idx]
            a = datos[idx + 1]
            b = datos[idx + 2]
            campos_interpretados.append(formatear_campo_vag(scaler, a, b))

    # Texto ASCII imprimible de fondo
    ascii_chars = [chr(b) if 32 <= b <= 126 else "." for b in datos]
    ascii_str = "".join(ascii_chars).strip()
    hex_str = " ".join(f"{b:02X}" for b in datos)

    res = ""
    if campos_interpretados:
        for num_c, val_c in enumerate(campos_interpretados, 1):
            res += f"\n       Campo {num_c}: {val_c}"

    res += f"\n       Trama: [{hex_str}]"
    if any(32 <= b <= 126 for b in datos):
        res += f" | '{ascii_str}'"

    return res


def inspeccionar_gateway(pref_interfaz: str = "auto") -> None:
    print("=" * 76)
    print(" INSPECCIÓN FORENSE EXHAUSTIVA DE LA PASARELA GATEWAY J533 Y BEM")
    print("=" * 76)
    print("Comprobando TODO: estado de todos los módulos, fallos y salud del bus CAN.\n")

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

    # 1. Intentar abrir canal con la Gateway (0x19 o 0x13)
    print("-" * 76)
    print("[PASO 1] Abriendo canal TP 2.0 con Dirección 0x19 (CAN Gateway)...")
    print("-" * 76)

    canal_ok = tp20.open_channel(0x19, attempts=3, setup_timeout=1.5)
    if not canal_ok:
        print("\n[ALERTA] No se pudo abrir canal TP 2.0 con 0x19.")
        print("         Probando dirección alternativa 0x13 (19 decimal)...")
        canal_ok = tp20.open_channel(0x13, attempts=2, setup_timeout=1.5)

    if not canal_ok:
        print("[ERROR] La Pasarela no respondió al Channel Setup TP 2.0 en 0x19 ni 0x13.")
        print("        Asegúrate de que el contacto esté puesto o el motor en marcha.")
        can_mgr.desconectar()
        return

    print(f"[OK] Canal TP 2.0 establecido (TX 0x{tp20.tx_addr:03X} / RX 0x{tp20.rx_addr:03X}).\n")

    try:
        # 2. Identificación del módulo
        print("-" * 76)
        print("[PASO 2] Leyendo Identificación Completa del Módulo...")
        print("-" * 76)
        ident = kwp.read_ecu_identification()
        part_num = ident.get("part_number", "Desconocido")
        comp = ident.get("component", "Desconocido")
        sw = ident.get("sw_version", "Desconocido")
        hw = ident.get("hw_version", "Desconocido")
        coding = ident.get("coding", "No disponible")

        print(f"  • Referencia SW:    {part_num}")
        print(f"  • Componente / Sis: {comp}")
        print(f"  • Versión SW:       {sw}")
        print(f"  • Versión HW:       {hw}")
        print(f"  • Codificación:     {coding}")

        if "EPB" in comp or "801" in part_num:
            print("\n  [NOTA FORENSE]")
            print("  La centralita que contesta en 0x19 se identifica como Freno de Mano EPB.")
        elif "GW" in comp or "468" in part_num:
            print("\n  [CONFIRMADO] Esta es la auténtica Pasarela Central CAN Gateway J533.")

        # 3. Lectura de DTCs (Códigos de avería de comunicación)
        print("\n" + "-" * 76)
        print("[PASO 3] Consultando Memoria de Averías del Bus (DTCs)...")
        print("-" * 76)
        dtcs = kwp.read_dtcs()
        if dtcs:
            print(f"  [!] Averías encontradas ({len(dtcs)}):")
            for d in dtcs:
                print(f"     → {d}")
        else:
            print("  [OK] No hay códigos de avería registrados (memoria limpia).")

        # 4. Lectura Exhaustiva de Bloques de Medición (MWB)
        print("\n" + "-" * 76)
        print("[PASO 4] LECTURA EXHAUSTIVA DE BLOQUES DE MEDICIÓN (MWB 1-6 y 125-135)...")
        print("-" * 76)

        bloques_a_escanear = list(range(1, 7)) + list(range(125, 136))
        exitosos = 0

        for num_bloque in bloques_a_escanear:
            desc = GRUPOS_GATEWAY_VAG.get(num_bloque, f"Grupo de Medición {num_bloque}")
            print(f"\n[*] Grupo {num_bloque:03d} (0x{num_bloque:02X}) — {desc}")
            try:
                # Servicio KWP2000 0x21: ReadDataByLocalIdentifier
                resp = kwp.execute_service(0x21, subfunction=num_bloque)
                if resp:
                    exitosos += 1
                    detalle = decodificar_bloque_mwb(num_bloque, resp)
                    print(f"    Respuesta Gateway:{detalle}")
            except Exception as e:
                print(f"    (Sin respuesta o grupo no equipado: {e})")
            time.sleep(0.06)

        print("\n" + "=" * 76)
        print(f" RESUMEN: {exitosos}/{len(bloques_a_escanear)} bloques de medición leídos con éxito.")
        print("=" * 76)

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
