# obd/tp20_can.py
# ══════════════════════════════════════════════════════════════════════════════
# Implementación NATIVA de VW TP 2.0 y KWP2000 sobre python-can para CANable.
# Basado en la especificación de ingeniería inversa VAG (jazdw.net / pq-flasher)
# y optimizado para la plataforma Audi A6 C6 (4F Facelift).
# ══════════════════════════════════════════════════════════════════════════════

import time
import struct
import threading
from typing import Optional, List, Tuple
from core.can_manager import CANManager
from core.diagnostic_logger import diag_logger

BROADCAST_ADDR = 0x200


class TP20TimeoutError(TimeoutError):
    pass


class KWPError(Exception):
    def __init__(self, message, service_id=None, nrc=None):
        super().__init__(message)
        self.service_id = service_id
        self.nrc = nrc


# Mapeo de direcciones lógicas del Gateway J533 en Audi A6 C6
LOGICAL_MODULES = {
    0x01: "Motor (ECU)",
    0x02: "Transmisión",
    0x03: "ABS / ESP",
    0x08: "Climatización",
    0x09: "Central Eléctrica / Luces (J519)",
    0x15: "Airbag",
    0x17: "Cuadro Instrumentos (J285)",
    0x19: "Gateway CAN (J533)",
    0x46: "Confort / BCM (J393)",
    0x5F: "MMI / Infotainment",
}

NRC_DESCRIPTIONS = {
    0x10: "General Reject",
    0x11: "Servicio no soportado",
    0x12: "Subfunción no soportada / Formato inválido",
    0x21: "ECU ocupada - Repetir petición",
    0x22: "Condiciones no correctas",
    0x31: "Petición fuera de rango",
    0x33: "Acceso de seguridad denegado (Requiere Login)",
    0x35: "Clave de seguridad inválida",
    0x36: "Límite de intentos de seguridad excedido",
    0x78: "Petición aceptada - Respuesta pendiente",
}


class TP20Transport:
    """
    Capa de transporte VW TP 2.0 nativa sobre python-can.
    Abre y mantiene canales punto a punto a través del Gateway J533.
    """

    def __init__(self, can_mgr: CANManager, timeout: float = 0.8, debug: bool = False):
        self.can = can_mgr
        self.timeout = timeout
        self.debug = debug

        self.rx_addr = 0x300
        self.tx_addr = 0x000
        self.tx_seq = 0
        self.rx_seq = 0
        self.is_channel_open = False
        self.current_module = None

        self._keepalive_stop = threading.Event()
        self._keepalive_thread = None

    def _log(self, msg: str):
        if self.debug:
            print(f"[TP2.0] {msg}")
        diag_logger.log_info(f"[TP2.0] {msg}")

    def open_channel(self, module_addr: int, retries: int = 1) -> bool:
        """
        Abre un canal de diagnóstico con la centralita solicitada.
        Transmite al broadcast 0x200 y espera respuesta en 0x200 + module_addr o 0x200.
        Optimizado para evitar bloqueos del bus CAN y saturación de la pasarela J533.
        """
        self.close_channel()
        mod_name = LOGICAL_MODULES.get(module_addr, f"0x{module_addr:02X}")
        self._log(f"Abriendo canal TP 2.0 con {mod_name} (0x{module_addr:02X})...")

        # Módulos en buses secundarios (Kombi, Confort) requieren más tiempo para que el Gateway responda
        if module_addr in (0x17, 0x08, 0x09, 0x46, 0x5F, 0x53):
            timeout_to_use = 1.2
            max_attempts = max(retries + 1, 3)
        else:
            timeout_to_use = 0.45
            max_attempts = retries + 1

        for attempt in range(1, max_attempts + 1):
            self.can.flush_rx()

            # Probar payload estándar o alternativo según intento
            if attempt % 2 == 1:
                setup_payload = bytes([module_addr, 0xC0, 0x00, 0x10, 0x00, 0x03, 0x01])
            else:
                setup_payload = bytes([module_addr, 0xC0, 0x00, 0x03, 0x40, 0x07, 0x01])

            if not self.can.send_frame(BROADCAST_ADDR, setup_payload):
                self._log("Fallo al enviar trama de Channel Setup.")
                continue

            resp_id = BROADCAST_ADDR + module_addr
            msg = None
            start_wait = time.perf_counter()
            while (time.perf_counter() - start_wait) < timeout_to_use:
                rem = timeout_to_use - (time.perf_counter() - start_wait)
                if rem <= 0:
                    break
                m = self.can.recv_frame(timeout=min(0.08, rem), expected_id=None)
                if m and len(m.data) >= 7:
                    if m.arbitration_id in (resp_id, BROADCAST_ADDR):
                        if m.data[1] == 0xD0:
                            msg = m
                            break

            if not msg or len(msg.data) < 7:
                if attempt < max_attempts:
                    time.sleep(0.08)
                    continue
                self._log(f"Sin respuesta de Channel Setup desde 0x{resp_id:03X} para {mod_name}")
                return False

            status, rx, tx, _ = struct.unpack("<xBHHB", bytes(msg.data[:7]))
            if status != 0xD0:
                self._log(f"Gateway rechazó canal para {mod_name} (código {status:02X})")
                return False

            self.rx_addr = rx  # Normalmente 0x300
            self.tx_addr = tx  # ID CAN asignado por el módulo
            self.current_module = module_addr
            self._log(f"Canal asignado: TX -> 0x{self.tx_addr:03X} | RX <- 0x{self.rx_addr:03X}")
            break
        else:
            return False

        # Negociación de parámetros de tiempo (Parameters Request)
        param_req = b"\xa0\x0f\x8a\xff\x0a\xff"
        if not self.can.send_frame(self.tx_addr, param_req):
            self._log("Fallo al enviar Parameters Request.")
            return False

        param_resp = self.can.recv_frame(timeout=0.35, expected_id=self.rx_addr)
        if not param_resp or len(param_resp.data) < 1 or param_resp.data[0] != 0xA1:
            self._log("Fallo en negociación de parámetros TP 2.0")
            return False

        self.tx_seq = 0
        self.rx_seq = 0
        self.is_channel_open = True
        self._log(f"¡Canal TP 2.0 establecido con éxito con {mod_name}!")

        # Iniciar hilo de Keep-Alive para evitar que la sesión caduque
        self._start_keepalive()
        return True

    def _start_keepalive(self):
        """Inicia el envío periódico de keep-alives (0xA3) cada 1.5s en segundo plano."""
        self._keepalive_stop.clear()

        def loop():
            while not self._keepalive_stop.wait(1.5):
                if self.is_channel_open and self.tx_addr:
                    try:
                        self.can.send_frame(self.tx_addr, b"\xa3")
                    except Exception:
                        pass

        self._keepalive_thread = threading.Thread(target=loop, daemon=True)
        self._keepalive_thread.start()

    def close_channel(self):
        """Cierra el canal TP 2.0 y detiene el keep-alive."""
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_stop.set()
            self._keepalive_thread.join(timeout=0.3)

        if self.is_channel_open and self.tx_addr:
            try:
                # 0xA8 = Desconexión
                self.can.send_frame(self.tx_addr, b"\xa8")
                time.sleep(0.02)
            except Exception:
                pass

        self.is_channel_open = False
        self.current_module = None
        self.tx_seq = 0
        self.rx_seq = 0
        self.can.flush_rx()

    def wait_for_ack(self):
        """Espera el ACK con secuencia + 1."""
        expected_ack = 0xB0 | ((self.tx_seq + 1) & 0xF)
        msg = self.can.recv_frame(timeout=self.timeout, expected_id=self.rx_addr)
        if not msg or len(msg.data) == 0:
            raise TP20TimeoutError("Timeout esperando ACK de TP 2.0")
        if msg.data[0] != expected_ack:
            raise RuntimeError(f"ACK inválido: esperado {expected_ack:02X}, recibido {msg.data[0]:02X}")

    def send_ack(self):
        """Envía ACK al módulo."""
        ack_byte = 0xB0 | ((self.rx_seq + 1) & 0xF)
        self.can.send_frame(self.tx_addr, bytes([ack_byte]))

    def send_data(self, payload: bytes):
        """
        Envía un payload de datos KWP2000 dividiéndolo en tramas CAN de 8 bytes.
        """
        if not self.is_channel_open:
            raise RuntimeError("Canal TP 2.0 no abierto.")

        full_data = struct.pack(">H", len(payload)) + payload

        while full_data:
            last = len(full_data) <= 7
            header_byte = (0x10 if last else 0x20) | (self.tx_seq & 0xF)
            chunk = bytes([header_byte]) + full_data[:7]

            if not self.can.send_frame(self.tx_addr, chunk):
                raise RuntimeError("Error transmitiendo trama de datos TP 2.0")

            if last:
                self.wait_for_ack()

            self.tx_seq = (self.tx_seq + 1) & 0xF
            full_data = full_data[7:]

    def recv_data(self, timeout: float = 1.0) -> bytes:
        """
        Recibe tramas de datos del módulo y reconstruye el payload KWP2000 completo.
        """
        if not self.is_channel_open:
            raise RuntimeError("Canal TP 2.0 no abierto.")

        collected = bytearray()
        start = time.perf_counter()

        while (time.perf_counter() - start) < timeout:
            msg = self.can.recv_frame(timeout=0.3, expected_id=self.rx_addr)
            if not msg or len(msg.data) == 0:
                continue

            first_byte = msg.data[0]
            opcode = first_byte >> 4
            seq = first_byte & 0xF

            # Opcodes en TP2.0:
            # 0x1 = Último paquete de datos (0x10 | seq)
            # 0x2 = Paquete intermedio de datos (0x20 | seq)
            # 0xA = Parámetros / Keep-Alive (0xA1, 0xA3, 0xA8) -> Ignorar en flujo de datos
            # 0xB = ACK (0xB0 | seq) -> Ignorar en flujo de datos
            if opcode not in (0x1, 0x2):
                continue

            self.rx_seq = seq
            collected.extend(msg.data[1:])

            if opcode == 0x1:  # Último paquete
                self.send_ack()
                break

        if len(collected) < 2:
            raise TP20TimeoutError("Sin datos recibidos del módulo KWP.")

        length = struct.unpack(">H", collected[:2])[0]
        payload = bytes(collected[2:2 + length])
        return payload


class KWP2000NativeClient:
    """
    Cliente de diagnóstico KWP2000 de alto nivel ejecutándose sobre TP20Transport.
    Proporciona lectura/borrado de DTCs, identificación y Long Coding.
    """

    def __init__(self, transport: TP20Transport):
        self.transport = transport

    def execute_service(self, service_id: int, subfunction: Optional[int] = None, data: bytes = b"") -> bytes:
        """Ejecuta un servicio KWP2000 y valida la respuesta."""
        req = bytes([service_id])
        if subfunction is not None:
            req += bytes([subfunction])
        if data:
            req += data

        self.transport.send_data(req)
        resp = self.transport.recv_data()

        if not resp:
            raise KWPError("Respuesta vacía de la ECU")

        resp_sid = resp[0]

        # Respuesta negativa (0x7F)
        if resp_sid == 0x7F:
            req_sid = resp[1] if len(resp) > 1 else service_id
            nrc = resp[2] if len(resp) > 2 else 0x00
            desc = NRC_DESCRIPTIONS.get(nrc, f"Error desconocido 0x{nrc:02X}")
            raise KWPError(f"Respuesta Negativa (NRC 0x{nrc:02X}): {desc}", service_id=req_sid, nrc=nrc)

        # Respuesta positiva esperada: service_id + 0x40
        if resp_sid != (service_id + 0x40):
            raise KWPError(f"SID de respuesta inesperado: 0x{resp_sid:02X} (esperado 0x{service_id+0x40:02X})")

        return resp[1:]

    # ──────────────────────────────────────────────────────────────────────────
    #  SERVICIOS ESTÁNDAR KWP2000
    # ──────────────────────────────────────────────────────────────────────────
    def start_diagnostic_session(self, session_type: int = 0x86) -> bool:
        """
        Inicia sesión de diagnóstico con negociación inteligente y fallback.
        1. Si es Gateway (0x19), omite la sesión (no soportada).
        2. Prueba session_type (por defecto 0x86 - Engineering / VAG).
        3. Si la ECU responde NRC 0x12 / 0x11, prueba 0x89 y luego 0x01.
        4. Si ninguno es aceptado, continúa en sesión por defecto de la ECU sin fallar.
        """
        if self.transport.current_module == 0x19:
            # Gateway J533 opera directamente sin servicio 0x10
            return True

        sessions_to_try = [session_type]
        for s_cand in (0x03, 0x86, 0x89, 0x01):
            if s_cand not in sessions_to_try:
                sessions_to_try.append(s_cand)

        for s in sessions_to_try:
            try:
                self.execute_service(0x10, subfunction=s)
                diag_logger.log_info(f"[KWP] Sesión diagnóstica 0x{s:02X} aceptada.")
                return True
            except KWPError as e:
                # NRC 0x11, 0x12, 0x31, 0x33 (security/not supported), 0x22, 0x7E, 0x7F
                if e.nrc in (0x11, 0x12, 0x22, 0x31, 0x33, 0x7E, 0x7F):
                    continue
                else:
                    break
            except Exception:
                break

        # Si la centralita no requiere sesión especial, continúa en su sesión por defecto
        diag_logger.log_info("[KWP] Continuando en sesión estándar por defecto de la ECU.")
        return True

    def security_access(self, login_code: int) -> bool:
        """
        Realiza login con código fijo (ej: 13861 para Cuadro 17).
        """
        try:
            # Petición de login: Service 0x27, Sub 0x01
            # Para logins fijos VAG, se envían los 2 bytes del código
            login_bytes = struct.pack(">H", login_code)
            self.execute_service(0x27, subfunction=0x01, data=login_bytes)
            return True
        except Exception as e:
            diag_logger.log_error(f"Login {login_code} fallido", str(e))
            return False

    def read_ecu_identification(self) -> dict:
        """
        Lee identificación completa de la ECU según el estándar oficial VAG KWP2000 (Service 0x1A sub 0x9B / 0x91 / 0x80).
        Extrae: Número de referencia, versión de software, codificación (Coding / Long Coding) y nombre de componente.
        """
        for subfn in (0x9B, 0x91, 0x80):
            try:
                resp = self.execute_service(0x1A, subfunction=subfn)
                if not resp or len(resp) < 12:
                    continue
                part_number = resp[1:13].decode("latin1", errors="replace").strip()
                sw_version = resp[13:17].decode("latin1", errors="replace").strip() if len(resp) >= 17 else ""
                coding_bytes = b""
                component = ""
                if len(resp) >= 18:
                    coding_len = resp[17]
                    if 1 <= coding_len <= 32 and (18 + coding_len) <= len(resp):
                        coding_bytes = resp[18:18 + coding_len]
                        if len(resp) >= (18 + coding_len + 5):
                            component = resp[18 + coding_len + 5:].decode("latin1", errors="replace").strip()

                return {
                    "part_number": part_number,
                    "sw_version": sw_version,
                    "coding": bytes(coding_bytes),
                    "coding_hex": " ".join(f"{b:02X}" for b in coding_bytes),
                    "component": component,
                    "raw": resp.hex()
                }
            except Exception:
                continue
        return {"part_number": "Desconocido", "sw_version": "", "coding": b"", "coding_hex": "", "component": "", "raw": ""}

    def read_dtcs(self) -> List[str]:
        """
        Lee códigos de avería almacenados.
        Prueba en orden los servicios VAG KWP2000:
        1. Service 0x13 (ReadDiagnosticTroubleCodesByStatus / All DTCs) -> 13 FF FF
        2. Service 0x13 con máscara 13 FF 00
        3. Service 0x18 sin subfunción -> 18 FF FF
        4. Service 0x18 sub 0x02 -> 18 02 FF
        """
        resp = None
        attempts = [
            (0x18, None, b"\x00\xff\x00"),
            (0x18, None, b"\x00\x00\x00"),
            (0x18, None, b"\x00\xff"),
            (0x13, None, b"\xff\xff"),
            (0x13, None, b"\xff\x00"),
            (0x18, None, b"\xff\xff"),
            (0x18, 0x02, b"\xff"),
        ]

        for sid, subfn, data in attempts:
            try:
                resp = self.execute_service(sid, subfunction=subfn, data=data)
                if resp is not None and len(resp) >= 2:
                    break
            except Exception:
                continue

        if resp is None or len(resp) < 2:
            return []

        dtcs = []
        # En Service 0x13 VAG, a menudo resp[0] es la cantidad de fallos reportados
        offset = 0
        if len(resp) >= 4 and (len(resp) - 1) % 3 == 0:
            offset = 1
        elif len(resp) % 3 == 0:
            offset = 0
        else:
            offset = 0

        for i in range(offset, len(resp) - 2, 3):
            b1 = resp[i]
            b2 = resp[i + 1]
            status = resp[i + 2]
            if b1 == 0 and b2 == 0:
                continue
            vag_num = (b1 << 8) | b2
            dtc_hex = f"{b1:02X}{b2:02X}"

            # Decodificación SAE J2012 estándar
            prefix_map = {0: "P", 1: "C", 2: "B", 3: "U"}
            prefix = prefix_map.get((b1 >> 6) & 0x03, "P")
            d1 = (b1 >> 4) & 0x03
            d2 = b1 & 0x0F
            d3 = (b2 >> 4) & 0x0F
            d4 = b2 & 0x0F
            sae_code = f"{prefix}{d1}{d2:X}{d3:X}{d4:X}"

            # Estado KWP2000:
            # 0x20 / bit 5 = Esporádico / Intermitente (histórico grabado en memoria)
            # Otros bits = Permanente / Presente
            if status & 0x20:
                estado_kwp = "HISTÓRICO / ESPORÁDICO"
            elif status == 0x00 or (status & 0x01):
                estado_kwp = "ACTIVO / PRESENTE"
            else:
                estado_kwp = "GUARDADO EN MEMORIA"

            # Para motor y caja de cambios (01 y 02) el estándar Ross-Tech VCDS prioriza el código SAE (Pxxxx).
            # Para el resto de módulos (luces 09, confort 46, abs 03, cuadro 17...) se prioriza el código VAG de 5 dígitos (ej. 01496, 00985).
            mod_actual = getattr(self.transport, "current_module", None)
            if mod_actual in (0x01, 0x02):
                cod_display = sae_code
            else:
                cod_display = f"{vag_num:05d}"

            dtcs.append(f"{cod_display} [{estado_kwp}] (VAG {vag_num:05d} / {sae_code}, Status 0x{status:02X})")

        return dtcs

    def read_odometer(self) -> Optional[int]:
        """
        Lee el odómetro en KWP2000 mediante bloques de medición (Service 0x21)
        o lectura por identificador (Service 0x22).
        Utiliza el escalador nativo VAG 0x24: km = (a * 2560) + (b * 10)
        y escalador 0x21: km = (a * 256) + b, descartando lecturas no formateadas.
        """
        # 1. Probar bloques de medición estándar (Grupo 002 Cuadro, Grupo 001, Grupo 003)
        for local_id in (0x02, 0x01, 0x03):
            try:
                resp = self.execute_service(0x21, subfunction=local_id)
                if not resp or len(resp) < 4:
                    continue

                # resp[0] es el eco de la subfunción.
                # Los 4 campos VAG KWP2000 están en resp[1:] en bloques de 3 bytes: [scaler, a, b]
                data = resp[1:]
                for idx in range(0, len(data) - 2, 3):
                    scaler = data[idx]
                    a = data[idx + 1]
                    b = data[idx + 2]

                    # Escalador oficial VAG 0x24: Kilómetros (Fórmula Ross-Tech / VAG: km = a*2560 + b*10)
                    if scaler == 0x24:
                        km = (a * 2560) + (b * 10)
                        if 1000 <= km <= 999999:
                            diag_logger.log_info(f"[KWP] Odómetro detectado por escalador 0x24 en bloque 0x{local_id:02X}: {km} km")
                            return km

            except Exception:
                continue

        # 2. Probar lectura por Identificador UDS/KWP (Service 0x22 DID 0x02BD / 0xF1A5 / 0x0009)
        for did in (0x02BD, 0xF1A5, 0x0009):
            try:
                resp = self.execute_service(0x22, data=bytes([did >> 8, did & 0xFF]))
                if resp and len(resp) >= 5:
                    did_data = resp[2:] if len(resp) >= 5 else resp
                    if len(did_data) >= 3:
                        if len(did_data) >= 4:
                            val = struct.unpack(">I", did_data[:4])[0]
                        else:
                            val = (did_data[0] << 16) | (did_data[1] << 8) | did_data[2]
                        if 1000 <= val <= 999999:
                            diag_logger.log_info(f"[KWP] Odómetro detectado por DID 0x{did:04X}: {val} km")
                            return val
            except Exception:
                continue

        return None

    def read_freeze_frame(self, b1: int, b2: int, frame_idx: int = 0) -> dict:
        """
        Lee la instantánea / Freeze Frame de una avería DTC (Service 0x12).
        Extrae los kilómetros congelados al producirse el fallo usando el escalador oficial 0x24.
        """
        ff_data = {"km": None, "raw": ""}
        for sub in (frame_idx, 0x00, 0x01):
            try:
                resp = self.execute_service(0x12, data=bytes([b1, b2, sub]))
                if not resp or len(resp) < 4:
                    continue

                ff_data["raw"] = resp.hex()

                # Buscar estrictamente el escalador 0x24 en el freeze frame
                for idx in range(0, len(resp) - 2):
                    if resp[idx] == 0x24:
                        a = resp[idx + 1]
                        b = resp[idx + 2]
                        km = (a * 2560) + (b * 10)
                        if 1000 <= km <= 999999:
                            ff_data["km"] = km
                            return ff_data

                return ff_data
            except Exception:
                continue
        return ff_data

    def clear_dtcs(self) -> bool:
        """
        Borra todos los fallos almacenados (Service 0x14).
        Prueba formatos estándar VAG:
        1. 14 FF 00
        2. 14 FF FF
        3. 14
        """
        attempts = [
            (0x14, None, b"\xff\x00"),
            (0x14, 0xFF, b"\xff\xff"),
            (0x14, None, b""),
        ]
        for sid, subfn, data in attempts:
            try:
                self.execute_service(sid, subfunction=subfn, data=data)
                diag_logger.log_info("[KWP] Memoria de averías borrada exitosamente.")
                return True
            except Exception:
                continue

        diag_logger.log_error("Fallo borrando DTCs KWP", "Ningún servicio 0x14 aceptado")
        return False

    def read_coding(self) -> Optional[bytes]:
        """
        Lee el Coding / Long Coding del módulo activo mediante el estándar oficial VAG KWP2000 (Ross-Tech VCDS):
        1. Servicio 0x1A con subfunción 0x9E (ReadECUIdentificationByType - Coding).
        2. Servicio 0x1A con subfunción 0x9B (Identification general).
        3. Identificador UDS/KWP (Service 0x22 DID 0x0600 / 0x0601 / 0xF1A0).
        """
        for subfn in (0x9E, 0x9B, 0x80, 0x91):
            try:
                resp = self.execute_service(0x1A, subfunction=subfn)
                if resp:
                    if subfn == 0x9E:
                        coding = resp[1:] if (len(resp) > 1 and resp[0] == 0x9E) else resp
                        if len(coding) >= 1:
                            diag_logger.log_info(f"[KWP] Codificación leída vía 0x1A 0x9E ({len(coding)} bytes): {coding.hex()}")
                            return bytes(coding)

                    elif len(resp) >= 18:
                        coding_len = resp[17]
                        if 1 <= coding_len <= 32 and (18 + coding_len) <= len(resp):
                            coding_bytes = resp[18:18 + coding_len]
                            diag_logger.log_info(f"[KWP] Codificación leída ({coding_len} bytes) en 0x1A 0x{subfn:02X}: {coding_bytes.hex()}")
                            return bytes(coding_bytes)
            except Exception:
                continue

        # Fallback a lectura por identificador UDS / KWP si estuviese disponible
        for did in (0x0600, 0x0601, 0xF1A0):
            try:
                resp = self.execute_service(0x22, subfunction=None, data=bytes([did >> 8, did & 0xFF]))
                if resp and len(resp) >= 2:
                    data = resp[2:] if len(resp) >= 4 else resp
                    return bytes(data)
            except Exception:
                continue

        return None

    def write_coding(self, coding_bytes: bytes) -> bool:
        """
        Escribe la codificación en el módulo mediante el servicio estándar VAG KWP2000:
        Service 0x3B (WriteDataByLocalIdentifier) subfunción 0x9E (Coding).
        """
        for subfn in (0x9E, 0x00):
            try:
                resp = self.execute_service(0x3B, subfunction=subfn, data=coding_bytes)
                if resp is not None:
                    diag_logger.log_info(f"[KWP] Codificación escrita correctamente con Service 0x3B sub 0x{subfn:02X}.")
                    return True
            except Exception as e:
                diag_logger.log_info(f"[KWP] Intento 0x3B sub 0x{subfn:02X} falló: {e}")
                continue

        diag_logger.log_error("Fallo escribiendo coding KWP", "Ninguna subfunción de Service 0x3B fue aceptada por la centralita")
        return False

