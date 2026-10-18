"""
PRUEBAS/comprobar_longcoding_retrovisores_y_cuadro.py
══════════════════════════════════════════════════════════════════════════════
Script de diagnóstico y lectura forense de Long Coding (100% SOLO LECTURA).

IMPORTANTE — TODOS los módulos se interrogan por VW TP 2.0 / KWP2000
a través de la Gateway J533:
  - 0x17 Cuadro J285  → VW TP 2.0 / KWP2000
  - 0x46 Confort J393 → VW TP 2.0 / KWP2000
  - 0x42 Puerta Conductor J386 → VW TP 2.0 / KWP2000
  - 0x52 Puerta Copiloto J387   → VW TP 2.0 / KWP2000

Nota: El Cuadro 17 del A6 C6 (4F) NO responde por UDS ISO-TP directo
(0x714/0x77E); eso es de plataformas posteriores (A4 B8 / A6 C7). En el C6
se alcanza por TP 2.0 con dirección lógica 0x17, igual que el resto.

Inspecciona:
  - 0x17: Needle Sweep / Staging (Byte 1 Bit 0) y Lap Timer (Bit 3)
  - 0x46: lógica de plegado con mando (Byte 4 Bits 4/6)
  - 0x42/0x52: motor de plegado presente (Byte 4 Bits 4/6)

Uso:
    python PRUEBAS/comprobar_longcoding_retrovisores_y_cuadro.py
    python PRUEBAS/comprobar_longcoding_retrovisores_y_cuadro.py gs_usb
    python PRUEBAS/comprobar_longcoding_retrovisores_y_cuadro.py gs_usb reintentar
    python PRUEBAS/comprobar_longcoding_retrovisores_y_cuadro.py gs_usb monitor
    python PRUEBAS/comprobar_longcoding_retrovisores_y_cuadro.py gs_usb scan
══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time
import logging
import datetime

# Configurar stdout para evitar errores de codificación en consolas Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Asegurar que Python encuentra los módulos del proyecto raíz
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.can_manager import CANManager
from obd.tp20_can import TP20Transport, KWP2000NativeClient, KWPError

# ── CONFIGURACIÓN DEL LOGGER ──────────────────────────────────────────────
log_dir = os.path.join(BASE_DIR, "datos", "reportes")
os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = os.path.join(log_dir, f"diagnostico_coding_{timestamp}.log")

logger = logging.getLogger("DiagnosticoCoding")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Archivo de log permanente: recibe TODO, incluido el nivel DEBUG (tramas CAN)
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Consola en tiempo real: solo INFO o superior, para que sea legible
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# ── MÓDULOS (todos por VW TP 2.0 / KWP2000 vía Gateway J533) ───────────────
MODULOS_TP20 = {
    0x17: "Cuadro de Instrumentos J285 (17)",
    0x46: "Centralita de Confort J393 (46)",
    0x42: "Puerta Conductor J386 (42)",
    0x52: "Puerta Copiloto J387 (52)",
}


# ── CLASE WRAPPER PARA INTERCEPTAR TRÁFICO TP 2.0 ──────────────────────────
class LoggedKWPClient(KWP2000NativeClient):
    """Hereda de KWP2000NativeClient para interceptar y registrar todo el tráfico."""

    def execute_service(self, service_id: int, subfunction: int = None, data: bytes = b"") -> bytes:
        req_hex = f"{service_id:02X}"
        if subfunction is not None:
            req_hex += f" {subfunction:02X}"
        if data:
            req_hex += " " + " ".join(f"{b:02X}" for b in data)

        logger.info(f"  [TX -> ECU] Enviando: {req_hex}")

        try:
            resp = super().execute_service(service_id, subfunction, data)
            resp_hex = f"{service_id + 0x40:02X} " + " ".join(f"{b:02X}" for b in resp)
            logger.info(f"  [RX <- ECU] Recibido: {resp_hex}")
            return resp
        except Exception as e:
            logger.error(f"  [RX <- ECU] ERROR: {str(e)}")
            raise e


# ── ANÁLISIS DEL CODING SEGÚN MÓDULO ──────────────────────────────────────
def analizar_coding(addr: int, coding: bytes) -> None:
    """Decodifica los bits relevantes del Long Coding de cada centralita."""
    coding_bytes = list(coding)
    coding_hex = " ".join(f"{b:02X}" for b in coding_bytes)
    logger.info(f"  ✅ Coding leído con éxito ({len(coding_bytes)} bytes): {coding_hex}")

    # MÓDULO 17: CUADRO DE INSTRUMENTOS
    if addr == 0x17 and len(coding_bytes) > 1:
        b1 = coding_bytes[1]
        logger.info(f"  🔍 [Cuadro 17] Byte 1: 0x{b1:02X} (Binario: {b1:08b})")
        logger.info(f"     - Bit 0 (Needle Sweep / Barrido de agujas): "
                    f"{'[ACTIVO]' if (b1 & (1 << 0)) else '[DESACTIVADO]'}")
        logger.info(f"     - Bit 3 (Lap Timer / Cronómetro FIS)     : "
                    f"{'[ACTIVO]' if (b1 & (1 << 3)) else '[DESACTIVADO]'}")

    # MÓDULO 46: CONFORT
    elif addr == 0x46:
        if len(coding_bytes) > 7:
            b7 = coding_bytes[7]
            logger.info(f"  🔍 [Confort 46] Byte 7: 0x{b7:02X} (Binario: {b7:08b})")
            logger.info(f"     - Bit 7 (Espejos plegables instalados) : "
                        f"{'[ACTIVO]' if (b7 & (1 << 7)) else '[DESACTIVADO]'}")
        if len(coding_bytes) > 4:
            b4 = coding_bytes[4]
            logger.info(f"  🔍 [Confort 46] Byte 4: 0x{b4:02X} (Binario: {b4:08b})")
            logger.info(f"     - Bit 4 (Plegar al cerrar con mando)   : "
                        f"{'[ACTIVO]' if (b4 & (1 << 4)) else '[DESACTIVADO]'}")
            logger.info(f"     - Bit 6 (Desplegar al abrir con mando) : "
                        f"{'[ACTIVO]' if (b4 & (1 << 6)) else '[DESACTIVADO]'}")

    # MÓDULOS 42 Y 52: PUERTAS CONDUCTOR Y COPILOTO
    elif addr in (0x42, 0x52) and len(coding_bytes) > 4:
        b4 = coding_bytes[4]
        logger.info(f"  🔍 [Puerta 0x{addr:02X}] Byte 4: 0x{b4:02X} (Binario: {b4:08b})")
        logger.info(f"     - Bit 4 (Foldable Mirrors Installed)  : "
                    f"{'[ACTIVO]' if (b4 & (1 << 4)) else '[DESACTIVADO]'}")
        logger.info(f"     - Bit 6 (Comfort Mirror Folding Active): "
                    f"{'[ACTIVO]' if (b4 & (1 << 6)) else '[DESACTIVADO]'}")


# ── LECTURA DE VOLTAJE DE BATERÍA (OBD-II PID 0x42) ───────────────────────
def leer_voltaje_bateria(can_mgr: CANManager) -> float:
    """
    Lee el voltaje de control del módulo (PID 0x42) vía petición funcional OBD-II
    (0x7DF -> 0x7E8). Devuelve el voltaje en V o None si no responde.
    """
    try:
        can_mgr.flush_rx()
        req = bytes([0x02, 0x01, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00])
        can_mgr.send_frame(0x7DF, req)
        t0 = time.perf_counter()
        while (time.perf_counter() - t0) < 1.5:
            m = can_mgr.recv_frame(timeout=0.2, expected_id=0x7E8)
            if m and len(m.data) >= 5 and m.data[1] == 0x41 and m.data[2] == 0x42:
                return (m.data[3] * 256 + m.data[4]) / 1000.0
        return None
    except Exception:
        return None


# ── LECTURA TP 2.0 (Cuadro 17, Confort 46, Puertas 42/52) ──────────────────
def escanear_modulo_tp20(tp20: TP20Transport, kwp: LoggedKWPClient,
                         addr: int, nombre: str) -> dict:
    resultado = {"addr": addr, "nombre": nombre, "canal": False,
                 "coding": None, "fuente": None, "error": None}

    logger.info(f"\n{'─' * 60}")
    logger.info(f"[*] ESCANEANDO: {nombre} (0x{addr:02X}) [TP 2.0]")
    logger.info(f"{'─' * 60}")

    t_start = time.perf_counter()
    try:
        abierto = tp20.open_channel(addr, retries=2)
    except Exception as e:
        abierto = False
        tp20.last_setup_error = f"Excepción abriendo el canal: {e}"

    elapsed_ms = (time.perf_counter() - t_start) * 1000

    if not abierto:
        resultado["error"] = tp20.last_setup_error or "sin respuesta al Channel Setup"
        logger.error(f"  ❌ Sin respuesta del módulo 0x{addr:02X} (Timeout {elapsed_ms:.1f} ms).")
        logger.error(f"     Motivo: {resultado['error']}")
        return resultado

    resultado["canal"] = True
    logger.info(f"  ✅ Canal TP 2.0 abierto (TX 0x{tp20.tx_addr:03X} / "
                f"RX 0x{tp20.rx_addr:03X}) en {elapsed_ms:.0f} ms")

    try:
        kwp.start_diagnostic_session(0x86)
        if kwp.last_session is not None:
            logger.info(f"  ℹ️ Sesión de diagnóstico: 0x{kwp.last_session:02X}")
        time.sleep(0.08)

        coding = kwp.read_coding()
        if coding:
            resultado["coding"] = coding
            resultado["fuente"] = kwp.last_read_source
            analizar_coding(addr, coding)
            logger.info(f"  ℹ️ Fuente de lectura: {kwp.last_read_source}")
        else:
            resultado["error"] = kwp.last_read_error or "sin datos"
            logger.warning(f"  ⚠️ No se pudo leer la codificación del módulo 0x{addr:02X}.")
            logger.warning(f"     Detalle: {resultado['error']}")
    except KWPError as e:
        resultado["error"] = str(e)
        logger.error(f"  ❌ Error KWP2000 procesando módulo 0x{addr:02X}: {e}")
    except Exception as e:
        resultado["error"] = str(e)
        logger.error(f"  ❌ Excepción procesando módulo 0x{addr:02X}: {e}")
    finally:
        tp20.close_channel()
        time.sleep(0.15)

    return resultado


# ── DIAGNÓSTICO DEL GATEWAY J533 (0x19) ───────────────────────────────────
def diagnosticar_gateway(tp20: TP20Transport, kwp: LoggedKWPClient) -> None:
    """
    Abre canal con el Gateway (0x19), lee su identificación y sus DTCs.
    Si el gateway tiene averías "sin comunicación con J285/J393/J386", confirma
    que esos módulos están offline en el bus (fallo de hardware/cableado), no
    un problema de protocolo.
    """
    logger.info(f"\n{'─' * 60}")
    logger.info("[*] DIAGNÓSTICO DEL GATEWAY J533 (0x19) [TP 2.0]")
    logger.info(f"{'─' * 60}")

    if not tp20.open_channel(0x19, retries=2):
        logger.warning("  ⚠️ El Gateway 0x19 no responde al Channel Setup TP 2.0.")
        logger.warning("     (algunos gateways no aceptan auto-direccionamiento)")
        return

    logger.info(f"  ✅ Canal abierto con Gateway (TX 0x{tp20.tx_addr:03X} / RX 0x{tp20.rx_addr:03X})")
    try:
        ident = kwp.read_ecu_identification()
        part = ident.get("part_number", "")
        if part and part != "Desconocido":
            logger.info(f"  📋 Referencia Gateway: {part}")

        dtcs = kwp.read_dtcs()
        if dtcs:
            logger.info(f"  🔴 DTCs del Gateway ({len(dtcs)}):")
            for d in dtcs:
                logger.info(f"     → {d}")
        else:
            logger.info("  🟢 Gateway sin DTCs de comunicación (o no soporta su lectura).")
    except Exception as e:
        logger.error(f"  ❌ Error leyendo el Gateway: {e}")
    finally:
        tp20.close_channel()
        time.sleep(0.15)


# ── MODO MONITOR: comprobar si el coche está despierto ────────────────────
def monitor_bus(can_mgr: CANManager, duracion: float = 5.0) -> None:
    logger.info("=" * 70)
    logger.info(" MODO MONITOR: ESCUCHA PASIVA DEL BUS DE DIAGNÓSTICO")
    logger.info("=" * 70)
    logger.info(f"Escuchando {duracion:.0f} s SIN transmitir nada al coche...")

    conteo = {}
    total = 0
    t0 = time.perf_counter()
    while (time.perf_counter() - t0) < duracion:
        m = can_mgr.recv_frame(timeout=0.1)
        if m is None:
            continue
        total += 1
        conteo[m.arbitration_id] = conteo.get(m.arbitration_id, 0) + 1

    fps = total / duracion
    logger.info(f"  Tramas recibidas: {total} ({fps:.1f}/s)")
    if conteo:
        top = sorted(conteo.items(), key=lambda kv: -kv[1])[:12]
        logger.info("  IDs detectados: " + ", ".join(f"0x{i:03X}×{n}" for i, n in top))

    if total == 0:
        logger.warning("  ⚠️ Bus en silencio durante la escucha pasiva (normal en algunos VAG:")
        logger.warning("     el CAN de diagnóstico sólo habla cuando se le pregunta).")
    else:
        logger.info("  ✅ Bus VIVO: el coche está despierto y el adaptador ve el tráfico real.")

    logger.info("")
    logger.info("Comprobando el Gateway J533 (0x19) por TP 2.0...")
    tp = TP20Transport(can_mgr, timeout=1.0,
                       progress_fn=lambda m: logger.info(f"   {m}"))
    if tp.open_channel(0x19, retries=1):
        logger.info("  ✅ Gateway 0x19 responde: el bus de diagnóstico y la pasarela funcionan.")
        tp.close_channel()
    else:
        logger.warning("  ⚠️ Gateway 0x19 no responde al Channel Setup TP 2.0.")
    logger.info("")


# ── MODO SCAN: qué direcciones lógicas contesta el Gateway ────────────────
def escanear_direcciones(can_mgr: CANManager) -> None:
    direcciones = [
        (0x01, "Motor"), (0x02, "Transmisión"), (0x03, "ABS / ESP"),
        (0x08, "Climatización"), (0x09, "Central eléctrica (J519)"),
        (0x15, "Airbag"), (0x17, "Cuadro (J285)"), (0x19, "Gateway (J533)"),
        (0x42, "Puerta conductor (J386)"), (0x46, "Confort (J393)"),
        (0x52, "Puerta copiloto (J387)"), (0x5F, "MMI"),
    ]
    logger.info("=" * 70)
    logger.info(" MODO SCAN: DIRECCIONES LÓGICAS QUE RESPONDEN AL GATEWAY (TP 2.0)")
    logger.info("=" * 70)
    logger.info(" Nota: todos los módulos se alcanzan por TP 2.0 a través de la Gateway.")

    tp = TP20Transport(can_mgr, timeout=0.8)
    encontrados = []
    for addr, nombre in direcciones:
        try:
            can_mgr.flush_rx()
        except Exception:
            pass
        ok = tp.open_channel(addr, attempts=1, setup_timeout=1.2)
        if ok:
            logger.info(f"  ✅ 0x{addr:02X}  {nombre}  "
                        f"(TX 0x{tp.tx_addr:03X} / RX 0x{tp.rx_addr:03X})")
            encontrados.append(addr)
            tp.close_channel()
        else:
            logger.info(f"  —   0x{addr:02X}  {nombre}: sin respuesta TP 2.0")
        time.sleep(0.08)

    logger.info("")
    logger.info(f"  Responden por TP 2.0 {len(encontrados)}/{len(direcciones)}: "
                + ", ".join(f"0x{a:02X}" for a in encontrados))
    logger.info("")


# ── SCRIPT PRINCIPAL ──────────────────────────────────────────────────────
def main():
    logger.info("=" * 70)
    logger.info(" INICIANDO ESCANEO DE LONG CODING (MODO ESTRICTO SOLO LECTURA)")
    logger.info(f" Archivo de Log: {log_filename}")
    logger.info("=" * 70)

    # 1. Conexión con CANable 2.0
    can_mgr = CANManager(log_fn=lambda m: None)
    logger.info("[1/2] Conectando con adaptador CANable 2.0 (500 kbps)...")

    pref = "auto"
    if len(sys.argv) > 1 and sys.argv[1] in ("virtual", "gs_usb", "slcan", "auto"):
        pref = sys.argv[1]

    if not can_mgr.conectar(interface_preference=pref, bitrate=500000):
        logger.error("❌ No se detectó ningún adaptador CANable conectado.")
        logger.error("   Verifica: cable USB enchufado, driver WinUSB/gs_usb y contacto del coche puesto.")
        return

    interfaz = getattr(can_mgr, "connected_interface", "desconocida")
    logger.info(f"✅ Conectado exitosamente vía {interfaz} (500 kbps).")
    logger.info("ℹ️ Recuerda: contacto en Posición II con el CUADRO ILUMINADO y puerta cerrada.\n")

    # Modo monitor: solo escuchar el bus
    if "monitor" in sys.argv:
        monitor_bus(can_mgr)
        can_mgr.desconectar()
        return

    # Modo scan: qué direcciones lógicas rutea el Gateway por TP 2.0
    if "scan" in sys.argv:
        escanear_direcciones(can_mgr)
        can_mgr.desconectar()
        return

    # Comprobar voltaje de batería: por debajo de ~12 V el BEM/J644 duerme el
    # bus Confort (Load Shedding) y los módulos de confort no responden.
    volt = leer_voltaje_bateria(can_mgr)
    if volt is not None:
        logger.info(f"[1.5/2] Voltaje de batería (PID 0x42): {volt:.2f} V")
        if volt < 12.0:
            logger.warning("  ⚠️ BATERÍA BAJA: el BEM/J644 está haciendo Load Shedding y")
            logger.warning("     duerme ramas del bus Confort (Confort 46, puertas...).")
            logger.warning("     Conecta un cargador/mantenedor de batería y vuelve a intentar.")
        else:
            logger.info("  ✅ Voltaje correcto para diagnóstico.")
    else:
        logger.info("[1.5/2] No se pudo leer el voltaje de batería por OBD (continúa).")
    logger.info("")

    # 2. Transporte TP 2.0 (para Cuadro 17, Confort 46 y puertas 42/52)
    tp20 = TP20Transport(
        can_mgr,
        timeout=1.2,
        trace_fn=lambda m: logger.debug(f"   {m}"),
        progress_fn=lambda m: logger.info(f"   {m}"),
    )
    kwp = LoggedKWPClient(tp20)

    # 2.b Diagnóstico del Gateway J533: identificación + DTCs (para saber si
    #     J285/J393/J386 están realmente offline en el bus).
    diagnosticar_gateway(tp20, kwp)

    resultados = []

    # 3. Módulos TP 2.0 (Cuadro 17, Confort 46, Puertas 42/52)
    for addr, nombre in MODULOS_TP20.items():
        try:
            can_mgr.flush_rx()
        except Exception:
            pass
        resultados.append(escanear_modulo_tp20(tp20, kwp, addr, nombre))

    # 5. Segunda pasada opcional (solo TP 2.0 y solo con "reintentar")
    if "reintentar" in sys.argv:
        pendientes = [r for r in resultados if not r["coding"] and r["addr"] in MODULOS_TP20]
        if pendientes:
            logger.info("\n[↻] SEGUNDA PASADA solicitada para módulos TP 2.0 sin coding...")
            for r in pendientes:
                nuevo = escanear_modulo_tp20(tp20, kwp, r["addr"], r["nombre"])
                if nuevo["coding"]:
                    r.update(nuevo)
    else:
        logger.info("\n(Para reintentar los módulos que fallaron, añade el argumento: reintentar)\n")

    can_mgr.desconectar()

    # 6. Resumen final
    logger.info("\n" + "=" * 70)
    logger.info(" RESUMEN DEL ESCANEO")
    logger.info("=" * 70)
    for r in resultados:
        if r["coding"]:
            estado = "OK"
            detalle = f"{len(r['coding'])} bytes vía {r['fuente']}"
        else:
            estado = "SIN CODING"
            detalle = r["error"] or ""
        logger.info(f"  0x{r['addr']:02X}  {estado:<10}  {r['nombre']}")
        if detalle:
            logger.info(f"        └─ {detalle}")

    leidos = sum(1 for r in resultados if r["coding"])
    logger.info("")
    logger.info(f"  Coding leído: {leidos}/{len(resultados)} módulos")
    logger.info("\n" + "=" * 70)
    logger.info(" ESCANEO FINALIZADO.")
    logger.info(f" Log completo guardado en: {log_filename}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
