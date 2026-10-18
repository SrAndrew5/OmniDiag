#!/usr/bin/env python3
"""
SONDEO TP 2.0 CRUDO — SOLO LECTURA.

Qué envía (y nada más):
  1) Channel Setup (opcode 0xC0) al broadcast 0x200, con la trama estándar.
  2) Disconnect (0xA8) SOLO si el módulo abre canal (respuesta 0xD0).
No envía ningún servicio KWP2000 (nada de 0x10, 0x1A, 0x22, 0x27, 0x2E, 0x3B...).

Qué hace: muestra TODAS las tramas CAN que llegan mientras espera, no solo las del
ID esperado. Así se ve si el módulo calla del todo, si rechaza (0xD6..0xD8) o si
contesta por otro ID.

Uso (desde la raíz del proyecto):
    python PRUEBAS/sondeo_tp20_crudo.py                  # auto, 2 pasadas
    python PRUEBAS/sondeo_tp20_crudo.py gs_usb           # gs_usb real, 2 pasadas
    python PRUEBAS/sondeo_tp20_crudo.py gs_usb 3         # gs_usb real, 3 pasadas
    python PRUEBAS/sondeo_tp20_crudo.py 2 virtual        # simulación, sin coche
"""
import sys
import time
from collections import Counter
from datetime import datetime
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

BROADCAST = 0x200
SETUP_STD = [0xC0, 0x00, 0x10, 0x00, 0x03, 0x01]  # trama estándar de la especificación TP 2.0
LISTEN_PASIVO_S = 3.0
VENTANA_S = 1.5
PAUSA_ENTRE_MODULOS_S = 0.5
MAX_TRAMAS_MOSTRADAS = 12

# Controles (motor, ABS) incluidos a propósito: si ellos contestan y el cuadro no,
# el problema es del cuadro y no del cable ni del gateway.
OBJETIVOS = [
    (0x17, "Cuadro de instrumentos"),
    (0x46, "Confort"),
    (0x42, "Puerta conductor"),
    (0x52, "Puerta copiloto"),
    (0x07, "MMI (07)"),
    (0x5F, "MMI/Info (5F)"),
    (0x01, "Motor (control)"),
    (0x03, "ABS (control)"),
    (0x19, "Gateway J533 (control)"),
    (0x09, "Electrónica central (control)"),
    (0x08, "Climatizador (control)"),
    (0x15, "Airbag (control)"),
]

_salida = []


def out(txt=""):
    print(txt)
    _salida.append(txt)


def hexs(data):
    return " ".join(f"{b:02X}" for b in data)


def escucha_pasiva(cm):
    out(f"\n[A] Escucha pasiva {LISTEN_PASIVO_S:.0f} s (sin enviar nada)...")
    cuenta, ultimo = Counter(), {}
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < LISTEN_PASIVO_S:
        m = cm.recv_frame(timeout=0.05)
        if m is not None:
            cuenta[m.arbitration_id] += 1
            ultimo[m.arbitration_id] = bytes(m.data)
    if not cuenta:
        out("    Ninguna trama. Es normal en el CAN de diagnóstico: suele estar en silencio "
            "hasta que alguien pregunta.")
        return
    for cid, n in sorted(cuenta.items()):
        out(f"    ID 0x{cid:03X}: {n} tramas | última: {hexs(ultimo[cid])}")


def sondea(cm, addr, nombre):
    out(f"\n[0x{addr:02X}] {nombre}")
    cm.flush_rx()
    cm.send_frame(BROADCAST, bytes([addr] + SETUP_STD))
    esperado = BROADCAST + addr
    vistas, resultado = [], "SILENCIO (ninguna trama en la ventana)"
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < VENTANA_S:
        m = cm.recv_frame(timeout=0.05)
        if m is None:
            continue
        d = bytes(m.data)
        vistas.append((m.arbitration_id, d))
        if m.arbitration_id == esperado and len(d) >= 2:
            if d[1] == 0xD0 and len(d) >= 6:
                rx_id = ((d[3] & 0x0F) << 8) | d[2]
                tx_id = ((d[5] & 0x0F) << 8) | d[4]
                resultado = (f"CANAL ABIERTO (0xD0): tester transmite en 0x{tx_id:03X}, "
                             f"recibe en 0x{rx_id:03X}")
                cm.send_frame(tx_id, bytes([0xA8]))  # desconectar de inmediato
                cm.recv_frame(timeout=0.2)
                break
            if 0xD6 <= d[1] <= 0xD8:
                resultado = f"RECHAZO del módulo (opcode 0x{d[1]:02X}, respuesta negativa de setup)"
                break
            resultado = f"RESPUESTA EXTRAÑA en 0x{esperado:03X}: {hexs(d)}"
            break
    if resultado.startswith("SILENCIO") and vistas:
        resultado = (f"SIN RESPUESTA en 0x{esperado:03X} (pero SÍ hay otras tramas en el bus: "
                     f"mira la lista de abajo)")
    out(f"    TX 0x200: {hexs(bytes([addr] + SETUP_STD))}")
    out(f"    Resultado: {resultado}")
    if vistas:
        out(f"    Tramas vistas en la ventana: {len(vistas)}")
        for cid, d in vistas[:MAX_TRAMAS_MOSTRADAS]:
            marca = "  <-- ID esperado" if cid == esperado else ""
            out(f"       0x{cid:03X}: {hexs(d)}{marca}")
        if len(vistas) > MAX_TRAMAS_MOSTRADAS:
            out(f"       ... y {len(vistas) - MAX_TRAMAS_MOSTRADAS} más")
    else:
        out("    Tramas vistas en la ventana: 0")
    return resultado.split(" ")[0]


def main():
    pasadas = 2
    interfaz = "auto"
    for arg in sys.argv[1:]:
        if arg.isdigit():
            pasadas = int(arg)
        elif arg.lower() in ("virtual", "gs_usb", "slcan", "auto"):
            interfaz = arg.lower()

    out("=" * 70)
    out(f" SONDEO TP 2.0 CRUDO (SOLO LECTURA) — {datetime.now():%Y-%m-%d %H:%M:%S}")
    out("=" * 70)
    out(" Antes de lanzar: cuadro ENCENDIDO con sus testigos, puertas cerradas, motor apagado.")

    cm = CANManager(log_fn=lambda s: None)
    if not cm.conectar(interface_preference=interfaz, bitrate=500000):
        out("[!] No se pudo conectar con el adaptador. Revisa el cable USB y que ninguna otra app lo use.")
        return
    out(f"[OK] Conectado vía {cm.connected_interface}")

    try:
        escucha_pasiva(cm)
        resumen = {}
        for p in range(1, pasadas + 1):
            out(f"\n{'-' * 70}\n PASADA {p}/{pasadas}\n{'-' * 70}")
            for addr, nombre in OBJETIVOS:
                r = sondea(cm, addr, nombre)
                resumen.setdefault((addr, nombre), []).append(r)
                time.sleep(PAUSA_ENTRE_MODULOS_S)

        out(f"\n{'=' * 70}\n RESUMEN\n{'=' * 70}")
        for (addr, nombre), rs in resumen.items():
            out(f"  0x{addr:02X} {nombre:<24} -> {', '.join(rs)}")
    finally:
        cm.desconectar()

    carpeta = ROOT / "datos" / "reportes"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"sondeo_tp20_{datetime.now():%Y%m%d_%H%M%S}.txt"
    ruta.write_text("\n".join(_salida), encoding="utf-8")
    out(f"\nGuardado en: {ruta}")


if __name__ == "__main__":
    main()
