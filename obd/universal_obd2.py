# obd/universal_obd2.py
# ══════════════════════════════════════════════════════════════════════════════
# Cliente Universal OBD-II sobre bus CAN (ISO 15765-4 / SAE J1979) a 500 kbps.
# Compatible con:
#   - Opel Corsa (Corsa D / Corsa E - HSCAN pines 6 y 14)
#   - Cualquier vehículo gasolina (>2001) o diésel (>2004) con CAN OBD2 estándar.
# ══════════════════════════════════════════════════════════════════════════════

import time
from typing import List, Tuple, Dict, Optional
from core.can_manager import CANManager
from obd.isotp_uds import ISOTPClient
from obd.obd_parser import OBDParser
from gestion.database_manager import DatabaseManager
from core.diagnostic_logger import diag_logger


class UniversalOBD2Client:
    """
    Cliente universal para diagnóstico de motor y emisiones según ISO 15765-4.
    Utiliza tramas de broadcast 0x7DF y respuestas directas de centralitas (0x7E8..0x7EF).
    """

    BROADCAST_ID = 0x7DF
    ECU_ENGINE_TX = 0x7E0
    ECU_ENGINE_RX = 0x7E8
    ECU_TRANS_TX  = 0x7E1
    ECU_TRANS_RX  = 0x7E9

    def __init__(self, can_mgr: CANManager, log_fn=None):
        self.can = can_mgr
        self.log_fn = log_fn or (lambda msg: None)
        self.parser = OBDParser()
        self.db = DatabaseManager()

    def _log(self, msg: str):
        self.log_fn(msg)
        diag_logger.log_info(f"[OBD2_UNIVERSAL] {msg}")

    # ──────────────────────────────────────────────────────────────────────────
    #  1. DETECCIÓN Y VIN
    # ──────────────────────────────────────────────────────────────────────────
    def detectar_ecus(self) -> List[int]:
        """
        Envía Mode 01 PID 00 a 0x7DF y detecta qué centralitas responden en el bus CAN.
        """
        self.can.flush_rx()
        # Single frame: 02 01 00 00 00 00 00 00
        req = [0x02, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        self.can.send_frame(self.BROADCAST_ID, req)

        ecus = []
        start = time.perf_counter()
        while (time.perf_counter() - start) < 0.4:
            msg = self.can.recv_frame(timeout=0.1)
            if msg and len(msg.data) >= 3:
                # Comprobar respuesta positiva de Modo 01: 41 00
                if msg.data[1] == 0x41 and msg.data[2] == 0x00:
                    if msg.arbitration_id not in ecus:
                        ecus.append(msg.arbitration_id)

        return ecus

    def leer_vin(self) -> str:
        """
        Lee el número de bastidor (VIN) mediante Modo 09 PID 02.
        Soporta tramas multi-frame ISO-TP usando broadcast 0x7DF y Flow Control a 0x7E0.
        """
        try:
            self.can.flush_rx()
            self.can.send_frame(self.BROADCAST_ID, [0x02, 0x09, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])
            ff = self.can.recv_frame(timeout=0.4, expected_id=self.ECU_ENGINE_RX)
            if ff and len(ff.data) >= 3:
                # Single Frame
                if (ff.data[0] >> 4) == 0x0 and ff.data[1] == 0x49 and ff.data[2] == 0x02:
                    vin_bytes = ff.data[4:]
                    return "".join(chr(b) for b in vin_bytes if 32 <= b <= 126).strip()
                # First Frame multi-frame
                elif (ff.data[0] >> 4) == 0x1:
                    # Enviar Flow Control (CTS) a 0x7E0
                    self.can.send_frame(self.ECU_ENGINE_TX, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    raw = bytearray(ff.data[2:])
                    for _ in range(4):
                        cf = self.can.recv_frame(timeout=0.25, expected_id=self.ECU_ENGINE_RX)
                        if cf and len(cf.data) > 1 and (cf.data[0] >> 4) == 0x2:
                            raw.extend(cf.data[1:])
                    # En 49 02 <num_items>, los caracteres de VIN empiezan en byte 3
                    vin_str = "".join(chr(b) for b in raw[3:] if 32 <= b <= 126).strip()
                    if len(vin_str) >= 17:
                        return vin_str[:17]
                    return vin_str
        except Exception as e:
            self._log(f"Error leyendo VIN vía Modo 09 PID 02: {e}")

        return ""

    # ──────────────────────────────────────────────────────────────────────────
    #  2. ESTADO DE MIL (CHECK ENGINE)
    # ──────────────────────────────────────────────────────────────────────────
    def leer_estado_mil(self) -> Tuple[bool, int]:
        """
        Consulta Modo 01 PID 01.
        Devuelve (mil_encendida: bool, num_dtcs: int).
        """
        try:
            self.can.flush_rx()
            frame = [0x02, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]
            self.can.send_frame(self.BROADCAST_ID, frame)
            for _ in range(10):
                resp = self.can.recv_frame(timeout=0.15, expected_id=self.ECU_ENGINE_RX)
                if resp and len(resp.data) >= 4 and resp.data[1] == 0x41 and resp.data[2] == 0x01:
                    byte_a = resp.data[3]
                    mil_on = bool(byte_a & 0x80)
                    dtc_count = byte_a & 0x7F
                    return mil_on, dtc_count
        except Exception:
            pass
        return False, 0

    # ──────────────────────────────────────────────────────────────────────────
    #  3. LECTURA DE AVERÍAS (MODO 03, 07, 0A)
    # ──────────────────────────────────────────────────────────────────────────
    def leer_fallos_dtc(self) -> List[Tuple[str, str, str, str]]:
        """
        Lee todos los códigos de avería del vehículo usando el estándar OBD-II (Modo 03, 07, 0A).
        Devuelve una lista de tuplas: (codigo, descripcion, estado, modulo)
        """
        resultados = []
        modos = [
            (0x03, 0x43, "Activo / Confirmado"),
            (0x07, 0x47, "Pendiente (En Observación)"),
            (0x0A, 0x4A, "Permanente"),
        ]

        for modo_id, resp_id, estado_nombre in modos:
            try:
                self.can.flush_rx()
                self.can.send_frame(self.BROADCAST_ID, [0x01, modo_id, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                for _ in range(10):
                    resp = self.can.recv_frame(timeout=0.15, expected_id=self.ECU_ENGINE_RX)
                    if not resp or len(resp.data) < 2:
                        continue

                    pdu_type = resp.data[0] >> 4
                    datos_pdu = bytearray()

                    if pdu_type == 0x0:
                        if resp.data[1] == resp_id:
                            sf_len = resp.data[0] & 0x0F
                            datos_pdu = bytearray(resp.data[1:1 + sf_len])
                    elif pdu_type == 0x1:
                        if resp.data[2] == resp_id:
                            self.can.send_frame(self.ECU_ENGINE_TX, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                            datos_pdu = bytearray(resp.data[2:])
                            for _ in range(4):
                                cf = self.can.recv_frame(timeout=0.2, expected_id=self.ECU_ENGINE_RX)
                                if cf and len(cf.data) > 1 and (cf.data[0] >> 4) == 0x2:
                                    datos_pdu.extend(cf.data[1:])

                    if datos_pdu and len(datos_pdu) >= 2 and datos_pdu[0] == resp_id:
                        num_dtcs = datos_pdu[1]
                        datos_codigos = datos_pdu[2:]
                        for i in range(0, len(datos_codigos) - 1, 2):
                            b1, b2 = datos_codigos[i], datos_codigos[i + 1]
                            if b1 == 0 and b2 == 0:
                                continue
                            codigo = self.parser.parsear_dtc(b1, b2)
                            if codigo and not any(r[0] == codigo for r in resultados):
                                desc = self.db.buscar_descripcion(codigo)
                                resultados.append((codigo, desc, estado_nombre, "Motor (ECM 0x7E8)"))
                        break
            except Exception as e:
                self._log(f"Error leyendo fallos modo 0x{modo_id:02X}: {e}")

        return resultados

    # ──────────────────────────────────────────────────────────────────────────
    #  4. BORRADO DE AVERÍAS (MODO 04)
    # ──────────────────────────────────────────────────────────────────────────
    def borrar_fallos_dtc(self) -> bool:
        """
        Envía Modo 04 a 0x7DF para borrar memoria de fallos y apagar el Check Engine (MIL).
        Retorna True si la ECU confirma el borrado (respuesta 0x44).
        """
        self._log("[OBD2] Enviando orden de borrado de fallos (Modo 04) a ID 0x7DF...")
        self.can.flush_rx()

        # Single frame Modo 04: 01 04 00 00 00 00 00 00
        req = [0x01, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        self.can.send_frame(self.BROADCAST_ID, req)

        # También enviamos al ID directo de motor por compatibilidad con ECUs estrictas
        time.sleep(0.05)
        self.can.send_frame(self.ECU_ENGINE_TX, req)

        start = time.perf_counter()
        confirmado = False
        while (time.perf_counter() - start) < 1.0:
            resp = self.can.recv_frame(timeout=0.2)
            if resp and len(resp.data) >= 2:
                # Comprobar respuesta positiva de Modo 04: 0x44
                if resp.data[1] == 0x44:
                    confirmado = True
                    self._log(f"[✓ ÉXITO] La centralita 0x{resp.arbitration_id:03X} confirmó el borrado de fallos.")
                    break

        return confirmado
