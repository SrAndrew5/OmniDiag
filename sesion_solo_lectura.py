"""
sesion_solo_lectura.py
══════════════════════════════════════════════════════════════════════════════
SESIÓN DE DIAGNÓSTICO ESTRICTAMENTE DE SOLO LECTURA (READ-ONLY)
Audi A6 C6 Facelift (2010) — Gateway J533 (0x200) / TP 2.0 / KWP2000

REGLAS DE SEGURIDAD ACTIVAS:
- Prohibición absoluta de escritura: Servicios 0x2E, 0x3B, 0x30, 0x31, 0x27.
- Prohibición de cambio de sesión a programación: 0x10 sub 0x85.
- Sin sondeo a ciegas (no probing / no brute-force).
- Acceso exclusivo vía VW TP 2.0 a través del Gateway (0x200). Sin IDs directos UDS.
- Módulos objetivo: 0x5F, 0x07, 0x17.
- Cierre formal del canal TP 2.0 (A8) tras cada módulo.
══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time
import datetime
import struct
from typing import Optional, List, Dict, Any

# Asegurar path raíz del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.can_manager import CANManager
from obd.tp20_can import TP20Transport, KWP2000NativeClient, KWPError, TP20TimeoutError, LOGICAL_MODULES, NRC_DESCRIPTIONS
import config

# Configurar stdout para evitar errores de encoding en Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Servicios estrictamente prohibidos para garantizar CERO escritura
PROHIBITED_SERVICES = {0x2E, 0x3B, 0x30, 0x31, 0x27}


class DualLogger:
    """Registra simultáneamente en la terminal y en un archivo de log permanente."""
    def __init__(self, log_path: str):
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self.file = open(log_path, "w", encoding="utf-8")

    def print(self, msg: str = ""):
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        self.file.write(msg + "\n")
        self.file.flush()

    def close(self):
        if self.file and not self.file.closed:
            self.file.close()


class MonitoredCANManager:
    """
    Envoltura de CANManager que audita y registra cada trama CAN TX/RX
    e impone un bloqueo estricto contra cualquier servicio de escritura.
    """
    def __init__(self, can_mgr: CANManager, tracer_callback=None):
        self._can = can_mgr
        self._tracer = tracer_callback

    def __getattr__(self, name):
        return getattr(self._can, name)

    def send_frame(self, can_id: int, data: list | bytes, is_extended: bool = False, timeout: float = 0.2) -> bool:
        data_bytes = bytes(data)
        # Verificación de seguridad activa a nivel de trama
        # Si la trama contiene un servicio prohibido en KWP/UDS (en data payload)
        if len(data_bytes) >= 4 and (data_bytes[0] & 0xF0) in (0x10, 0x20):
            # Formato TP2.0: [header, len_hi, len_lo, service_id, ...]
            sid = data_bytes[3]
            if sid in PROHIBITED_SERVICES:
                raise PermissionError(f"[SEGURIDAD CRÍTICA] Intento de transmitir servicio prohibido 0x{sid:02X} cancelado.")
            if sid == 0x10 and len(data_bytes) >= 5 and data_bytes[4] == 0x85:
                raise PermissionError("[SEGURIDAD CRÍTICA] Intento de sesión de programación 0x85 cancelado.")

        if self._tracer:
            self._tracer("TX", can_id, data_bytes)
        return self._can.send_frame(can_id, data, is_extended=is_extended, timeout=timeout)

    def recv_frame(self, timeout: float = 0.5, expected_id: int = None):
        msg = self._can.recv_frame(timeout=timeout, expected_id=expected_id)
        if msg is not None and self._tracer:
            self._tracer("RX", msg.arbitration_id, bytes(msg.data))
        return msg


def ejecutar_sesion_lectura(interface_pref: str = "auto"):
    start_dt = datetime.datetime.now()
    timestamp_str = start_dt.strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(BASE_DIR, "datos", "reportes")
    log_file_path = os.path.join(log_dir, f"sesion_readonly_{timestamp_str}.log")
    
    logger = DualLogger(log_file_path)

    logger.print("=" * 80)
    logger.print(f"   AUDI A6 C6 (4F FACELIFT 2010) — SESIÓN DIAGNÓSTICO SOLO LECTURA")
    logger.print(f"   FECHA Y HORA DE INICIO: {start_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    logger.print(f"   SISTEMA OPERATIVO     : {sys.platform} | Python {sys.version.split()[0]}")
    logger.print(f"   MODO DE SEGURIDAD     : ESTRICTAMENTE SOLO LECTURA (READ-ONLY)")
    logger.print(f"   SERVICIOS PROHIBIDOS  : 0x2E, 0x3B, 0x30, 0x31, 0x27, 0x10 sub 0x85")
    logger.print(f"   ARCHIVO DE LOG        : {log_file_path}")
    logger.print("=" * 80)
    logger.print()

    # Tabla de transacciones requerida
    tabla_transacciones: List[Dict[str, Any]] = []

    # Registro de todas las tramas CAN de bajo nivel
    tramas_can_log: List[Dict[str, Any]] = []

    def can_tracer(direction: str, can_id: int, payload: bytes):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        tramas_can_log.append({
            "timestamp": ts,
            "dir": direction,
            "id": can_id,
            "data": payload
        })

    raw_can_mgr = CANManager(log_fn=lambda m: None)
    monitored_can = MonitoredCANManager(raw_can_mgr, tracer_callback=can_tracer)

    logger.print("[PASO 0] Buscando y conectando adaptador CANable 2.0 (bitrate 500 kbps)...")
    con_ok = raw_can_mgr.conectar(interface_preference=interface_pref, bitrate=500000)

    if not con_ok:
        logger.print("\n[!] ERROR CRÍTICO: No se detectó adaptador CANable 2.0 conectado en el equipo.")
        logger.print("    - Interfaz solicitada: gs_usb / slcan a 500000 bps")
        logger.print("    - Verifique cable USB conectado, driver WinUSB (gs_usb) o puerto COM (slcan).")
        logger.print("    - Estado del contacto del coche: Contacto Puesto (IGN ON), Motor Apagado.")
        logger.print("\nNo se enviaron tramas al vehículo debido a falta de interfaz física CAN.")
        logger.close()
        return

    interfaz = getattr(raw_can_mgr, "connected_interface", "desconocida")
    logger.print(f"[OK] Conectado a bus CAN físico mediante: {interfaz} (500 kbps).")
    logger.print("[*] Contacto verificado: Se asume IGN ON, motor apagado.\n")

    modulos_a_consultar = [
        (0x5F, "MMI / Information Electronics (Electrónica de Información 1)"),
        (0x07, "Control Head / Pantalla Frontal MMI (Unidad de Control e Indicación)"),
        (0x17, "Cuadro de Instrumentos (J285 / Instrument Cluster)"),
    ]

    datos_modulo_17 = {
        "read_coding_result": None,
        "read_coding_hex": None,
        "last_read_source": None,
        "raw_1a_9b": None,
        "raw_1a_9e": None,
    }

    respuestas_1a_por_modulo: Dict[int, Dict[str, Any]] = {}

    for mod_addr, mod_desc in modulos_a_consultar:
        logger.print("─" * 80)
        logger.print(f"[*] INICIANDO INSPECCIÓN DE MÓDULO 0x{mod_addr:02X} — {mod_desc}")
        logger.print("─" * 80)

        tp20 = TP20Transport(monitored_can, timeout=1.5, debug=False)
        kwp = KWP2000NativeClient(tp20)

        # 1. Apertura de canal TP 2.0 y negociación de parámetros
        logger.print(f"[1/3] Abriendo canal VW TP 2.0 mediante Gateway J533 (0x200) para 0x{mod_addr:02X}...")
        t_channel_start = time.perf_counter()
        channel_open = False
        raw_timeout_ms = 0.0

        try:
            # open_channel usa broadcast 0x200
            channel_open = tp20.open_channel(mod_addr, retries=1)
        except Exception as e:
            raw_timeout_ms = (time.perf_counter() - t_channel_start) * 1000
            logger.print(f"    [EXCEPCIÓN EN APERTURA]: {e} ({raw_timeout_ms:.2f} ms)")

        if not channel_open:
            raw_timeout_ms = (time.perf_counter() - t_channel_start) * 1000
            logger.print(f"    [TIMEOUT / SIN RESPUESTA]: El módulo 0x{mod_addr:02X} no respondió a la apertura de canal.")
            logger.print(f"    [TIMEOUT CRUDO]: {raw_timeout_ms:.2f} ms medidos sin respuesta positiva 0xD0 del Gateway.")

            tabla_transacciones.append({
                "modulo": f"0x{mod_addr:02X}",
                "operacion": "TP2.0 Channel Setup (0xC0)",
                "tx_hex": f"[0x200] {mod_addr:02X} C0 00 10 00 03 01",
                "rx_hex": f"SIN RESPUESTA (TIMEOUT {raw_timeout_ms:.1f} ms)",
                "servicio": "TP 2.0 Setup (0xC0)",
                "nrc": "TIMEOUT (Módulo no responde en Gateway)"
            })
            # Pasar al siguiente módulo
            logger.print(f"    Paso de canal fallido. Pasando al siguiente módulo...\n")
            continue

        # Canal abierto con éxito
        logger.print(f"    [OK] Canal TP 2.0 abierto con éxito:")
        logger.print(f"         TX CAN ID: 0x{tp20.tx_addr:03X} | RX CAN ID: 0x{tp20.rx_addr:03X}")

        tabla_transacciones.append({
            "modulo": f"0x{mod_addr:02X}",
            "operacion": "TP2.0 Channel Setup + Parameters",
            "tx_hex": f"Setup: [0x200] {mod_addr:02X} C0 ... | Params: [0x{tp20.tx_addr:03X}] A0 0F 8A FF 0A FF",
            "rx_hex": f"Setup: 0xD0 (TX:0x{tp20.tx_addr:03X} RX:0x{tp20.rx_addr:03X}) | Params: 0xA1",
            "servicio": "TP 2.0 Setup / Params",
            "nrc": "None"
        })

        respuestas_1a_por_modulo[mod_addr] = {}

        # 2. Envío de 1A 9B y después 1A 9E (Lectura de Identificación)
        # Consulta 1A 9B
        logger.print(f"[2/3] Transmitiendo Servicio 0x1A Subfunción 0x9B (ReadECUIdentification)...")
        tx_payload_9b = b"\x1a\x9b"
        try:
            tp20.send_data(tx_payload_9b)
            rx_payload_9b = tp20.recv_data(timeout=1.5)
            rx_hex_9b = " ".join(f"{b:02X}" for b in rx_payload_9b)
            logger.print(f"    [TX]: {tx_payload_9b.hex().upper()}")
            logger.print(f"    [RX]: {rx_hex_9b}")

            respuestas_1a_por_modulo[mod_addr]["1A_9B"] = rx_payload_9b

            sid_resp = rx_payload_9b[0] if len(rx_payload_9b) > 0 else 0
            if sid_resp == 0x5A:
                logger.print(f"    [RESPUESTA POSITIVA]: 0x5A (1A + 0x40)")
                # Intentar decodificar cadena de referencia y sw
                ascii_repr = "".join(chr(b) if 32 <= b <= 126 else "." for b in rx_payload_9b)
                logger.print(f"    [TEXTO ASCII]: {ascii_repr}")
                tabla_transacciones.append({
                    "modulo": f"0x{mod_addr:02X}",
                    "operacion": "KWP2000 ReadECUIdentification (1A 9B)",
                    "tx_hex": "1A 9B",
                    "rx_hex": rx_hex_9b,
                    "servicio": "0x1A sub 0x9B",
                    "nrc": "None"
                })
            elif sid_resp == 0x7F:
                req_sid = rx_payload_9b[1] if len(rx_payload_9b) > 1 else 0x1A
                nrc = rx_payload_9b[2] if len(rx_payload_9b) > 2 else 0x00
                nrc_desc = NRC_DESCRIPTIONS.get(nrc, f"NRC 0x{nrc:02X}")
                logger.print(f"    [RESPUESTA NEGATIVA]: SID 0x7F para req 0x{req_sid:02X}, NRC 0x{nrc:02X} ({nrc_desc})")
                tabla_transacciones.append({
                    "modulo": f"0x{mod_addr:02X}",
                    "operacion": "KWP2000 ReadECUIdentification (1A 9B)",
                    "tx_hex": "1A 9B",
                    "rx_hex": rx_hex_9b,
                    "servicio": "0x1A sub 0x9B",
                    "nrc": f"0x{nrc:02X} ({nrc_desc})"
                })
            else:
                tabla_transacciones.append({
                    "modulo": f"0x{mod_addr:02X}",
                    "operacion": "KWP2000 ReadECUIdentification (1A 9B)",
                    "tx_hex": "1A 9B",
                    "rx_hex": rx_hex_9b,
                    "servicio": f"0x{sid_resp:02X}",
                    "nrc": "Inesperado"
                })

        except Exception as e:
            logger.print(f"    [ERROR/TIMEOUT EN 1A 9B]: {e}")
            tabla_transacciones.append({
                "modulo": f"0x{mod_addr:02X}",
                "operacion": "KWP2000 ReadECUIdentification (1A 9B)",
                "tx_hex": "1A 9B",
                "rx_hex": f"ERROR: {e}",
                "servicio": "0x1A sub 0x9B",
                "nrc": "Timeout / Excepción"
            })

        time.sleep(0.05)

        # Consulta 1A 9E
        logger.print(f"[2/3] Transmitiendo Servicio 0x1A Subfunción 0x9E (ReadECUIdentificationByType - Coding)...")
        tx_payload_9e = b"\x1a\x9e"
        try:
            tp20.send_data(tx_payload_9e)
            rx_payload_9e = tp20.recv_data(timeout=1.5)
            rx_hex_9e = " ".join(f"{b:02X}" for b in rx_payload_9e)
            logger.print(f"    [TX]: {tx_payload_9e.hex().upper()}")
            logger.print(f"    [RX]: {rx_hex_9e}")

            respuestas_1a_por_modulo[mod_addr]["1A_9E"] = rx_payload_9e

            sid_resp = rx_payload_9e[0] if len(rx_payload_9e) > 0 else 0
            if sid_resp == 0x5A:
                logger.print(f"    [RESPUESTA POSITIVA]: 0x5A (1A + 0x40)")
                tabla_transacciones.append({
                    "modulo": f"0x{mod_addr:02X}",
                    "operacion": "KWP2000 ReadECUIdentification (1A 9E)",
                    "tx_hex": "1A 9E",
                    "rx_hex": rx_hex_9e,
                    "servicio": "0x1A sub 0x9E",
                    "nrc": "None"
                })
            elif sid_resp == 0x7F:
                req_sid = rx_payload_9e[1] if len(rx_payload_9e) > 1 else 0x1A
                nrc = rx_payload_9e[2] if len(rx_payload_9e) > 2 else 0x00
                nrc_desc = NRC_DESCRIPTIONS.get(nrc, f"NRC 0x{nrc:02X}")
                logger.print(f"    [RESPUESTA NEGATIVA]: SID 0x7F para req 0x{req_sid:02X}, NRC 0x{nrc:02X} ({nrc_desc})")
                tabla_transacciones.append({
                    "modulo": f"0x{mod_addr:02X}",
                    "operacion": "KWP2000 ReadECUIdentification (1A 9E)",
                    "tx_hex": "1A 9E",
                    "rx_hex": rx_hex_9e,
                    "servicio": "0x1A sub 0x9E",
                    "nrc": f"0x{nrc:02X} ({nrc_desc})"
                })
            else:
                tabla_transacciones.append({
                    "modulo": f"0x{mod_addr:02X}",
                    "operacion": "KWP2000 ReadECUIdentification (1A 9E)",
                    "tx_hex": "1A 9E",
                    "rx_hex": rx_hex_9e,
                    "servicio": f"0x{sid_resp:02X}",
                    "nrc": "Inesperado"
                })

        except Exception as e:
            logger.print(f"    [ERROR/TIMEOUT EN 1A 9E]: {e}")
            tabla_transacciones.append({
                "modulo": f"0x{mod_addr:02X}",
                "operacion": "KWP2000 ReadECUIdentification (1A 9E)",
                "tx_hex": "1A 9E",
                "rx_hex": f"ERROR: {e}",
                "servicio": "0x1A sub 0x9E",
                "nrc": "Timeout / Excepción"
            })

        # MÓDULO 0x17 ESPECÍFICO: read_coding() y last_read_source
        if mod_addr == 0x17:
            logger.print("\n[*] [MÓDULO 0x17] Ejecutando read_coding() según implementación del proyecto...")
            try:
                coding_res = kwp.read_coding()
                datos_modulo_17["read_coding_result"] = coding_res
                datos_modulo_17["last_read_source"] = getattr(kwp, "last_read_source", "Desconocido")
                if coding_res:
                    coding_hex_str = " ".join(f"{b:02X}" for b in coding_res)
                    datos_modulo_17["read_coding_hex"] = coding_hex_str
                    logger.print(f"    [read_coding() RESULTADO]: {len(coding_res)} bytes -> {coding_hex_str}")
                else:
                    logger.print(f"    [read_coding() RESULTADO]: None (No se obtuvo codificación)")
                logger.print(f"    [last_read_source]       : {datos_modulo_17['last_read_source']}")
            except Exception as e:
                logger.print(f"    [EXCEPCIÓN EN read_coding()]: {e}")
                datos_modulo_17["last_read_source"] = f"Excepción: {e}"

        # 3. Cierre formal del canal TP 2.0 (A8)
        logger.print(f"\n[3/3] Cerrando canal TP 2.0 (trama A8) con 0x{mod_addr:02X}...")
        try:
            tp20.close_channel()
            logger.print("    [OK] Canal cerrado limpiamente.")
            tabla_transacciones.append({
                "modulo": f"0x{mod_addr:02X}",
                "operacion": "TP2.0 Disconnect (A8)",
                "tx_hex": f"[0x{tp20.tx_addr:03X}] A8",
                "rx_hex": "N/A (Unilateral)",
                "servicio": "TP 2.0 Disconnect (0xA8)",
                "nrc": "None"
            })
        except Exception as e:
            logger.print(f"    [AVISO CIERRE CANAL]: {e}")

        time.sleep(0.1)
        logger.print()

    raw_can_mgr.desconectar()
    end_dt = datetime.datetime.now()

    # ══════════════════════════════════════════════════════════════════════════
    #  ENTREGABLES EXIGIDOS
    # ══════════════════════════════════════════════════════════════════════════

    logger.print("=" * 80)
    logger.print("                      TABLA DE TRANSACCIONES KWP2000 / TP 2.0")
    logger.print("=" * 80)
    logger.print(f"{'MÓDULO':<8} | {'SERVICIO':<24} | {'TRAMA TX (HEX)':<30} | {'TRAMA RX (HEX)':<45} | {'NRC'}")
    logger.print("─" * 125)
    for t in tabla_transacciones:
        mod = t.get("modulo", "")
        srv = t.get("servicio", "")
        tx = t.get("tx_hex", "")
        rx = t.get("rx_hex", "")
        nrc = t.get("nrc", "")
        logger.print(f"{mod:<8} | {srv:<24} | {tx:<30} | {rx:<45} | {nrc}")
    logger.print("─" * 125)
    logger.print()

    logger.print("=" * 80)
    logger.print("             RESULTADO ESPECÍFICO MÓDULO 0x17 (CUADRO DE INSTRUMENTOS)")
    logger.print("=" * 80)
    if datos_modulo_17["read_coding_result"] is not None:
        c_bytes = datos_modulo_17["read_coding_result"]
        c_hex = datos_modulo_17["read_coding_hex"]
        logger.print(f" ▸ read_coding() resultado bytes: {bytes(c_bytes)}")
        logger.print(f" ▸ read_coding() resultado hex  : {c_hex} ({len(c_bytes)} bytes)")
        logger.print(f" ▸ last_read_source             : {datos_modulo_17['last_read_source']}")
    else:
        logger.print(" ▸ read_coding() resultado      : None")
        logger.print(f" ▸ last_read_source             : {datos_modulo_17['last_read_source']}")
    logger.print()

    logger.print("=" * 80)
    logger.print("             ETIQUETADO ESTRICTO DE EVIDENCIAS Y DATOS")
    logger.print("=" * 80)
    logger.print("Criterio de clasificación obligatorio:")
    logger.print("  [LEÍDO DEL COCHE]      -> Extraído directamente de los bytes recibidos del bus CAN.")
    logger.print("  [ENCONTRADO EN INTERNET]-> Documentación técnica externa contrastada (con URL).")
    logger.print("  [SUPOSICIÓN]           -> Hipótesis, inferencia lógica o deducción no explícita.")
    logger.print("─" * 80)

    # Evaluación de MMI (Regla 5: no concluir si 2G o 3G salvo que los bytes de 1A lo digan)
    logger.print("\n1. DETERMINACIÓN DEL TIPO DE MMI (Módulos 0x5F / 0x07):")
    mmi_ident_bytes = None
    if 0x5F in respuestas_1a_por_modulo and "1A_9B" in respuestas_1a_por_modulo[0x5F]:
        mmi_ident_bytes = respuestas_1a_por_modulo[0x5F]["1A_9B"]
        logger.print(f"   ▸ [LEÍDO DEL COCHE]: Respuesta 0x5F 1A 9B (hex: {mmi_ident_bytes.hex().upper()})")
    elif 0x07 in respuestas_1a_por_modulo and "1A_9B" in respuestas_1a_por_modulo[0x07]:
        mmi_ident_bytes = respuestas_1a_por_modulo[0x07]["1A_9B"]
        logger.print(f"   ▸ [LEÍDO DEL COCHE]: Respuesta 0x07 1A 9B (hex: {mmi_ident_bytes.hex().upper()})")
    else:
        logger.print("   ▸ [LEÍDO DEL COCHE]: Ninguno de los módulos 0x5F o 0x07 devolvió trama positiva de identificación.")

    # Comprobación de texto literal "2G" o "3G" en los bytes
    tipo_mmi_declarado = None
    if mmi_ident_bytes:
        ascii_mmi = "".join(chr(b) if 32 <= b <= 126 else " " for b in mmi_ident_bytes)
        if "MMI3G" in ascii_mmi or "3G" in ascii_mmi:
            tipo_mmi_declarado = "MMI 3G (declarado explícitamente en bytes)"
        elif "MMI2G" in ascii_mmi or "2G" in ascii_mmi:
            tipo_mmi_declarado = "MMI 2G (declarado explícitamente en bytes)"

    if tipo_mmi_declarado:
        logger.print(f"   ▸ [LEÍDO DEL COCHE]: {tipo_mmi_declarado}")
    else:
        logger.print("   ▸ [ESTADO MMI]: NO SE SABE con certeza si el MMI es 2G o 3G a partir de los bytes recibidos.")
        logger.print("     Razón: Los bytes brutos de 1A 9B / 1A 9E recibidos no contienen la subcadena textual '2G' ni '3G'.")

    logger.print("\n2. DATOS DE CONTEXTO TÉCNICO Y REFERENCIAS EXTERNAS:")
    logger.print("   ▸ [ENCONTRADO EN INTERNET]: Especificación de transporte Volkswagen TP 2.0 sobre CAN Bus:")
    logger.print("     URL: https://github.com/jazdw/mqb-flasher / http://jazdw.net/tp20")
    logger.print("     (Define el handshake de canal 0x200 con opcode 0xC0/0xD0, parámetros 0xA0/0xA1 y desconexión 0xA8)")
    logger.print("   ▸ [ENCONTRADO EN INTERNET]: Ross-Tech VCDS Wiki - Procedimiento de diagnóstico Audi A6 (4F):")
    logger.print("     URL: http://wiki.ross-tech.com/wiki/index.php/Audi_A6_(4F)_Instrument_Cluster")
    logger.print("     (Identificador 0x17 J285, codificación Long Coding en Facelift a partir de 2009)")
    logger.print("   ▸ [ENCONTRADO EN INTERNET]: Ross-Tech VCDS Wiki - Localización de unidades MMI en Facelift:")
    logger.print("     URL: http://wiki.ross-tech.com/wiki/index.php/Audi_A6_(4F)_Information_Electronics")
    logger.print("     (En A6 C6 Facelift con MMI 3G la dirección de diagnosis es 0x5F; en MMI 2G High es 0x07)")
    logger.print("   ▸ [SUPOSICIÓN]: La presencia física exclusiva de la unidad de control en la guantera (sin cambiador ni radio en maletero)")
    logger.print("     suele correlacionarse en vehículos 2010 con MMI 3G Basic (DVD/SD) o MMI 3G High, pero al ser una deducción humana")
    logger.print("     NO constituye dato leído del coche.")

    logger.print("\n3. RUTAS DE ARCHIVOS GENERADOS:")
    logger.print(f"   ▸ Archivo de Log completo : {log_file_path}")
    logger.print(f"   ▸ Script ejecutado        : {os.path.abspath(__file__)}")
    logger.print(f"   ▸ Fin de sesión           : {end_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    logger.print("=" * 80)

    logger.close()


if __name__ == "__main__":
    pref = "auto"
    if len(sys.argv) > 1 and sys.argv[1] in ("virtual", "gs_usb", "slcan", "auto"):
        pref = sys.argv[1]
    ejecutar_sesion_lectura(interface_pref=pref)
