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
    0x07: "Cuadro Instrumentos J285 (A6 C6 Facelift)",
    0x08: "Climatización",
    0x09: "Central Eléctrica / Luces (J519)",
    0x15: "Airbag",
    0x17: "Cuadro Instrumentos (J285)",
    0x19: "Gateway CAN (J533)",
    0x42: "Puerta Conductor (J386)",
    0x46: "Confort / BCM (J393)",
    0x52: "Puerta Copiloto (J387)",
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

    # Módulos que cuelgan de un bus secundario detrás del Gateway J533 (CAN Confort,
    # Kombi, etc.). El Gateway tiene que despertarlos antes de contestar, por lo que
    # necesitan más margen de espera que los módulos del bus de diagnóstico.
    SECONDARY_BUS_MODULES = (0x08, 0x09, 0x15, 0x17, 0x42, 0x46, 0x52, 0x53, 0x5F)

    def __init__(self, can_mgr: CANManager, timeout: float = 0.8, debug: bool = False,
                 trace_fn=None, progress_fn=None):
        self.can = can_mgr
        self.timeout = timeout
        self.debug = debug
        self._trace_fn = trace_fn
        self._progress_fn = progress_fn

        self.rx_addr = 0x300
        self.tx_addr = 0x000
        self.tx_seq = 0
        self.rx_seq = 0
        self.is_channel_open = False
        self.current_module = None

        # Último motivo de fallo al abrir canal (para poder informarlo al usuario)
        self.last_setup_error: Optional[str] = None
        # Tramas CAN de otros módulos vistas durante los Channel Setup (si es 0, el
        # bus del coche estaba en silencio: síntoma claro de contacto apagado)
        self.rx_foreign = 0
        # Tramas de datos recibidas mientras se esperaba un ACK (pueden ser la
        # respuesta retransmitida por el módulo)
        self._pending_frames: List[Tuple[int, bytes]] = []

        self._keepalive_stop = threading.Event()
        self._keepalive_thread = None

    def _log(self, msg: str):
        if self.debug:
            print(f"[TP2.0] {msg}")
        diag_logger.log_info(f"[TP2.0] {msg}")

    # ──────────────────────────────────────────────────────────────────────────
    #  TRAZAS Y ACCESO AL BUS
    # ──────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _hex(data) -> str:
        return " ".join(f"{b:02X}" for b in data)

    def _trace(self, mensaje: str):
        """Traza de bajo nivel: tramas CAN, opcodes, ACKs, reintentos."""
        if self.debug:
            print(f"[TP2.0] {mensaje}")
        if self._trace_fn is not None:
            try:
                self._trace_fn(mensaje)
            except Exception:
                pass
        try:
            diag_logger.log_debug(f"[TP2.0] {mensaje}")
        except Exception:
            pass

    def _progress(self, mensaje: str):
        """
        Mensaje de progreso pensado para el usuario (consola).
        Sirve para que un escaneo con módulos que no responden no parezca colgado.
        """
        if self._progress_fn is not None:
            try:
                self._progress_fn(mensaje)
                return
            except Exception:
                pass
        self._trace(mensaje)

    def _send_frame(self, can_id: int, data: bytes) -> bool:
        self._trace(f"TX [0x{can_id:03X}] {self._hex(data)}")
        return self.can.send_frame(can_id, data)

    def _recv_frame(self, timeout: float, expected_id: Optional[int] = None, trace: bool = True):
        msg = self.can.recv_frame(timeout=timeout, expected_id=expected_id)
        if msg is not None and trace:
            self._trace(f"RX [0x{msg.arbitration_id:03X}] {self._hex(bytes(msg.data))}")
        return msg

    def _next_rx(self, timeout: float):
        """Devuelve la siguiente trama del canal como (can_id, bytes) o None."""
        if self._pending_frames:
            return self._pending_frames.pop(0)
        msg = self._recv_frame(timeout=timeout, expected_id=self.rx_addr)
        if msg is None:
            return None
        return (msg.arbitration_id, bytes(msg.data))

    def resync_rx(self):
        """
        Descarta tramas residuales del canal sin tocar los contadores de secuencia.
        Se usa tras una respuesta negativa para que la siguiente petición no se
        confunda con la respuesta anterior.
        """
        self._pending_frames.clear()
        self.can.flush_rx()

    def open_channel(self, module_addr: int, retries: int = 1,
                     attempts: Optional[int] = None,
                     setup_timeout: Optional[float] = None) -> bool:
        """
        Abre un canal de diagnóstico con la centralita solicitada.
        Transmite al broadcast 0x200 y espera respuesta en 0x200 + module_addr o 0x200.
        Optimizado para evitar bloqueos del bus CAN y saturación de la pasarela J533.
        """
        self.close_channel()
        mod_name = LOGICAL_MODULES.get(module_addr, f"0x{module_addr:02X}")
        self._log(f"Abriendo canal TP 2.0 con {mod_name} (0x{module_addr:02X})...")
        self.last_setup_error = None

        # Módulos en buses secundarios (Kombi, Confort) requieren algo más de margen para
        # que el Gateway responda, pero sin eternizarse: si el bus está dormido no contesta
        # ni en 6 s, y al usuario le parece que el programa se ha colgado.
        if module_addr in self.SECONDARY_BUS_MODULES:
            timeout_to_use = 1.5
        else:
            timeout_to_use = 0.8
        if setup_timeout is not None:
            timeout_to_use = setup_timeout
        max_attempts = attempts if attempts is not None else max(retries, 2)

        resp_id = BROADCAST_ADDR + module_addr

        for attempt in range(1, max_attempts + 1):
            self.can.flush_rx()
            self._pending_frames.clear()

            # Probar payload estándar o alternativo según intento
            if attempt % 2 == 1:
                setup_payload = bytes([module_addr, 0xC0, 0x00, 0x10, 0x00, 0x03, 0x01])
            else:
                setup_payload = bytes([module_addr, 0xC0, 0x00, 0x03, 0x40, 0x07, 0x01])

            self._progress(f"Intento {attempt}/{max_attempts} con {mod_name}: "
                           f"Channel Setup (espera {timeout_to_use * 1000:.0f} ms)...")

            if not self._send_frame(BROADCAST_ADDR, setup_payload):
                self.last_setup_error = "No se pudo transmitir la trama de Channel Setup (bus CAN no disponible)."
                continue

            msg = None
            rechazo = None
            ajenas = 0
            start_wait = time.perf_counter()
            while (time.perf_counter() - start_wait) < timeout_to_use:
                rem = timeout_to_use - (time.perf_counter() - start_wait)
                if rem <= 0:
                    break
                m = self._recv_frame(timeout=min(0.1, rem), expected_id=None, trace=False)
                if m is None or len(m.data) < 2:
                    continue
                if m.arbitration_id not in (resp_id, BROADCAST_ADDR):
                    ajenas += 1
                    self.rx_foreign += 1
                    continue
                self._trace(f"RX [0x{m.arbitration_id:03X}] {self._hex(bytes(m.data))}")

                if m.data[1] == 0xC0:
                    # Eco de nuestra propia petición devuelto por el adaptador: se ignora
                    self._trace("(eco de nuestra propia petición de Channel Setup)")
                    continue

                opcode = m.data[1] & 0xF0
                if opcode == 0xD0 and len(m.data) >= 7:
                    msg = m
                    break
                if opcode in (0xD6, 0xD7, 0xD8):
                    rechazo = self._hex(bytes(m.data))
                    break

            if rechazo is not None:
                self.last_setup_error = (
                    f"El Gateway J533 rechazó el canal de {mod_name} (0x{module_addr:02X}) con una "
                    f"respuesta negativa TP 2.0: [{rechazo}]. Esa dirección lógica no está disponible "
                    f"en este gateway (módulo no instalado, bus secundario sin alimentación o "
                    f"dirección incorrecta)."
                )
                self._log(self.last_setup_error)
                return False

            if msg is None or len(msg.data) < 7:
                self._trace(f"Sin respuesta de Channel Setup en 0x{resp_id:03X} "
                            f"({ajenas} tramas de otros IDs descartadas)")
                self._progress(f"  ↳ sin respuesta en 0x{resp_id:03X} "
                               f"(intento {attempt}/{max_attempts})")
                if attempt == 1:
                    # Intento de despertar la centralita dormida antes del siguiente intento
                    self._wake_module(module_addr, mod_name)
                if attempt < max_attempts:
                    time.sleep(0.1)
                continue

            status, rx, tx, _app = struct.unpack("<xBHHB", bytes(msg.data[:7]))
            if status != 0xD0:
                self.last_setup_error = (f"Respuesta de Channel Setup inválida de {mod_name}: "
                                         f"opcode 0x{status:02X} (se esperaba 0xD0).")
                self._log(self.last_setup_error)
                return False

            self.rx_addr = rx  # ID CAN por el que transmite el módulo (nosotros recibimos)
            self.tx_addr = tx  # ID CAN al que escucha el módulo (nosotros transmitimos)
            self.current_module = module_addr
            self.is_channel_open = True
            self._log(f"Canal asignado: TX -> 0x{self.tx_addr:03X} | RX <- 0x{self.rx_addr:03X}")

            # Negociación de parámetros de tiempo (Parameters Request)
            if not self._negotiate_parameters():
                self.last_setup_error = (
                    f"{mod_name} aceptó el canal pero no respondió a la negociación de "
                    f"parámetros TP 2.0 (0xA0/0xA1)."
                )
                self._log(self.last_setup_error)
                self.close_channel()
                return False

            self.tx_seq = 0
            self.rx_seq = 0
            self._pending_frames.clear()
            self.is_channel_open = True
            self._log(f"¡Canal TP 2.0 establecido con éxito con {mod_name}!")

            # Iniciar hilo de Keep-Alive para evitar que la sesión caduque
            self._start_keepalive()
            return True

        self.last_setup_error = (
            f"Sin respuesta del Gateway J533 ni de {mod_name} (0x{module_addr:02X}) tras "
            f"{max_attempts} intentos de {timeout_to_use * 1000:.0f} ms. Causas típicas: "
            f"contacto no está en posición II con el cuadro iluminado, centralita dormida en "
            f"el bus Confort por batería baja (Load Shedding del BEM/J644 si < 12 V), o "
            f"dirección lógica incorrecta. Conecta un cargador de batería y repite."
        )
        self._log(self.last_setup_error)
        return False

    def _negotiate_parameters(self) -> bool:
        """Negocia BlockSize/T1/T3 con el módulo (0xA0 -> 0xA1)."""
        param_req = b"\xa0\x0f\x8a\xff\x0a\xff"
        if not self._send_frame(self.tx_addr, param_req):
            self._log("Fallo al enviar Parameters Request.")
            return False

        deadline = time.perf_counter() + 0.8
        while time.perf_counter() < deadline:
            restante = max(0.01, deadline - time.perf_counter())
            resp = self._recv_frame(timeout=min(0.2, restante), expected_id=self.rx_addr)
            if resp is None or len(resp.data) == 0:
                continue
            if resp.data[0] == 0xA1 and len(resp.data) >= 2:
                return True
            if resp.data[0] == 0xA8:
                self._trace("El módulo devolvió 0xA8 (desconexión) durante la negociación")
                return False

        self._log("Fallo en negociación de parámetros TP 2.0")
        return False

    def _wake_module(self, module_addr: int, mod_name: str):
        """
        Intenta despertar una centralita dormida enviando un paquete Broadcast TP 2.0
        (opcode 0x23) con TesterPresent (0x3E). Los broadcast no llevan ACK: se
        repiten 5 veces según la especificación.
        """
        wake = bytes([module_addr, 0x23, 0x3E, 0x00, 0x00, 0x00, 0x00])
        self._trace(f"Wake-up Broadcast (0x23 TesterPresent) hacia {mod_name}...")
        for _ in range(5):
            try:
                self.can.send_frame(BROADCAST_ADDR, wake)
            except Exception:
                pass
            time.sleep(0.02)

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
                # 0xA8 = Desconexión: el módulo contesta con otro 0xA8.
                # Esperar esa confirmación deja el canal libre en el Gateway para el
                # siguiente módulo (si no, el J533 puede rechazar el nuevo canal).
                self._send_frame(self.tx_addr, b"\xa8")
                deadline = time.perf_counter() + 0.25
                while time.perf_counter() < deadline:
                    resp = self._recv_frame(timeout=0.1, expected_id=self.rx_addr)
                    if resp and len(resp.data) >= 1:
                        if (resp.data[0] & 0xF0) == 0xA0:
                            break
            except Exception:
                pass

        self.is_channel_open = False
        self.current_module = None
        self.tx_seq = 0
        self.rx_seq = 0
        self._pending_frames.clear()
        self.can.flush_rx()

    def wait_for_ack(self, timeout: Optional[float] = None):
        """
        Espera el ACK del módulo para la última trama enviada.

        TP 2.0 define dos ACK distintos y el segundo NO es un error:
          0xBn = ACK listo para más datos.
          0x9n = ACK pero SIN disponibilidad para más datos (ECU ocupada, por ejemplo
                 mientras procesa un cambio de sesión). Abortar aquí desincroniza los
                 contadores de secuencia y rompe el resto de la sesión.
        """
        t1 = timeout if timeout is not None else max(self.timeout, 1.0)
        deadline = time.perf_counter() + t1
        expected_ack = 0xB0 | ((self.tx_seq + 1) & 0xF)
        ultima_trama = None

        while time.perf_counter() < deadline:
            restante = max(0.01, deadline - time.perf_counter())
            msg = self._recv_frame(timeout=min(0.1, restante), expected_id=self.rx_addr)
            if msg is None or len(msg.data) == 0:
                continue

            primero = msg.data[0]
            opcode = primero >> 4
            seq = primero & 0x0F
            ultima_trama = primero

            if opcode == 0xB:
                if primero != expected_ack:
                    self._trace(f"ACK fuera de secuencia (0x{primero:02X}, esperado "
                                f"0x{expected_ack:02X}); se resincroniza el contador")
                    self.tx_seq = (seq - 1) & 0x0F
                return

            if opcode == 0x9:
                self._trace(f"ECU ocupada: ACK 0x{primero:02X} sin disponibilidad; se sigue esperando")
                time.sleep(0.02)
                continue

            if opcode in (0x0, 0x1, 0x2, 0x3):
                # Respuesta retransmitida o que llegó antes de tiempo: se reserva
                self._pending_frames.append((msg.arbitration_id, bytes(msg.data)))
                continue

            self._trace(f"Trama no esperada mientras se aguardaba ACK: 0x{primero:02X}")

        detalle = f" (última trama vista: 0x{ultima_trama:02X})" if ultima_trama is not None else ""
        raise TP20TimeoutError(f"Timeout esperando ACK de TP 2.0{detalle}")

    def send_ack(self):
        """Envía ACK al módulo con la secuencia de la trama recibida + 1."""
        ack_byte = 0xB0 | ((self.rx_seq + 1) & 0xF)
        self._send_frame(self.tx_addr, bytes([ack_byte]))

    def send_data(self, payload: bytes):
        """
        Envía un payload de datos KWP2000 dividiéndolo en tramas CAN de 8 bytes.
        """
        if not self.is_channel_open:
            raise RuntimeError("Canal TP 2.0 no abierto.")

        # Las tramas residuales de una respuesta anterior no deben mezclarse con ésta
        self._pending_frames.clear()

        full_data = struct.pack(">H", len(payload)) + payload

        while full_data:
            last = len(full_data) <= 7
            header_byte = (0x10 if last else 0x20) | (self.tx_seq & 0xF)
            chunk = bytes([header_byte]) + full_data[:7]

            if not self._send_frame(self.tx_addr, chunk):
                raise RuntimeError("Error transmitiendo trama de datos TP 2.0")

            if last:
                intentos = 0
                while True:
                    intentos += 1
                    try:
                        self.wait_for_ack()
                        break
                    except TP20TimeoutError:
                        if intentos >= 2:
                            raise
                        # Se reenvía la MISMA trama con la MISMA secuencia
                        self._trace("Sin ACK: se reenvía la misma trama (misma secuencia)")
                        if not self._send_frame(self.tx_addr, chunk):
                            raise RuntimeError("Error retransmitiendo trama de datos TP 2.0")

            self.tx_seq = (self.tx_seq + 1) & 0xF
            full_data = full_data[7:]

    def recv_data(self, timeout: Optional[float] = None) -> bytes:
        """
        Recibe tramas de datos del módulo y reconstruye el payload KWP2000 completo.
        """
        if not self.is_channel_open:
            raise RuntimeError("Canal TP 2.0 no abierto.")

        total = timeout if timeout is not None else max(self.timeout, 1.0) * 2
        collected = bytearray()
        start = time.perf_counter()

        while (time.perf_counter() - start) < total:
            frame = self._next_rx(timeout=0.3)
            if frame is None:
                continue
            _can_id, data = frame
            if len(data) == 0:
                continue

            first_byte = data[0]
            opcode = first_byte >> 4
            seq = first_byte & 0xF

            # Opcodes de transferencia de datos en TP 2.0:
            # 0x0 = esperando ACK, quedan paquetes
            # 0x1 = esperando ACK, último paquete
            # 0x2 = sin ACK, quedan paquetes
            # 0x3 = sin ACK, último paquete
            # 0x9/0xB = ACK; 0xA1/0xA3/0xA8 = parámetros/keep-alive/desconexión -> ignorar
            if opcode not in (0x0, 0x1, 0x2, 0x3):
                self._trace(f"Trama ignorada en el flujo de datos: 0x{first_byte:02X}")
                continue

            self.rx_seq = seq
            collected.extend(data[1:])

            # Hay que confirmar los bloques que esperan ACK (0x0 y el último 0x1)
            if opcode in (0x0, 0x1):
                self.send_ack()

            if opcode in (0x1, 0x3):
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
        self.last_read_source: Optional[str] = None
        self.last_read_error: Optional[str] = None
        self.last_session: Optional[int] = None

    def execute_service(self, service_id: int, subfunction: Optional[int] = None, data: bytes = b"") -> bytes:
        """Ejecuta un servicio KWP2000 y valida la respuesta."""
        req = bytes([service_id])
        if subfunction is not None:
            req += bytes([subfunction])
        if data:
            req += data

        self.transport.send_data(req)
        resp = self.transport.recv_data()

        # NRC 0x78 = requestCorrectlyReceived-ResponsePending: la ECU pide más tiempo
        # y enviará la respuesta definitiva en otra trama.
        intentos_pendiente = 0
        while (resp and len(resp) >= 3 and resp[0] == 0x7F and resp[2] == 0x78
               and intentos_pendiente < 5):
            intentos_pendiente += 1
            diag_logger.log_debug("[KWP] ECU ocupada (NRC 0x78 responsePending); "
                                  "esperando respuesta final...")
            try:
                resp = self.transport.recv_data(timeout=2.0)
            except TP20TimeoutError:
                raise KWPError("Timeout esperando la respuesta final tras un NRC 0x78")

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
            self.last_session = None
            return True

        sessions_to_try = [session_type]
        for s_cand in (0x03, 0x86, 0x89, 0x01):
            if s_cand not in sessions_to_try:
                sessions_to_try.append(s_cand)

        for s in sessions_to_try:
            try:
                self.execute_service(0x10, subfunction=s)
                self.last_session = s
                diag_logger.log_info(f"[KWP] Sesión diagnóstica 0x{s:02X} aceptada.")
                return True
            except KWPError as e:
                diag_logger.log_debug(f"[KWP] Sesión 0x{s:02X} rechazada: {e}")
                # NRC 0x11, 0x12, 0x31, 0x33 (security/not supported), 0x22, 0x7E, 0x7F
                if e.nrc in (0x11, 0x12, 0x22, 0x31, 0x33, 0x7E, 0x7F):
                    self.transport.resync_rx()
                    continue
                else:
                    break
            except Exception as e:
                diag_logger.log_debug(f"[KWP] Sesión 0x{s:02X} sin respuesta válida: {e}")
                self.transport.resync_rx()
                break

        # Si la centralita no requiere sesión especial, continúa en su sesión por defecto
        self.last_session = None
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
        Lee códigos de avería almacenados en la ECU.
        Prueba únicamente los 2 servicios oficiales VAG KWP2000:
        1. Service 0x18 sub 0x02 (ReadDtcByStatus All) -> 18 02 FF
        2. Service 0x13 (ReadDiagnosticTroubleCodesByStatus) -> 13 FF FF
        Si la ECU no soporta lectura de DTCs o no contesta, aborta de inmediato
        sin colgar la sesión.
        """
        resp = None
        attempts = [
            (0x18, 0x02, b"\xff"),  # Estándar oficial VAG KWP2000
            (0x13, None, b"\xff\xff"),  # Alternativa estándar KWP
        ]

        for sid, subfn, data in attempts:
            try:
                resp = self.execute_service(sid, subfunction=subfn, data=data)
                if resp is not None and len(resp) >= 2:
                    break
            except Exception:
                self.transport.resync_rx()
                break  # Si el primer intento falla, no seguir reintentando en bucle

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

        Devuelve None si ninguna vía funciona y deja el motivo en self.last_read_error.
        Ningún fallo de una vía debe abortar las demás: cada intento se aísla.
        """
        self.last_read_source = None
        self.last_read_error = None
        errores: List[str] = []

        for subfn in (0x9E, 0x9A, 0x9B, 0x80, 0x91):
            try:
                resp = self.execute_service(0x1A, subfunction=subfn)
                if not resp:
                    errores.append(f"1A {subfn:02X}: respuesta vacía")
                    continue

                if subfn in (0x9E, 0x9A):
                    coding = resp[1:] if (len(resp) > 1 and resp[0] == subfn) else resp
                    if len(coding) >= 1:
                        diag_logger.log_info(
                            f"[KWP] Codificación leída vía 0x1A 0x{subfn:02X} ({len(coding)} bytes): {coding.hex()}"
                        )
                        self.last_read_source = f"0x1A 0x{subfn:02X}"
                        return bytes(coding)
                    errores.append(f"1A {subfn:02X}: respuesta sin bytes de codificación")
                    continue

                if len(resp) >= 18:
                    coding_len = resp[17]
                    if 1 <= coding_len <= 32 and (18 + coding_len) <= len(resp):
                        coding_bytes = resp[18:18 + coding_len]
                        diag_logger.log_info(
                            f"[KWP] Codificación leída ({coding_len} bytes) en 0x1A 0x{subfn:02X}: "
                            f"{coding_bytes.hex()}"
                        )
                        self.last_read_source = f"0x1A 0x{subfn:02X}"
                        return bytes(coding_bytes)
                errores.append(f"1A {subfn:02X}: respuesta sin bloque de codificación reconocible")

            except KWPError as e:
                errores.append(f"1A {subfn:02X}: {e}")
                diag_logger.log_debug(f"[KWP] Lectura 0x1A sub 0x{subfn:02X} rechazada: {e}")
                # Tras una respuesta negativa conviene limpiar lo que quede en el canal
                self.transport.resync_rx()
                continue
            except Exception as e:
                errores.append(f"1A {subfn:02X}: {e}")
                diag_logger.log_debug(f"[KWP] Lectura 0x1A sub 0x{subfn:02X} sin respuesta: {e}")
                self.transport.resync_rx()
                continue

        # Fallback a lectura por identificador UDS / KWP si estuviese disponible
        for did in (0x0600, 0x0601, 0xF1A0):
            try:
                resp = self.execute_service(0x22, subfunction=None,
                                            data=bytes([did >> 8, did & 0xFF]))
                if resp and len(resp) >= 3:
                    # Respuesta 0x62: [DID_hi, DID_lo, datos...]
                    data = resp[2:]
                    if len(data) >= 1:
                        diag_logger.log_info(
                            f"[KWP] Codificación leída vía 0x22 DID 0x{did:04X}: {data.hex()}"
                        )
                        self.last_read_source = f"0x22 0x{did:04X}"
                        return bytes(data)
                errores.append(f"22 {did:04X}: respuesta vacía o demasiado corta")
            except KWPError as e:
                errores.append(f"22 {did:04X}: {e}")
                diag_logger.log_debug(f"[KWP] Lectura 0x22 DID 0x{did:04X} rechazada: {e}")
                self.transport.resync_rx()
                continue
            except Exception as e:
                errores.append(f"22 {did:04X}: {e}")
                diag_logger.log_debug(f"[KWP] Lectura 0x22 DID 0x{did:04X} sin respuesta: {e}")
                self.transport.resync_rx()
                continue

        self.last_read_error = " | ".join(errores)
        diag_logger.log_debug(f"[KWP] No se pudo leer el coding: {self.last_read_error}")
        return None

    def write_coding(self, coding_bytes: bytes) -> bool:
        """
        Escribe la codificación en el módulo adaptándose al tipo de centralita:
        1. Si se leyó vía UDS (0x22 DID 0x0600/0x0601), escribe con Service 0x2E (WriteDataByIdentifier).
        2. Si es KWP2000 Long Coding, escribe con Service 0x3B subfunción 0x9A.
        3. Si es KWP2000 estándar, escribe con Service 0x3B subfunción 0x9E.
        """
        # Si la lectura provino de UDS DID 0x0600 (como las puertas del Facelift o Cuadro), priorizar UDS 0x2E
        if self.last_read_source and "0x22" in self.last_read_source:
            did = 0x0600 if "0600" in self.last_read_source else 0x0601
            payload = bytes([did >> 8, did & 0xFF]) + coding_bytes
            try:
                resp = self.execute_service(0x2E, subfunction=None, data=payload)
                if resp is not None:
                    diag_logger.log_info(f"[UDS-TP2.0] Codificación escrita con Service 0x2E DID 0x{did:04X}.")
                    return True
            except Exception as e:
                diag_logger.log_debug(f"[UDS-TP2.0] Escritura 0x2E directa rechazada ({e}), probando Sesión de Taller 0x89 con WSC...")
                # Reintento quirúrgico oficial VAG: Sesión de Taller 0x89 + registro de WSC (DID 0xF198)
                try:
                    self.execute_service(0x10, subfunction=0x89)
                    time.sleep(0.05)
                    wsc_def = bytes([0x0B, 0x07, 0xBC, 0x78, 0x01, 0xBD])
                    try:
                        self.execute_service(0x2E, data=b"\xF1\x98" + wsc_def)
                    except Exception:
                        pass
                    resp_wsc = self.execute_service(0x2E, subfunction=None, data=payload)
                    if resp_wsc is not None:
                        diag_logger.log_info("[UDS-TP2.0] Codificación aceptada bajo Sesión 0x89 con huella WSC.")
                        return True
                except Exception as e2:
                    diag_logger.log_debug(f"[UDS-TP2.0] Intento 0x89 con WSC rechazado ({e2}), probando KWP 0x3B...")

        # Vías KWP2000
        for subfn in (0x9E, 0x9A):
            try:
                resp = self.execute_service(0x3B, subfunction=subfn, data=coding_bytes)
                if resp is not None:
                    diag_logger.log_info(f"[KWP] Codificación escrita correctamente con Service 0x3B sub 0x{subfn:02X}.")
                    return True
            except KWPError as e:
                diag_logger.log_debug(f"[KWP] Escritura 0x3B sub 0x{subfn:02X} rechazada: {e}")
            except Exception as e:
                diag_logger.log_error(f"Fallo escribiendo coding KWP (0x3B 0x{subfn:02X})", str(e))

        # Fallback de seguridad: si KWP falló y no habíamos probado 0x2E, intentarlo como último recurso
        if not (self.last_read_source and "0x22" in self.last_read_source):
            try:
                payload = bytes([0x06, 0x00]) + coding_bytes
                resp = self.execute_service(0x2E, subfunction=None, data=payload)
                if resp is not None:
                    diag_logger.log_info("[UDS-TP2.0] Codificación escrita con Service 0x2E DID 0x0600 (fallback).")
                    return True
            except Exception:
                pass

        return False


