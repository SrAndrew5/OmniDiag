# obd/isotp_uds.py
# ══════════════════════════════════════════════════════════════════════════════
# Implementación nativa de transporte ISO-TP (ISO 15765-2) y cliente de diagnóstico
# UDS (ISO 14229) para centralitas del Grupo VAG (Audi A6 C6 Facelift / 4F).
# Permite comunicación punto a punto con centralitas en sus IDs CAN dedicados
# a través del Gateway J533 (Cuadro 17, Luces 09, Confort 46, Clima 08, Airbag 15).
# ══════════════════════════════════════════════════════════════════════════════

import time
import struct
from typing import Optional, Dict, List, Tuple
from core.can_manager import CANManager
from core.diagnostic_logger import diag_logger

# ──────────────────────────────────────────────────────────────────────────────
#  MAPEO DE DIRECCIONES CAN UDS VERIFICADAS PARA GRUPO VAG (AUDI A6 C6 FACELIFT)
#  En Audi A6 C6, la inmensa mayoría de módulos operan mediante VW TP 2.0 vía Gateway J533.
#  Solo módulos UDS nativos confirmados (como Airbag 15 en 4F Facelift) usan ISO-TP directo.
#  NUNCA emitir tramas ciegas a IDs no existentes para evitar estados CAN BUS-OFF y fallos de ESP.
# ──────────────────────────────────────────────────────────────────────────────
VAG_UDS_MODULES = {
    "Cuadro Instrumentos (17)": {"tx_id": 0x714, "rx_id": 0x77E, "nombre": "Cuadro Instrumentos / J285"},
    "Airbag (15)": {"tx_id": 0x715, "rx_id": 0x77F, "nombre": "Airbag / J234"},
    "MMI 3G (5F)": {"tx_id": 0x770, "rx_id": 0x7DA, "nombre": "Información Electrónica / J794 (MMI 3G)"},
    "Pantalla / MMI (5F)": {"tx_id": 0x770, "rx_id": 0x7DA, "nombre": "Información Electrónica / J794 (MMI 3G)"},
}

UDS_NRC_DESCRIPTIONS = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x72: "generalProgrammingFailure",
    0x78: "requestCorrectlyReceived-ResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}


class UDSError(Exception):
    def __init__(self, message: str, service_id: int = 0, nrc: int = 0):
        super().__init__(message)
        self.service_id = service_id
        self.nrc = nrc


class ISOTPClient:
    """
    Cliente de transporte ISO 15765-2 (ISO-TP) nativo sobre CANManager.
    Soporta tramas Single Frame (SF), First Frame (FF), Flow Control (FC) y Consecutive Frames (CF).
    """

    def __init__(self, can_mgr: CANManager, tx_id: int, rx_id: int, timeout: float = 0.8):
        self.can = can_mgr
        self.tx_id = tx_id
        self.rx_id = rx_id
        self.timeout = timeout

    def send_and_recv(self, payload: bytes, timeout: Optional[float] = None) -> bytes:
        """
        Envía un mensaje ISO-TP y espera la respuesta completa.
        """
        if hasattr(self.can, "flush_rx"):
            self.can.flush_rx()
        self.send(payload)
        return self.recv(timeout or self.timeout)

    def send(self, payload: bytes):
        """
        Transmite un payload de datos segmentándolo según ISO-TP.
        """
        p_len = len(payload)
        if p_len == 0:
            return

        # 1. Single Frame (SF): hasta 7 bytes
        if p_len <= 7:
            frame = bytes([p_len]) + payload
            # Rellenar a 8 bytes con 0x00 para tramas fijas CAN de diagnóstico
            frame = frame + b"\x00" * (8 - len(frame))
            if not self.can.send_frame(self.tx_id, frame):
                raise RuntimeError(f"Fallo enviando trama SF ISO-TP a 0x{self.tx_id:03X}")
            return

        # 2. Multi-frame: First Frame (FF)
        ff_header = struct.pack(">H", 0x1000 | (p_len & 0x0FFF))
        ff_frame = ff_header + payload[:6]
        if not self.can.send_frame(self.tx_id, ff_frame):
            raise RuntimeError(f"Fallo enviando First Frame ISO-TP a 0x{self.tx_id:03X}")

        # Esperar Flow Control (FC)
        fc_msg = self.can.recv_frame(timeout=0.6, expected_id=self.rx_id)
        if not fc_msg or len(fc_msg.data) < 3 or (fc_msg.data[0] >> 4) != 0x3:
            raise RuntimeError("Fallo recibiendo Flow Control de la ECU")

        fc_status = fc_msg.data[0] & 0x0F
        if fc_status != 0:  # 0 = CTS (Clear To Send)
            raise RuntimeError(f"ECU no está lista para recibir (FC status={fc_status})")

        block_size = fc_msg.data[1]
        st_min_raw = fc_msg.data[2]
        st_min_sec = (st_min_raw / 1000.0) if st_min_raw <= 0x7F else 0.005

        # Enviar Consecutive Frames (CF)
        remaining = payload[6:]
        seq = 1
        bs_count = 0

        while remaining:
            chunk = remaining[:7]
            cf_byte = 0x20 | (seq & 0x0F)
            cf_frame = bytes([cf_byte]) + chunk
            cf_frame = cf_frame + b"\x00" * (8 - len(cf_frame))

            if not self.can.send_frame(self.tx_id, cf_frame):
                raise RuntimeError("Fallo enviando Consecutive Frame ISO-TP")

            remaining = remaining[7:]
            seq = (seq + 1) & 0x0F
            bs_count += 1

            if block_size > 0 and bs_count >= block_size and remaining:
                # Esperar siguiente FC
                fc_msg = self.can.recv_frame(timeout=0.5, expected_id=self.rx_id)
                if not fc_msg or (fc_msg.data[0] >> 4) != 0x3:
                    raise RuntimeError("Timeout esperando Flow Control intermedio")
                bs_count = 0

            if st_min_sec > 0:
                time.sleep(st_min_sec)

    def recv(self, timeout: float = 0.8) -> bytes:
        """
        Recibe un mensaje ISO-TP completo (SF o FF+CFs) de la ECU.
        """
        start = time.perf_counter()
        collected = bytearray()
        total_len = 0
        expected_seq = 1

        while (time.perf_counter() - start) < timeout:
            msg = self.can.recv_frame(timeout=0.25, expected_id=self.rx_id)
            if not msg or len(msg.data) == 0:
                continue

            frame_type = msg.data[0] >> 4

            # Single Frame (SF)
            if frame_type == 0x0:
                sf_len = msg.data[0] & 0x0F
                if sf_len == 0:
                    continue
                return bytes(msg.data[1:1 + sf_len])

            # First Frame (FF)
            elif frame_type == 0x1:
                total_len = ((msg.data[0] & 0x0F) << 8) | msg.data[1]
                collected = bytearray(msg.data[2:])
                expected_seq = 1

                # Enviar Flow Control (CTS, BlockSize=0, STmin=0)
                fc_frame = bytes([0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                self.can.send_frame(self.tx_id, fc_frame)

                # Reset timeout para recepción de bloques
                start = time.perf_counter()

            # Consecutive Frame (CF)
            elif frame_type == 0x2:
                seq = msg.data[0] & 0x0F
                if seq != expected_seq:
                    diag_logger.log_info(f"[ISO-TP] Desajuste de secuencia: esperado {expected_seq}, recibido {seq}")
                expected_seq = (seq + 1) & 0x0F
                collected.extend(msg.data[1:])

                if len(collected) >= total_len:
                    return bytes(collected[:total_len])

            # Flow Control recibido inesperadamente
            elif frame_type == 0x3:
                continue

        if collected and total_len > 0 and len(collected) >= total_len:
            return bytes(collected[:total_len])

        raise TimeoutError(f"Timeout ISO-TP esperando respuesta de 0x{self.rx_id:03X}")


class UDSClient:
    """
    Cliente de diagnóstico UDS (ISO 14229) de alto nivel ejecutándose sobre ISOTPClient.
    """

    def __init__(self, isotp: ISOTPClient):
        self.isotp = isotp

    def execute_service(self, service_id: int, subfunction: Optional[int] = None, data: bytes = b"", timeout: float = 1.0) -> bytes:
        """
        Ejecuta un servicio UDS y valida la respuesta.
        Maneja NRC 0x78 (ResponsePending).
        """
        req = bytes([service_id])
        if subfunction is not None:
            req += bytes([subfunction])
        if data:
            req += data

        resp = self.isotp.send_and_recv(req, timeout=timeout)

        # Bucle para manejar ResponsePending (NRC 0x78)
        start_wait = time.perf_counter()
        while len(resp) >= 3 and resp[0] == 0x7F and resp[2] == 0x78 and (time.perf_counter() - start_wait) < 3.0:
            diag_logger.log_info("[UDS] ECU ocupada (ResponsePending 0x78), esperando respuesta final...")
            try:
                resp = self.isotp.recv(timeout=1.5)
            except TimeoutError:
                break

        if not resp:
            raise UDSError("Respuesta vacía de la ECU")

        # Respuesta negativa
        if resp[0] == 0x7F:
            req_sid = resp[1] if len(resp) > 1 else service_id
            nrc = resp[2] if len(resp) > 2 else 0x00
            desc = UDS_NRC_DESCRIPTIONS.get(nrc, f"NRC desconocido 0x{nrc:02X}")
            raise UDSError(f"UDS Negativo (NRC 0x{nrc:02X}): {desc}", service_id=req_sid, nrc=nrc)

        # Respuesta positiva esperada: service_id + 0x40
        if resp[0] != (service_id + 0x40):
            raise UDSError(f"SID inesperado: 0x{resp[0]:02X} (esperado 0x{service_id+0x40:02X})")

        return resp[1:]

    def diagnostic_session_control(self, session_type: int = 0x03) -> bool:
        """
        Cambia la sesión de diagnóstico (0x01=Default, 0x02=Programming, 0x03=Extended).
        """
        for s in (session_type, 0x03, 0x01):
            try:
                self.execute_service(0x10, subfunction=s)
                diag_logger.log_info(f"[UDS] Sesión diagnóstica 0x{s:02X} aceptada.")
                return True
            except UDSError as e:
                if e.nrc in (0x12, 0x11, 0x31):
                    continue
                break
            except Exception:
                break
        return False

    def security_access(self, login_code: int = 13861) -> bool:
        """
        Realiza acceso de seguridad (Service 0x27).
        Para VAG login fijo (ej: 13861 en Cuadro 17): se envía el código empaquetado.
        """
        code_bytes = struct.pack(">H", login_code)
        # Probar envío directo de clave fija si el cuadro lo acepta
        for subfn in (0x01, 0x11):
            try:
                self.execute_service(0x27, subfunction=subfn, data=code_bytes)
                diag_logger.log_info(f"[UDS] Login 0x{login_code:04X} aceptado.")
                return True
            except UDSError as e:
                if e.nrc in (0x35, 0x12, 0x31):
                    continue
                break
            except Exception:
                pass
        return False

    def read_data_by_identifier(self, did: int) -> bytes:
        """
        Lee datos por identificador (Service 0x22).
        Devuelve el contenido del DID sin el encabezado DID.
        """
        did_bytes = struct.pack(">H", did)
        resp = self.execute_service(0x22, data=did_bytes)
        # La respuesta positiva contiene los 2 bytes del DID seguidos del valor
        if len(resp) >= 2 and resp[:2] == did_bytes:
            return resp[2:]
        return resp

    def write_data_by_identifier(self, did: int, data: bytes) -> bool:
        """
        Escribe datos por identificador (Service 0x2E).
        """
        did_bytes = struct.pack(">H", did)
        payload = did_bytes + data
        try:
            self.execute_service(0x2E, data=payload)
            return True
        except Exception as e:
            diag_logger.log_error(f"Fallo escribiendo DID 0x{did:04X}", str(e))
            return False

    def read_ecu_identification(self) -> dict:
        """
        Lee información de identificación de la centralita UDS:
        - 0xF187: Número de pieza de repuesto VAG (ej: 4F0920933P)
        - 0xF189: Versión de software VAG
        - 0xF190: Bastidor (VIN)
        - 0xF191: Número de pieza de hardware VAG
        """
        info = {"part_number": "Desconocido", "sw_version": "", "vin": "", "hw_number": ""}

        # 1. Part Number VAG (DID 0xF187)
        try:
            raw = self.read_data_by_identifier(0xF187)
            part_num = raw.decode("ascii", errors="replace").strip().replace("\x00", "")
            if part_num:
                info["part_number"] = part_num
        except Exception:
            pass

        # Si 0xF187 falló, probar 0xF189 o 0xF191
        if info["part_number"] == "Desconocido":
            try:
                raw = self.read_data_by_identifier(0xF191)
                part_num = raw.decode("ascii", errors="replace").strip().replace("\x00", "")
                if part_num:
                    info["part_number"] = part_num
            except Exception:
                pass

        # 2. SW Version (DID 0xF189)
        try:
            raw = self.read_data_by_identifier(0xF189)
            info["sw_version"] = raw.decode("ascii", errors="replace").strip().replace("\x00", "")
        except Exception:
            pass

        # 3. VIN (DID 0xF190)
        try:
            raw = self.read_data_by_identifier(0xF190)
            vin = raw.decode("ascii", errors="replace").strip()
            if len(vin) == 17:
                info["vin"] = vin
        except Exception:
            pass

        return info

    def read_coding(self) -> Optional[bytes]:
        """
        Lee la codificación larga (Long Coding) de la centralita UDS.
        En el Grupo VAG, el Long Coding se almacena normalmente en el DID 0x0600, 0x0601 o 0xF18C.
        """
        try:
            self.diagnostic_session_control(0x03)
            time.sleep(0.04)
        except Exception:
            pass

        for did in (0x0600, 0x0601, 0xF18C, 0xF1A0):
            try:
                coding = self.read_data_by_identifier(did)
                if coding and len(coding) >= 2:
                    return coding
            except Exception:
                continue
        return None

    def write_coding(self, new_coding: bytes) -> bool:
        """
        Escribe la nueva codificación larga (Long Coding) en el DID 0x0600.
        """
        # Asegurar sesión de diagnóstico extendida antes de escribir
        self.diagnostic_session_control(0x03)
        time.sleep(0.05)

        for did in (0x0600, 0x0601):
            if self.write_data_by_identifier(did, new_coding):
                return True
        return False

    def read_dtcs(self) -> List[str]:
        """
        Lee los códigos de error almacenados (Service 0x19 subfunction 0x02 - ReportDTCByStatusMask).
        Cumple estrictamente con la especificación ISO 14229 / Ross-Tech VCDS:
        1. Consulta con máscara de fallos reales (0x09: testFailed | confirmedDTC, o 0x2F).
        2. Descarta registros que no representen fallos activos o confirmados (ej. status 0x10 testNotCompleted).
        3. Decodifica el código SAE J2012 (Pxxxx, Bxxxx, Cxxxx, Uxxxx) y el byte de subtipo/fallo FTB.
        """
        dtcs = []
        try:
            # Probar primero máscara 0x09 (fallos confirmados y activos) y luego 0x2F
            resp = None
            for mask in (b"\x09", b"\x2f", b"\xff"):
                try:
                    resp = self.execute_service(0x19, subfunction=0x02, data=mask)
                    if resp and len(resp) >= 2:
                        break
                except Exception:
                    continue

            if not resp or len(resp) < 2:
                return []

            records = resp[2:]
            record_len = 4
            if len(records) % record_len != 0:
                if len(records) % 3 == 0:
                    record_len = 3

            prefix_map = {0: "P", 1: "C", 2: "B", 3: "U"}

            for i in range(0, len(records) - (record_len - 1), record_len):
                b1 = records[i]
                b2 = records[i + 1]
                b3 = records[i + 2] if record_len >= 3 else 0
                status = records[i + 3] if record_len >= 4 else b3

                if b1 == 0 and b2 == 0:
                    continue

                # FILTRO CRÍTICO VCDS / ISO 14229:
                # Un registro SOLO es una avería si tiene al menos uno de los bits de fallo:
                # Bit 0: testFailed (0x01)
                # Bit 2: pendingDTC (0x04)
                # Bit 3: confirmedDTC (0x08)
                # Bit 5: testFailedSinceLastClear (0x20)
                # Los bits 4 (0x10 testNotCompletedSinceLastClear) y 6 (0x40) NO indican avería.
                if not (status & 0x2D):
                    continue

                vag_num = (b1 << 8) | b2

                # Decodificación SAE J2012 estándar
                prefix = prefix_map.get((b1 >> 6) & 0x03, "B")
                d1 = (b1 >> 4) & 0x03
                d2 = b1 & 0x0F
                d3 = (b2 >> 4) & 0x0F
                d4 = b2 & 0x0F
                ftb_str = f"-{b3:02X}" if b3 != 0 else ""
                sae_code = f"{prefix}{d1}{d2:X}{d3:X}{d4:X}{ftb_str}"

                # Decodificación del estado de avería UDS
                if status & 0x01:
                    estado_txt = "ACTIVO / PRESENTE"
                elif status & 0x08:
                    estado_txt = "GUARDADO EN MEMORIA (Confirmado)"
                elif status & 0x20:
                    estado_txt = "HISTÓRICO / ESPORÁDICO"
                elif status & 0x04:
                    estado_txt = "PENDIENTE"
                else:
                    estado_txt = "ALMACENADO EN MEMORIA"

                dtcs.append(f"{sae_code} [{estado_txt}] (VAG {vag_num:05d}, Status 0x{status:02X})")

        except Exception as e:
            diag_logger.log_error("Fallo leyendo DTCs UDS", str(e))

        return dtcs

    def read_odometer(self) -> Optional[int]:
        """
        Intenta leer los kilómetros reales almacenados en la centralita mediante DIDs estándar VAG:
        - 0x02BD: Odometer (3 o 4 bytes en km)
        - 0x2203: Odómetro alternativo VAG
        - 0x295B: Odometer EEPROM / cluster
        - 0x01BD: Distance
        - 0x0182: Vehicle distance
        Devuelve el valor en km (entero) o None si no está soportado.
        """
        for did in (0x02BD, 0x2203, 0x295B, 0x01BD, 0x0182):
            try:
                data = self.read_data_by_identifier(did)
                if data and len(data) >= 3:
                    # En VAG, normalmente son 3 bytes (ej: 0x03 0xA9 0x80 = 240.000) o 4 bytes
                    if len(data) == 3:
                        val = (data[0] << 16) | (data[1] << 8) | data[2]
                    else:
                        val = struct.unpack(">I", data[:4])[0]

                    # Rango plausible de kilometraje para un coche: 1.000 a 1.500.000 km
                    if 1000 <= val <= 1500000:
                        return val
                    # En algunos casos viene en metros o décimas de km
                    if 10000 <= (val // 1000) <= 1500000:
                        return val // 1000
                    if 10000 <= (val // 10) <= 1500000:
                        return val // 10
            except Exception:
                continue
        return None

    def read_freeze_frame(self, b1: int, b2: int, b3: int = 0) -> Optional[dict]:
        """
        Lee el Freeze Frame (instantánea con kilometraje) de una avería específica
        mediante Service 0x19 subfunction 0x04 (ReportDTCSnapshotRecordByDTCNumber).
        """
        try:
            req_data = bytes([b1, b2, b3, 0xFF])
            resp = self.execute_service(0x19, subfunction=0x04, data=req_data)
            if not resp or len(resp) < 6:
                return None

            ff_data = {"km": None, "raw": resp.hex()}

            # Buscar dentro del snapshot si viene el DID 0x02BD (3 bytes de km)
            # o buscar secuencia de 3 bytes que corresponda a kilometraje coherente
            for j in range(len(resp) - 4):
                if resp[j] == 0x02 and resp[j+1] == 0xBD:
                    km_val = (resp[j+2] << 16) | (resp[j+3] << 8) | resp[j+4]
                    if 1000 <= km_val <= 1500000:
                        ff_data["km"] = km_val
                        break

            return ff_data
        except Exception:
            return None

    def clear_dtcs(self) -> bool:
        """
        Borra la memoria de averías (Service 0x14 - ClearDiagnosticInformation).
        0x14 0xFF 0xFF 0xFF = todos los grupos de DTCs.
        """
        try:
            self.execute_service(0x14, data=b"\xff\xff\xff")
            diag_logger.log_info("[UDS] Averías borradas exitosamente (0x14).")
            return True
        except Exception as e:
            diag_logger.log_error("Fallo borrando averías UDS", str(e))
            return False
