import time
from gestion.backup_manager import BackupManager
from core.diagnostic_logger import diag_logger

# ──────────────────────────────────────────────────────────────────────────────
#  MAPA DE MÓDULOS CANÓNICO
#  Clave: nombre exacto tal como aparece en los ComboBox de la GUI.
#  Valor: (CAN_header_11bit, descripcion_corta)
#
#  IMPORTANTE: Este diccionario es la ÚNICA fuente de verdad para los headers.
#  controlador.py y audi_diag_pro.py deben usar exactamente estas mismas claves.
# ──────────────────────────────────────────────────────────────────────────────
def extraer_bytes_hex(resp: str) -> list[int]:
    """
    Convierte cualquier respuesta hexadecimal (con espacios, sin espacios o combinada)
    en una lista limpia de enteros (bytes).
    Ignora caracteres no hexadecimales y asegura longitud par.
    """
    if not resp:
        return []
    hex_clean = "".join(c for c in resp.strip().upper() if c in "0123456789ABCDEF")
    if len(hex_clean) % 2 != 0:
        hex_clean = hex_clean[:-1]
    return [int(hex_clean[i:i+2], 16) for i in range(0, len(hex_clean), 2)]


# Mapeo oficial VAG UDS (ODIS / ISO 14229 sobre CAN 11-bit 500k):
# Cada módulo se define como (CAN_TX_Header, CAN_RX_Filter, Descripcion, Logical_Addr)
MODULOS_VAG = {
    "Motor (01)":                     ("7E0", "7E8", "ECU Motor / Gestión (EDC17)", 0x01),
    "Caja de Cambios (02)":           ("7E1", "7E9", "Transmisión automática",       0x02),
    "ABS / ESP (03)":                 ("713", "77D", "Sistema de frenos ABS/ESP",     0x03),
    "Climatización (08)":             ("746", "7B0", "Control de clima / Climatronic",0x08),
    "Central Eléctrica / Luces (09)": ("70E", "778", "Red de a bordo / J519 (Luces)",0x09),
    "Airbag (15)":                    ("715", "77F", "SRS / Airbag",                  0x15),
    "Cuadro Instrumentos (17)":       ("714", "77E", "Combinado de instrumentos (J285)", 0x17),
    "Gateway CAN (19)":               ("710", "77A", "CAN Gateway (J533)",            0x19),
    "Confort / Electrónica (46)":     ("70D", "777", "Módulo de Confort / BCM (J393)",0x46),
    "Pantalla / MMI (5F)":            ("773", "7DD", "Sistema MMI / Infotainment (J794)", 0x5F),
}

LOGICAL_ADDRESSES_VAG = {k: v[3] for k, v in MODULOS_VAG.items()}


class VAGProtocol:
    """
    Implementa el protocolo UDS (ISO 14229) sobre CAN (ISO 15765-4)
    específico para vehículos del Grupo VAG (Audi, VW, Seat, Skoda).
    Registra cada trama y validación en audidiag_registro_detallado.txt.
    """

    def __init__(self, connection, log_fn=None):
        self.conexion = connection
        self._log = log_fn if log_fn else print

    def _emit(self, msg: str):
        """Emite un mensaje de log de forma segura a la GUI y al archivo de registro."""
        try:
            self._log(msg)
        except Exception:
            print(msg)
        diag_logger.log_info(msg)

    # ──────────────────────────────────────────────────────────────────────────
    #  INICIALIZACIÓN DEL MÓDULO (CAMBIO DE HEADER CAN Y FILTRO RX)
    # ──────────────────────────────────────────────────────────────────────────
    def inicializar_modulo(self, nombre_modulo: str) -> bool:
        """
        Configura el chip ELM327 para hablar con un módulo específico cambiando su header CAN
        y su filtro de recepción (ATCRA) para capturar la respuesta del módulo sin descartarla.
        """
        if nombre_modulo not in MODULOS_VAG:
            self._emit(f"[WARN] Módulo desconocido '{nombre_modulo}'. Usando Motor (01) por defecto.")
            nombre_modulo = "Motor (01)"

        info = MODULOS_VAG[nombre_modulo]
        header = info[0]
        rx_filter = info[1] if len(info) > 1 else header
        descripcion = info[2] if len(info) > 2 else ""

        self._emit(f"[INFO] Direccionando a {nombre_modulo} ({descripcion}) | TX: {header} -> RX: {rx_filter}")

        comandos_modulo = [
            ("ATCAF1",          "Auto-formateo CAN activado"),
            (f"ATSH{header}",   f"Set Header (TX) -> {header}"),
            (f"ATCRA{rx_filter}", f"CAN Receive Filter (RX) -> {rx_filter}"),
            (f"ATFCSH{header}", f"Flow Control Header -> {header}"),
            ("ATFCSD300000",    "Flow Control Data (CTS, BS=0, STmin=0)"),
            ("ATFCSM1",         "Flow Control Mode 1 (Manual/User defined)"),
        ]

        for cmd, desc in comandos_modulo:
            self.conexion.enviar_comando(cmd, descripcion=desc)
            time.sleep(0.02)
            self.conexion.leer_respuesta(timeout_s=0.5)

        return True

    # ──────────────────────────────────────────────────────────────────────────
    #  LECTURA DE IDENTIFICADORES UDS
    # ──────────────────────────────────────────────────────────────────────────
    def leer_identificador(self, did: str) -> str:
        """Lee un Data Identifier (DID) usando el servicio UDS 0x22 (ReadDataByIdentifier)."""
        self.conexion.enviar_comando(f"22{did}", descripcion=f"UDS Read DID 0x{did}")
        time.sleep(0.1)
        respuesta = self.conexion.leer_respuesta(timeout_s=1.5)

        if respuesta and ("62" in respuesta or "62 " in respuesta):
            return respuesta
        return f"Sin soporte o error: {respuesta}"

    # ──────────────────────────────────────────────────────────────────────────
    #  LECTURA DE FALLOS (DTC)
    # ──────────────────────────────────────────────────────────────────────────
    def leer_dtcs_uds(self) -> tuple[str, str]:
        """
        Lee los códigos de fallo usando el servicio UDS 0x19 0x02.
        Prueba diferentes status masks (09, 08, FF) y abre sesión extendida si es requerido.

        Returns:
            Tupla (estado, respuesta_cruda):
            - estado: "OK" (si la ECU respondió con DTCs o sin fallos), "ERROR" (si no hubo comunicación), "NRC" (rechazado).
        """
        for mask in ["09", "08", "FF"]:
            cmd = f"1902{mask}"
            self.conexion.enviar_comando(cmd, descripcion=f"UDS ReadDTCs ({cmd})")
            time.sleep(0.2)
            respuesta = self.conexion.leer_respuesta(timeout_s=2.0)

            if not respuesta or any(err in respuesta.upper() for err in ["NO DATA", "CAN ERROR", "BUS INIT", "UNABLE TO CONNECT", "ERR"]):
                continue

            if "59" in respuesta:
                return "OK", respuesta

            # Si el módulo requiere sesión de diagnóstico activa (NRC 7E o 22)
            if "7F 19 7E" in respuesta.upper() or "7F 19 22" in respuesta.upper():
                self._emit("[INFO] Módulo solicita sesión extendida para DTCs. Enviando 10 03...")
                self.conexion.enviar_comando("1003", descripcion="UDS Extended Diagnostic Session (10 03)")
                time.sleep(0.15)
                self.conexion.leer_respuesta(timeout_s=1.0)
                self.conexion.enviar_comando(cmd, descripcion=f"UDS ReadDTCs ({cmd}) tras 1003")
                time.sleep(0.2)
                resp_s = self.conexion.leer_respuesta(timeout_s=2.0)
                if resp_s and "59" in resp_s:
                    return "OK", resp_s

            if "7F" in respuesta:
                return "NRC", respuesta

        return "ERROR", "TIMEOUT o NO DATA"

    def leer_dtcs_kwp2000(self) -> tuple[bool, list[str]]:
        """
        Lee fallos usando el servicio KWP2000 0x18 (ReadDiagnosticTroubleCodesByStatus).
        Nativo para Audi A6 C6 (ECU motor EDC17/EDC16 y cambio automático).
        Returns:
            Tupla (respondio_ecu: bool, codigos: list[str]).
        """
        codigos = set()
        respondio = False

        for cmd in ["1800FF00", "1802FF00"]:
            self.conexion.enviar_comando(cmd, descripcion=f"KWP2000 ReadDTCs ({cmd})")
            time.sleep(0.2)
            resp = self.conexion.leer_respuesta(timeout_s=2.0)
            if not resp or any(err in resp.upper() for err in ["NO DATA", "CAN ERROR", "BUS INIT", "UNABLE TO CONNECT"]):
                continue

            bytes_resp = extraer_bytes_hex(resp)
            if 0x58 in bytes_resp:
                respondio = True
                idx = bytes_resp.index(0x58)
                datos = bytes_resp[idx + 1:]
                if not datos:
                    continue
                num_dtcs = datos[0]
                if num_dtcs == 0:
                    continue

                dtc_bytes = datos[1:]
                step = 3 if len(dtc_bytes) >= 3 and len(dtc_bytes) % 3 == 0 else 2
                for i in range(0, len(dtc_bytes) - 1, step):
                    b1 = dtc_bytes[i]
                    b2 = dtc_bytes[i+1]
                    if b1 == 0 and b2 == 0:
                        continue
                    prefijo = ["P", "C", "B", "U"][(b1 >> 6) & 0x03]
                    d1 = (b1 >> 4) & 0x03
                    d2 = b1 & 0x0F
                    d3 = (b2 >> 4) & 0x0F
                    d4 = b2 & 0x0F
                    codigos.add(f"{prefijo}{d1}{d2:X}{d3:X}{d4:X}")
                    codigos.add(f"VAG-{(b1 << 8) | b2:05d}")
                break

        return respondio, list(codigos)

    def leer_dtcs_obd2_estandar(self) -> tuple[bool, list[str]]:
        """
        Lee fallos OBD2 estándar (Modo 03 confirmados y Modo 07 pendientes).
        Returns:
            Tupla (respondio_ecu: bool, codigos: list[str]).
        """
        codigos = set()
        respondio = False
        for modo in ["03", "07"]:
            desc = "OBD2 DTCs Confirmados" if modo == "03" else "OBD2 DTCs Pendientes"
            self.conexion.enviar_comando(modo, descripcion=desc)
            time.sleep(0.2)
            resp = self.conexion.leer_respuesta(timeout_s=2.0)
            if not resp or any(err in resp.upper() for err in ["NO DATA", "CAN ERROR", "BUS INIT", "UNABLE TO CONNECT"]):
                continue

            bytes_resp = extraer_bytes_hex(resp)
            cabecera_esperada = 0x43 if modo == "03" else 0x47
            if cabecera_esperada in bytes_resp:
                respondio = True
                idx = bytes_resp.index(cabecera_esperada)
                datos = bytes_resp[idx + 1:]
                if len(datos) == 1 and datos[0] == 0:
                    continue
                for i in range(0, len(datos) - 1, 2):
                    b1 = datos[i]
                    b2 = datos[i+1]
                    if b1 == 0 and b2 == 0:
                        continue
                    prefijo = ["P", "C", "B", "U"][(b1 >> 6) & 0x03]
                    d1 = (b1 >> 4) & 0x03
                    d2 = b1 & 0x0F
                    d3 = (b2 >> 4) & 0x0F
                    d4 = b2 & 0x0F
                    codigos.add(f"{prefijo}{d1}{d2:X}{d3:X}{d4:X}")

        return respondio, list(codigos)

    def parsear_dtcs_uds(self, respuesta: str) -> list[str]:
        """Decodifica la trama de respuesta UDS 0x59 0x02 en una lista de códigos SAE."""
        if not respuesta or "59" not in respuesta:
            return []

        bytes_resp = extraer_bytes_hex(respuesta)
        if 0x59 not in bytes_resp:
            return []

        idx = bytes_resp.index(0x59)
        datos = bytes_resp[idx + 2:]
        codigos = []
        step = 4 if len(datos) >= 4 and len(datos) % 4 == 0 else 3
        for i in range(0, len(datos), step):
            if i + 1 < len(datos):
                b1 = datos[i]
                b2 = datos[i+1]
                if b1 == 0 and b2 == 0:
                    continue
                primera = ["P", "C", "B", "U"][(b1 >> 6) & 0x03]
                d1 = (b1 >> 4) & 0x03
                d2 = b1 & 0x0F
                d3 = (b2 >> 4) & 0x0F
                d4 = b2 & 0x0F
                codigos.append(f"{primera}{d1}{d2:X}{d3:X}{d4:X}")
        return codigos

    # ──────────────────────────────────────────────────────────────────────────
    #  VAG TP 2.0 — CANAL DINÁMICO SOBRE GATEWAY J533 (ID 0x200)
    # ──────────────────────────────────────────────────────────────────────────
    def abrir_canal_tp20(self, logical_addr: int) -> tuple[bool, int, int]:
        """
        Intenta negociar un canal TP 2.0 con una centralita a través de la Gateway (ID 0x200).
        Retorna (exito: bool, ecu_rx_id: int, ecu_tx_id: int).
        """
        try:
            self.conexion.enviar_comando("ATCAF0", descripcion="TP2.0 Raw CAN Mode")
            time.sleep(0.04)
            self.conexion.leer_respuesta(timeout_s=0.3)

            self.conexion.enviar_comando("ATSH200", descripcion="Set Header 200 (TP2.0 Setup)")
            time.sleep(0.04)
            self.conexion.leer_respuesta(timeout_s=0.3)

            filtro_id = 0x200 + logical_addr
            self.conexion.enviar_comando(f"ATCRA{filtro_id:03X}", descripcion=f"Filter CAN ID 0x{filtro_id:03X}")
            time.sleep(0.04)
            self.conexion.leer_respuesta(timeout_s=0.3)

            cmd_setup = f"{logical_addr:02X}C00010000301"
            self.conexion.enviar_comando(cmd_setup, descripcion=f"TP2.0 Setup Request -> 0x{logical_addr:02X}")
            time.sleep(0.15)
            resp = self.conexion.leer_respuesta(timeout_s=1.5)

            if not resp or any(e in resp.upper() for e in ["NO DATA", "CAN ERROR", "ERR"]):
                self._restaurar_modo_estandar()
                return False, 0, 0

            bytes_resp = extraer_bytes_hex(resp)
            if len(bytes_resp) >= 6 and bytes_resp[0] == logical_addr and bytes_resp[1] == 0xD0:
                rx_low = bytes_resp[2]
                rx_info = bytes_resp[3]
                tx_low = bytes_resp[4]
                tx_info = bytes_resp[5]
                ecu_rx_id = rx_low | ((rx_info & 0x07) << 8)
                ecu_tx_id = tx_low | ((tx_info & 0x07) << 8)

                if ecu_rx_id and ecu_tx_id:
                    self.conexion.enviar_comando(f"ATSH{ecu_rx_id:03X}", descripcion=f"TP2.0 TX ID 0x{ecu_rx_id:03X}")
                    time.sleep(0.04)
                    self.conexion.leer_respuesta(timeout_s=0.3)

                    self.conexion.enviar_comando(f"ATCRA{ecu_tx_id:03X}", descripcion=f"TP2.0 RX ID 0x{ecu_tx_id:03X}")
                    time.sleep(0.04)
                    self.conexion.leer_respuesta(timeout_s=0.3)

                    self.conexion.enviar_comando("A00F8AFF32FF", descripcion="TP2.0 Parameters Request")
                    time.sleep(0.1)
                    self.conexion.leer_respuesta(timeout_s=1.0)
                    diag_logger.log_info(f"Canal TP 2.0 abierto con módulo 0x{logical_addr:02X} (TX: 0x{ecu_rx_id:03X}, RX: 0x{ecu_tx_id:03X})")
                    return True, ecu_rx_id, ecu_tx_id

            self._restaurar_modo_estandar()
            return False, 0, 0
        except Exception as e:
            diag_logger.log_error("Excepción en abrir_canal_tp20", str(e))
            self._restaurar_modo_estandar()
            return False, 0, 0

    def cerrar_canal_tp20(self):
        """Cierra el canal TP 2.0 y restablece el ELM327 al modo ISO-TP estándar."""
        try:
            self.conexion.enviar_comando("A8", descripcion="TP2.0 Disconnect")
            time.sleep(0.04)
            self.conexion.leer_respuesta(timeout_s=0.3)
        except Exception:
            pass
        self._restaurar_modo_estandar()

    def _restaurar_modo_estandar(self):
        """Restablece los filtros y el autoformateo CAN del ELM327."""
        try:
            self.conexion.enviar_comando("ATAR", descripcion="Clear CAN Filter")
            time.sleep(0.03)
            self.conexion.leer_respuesta(timeout_s=0.3)
            self.conexion.enviar_comando("ATCAF1", descripcion="Restore Auto Formatting")
            time.sleep(0.03)
            self.conexion.leer_respuesta(timeout_s=0.3)
        except Exception:
            pass

    def leer_dtcs_tp20(self, logical_addr: int) -> tuple[bool, list[str]]:
        """Lee códigos de fallo usando KWP2000 dentro de un canal TP 2.0 dinámico."""
        ok, ecu_rx, ecu_tx = self.abrir_canal_tp20(logical_addr)
        if not ok:
            return False, []

        codigos = set()
        try:
            self.conexion.enviar_comando("1000041800FF00", descripcion="TP2.0 Data: KWP2000 ReadDTCs")
            time.sleep(0.2)
            resp = self.conexion.leer_respuesta(timeout_s=2.0)

            if resp:
                bytes_resp = extraer_bytes_hex(resp)
                if 0x58 in bytes_resp:
                    idx = bytes_resp.index(0x58)
                    datos = bytes_resp[idx + 1:]
                    if datos and len(datos) > 1:
                        dtc_bytes = datos[1:]
                        step = 3 if len(dtc_bytes) >= 3 and len(dtc_bytes) % 3 == 0 else 2
                        for i in range(0, len(dtc_bytes) - 1, step):
                            b1 = dtc_bytes[i]
                            b2 = dtc_bytes[i+1]
                            if b1 == 0 and b2 == 0:
                                continue
                            prefijo = ["P", "C", "B", "U"][(b1 >> 6) & 0x03]
                            d1 = (b1 >> 4) & 0x03
                            d2 = b1 & 0x0F
                            d3 = (b2 >> 4) & 0x0F
                            d4 = b2 & 0x0F
                            codigos.add(f"{prefijo}{d1}{d2:X}{d3:X}{d4:X}")
                            codigos.add(f"VAG-{(b1 << 8) | b2:05d}")
            return True, list(codigos)
        finally:
            self.cerrar_canal_tp20()

    def leer_fallos_modulo(self, nombre_modulo: str) -> tuple[bool, list[str]]:
        """
        Lee los códigos de avería de un módulo específico utilizando el protocolo
        óptimo para Audi A6 C6 (KWP2000 sobre CAN, TP2.0 a través de Gateway o UDS).
        Returns:
            Tupla (comunicacion_ok: bool, lista_codigos_dtc: list[str])
        """
        self.inicializar_modulo(nombre_modulo)
        codigos = set()
        comunicacion_ok = False

        logical_addr = LOGICAL_ADDRESSES_VAG.get(nombre_modulo)

        # 1. Módulos de la línea de tracción (Motor y Caja de Cambios)
        if nombre_modulo in ["Motor (01)", "Caja de Cambios (02)"]:
            ok_kwp, dtcs_kwp = self.leer_dtcs_kwp2000()
            if ok_kwp:
                comunicacion_ok = True
                codigos.update(dtcs_kwp)

            estado_uds, resp_uds = self.leer_dtcs_uds()
            if estado_uds == "OK":
                comunicacion_ok = True
                codigos.update(self.parsear_dtcs_uds(resp_uds))
            elif estado_uds == "NRC":
                comunicacion_ok = True

            ok_obd, dtcs_obd = self.leer_dtcs_obd2_estandar()
            if ok_obd:
                comunicacion_ok = True
                codigos.update(dtcs_obd)

            return comunicacion_ok, sorted(list(codigos))

        # 2. Módulos secundarios tras la Gateway J533 (TP 2.0)
        if logical_addr is not None:
            ok_tp, dtcs_tp = self.leer_dtcs_tp20(logical_addr)
            if ok_tp:
                comunicacion_ok = True
                codigos.update(dtcs_tp)
                return True, sorted(list(codigos))

        # 3. Respaldo por ISO-TP directo
        estado_uds, resp_uds = self.leer_dtcs_uds()
        if estado_uds == "OK":
            comunicacion_ok = True
            codigos.update(self.parsear_dtcs_uds(resp_uds))
        elif estado_uds == "NRC":
            comunicacion_ok = True

        ok_kwp, dtcs_kwp = self.leer_dtcs_kwp2000()
        if ok_kwp:
            comunicacion_ok = True
            codigos.update(dtcs_kwp)

        return comunicacion_ok, sorted(list(codigos))

    def borrar_dtcs(self) -> str:
        """Borra todos los fallos usando KWP2000 (14FF00), UDS (14FFFFFF) y OBD2 (04)."""
        for cmd, desc in [("14FF00", "KWP2000 Clear DTCs"), ("14FFFFFF", "UDS Clear DTCs"), ("04", "OBD2 Mode 04 Clear DTCs")]:
            self.conexion.enviar_comando(cmd, descripcion=desc)
            time.sleep(0.3)
            resp = self.conexion.leer_respuesta(timeout_s=2.0)
            if resp:
                bytes_resp = extraer_bytes_hex(resp)
                if 0x54 in bytes_resp or 0x44 in bytes_resp or "OK" in resp.upper():
                    diag_logger.log_transferencia(f"Borrado DTCs ({cmd})", True)
                    return "Fallos borrados correctamente de la centralita."

        diag_logger.log_transferencia("Borrado DTCs", False, "Sin confirmación de borrado")
        return "Comando de borrado enviado."

    def borrar_dtcs_uds(self) -> str:
        """Alias para compatibilidad."""
        return self.borrar_dtcs()


    # ──────────────────────────────────────────────────────────────────────────
    #  LONG CODING
    # ──────────────────────────────────────────────────────────────────────────
    def leer_coding_uds(self) -> str | None:
        """
        Lee el Long Coding actual usando DID 0x0600 (UDS), DID 0xF18C o KWP2000.
        Si la ECU requiere sesión extendida, envía automáticamente 10 03.
        """
        # 1. Intentar UDS 220600
        self.conexion.enviar_comando("220600", descripcion="UDS Read Coding 0x0600")
        time.sleep(0.25)
        respuesta = self.conexion.leer_respuesta(timeout_s=2.0)

        # Si el módulo requiere sesión extendida (NRC 7E o 22)
        if respuesta and ("7F 22 7E" in respuesta.upper() or "7F 22 22" in respuesta.upper()):
            self._emit("[INFO] Módulo solicita sesión extendida para Coding. Enviando 10 03...")
            self.conexion.enviar_comando("1003", descripcion="UDS Extended Diagnostic Session (10 03)")
            time.sleep(0.15)
            self.conexion.leer_respuesta(timeout_s=1.0)
            self.conexion.enviar_comando("220600", descripcion="UDS Read Coding 0x0600 (tras 1003)")
            time.sleep(0.25)
            respuesta = self.conexion.leer_respuesta(timeout_s=2.0)

        if respuesta and "62" in respuesta:
            bytes_resp = extraer_bytes_hex(respuesta)
            if len(bytes_resp) >= 4 and 0x62 in bytes_resp:
                idx = bytes_resp.index(0x62)
                # Si viene con 62 06 00, los datos empiezan tras 00
                idx_data = idx + 3 if (len(bytes_resp) > idx + 2 and bytes_resp[idx+1] == 0x06 and bytes_resp[idx+2] == 0x00) else idx + 1
                datos = bytes_resp[idx_data:]
                if datos:
                    return " ".join(f"{b:02X}" for b in datos)

        # 2. Intentar DID alternativo F18C (identificador de codificación en ciertos cuadros VAG)
        self.conexion.enviar_comando("22F18C", descripcion="UDS Read Coding DID 0xF18C")
        time.sleep(0.25)
        resp_f18c = self.conexion.leer_respuesta(timeout_s=1.5)
        if resp_f18c and "62" in resp_f18c:
            bytes_resp = extraer_bytes_hex(resp_f18c)
            if len(bytes_resp) >= 4 and 0x62 in bytes_resp:
                idx = bytes_resp.index(0x62)
                idx_data = idx + 3 if (len(bytes_resp) > idx + 2 and bytes_resp[idx+1] == 0xF1 and bytes_resp[idx+2] == 0x8C) else idx + 1
                datos = bytes_resp[idx_data:]
                if datos:
                    return " ".join(f"{b:02X}" for b in datos)

        # 3. Intentar KWP2000 Read Coding (1A 9E o 1A 9B)
        for cmd in ["1A9E", "1A9B"]:
            self.conexion.enviar_comando(cmd, descripcion=f"KWP2000 Read Coding ({cmd})")
            time.sleep(0.25)
            resp_kwp = self.conexion.leer_respuesta(timeout_s=1.5)
            if resp_kwp and "5A" in resp_kwp:
                bytes_kwp = extraer_bytes_hex(resp_kwp)
                if len(bytes_kwp) > 3 and 0x5A in bytes_kwp:
                    idx = bytes_kwp.index(0x5A)
                    datos = bytes_kwp[idx + 2:]
                    if datos:
                        return " ".join(f"{b:02X}" for b in datos)

        return None

    def leer_coding_modulo(self, nombre_modulo: str) -> str | None:
        """
        Lee la codificación de un módulo, configurando su cabecera TX y filtro RX correspondientes.
        Si la comunicación directa no responde, intenta fallback a canal TP 2.0 dinámico.
        """
        self.inicializar_modulo(nombre_modulo)
        # 1. Intentar canal directo UDS / KWP2000 con filtros TX/RX correctos
        coding = self.leer_coding_uds()
        if coding:
            return coding

        # 2. Intentar por canal TP 2.0 si tiene dirección lógica detrás de Gateway
        logical_addr = LOGICAL_ADDRESSES_VAG.get(nombre_modulo)
        if logical_addr is not None:
            ok, ecu_rx, ecu_tx = self.abrir_canal_tp20(logical_addr)
            if ok:
                try:
                    self.conexion.enviar_comando("100003220600", descripcion="TP2.0 Read Coding (220600)")
                    time.sleep(0.25)
                    resp = self.conexion.leer_respuesta(timeout_s=2.0)
                    if resp and "62" in resp:
                        bytes_resp = extraer_bytes_hex(resp)
                        if 0x62 in bytes_resp:
                            idx = bytes_resp.index(0x62)
                            idx_data = idx + 3 if (len(bytes_resp) > idx + 2 and bytes_resp[idx+1] == 0x06 and bytes_resp[idx+2] == 0x00) else idx + 1
                            datos = bytes_resp[idx_data:]
                            if datos:
                                return " ".join(f"{b:02X}" for b in datos)
                finally:
                    self.cerrar_canal_tp20()

        return None

    def security_access(self, nivel: int = 1, login_code: int = None) -> bool:
        """
        Solicita acceso de seguridad (UDS 0x27) antes de escribir coding si la ECU lo requiere.
        """
        subf_seed = f"{nivel:02X}"      # ej. "01"
        subf_key  = f"{nivel + 1:02X}"  # ej. "02"

        self._emit(f"[INFO] Comprobando Security Access nivel {nivel}...")

        # Paso 1: Pedir semilla
        self.conexion.enviar_comando(f"27{subf_seed}", descripcion=f"Security Access Request Seed (27 {subf_seed})")
        time.sleep(0.2)
        seed_resp = self.conexion.leer_respuesta(timeout_s=1.0)
        if not seed_resp:
            self._emit("[INFO] Módulo no respondió a Security Access; continuando.")
            return True

        resp_clean = seed_resp.replace(" ", "").upper()
        # Si la ECU responde con Negative Response (ej. 7F 27 12 subfunción no soportada en esta sesión)
        if "7F27" in resp_clean:
            self._emit("[INFO] Módulo no requiere Security Access previo en esta sesión.")
            return True

        # Respuesta positiva a 0x27 empieza con 0x67
        idx_67 = resp_clean.find("67" + subf_seed)
        if idx_67 != -1:
            seed_data = resp_clean[idx_67 + 4:]
            seed_hex = "".join(c for c in seed_data if c in "0123456789ABCDEF")
            # Semilla todo ceros: ECU ya desbloqueada
            if not seed_hex or set(seed_hex) == {"0"}:
                self._emit("[OK] Módulo ya desbloqueado (semilla 00). No requiere envío de clave.")
                return True

            if login_code is not None:
                llave = f"{login_code:04X}"
                self.conexion.enviar_comando(f"27{subf_key}{llave}", descripcion=f"Security Access Send Key ({llave})")
                time.sleep(0.2)
                key_resp = self.conexion.leer_respuesta(timeout_s=1.0)
                if key_resp and ("67" + subf_key) in key_resp.replace(" ", "").upper():
                    self._emit("[OK] Security Access concedido con código de acceso.")
                    return True
                else:
                    self._emit(f"[ERROR] Security Access rechazado con el código proporcionado: {key_resp}")
                    return False

            self._emit(f"[WARN] El módulo requiere cálculo algorítmico de semilla ({seed_hex}) o login no suministrado.")
            return False

        return True

    def escribir_coding_uds(self, nombre_modulo: str, vin: str,
                             nuevo_coding: str, coding_antiguo: str) -> str:
        """
        Escribe un nuevo Long Coding en la ECU usando el servicio UDS 0x2E.

        Proceso seguro obligatorio:
        1. Comprobación estricta de longitudes (nuevo vs antiguo).
        2. Backup automático preventivo del coding antiguo en disco (.json) con aborto si falla.
        3. Inicialización de cabecera y filtro CAN del módulo.
        4. Sesión extendida de diagnóstico (UDS 10 03).
        5. Comprobación de Security Access real.
        6. Escritura con servicio 0x2E + DID 0x0600.
        7. Reinicio suave (Soft Reset 11 03) para activar los cambios.
        8. Verificación byte a byte de relectura obligatoria.
        """
        if not coding_antiguo:
            return "[ERROR] Operación abortada: falta el coding original para hacer el backup."

        coding_limpio = nuevo_coding.replace(" ", "").upper()
        antiguo_limpio = coding_antiguo.replace(" ", "").upper()

        # Comprobación de longitudes
        if len(coding_limpio) != len(antiguo_limpio):
            return f"[ERROR] Longitud no coincide: nuevo ({len(coding_limpio)//2} bytes) vs original ({len(antiguo_limpio)//2} bytes). Abortado por seguridad."

        self._emit(f"[INFO] Iniciando escritura de coding en {nombre_modulo}...")

        # 1. Backup obligatorio previo
        try:
            backup_mgr = BackupManager()
            ruta = backup_mgr.guardar_backup(
                modulo=nombre_modulo, coche=vin, bytes_coding=coding_antiguo, etiqueta="AUTO_PREVIO_ESCRITURA"
            )
            self._emit(f"[SEGURIDAD] Copia de seguridad obligatoria guardada en: {ruta}")
        except Exception as e:
            return f"[ERROR CRÍTICO] Falló el backup obligatorio ({e}). Escritura abortada por seguridad."

        # 2. Configurar TX y RX del módulo
        self.inicializar_modulo(nombre_modulo)

        # 3. Sesión extendida UDS obligatoria para escritura
        self.conexion.enviar_comando("1003", descripcion="UDS Extended Diagnostic Session (10 03)")
        time.sleep(0.15)
        self.conexion.leer_respuesta(timeout_s=1.0)

        # 4. Security Access
        if not self.security_access():
            return "[ERROR] Security Access no superado. Escritura abortada por seguridad."

        # 5. Escritura (servicio 0x2E + DID 0x0600 + datos)
        self.conexion.enviar_comando(f"2E0600{coding_limpio}", descripcion=f"UDS Write Coding 0x0600 ({len(coding_limpio)//2} bytes)")
        time.sleep(0.5)
        respuesta = self.conexion.leer_respuesta(timeout_s=3.0)

        resp_clean = respuesta.replace(" ", "").upper() if respuesta else ""
        if "7F2E" in resp_clean:
            self._emit(f"[ERROR] La centralita rechazó el comando 0x2E (Negative Response): {respuesta}")
            diag_logger.log_transferencia(f"Escritura Coding en {nombre_modulo}", False, respuesta)
            return f"Error: La centralita rechazó el comando 0x2E → {respuesta}"

        if resp_clean.startswith("6E0600") or "6E0600" in resp_clean or (resp_clean.startswith("6E") and "7F" not in resp_clean):
            self._emit("[OK] ¡Coding aceptado y grabado con éxito en la memoria del módulo!")
            diag_logger.log_transferencia(f"Escritura Coding en {nombre_modulo}", True, nuevo_coding)

            # 6. Reinicio suave para que la centralita cargue el nuevo mapa inmediatamente
            self._emit("[INFO] Enviando soft-reset para aplicar configuración...")
            self.conexion.enviar_comando("1103", descripcion="UDS Soft Reset (11 03)")
            time.sleep(0.3)
            self.conexion.leer_respuesta(timeout_s=1.0)

            # 7. Verificación completa byte a byte
            time.sleep(0.5)
            cod_verif = self.leer_coding_uds()
            if cod_verif:
                cod_verif_limpio = cod_verif.replace(" ", "").upper()
                self._emit(f"[VERIFICACIÓN] Coding releído tras grabación: {cod_verif}")
                if cod_verif_limpio == coding_limpio:
                    return "¡Codificación escrita y confirmada correctamente en la centralita!"
                else:
                    self._emit(f"[ERROR] Verificación fallida: Releído [{cod_verif_limpio}] != Escrito [{coding_limpio}]")
                    return f"Error: Verificación fallida tras escritura. Releído [{cod_verif_limpio}] != Escrito [{coding_limpio}]."

            return "Error: No se pudo verificar la codificación tras la escritura (sin respuesta de relectura)."
        else:
            self._emit(f"[ERROR] La centralita no aceptó el coding: {respuesta}")
            diag_logger.log_transferencia(f"Escritura Coding en {nombre_modulo}", False, respuesta)
            return f"Error: La centralita no aceptó el comando → {respuesta}"

    def ejecutar_actuador_uds(self, canal: str, duracion: int = 2) -> tuple[bool, str]:
        """
        Activa un componente usando UDS (0x31 RoutineControl / 0x2F IOControl) o KWP2000 (0x30).
        Abre sesión extendida (10 03) y mantiene TesterPresent (3E 00).
        """
        # 1. Sesión extendida de diagnóstico UDS
        self.conexion.enviar_comando("1003", descripcion="UDS Extended Diagnostic Session (10 03)")
        time.sleep(0.15)
        self.conexion.leer_respuesta(timeout_s=0.5)

        # 2. Tester Present Keep-Alive
        self.conexion.enviar_comando("3E00", descripcion="Tester Present Keep-Alive (3E 00)")
        time.sleep(0.08)
        self.conexion.leer_respuesta(timeout_s=0.5)

        # 3. Intentar UDS Service 0x31 (RoutineControl Start)
        cmd_start = f"310101{canal}00"
        self.conexion.enviar_comando(cmd_start, descripcion=f"UDS StartRoutine 0x31 canal {canal}")
        time.sleep(0.25)
        resp_uds = self.conexion.leer_respuesta(timeout_s=2.0)

        bytes_uds = extraer_bytes_hex(resp_uds)
        if 0x71 in bytes_uds:
            self._emit(f"[OK] Centralita aceptó la orden UDS. Activando componente ({duracion}s)...")
            diag_logger.log_transferencia(f"Actuador canal {canal} activado (UDS)", True)
            time.sleep(duracion)
            cmd_stop = f"310201{canal}00"
            self.conexion.enviar_comando(cmd_stop, descripcion=f"UDS StopRoutine canal {canal}")
            time.sleep(0.2)
            self.conexion.leer_respuesta(timeout_s=1.0)
            return True, "Actuador ejecutado y confirmado por la centralita."

        # 4. Intentar UDS Service 0x2F (InputOutputControlByIdentifier)
        cmd_2f = f"2F{canal}000301"
        self.conexion.enviar_comando(cmd_2f, descripcion=f"UDS IOControl 0x2F canal {canal}")
        time.sleep(0.25)
        resp_2f = self.conexion.leer_respuesta(timeout_s=2.0)

        bytes_2f = extraer_bytes_hex(resp_2f)
        if 0x6F in bytes_2f:
            self._emit(f"[OK] Centralita aceptó orden 0x2F. Activando ({duracion}s)...")
            diag_logger.log_transferencia(f"Actuador canal {canal} activado (UDS 2F)", True)
            time.sleep(duracion)
            self.conexion.enviar_comando(f"2F{canal}0000", descripcion="UDS IOControl Return Control to ECU")
            time.sleep(0.15)
            self.conexion.leer_respuesta(timeout_s=0.5)
            return True, "Actuador ejecutado y confirmado por la centralita."

        # 5. Intentar KWP2000 Actuator Service 0x30
        cmd_kwp = f"30{canal}01"
        self.conexion.enviar_comando(cmd_kwp, descripcion=f"KWP2000 Actuator Test canal {canal}")
        time.sleep(0.25)
        resp_kwp = self.conexion.leer_respuesta(timeout_s=1.5)

        bytes_kwp = extraer_bytes_hex(resp_kwp)
        if 0x70 in bytes_kwp:
            self._emit(f"[OK] Centralita aceptó la orden KWP2000. Activando componente ({duracion}s)...")
            diag_logger.log_transferencia(f"Actuador canal {canal} activado (KWP2000)", True)
            time.sleep(duracion)
            self.conexion.enviar_comando(f"30{canal}00", descripcion=f"KWP2000 Stop Actuator canal {canal}")
            time.sleep(0.1)
            self.conexion.leer_respuesta(timeout_s=0.5)
            return True, "Actuador ejecutado y confirmado por la centralita."

        if 0x7F in bytes_uds or 0x7F in bytes_2f or 0x7F in bytes_kwp:
            cod_err = resp_uds if 0x7F in bytes_uds else (resp_2f if 0x7F in bytes_2f else resp_kwp)
            msg = f"La centralita respondió con rechazo ({cod_err}). En motores diésel V6 EDC17, la activación de actuadores requiere condiciones de seguridad estrictas (motor apagado, contacto puesto y en algunos casos desbloqueo de seguridad)."
            diag_logger.log_alerta(msg)
            return False, msg

        msg = "Sin respuesta del módulo al comando de actuador. Esta centralita no admite test de actuadores con el contacto actual."
        diag_logger.log_alerta(msg)
        return False, msg

