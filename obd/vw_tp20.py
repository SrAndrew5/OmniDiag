# vw_tp20.py — VW Transport Protocol 2.0 sobre ELM327 (modo raw CAN)
# ══════════════════════════════════════════════════════════════════════════════
# Implementación basada en la documentación de ingeniería inversa de:
#   - Jared Wiltshire (jazdw.net/tp20)
#   - Proyecto ediabaslib (uholeschak/ediabaslib)
#   - Comunidad NefMoto / r/CarHacking
#
# Este módulo permite abrir canales TP 2.0 con el Gateway J533 de coches VAG
# (Audi, VW, Seat, Skoda) usando un adaptador ELM327 estándar en modo raw CAN.
#
# NOTA: El ELM327 tiene limitaciones de timing que pueden causar timeouts
# en algunos módulos. La lectura de datos funciona mejor que la escritura.
# ══════════════════════════════════════════════════════════════════════════════

import time
import threading
from core.diagnostic_logger import diag_logger


# ──────────────────────────────────────────────────────────────────────────────
#  CONSTANTES DEL PROTOCOLO VW TP 2.0
# ──────────────────────────────────────────────────────────────────────────────

# ID CAN del Gateway para channel setup (broadcast)
GATEWAY_BROADCAST_ID = 0x200

# Opcodes de Channel Setup
CS_REQUEST  = 0xC0   # Petición de apertura de canal (tester → Gateway)
CS_RESPONSE = 0xD0   # Respuesta positiva (Gateway → tester)
CS_REJECT   = 0xD6   # Respuesta negativa (Gateway → tester)

# Opcodes de Channel Parameters
CP_REQUEST  = 0xA0   # Petición de parámetros (tester → módulo)
CP_RESPONSE = 0xA1   # Respuesta de parámetros (módulo → tester)

# Opcodes de Data Transfer (nibble alto del byte de opcode)
DT_WAITING_MORE   = 0x00  # Esperando más paquetes, sin ACK
DT_WAITING_ACK    = 0x10  # Esperando más paquetes, requiere ACK
DT_LAST_NO_ACK    = 0x20  # Último paquete, sin ACK
DT_LAST_ACK       = 0x30  # Último paquete, requiere ACK

# Keep-alive / Channel Test
CT_KEEPALIVE      = 0xA3  # Ping para mantener canal vivo
CT_KEEPALIVE_RESP = 0xA1  # Respuesta al keep-alive

# Disconnect
DISCONNECT_REQ    = 0xA8  # Petición de desconexión

# Mapeo de dirección lógica del módulo → ID CAN de broadcast para channel setup
# En TP 2.0, el tester envía al ID 0x200 con la dirección lógica del módulo
# El Gateway responde desde 0x200 + dirección_lógica
MODULE_LOGICAL_ADDRESSES = {
    0x01: "Motor (ECU)",
    0x02: "Transmisión",
    0x03: "ABS / ESP",
    0x08: "Climatización",
    0x09: "Central Eléctrica / Luces",
    0x15: "Airbag",
    0x17: "Cuadro Instrumentos",
    0x19: "Gateway CAN",
    0x46: "Confort / BCM",
    0x5F: "Pantalla / MMI",
}


class TP20Channel:
    """Representa un canal TP 2.0 abierto con un módulo específico."""

    def __init__(self):
        self.is_open = False
        self.module_addr = 0x00       # Dirección lógica del módulo (ej: 0x17)
        self.tester_tx_id = 0x000     # ID CAN que usa el tester para enviar
        self.module_tx_id = 0x000     # ID CAN que usa el módulo para enviar
        self.seq_num = 0              # Contador de secuencia (0-F)
        self.block_size = 15          # Tamaño de bloque negociado
        self.t1_ms = 100              # Timeout T1 (ms) - tiempo de espera de ACK
        self.t3_ms = 5000             # Timeout T3 (ms) - tiempo de keep-alive
        self.last_activity = 0.0      # Timestamp de última actividad


class VWTP20:
    """
    Implementación del protocolo VW Transport Protocol 2.0 sobre ELM327.

    Usa el ELM327 en modo raw CAN (ATCAF0) para enviar y recibir tramas CAN
    directas sin la capa de abstracción OBD-II estándar.

    Optimizaciones aplicadas:
    - Mínimos time.sleep() entre comandos
    - Lectura directa por bytes sin esperar prompt '>'
    - Timeouts cortos y adaptativos
    - Reutilización de conexión serie sin reabrir
    """

    def __init__(self, connection, log_fn=None):
        self.conn = connection        # Objeto Connection con .puerto (serial.Serial)
        self._log = log_fn or print
        self.channel = TP20Channel()
        self._raw_mode = False        # Si ya estamos en modo raw CAN
        self._lock = threading.Lock()

    def _emit(self, msg: str):
        """Log seguro a GUI y archivo."""
        try:
            self._log(msg)
        except Exception:
            print(msg)
        diag_logger.log_info(msg)

    # ══════════════════════════════════════════════════════════════════════════
    #  CAPA DE COMUNICACIÓN RAW (ELM327 → CAN)
    # ══════════════════════════════════════════════════════════════════════════

    def _send_raw(self, cmd: str):
        """Envía un comando al ELM327 sin delays extras."""
        if self.conn.puerto is None:
            return
        self.conn.puerto.reset_input_buffer()
        self.conn.puerto.write((cmd + "\r").encode())
        diag_logger.log_tx(cmd, "TP2.0 RAW")

    def _read_raw(self, timeout_s: float = 0.3) -> str:
        """
        Lee respuesta del ELM327 optimizada para velocidad.
        Termina al encontrar '>' o al agotar timeout.
        """
        if self.conn.puerto is None:
            return ""
        buf = bytearray()
        start = time.perf_counter()
        while (time.perf_counter() - start) < timeout_s:
            avail = self.conn.puerto.in_waiting
            if avail > 0:
                chunk = self.conn.puerto.read(avail)
                buf.extend(chunk)
                if b">" in chunk:
                    break
            else:
                time.sleep(0.001)  # Mínimo sleep para no quemar CPU

        result = buf.decode(errors="ignore").replace(">", "").strip()
        if result:
            diag_logger.log_rx(result, estado="RAW")
        return result

    def _send_and_read(self, cmd: str, timeout_s: float = 0.3) -> str:
        """Envía comando y lee respuesta, optimizado para latencia mínima."""
        self._send_raw(cmd)
        return self._read_raw(timeout_s)

    def _parse_can_response(self, raw: str) -> list[tuple[int, list[int]]]:
        """
        Parsea respuestas CAN del ELM327 en modo raw (ATH1 activo).
        Formato esperado: "XXX YY ZZ WW ..." donde XXX es el ID CAN.

        Retorna lista de (can_id, [data_bytes]).
        """
        results = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("AT") or "OK" in line or "?" in line:
                continue
            if any(err in line.upper() for err in ["NO DATA", "CAN ERROR", "ERROR",
                                                    "UNABLE", "STOPPED", "BUS"]):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            try:
                can_id = int(parts[0], 16)
                data = [int(b, 16) for b in parts[1:]]
                results.append((can_id, data))
            except ValueError:
                continue

        return results

    # ══════════════════════════════════════════════════════════════════════════
    #  INICIALIZACIÓN DEL MODO RAW CAN
    # ══════════════════════════════════════════════════════════════════════════

    def _enter_raw_can_mode(self) -> bool:
        """
        Configura el ELM327 para modo raw CAN sin auto-formateo.
        Esto permite enviar y recibir tramas CAN arbitrarias.
        """
        if self._raw_mode:
            return True

        self._emit("[TP2.0] Entrando en modo RAW CAN...")

        # Secuencia de inicialización para raw CAN a 500 kbps
        init_cmds = [
            ("ATZ",     0.5,  "Reset ELM327"),
            ("ATE0",    0.1,  "Echo off"),
            ("ATL0",    0.05, "Linefeeds off"),
            ("ATS1",    0.05, "Espacios on"),
            ("ATH1",    0.05, "Headers visibles (necesario para ver IDs CAN)"),
            ("ATSP6",   0.15, "Protocolo ISO 15765-4 CAN 500k"),
            ("ATCAF0",  0.05, "Auto-formateo OFF (modo raw)"),
            ("ATAT0",   0.05, "Adaptive timing OFF (respuesta inmediata)"),
            ("ATSTFF",  0.05, "Timeout máximo del bus (para channel setup)"),
        ]

        for cmd, delay, desc in init_cmds:
            self._emit(f"  → {cmd}: {desc}")
            resp = self._send_and_read(cmd, timeout_s=1.0)
            time.sleep(delay)

            if "?" in resp or "ERROR" in resp.upper():
                self._emit(f"  ✗ Error en '{cmd}': {resp}")
                return False

        self._raw_mode = True
        self._emit("[TP2.0] Modo RAW CAN activo ✓")
        return True

    def _exit_raw_can_mode(self):
        """Restaura el ELM327 al modo OBD-II estándar."""
        if not self._raw_mode:
            return

        self._emit("[TP2.0] Restaurando modo OBD-II estándar...")
        restore_cmds = [
            "ATCAF1",   # Auto-formateo ON
            "ATAT1",    # Adaptive timing ON
            "ATST32",   # Timeout estándar
            "ATH0",     # Headers ocultos
        ]
        for cmd in restore_cmds:
            self._send_and_read(cmd, timeout_s=0.3)

        self._raw_mode = False
        self._emit("[TP2.0] Modo OBD-II restaurado ✓")

    # ══════════════════════════════════════════════════════════════════════════
    #  FASE 1: CHANNEL SETUP (Abrir canal con el Gateway)
    # ══════════════════════════════════════════════════════════════════════════

    def _channel_setup(self, module_addr: int) -> bool:
        """
        Envía la petición de apertura de canal al Gateway (ID 0x200).

        Trama de Channel Setup Request (7 bytes):
          Byte 0: Dirección lógica del módulo destino (ej: 0x17 para Cuadro)
          Byte 1: Opcode (0xC0 = Setup Request)
          Byte 2-3: ID CAN del tester para recibir (nuestro RX) — lo proponemos
          Byte 4-5: ID CAN del tester para enviar (nuestro TX) — lo proponemos
          Byte 6: Tipo de aplicación (0x01 = diagnóstico)

        Respuesta del Gateway (7 bytes):
          Byte 0: Estado (0x00 = éxito)
          Byte 1: Opcode (0xD0 = Setup Response positiva)
          Byte 2-3: ID CAN que el módulo usará para enviar (nuestro RX)
          Byte 4-5: ID CAN que el módulo usará para recibir (nuestro TX)
          Byte 6: Tipo de aplicación
        """
        module_name = MODULE_LOGICAL_ADDRESSES.get(module_addr, f"0x{module_addr:02X}")
        self._emit(f"[TP2.0] Solicitando canal con módulo {module_name} (addr: 0x{module_addr:02X})...")

        # Proponemos IDs CAN para el tester: 0x300 para RX, 0x740 para TX
        # El Gateway nos asignará los reales en su respuesta
        tester_rx_proposed = 0x0300
        tester_tx_proposed = 0x0740

        # Construir trama de channel setup
        setup_data = [
            module_addr,                         # Byte 0: dirección lógica
            CS_REQUEST,                          # Byte 1: 0xC0 = setup request
            (tester_rx_proposed >> 8) & 0xFF,     # Byte 2: RX ID high
            tester_rx_proposed & 0xFF,            # Byte 3: RX ID low
            (tester_tx_proposed >> 8) & 0xFF,     # Byte 4: TX ID high
            tester_tx_proposed & 0xFF,            # Byte 5: TX ID low
            0x01,                                # Byte 6: tipo diagnóstico
        ]

        # Configurar header para broadcast al Gateway
        self._send_and_read(f"ATSH{GATEWAY_BROADCAST_ID:03X}", timeout_s=0.2)

        # Configurar filtro para escuchar la respuesta del Gateway
        # El Gateway responde desde 0x200 + module_addr
        response_id = GATEWAY_BROADCAST_ID + module_addr
        self._send_and_read(f"ATCRA{response_id:03X}", timeout_s=0.2)

        # Enviar la trama de channel setup
        hex_data = " ".join(f"{b:02X}" for b in setup_data)
        self._emit(f"  → TX [0x{GATEWAY_BROADCAST_ID:03X}]: {hex_data}")

        resp = self._send_and_read(hex_data, timeout_s=2.0)

        if not resp or "NO DATA" in resp.upper():
            self._emit(f"  ✗ Sin respuesta del Gateway al channel setup. Posibles causas:")
            self._emit(f"    - El contacto del coche no está puesto")
            self._emit(f"    - El cable no está bien enchufado al OBD")
            self._emit(f"    - El Gateway no soporta la dirección 0x{module_addr:02X}")
            return False

        # Parsear la respuesta
        frames = self._parse_can_response(resp)
        if not frames:
            self._emit(f"  ✗ Respuesta no parseable: {resp}")
            return False

        for can_id, data in frames:
            self._emit(f"  ← RX [0x{can_id:03X}]: {' '.join(f'{b:02X}' for b in data)}")

            if len(data) < 7:
                continue

            # Verificar opcode de respuesta
            opcode = data[1]
            if opcode == CS_RESPONSE:  # 0xD0 = éxito
                # Extraer IDs CAN asignados por el Gateway
                module_tx_id = (data[2] << 8) | data[3]  # ID que el módulo usa para TX
                module_rx_id = (data[4] << 8) | data[5]  # ID que el módulo escucha (nuestro TX)

                self.channel.module_addr = module_addr
                self.channel.module_tx_id = module_tx_id  # Nosotros RX desde este ID
                self.channel.tester_tx_id = module_rx_id   # Nosotros TX a este ID

                self._emit(f"  ✓ Canal asignado!")
                self._emit(f"    Tester TX (nosotros enviamos) → 0x{module_rx_id:03X}")
                self._emit(f"    Módulo TX (nosotros recibimos) ← 0x{module_tx_id:03X}")
                return True

            elif opcode == CS_REJECT:  # 0xD6 = rechazado
                self._emit(f"  ✗ Gateway rechazó la petición de canal (opcode 0xD6)")
                return False

        self._emit(f"  ✗ Respuesta del Gateway no contiene channel setup válido")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    #  FASE 2: CHANNEL PARAMETERS (Negociar tiempos y tamaños)
    # ══════════════════════════════════════════════════════════════════════════

    def _negotiate_params(self) -> bool:
        """
        Negocia los parámetros del canal con el módulo.

        Trama de Channel Parameters Request (6 bytes):
          Byte 0: Opcode (0xA0 = Parameters Request)
          Byte 1: Block Size (cuántos paquetes puede enviar antes de esperar ACK)
          Byte 2: T1 (timeout inter-paquete en ms, codificado)
          Byte 3: T2 (no usado, 0xFF)
          Byte 4: T3 (timeout keep-alive en ms, codificado)
          Byte 5: T4 (timeout keep-alive del tester en ms, codificado)

        Codificación de tiempos: nibble alto = unidades (0=100us, 1=1ms, 2=10ms, 3=100ms)
                                 nibble bajo = valor multiplicador
        """
        self._emit("[TP2.0] Negociando parámetros del canal...")

        # Configurar headers para el canal abierto
        self._send_and_read(f"ATSH{self.channel.tester_tx_id:03X}", timeout_s=0.2)
        self._send_and_read(f"ATCRA{self.channel.module_tx_id:03X}", timeout_s=0.2)

        # Parámetros que proponemos al módulo:
        #   Block Size = 15 (0x0F): máximo de paquetes antes de ACK
        #   T1 = 0x19: 1ms × 9 = 9ms (timeout inter-paquete)
        #   T2 = 0xFF: no usado
        #   T3 = 0x31: 10ms × 1 = 10ms (keep-alive enviado por tester, lo más corto posible
        #              pero el ELM puede no llegar — usaremos 0x34 = 10ms × 4 = 40ms)
        #   T4 = 0x34: 10ms × 4 = 40ms (keep-alive esperado del módulo)
        params_data = [
            CP_REQUEST,   # 0xA0
            0x0F,         # Block Size = 15
            0x8A,         # T1 = 100ms × 10 = 1000ms (generoso para ELM327)
            0xFF,         # T2 = not used
            0x4A,         # T3 = keep-alive = 1000ms × 10 = 10s (muy generoso)
            0x4A,         # T4 = keep-alive response = 10s
        ]

        hex_data = " ".join(f"{b:02X}" for b in params_data)
        self._emit(f"  → TX [0x{self.channel.tester_tx_id:03X}]: {hex_data}")

        resp = self._send_and_read(hex_data, timeout_s=2.0)

        if not resp or "NO DATA" in resp.upper():
            self._emit("  ✗ Sin respuesta a la negociación de parámetros")
            return False

        frames = self._parse_can_response(resp)
        for can_id, data in frames:
            self._emit(f"  ← RX [0x{can_id:03X}]: {' '.join(f'{b:02X}' for b in data)}")

            if len(data) >= 6 and data[0] == CP_RESPONSE:  # 0xA1
                self.channel.block_size = data[1]

                # Decodificar T1 del módulo
                t1_raw = data[2]
                t1_unit = (t1_raw >> 4) & 0x0F
                t1_val = t1_raw & 0x0F
                t1_multipliers = {0: 0.1, 1: 1, 2: 10, 3: 100, 4: 1000}
                self.channel.t1_ms = t1_val * t1_multipliers.get(t1_unit, 1)

                # Decodificar T3 (keep-alive)
                t3_raw = data[4]
                t3_unit = (t3_raw >> 4) & 0x0F
                t3_val = t3_raw & 0x0F
                self.channel.t3_ms = t3_val * t1_multipliers.get(t3_unit, 1)

                self.channel.is_open = True
                self.channel.last_activity = time.time()
                self.channel.seq_num = 0

                self._emit(f"  ✓ Parámetros negociados!")
                self._emit(f"    Block Size: {self.channel.block_size}")
                self._emit(f"    T1 (inter-paquete): {self.channel.t1_ms}ms")
                self._emit(f"    T3 (keep-alive): {self.channel.t3_ms}ms")
                return True

        self._emit("  ✗ Respuesta de parámetros no válida")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    #  FASE 3: DATA TRANSFER (Enviar/Recibir mensajes KWP2000)
    # ══════════════════════════════════════════════════════════════════════════

    def _send_tp20_data(self, kwp_payload: list[int]) -> list[int] | None:
        """
        Envía un mensaje KWP2000 encapsulado en TP 2.0 y espera la respuesta.

        Estructura de trama de datos TP 2.0:
          Byte 0: Opcode (nibble alto) + Sequence Number (nibble bajo)
                  Opcode: 0x1N = waiting, need ACK
                          0x3N = last packet, need ACK
          Byte 1: Length (de los datos KWP en este paquete, solo si primer paquete)
          Byte 2-7: Datos KWP2000

        Para mensajes cortos (≤6 bytes KWP), todo cabe en una sola trama CAN.
        """
        if not self.channel.is_open:
            self._emit("[TP2.0] Error: canal no abierto")
            return None

        # Construir trama TP 2.0 para datos cortos (≤6 bytes)
        # Para un paquete único: opcode = 0x10 (last + need ACK) | seq_num
        if len(kwp_payload) <= 6:
            seq = self.channel.seq_num & 0x0F
            opcode_byte = DT_LAST_ACK | seq  # 0x3N

            # Trama: [opcode+seq, length, ...kwp_data...]
            frame = [opcode_byte, len(kwp_payload)] + kwp_payload

            # Padding a 8 bytes con 0x00 si es necesario
            while len(frame) < 8:
                frame.append(0x00)

            hex_data = " ".join(f"{b:02X}" for b in frame)
            self._emit(f"  → TX DATA [0x{self.channel.tester_tx_id:03X}]: {hex_data}")

            resp = self._send_and_read(hex_data, timeout_s=2.0)
            self.channel.last_activity = time.time()

            if not resp or "NO DATA" in resp.upper():
                self._emit("  ✗ Sin respuesta a datos TP 2.0")
                return None

            # Parsear la respuesta y extraer datos KWP
            return self._parse_tp20_response(resp)
        else:
            # Mensajes largos: segmentación multi-frame
            return self._send_multiframe(kwp_payload)

    def _send_multiframe(self, kwp_payload: list[int]) -> list[int] | None:
        """Envía datos KWP2000 que necesitan múltiples tramas CAN."""
        # Primer paquete: 6 bytes de datos (2 bytes de cabecera TP 2.0)
        offset = 0
        total = len(kwp_payload)
        first = True

        while offset < total:
            remaining = total - offset
            is_last = remaining <= 6 if not first else remaining <= 5

            seq = self.channel.seq_num & 0x0F

            if is_last:
                opcode_byte = DT_LAST_ACK | seq  # 0x3N
            else:
                opcode_byte = DT_WAITING_ACK | seq  # 0x1N

            if first:
                # Primer paquete incluye longitud total
                chunk_size = min(5, remaining)
                frame = [opcode_byte, total] + kwp_payload[offset:offset + chunk_size]
                offset += chunk_size
                first = False
            else:
                chunk_size = min(7, remaining)
                frame = [opcode_byte] + kwp_payload[offset:offset + chunk_size]
                offset += chunk_size

            # Padding
            while len(frame) < 8:
                frame.append(0x00)

            hex_data = " ".join(f"{b:02X}" for b in frame)
            resp = self._send_and_read(hex_data, timeout_s=1.5)

            self.channel.seq_num = (self.channel.seq_num + 1) & 0x0F
            self.channel.last_activity = time.time()

            if is_last:
                return self._parse_tp20_response(resp) if resp else None

        return None

    def _parse_tp20_response(self, raw: str) -> list[int] | None:
        """
        Parsea la respuesta TP 2.0 y extrae los datos KWP2000 del payload.
        Maneja respuestas multi-frame reconstruyendo el mensaje completo.
        """
        frames = self._parse_can_response(raw)
        if not frames:
            return None

        kwp_data = bytearray()
        total_length = 0

        for can_id, data in frames:
            if can_id != self.channel.module_tx_id or len(data) < 2:
                continue

            self._emit(f"  ← RX DATA [0x{can_id:03X}]: {' '.join(f'{b:02X}' for b in data)}")

            opcode = data[0] & 0xF0
            seq = data[0] & 0x0F

            if opcode in (DT_LAST_ACK, DT_LAST_NO_ACK):
                # Último paquete o paquete único
                if not kwp_data:  # Primer (y único) paquete
                    total_length = data[1]
                    kwp_data.extend(data[2:2 + total_length])
                else:
                    kwp_data.extend(data[1:])

                # Si requiere ACK, enviarlo
                if opcode == DT_LAST_ACK:
                    ack_byte = 0xB0 | seq  # ACK con el seq number recibido
                    ack_frame = f"{ack_byte:02X}"
                    self._send_raw(ack_frame)
                    time.sleep(0.005)
                    self._read_raw(timeout_s=0.1)

                break

            elif opcode in (DT_WAITING_ACK, DT_WAITING_MORE):
                # Paquete intermedio
                if not kwp_data:  # Primer paquete de multi-frame
                    total_length = data[1]
                    kwp_data.extend(data[2:])
                else:
                    kwp_data.extend(data[1:])

                # ACK si lo requiere
                if opcode == DT_WAITING_ACK:
                    ack_byte = 0xB0 | seq
                    ack_frame = f"{ack_byte:02X}"
                    self._send_raw(ack_frame)
                    time.sleep(0.005)

                    # Leer siguiente frame
                    next_resp = self._read_raw(timeout_s=1.5)
                    if next_resp:
                        more = self._parse_tp20_response(next_resp)
                        if more:
                            kwp_data.extend(more)

        if kwp_data:
            result = list(kwp_data[:total_length]) if total_length > 0 else list(kwp_data)
            self._emit(f"  ✓ KWP2000 recibido ({len(result)} bytes): {' '.join(f'{b:02X}' for b in result)}")
            return result

        return None

    # ══════════════════════════════════════════════════════════════════════════
    #  KEEP-ALIVE (Mantener canal vivo)
    # ══════════════════════════════════════════════════════════════════════════

    def _send_keepalive(self):
        """Envía un ping de keep-alive para evitar que el canal expire."""
        if not self.channel.is_open:
            return
        ka_frame = f"{CT_KEEPALIVE:02X}"
        self._send_raw(ka_frame)
        resp = self._read_raw(timeout_s=0.5)
        self.channel.last_activity = time.time()

    # ══════════════════════════════════════════════════════════════════════════
    #  DESCONEXIÓN
    # ══════════════════════════════════════════════════════════════════════════

    def _close_channel(self):
        """Cierra el canal TP 2.0 de forma limpia."""
        if not self.channel.is_open:
            return

        self._emit("[TP2.0] Cerrando canal...")
        disc_frame = f"{DISCONNECT_REQ:02X}"
        self._send_raw(disc_frame)
        self._read_raw(timeout_s=0.3)

        self.channel.is_open = False
        self.channel.seq_num = 0
        self._emit("[TP2.0] Canal cerrado ✓")

    # ══════════════════════════════════════════════════════════════════════════
    #  API PÚBLICA: Abrir canal + enviar KWP2000
    # ══════════════════════════════════════════════════════════════════════════

    def abrir_canal(self, module_addr: int) -> bool:
        """
        Abre un canal TP 2.0 completo con un módulo del coche.

        Args:
            module_addr: Dirección lógica del módulo (ej: 0x17 para Cuadro)

        Returns:
            True si el canal se abrió correctamente, False si falló.
        """
        with self._lock:
            # Si hay un canal abierto, cerrarlo primero
            if self.channel.is_open:
                self._close_channel()

            # Entrar en modo raw CAN
            if not self._enter_raw_can_mode():
                return False

            # Fase 1: Channel Setup
            if not self._channel_setup(module_addr):
                return False

            # Fase 2: Parameter Negotiation
            if not self._negotiate_params():
                return False

            module_name = MODULE_LOGICAL_ADDRESSES.get(module_addr, f"0x{module_addr:02X}")
            self._emit(f"[TP2.0] ═══ CANAL ABIERTO con {module_name} ═══")
            return True

    def cerrar_canal(self):
        """Cierra el canal TP 2.0 y restaura el modo OBD-II estándar."""
        with self._lock:
            self._close_channel()
            self._exit_raw_can_mode()

    def enviar_kwp(self, service_id: int, sub_data: list[int] = None) -> list[int] | None:
        """
        Envía un servicio KWP2000 por el canal TP 2.0 y devuelve la respuesta.

        Args:
            service_id: ID del servicio KWP2000 (ej: 0x1A = ReadECUIdentification)
            sub_data: Bytes adicionales del servicio (ej: [0x9B] para leer coding)

        Returns:
            Lista de bytes de respuesta KWP, o None si falla.
        """
        if not self.channel.is_open:
            self._emit("[TP2.0] Error: canal no abierto. Llama a abrir_canal() primero.")
            return None

        with self._lock:
            kwp_payload = [service_id]
            if sub_data:
                kwp_payload.extend(sub_data)

            return self._send_tp20_data(kwp_payload)

    # ══════════════════════════════════════════════════════════════════════════
    #  SERVICIOS KWP2000 PRE-CONSTRUIDOS
    # ══════════════════════════════════════════════════════════════════════════

    def leer_identificacion(self) -> dict | None:
        """
        Lee la identificación del módulo (KWP2000 Service 0x1A).
        Retorna dict con part_number, hw_version, sw_version, etc.
        """
        self._emit("[KWP] Leyendo identificación del módulo...")

        # 0x1A = ReadECUIdentification, 0x87 = todas las subids
        resp = self.enviar_kwp(0x1A, [0x87])
        if resp and len(resp) > 2 and resp[0] == 0x5A:  # 0x5A = respuesta positiva
            info = {
                "raw": resp,
                "service_ok": True,
            }
            # Intentar extraer texto ASCII del payload
            try:
                text = bytes(resp[2:]).decode("ascii", errors="replace")
                info["texto"] = text.strip()
            except Exception:
                pass
            return info

        # Intentar con sub-función 0x9B (part number + coding)
        resp = self.enviar_kwp(0x1A, [0x9B])
        if resp and len(resp) > 2 and resp[0] == 0x5A:
            return {"raw": resp, "service_ok": True}

        return None

    def leer_dtcs(self) -> list[str]:
        """
        Lee los DTCs almacenados (KWP2000 Service 0x18 / 0x19).
        Retorna lista de códigos de error en formato hexadecimal.
        """
        self._emit("[KWP] Leyendo códigos de avería (DTCs)...")

        # Service 0x18 (ReadDTCByStatus) o 0x19 (ReadDTCInfo)
        # Sub: 0x02 = reportDTCByStatusMask, Mask: 0xFF = todos
        resp = self.enviar_kwp(0x18, [0x02, 0xFF])

        if resp is None:
            # Intentar con UDS (0x19)
            resp = self.enviar_kwp(0x19, [0x02, 0xFF])

        if resp and len(resp) > 2:
            dtcs = []
            # Los DTCs vienen en grupos de 3 bytes (2 DTC + 1 status)
            positive_id = resp[0]
            if positive_id in (0x58, 0x59):  # Respuesta positiva
                payload = resp[2:]  # Saltar service ID + sub
                for i in range(0, len(payload) - 2, 3):
                    dtc_high = payload[i]
                    dtc_low = payload[i + 1]
                    status = payload[i + 2]
                    dtc_code = f"{dtc_high:02X}{dtc_low:02X}"
                    dtcs.append(f"DTC {dtc_code} (status: {status:02X})")
            return dtcs

        return []

    def borrar_dtcs(self) -> bool:
        """
        Borra todos los DTCs almacenados (KWP2000 Service 0x14 / 0x04).
        """
        self._emit("[KWP] Borrando códigos de avería...")

        # KWP2000: 0x14 = ClearDTC, 0xFF 0xFF 0xFF = todos los grupos
        resp = self.enviar_kwp(0x14, [0xFF, 0xFF, 0xFF])

        if resp and len(resp) >= 1 and resp[0] == 0x54:
            self._emit("  ✓ DTCs borrados correctamente")
            return True

        # Intentar UDS
        resp = self.enviar_kwp(0x14, [0xFF, 0xFF, 0xFF])
        if resp and len(resp) >= 1 and resp[0] == 0x54:
            self._emit("  ✓ DTCs borrados correctamente (UDS)")
            return True

        self._emit("  ✗ No se pudieron borrar los DTCs")
        return False

    def leer_coding(self) -> list[int] | None:
        """
        Lee la codificación larga del módulo.
        KWP2000: Service 0x1A sub 0x9E (ReadDataByLocalIdentifier → Coding)
        UDS: Service 0x22 DID 0x0600 (ReadDataByIdentifier → Coding)
        """
        self._emit("[KWP] Leyendo codificación del módulo...")

        # Intentar KWP2000 primero
        resp = self.enviar_kwp(0x1A, [0x9E])
        if resp and len(resp) > 2 and resp[0] == 0x5A:
            coding = resp[2:]
            self._emit(f"  ✓ Coding leído ({len(coding)} bytes): {' '.join(f'{b:02X}' for b in coding)}")
            return coding

        # Intentar con 0x9B
        resp = self.enviar_kwp(0x1A, [0x9B])
        if resp and len(resp) > 2 and resp[0] == 0x5A:
            coding = resp[2:]
            self._emit(f"  ✓ Coding leído vía 0x9B ({len(coding)} bytes)")
            return coding

        # Intentar UDS (0x22 0x06 0x00)
        resp = self.enviar_kwp(0x22, [0x06, 0x00])
        if resp and len(resp) > 3 and resp[0] == 0x62:
            coding = resp[3:]
            self._emit(f"  ✓ Coding leído vía UDS ({len(coding)} bytes)")
            return coding

        self._emit("  ✗ No se pudo leer la codificación")
        return None

    def escribir_coding(self, coding_bytes: list[int], login_code: int = 0) -> bool:
        """
        Escribe la codificación larga en el módulo.

        ADVERTENCIA: Esta operación modifica la configuración de la centralita.
        Un error puede dejar el módulo inoperable.

        Args:
            coding_bytes: Los bytes de coding a escribir.
            login_code: Código de acceso (ej: 13861 para módulo 17).

        Returns:
            True si se escribió correctamente.
        """
        self._emit("[KWP] ═══ ESCRIBIENDO CODIFICACIÓN ═══")
        self._emit(f"  Bytes: {' '.join(f'{b:02X}' for b in coding_bytes)}")

        # Paso 1: Iniciar sesión de diagnóstico extendida
        resp = self.enviar_kwp(0x10, [0x03])  # DiagnosticSessionControl → Extended
        if not resp or resp[0] != 0x50:
            self._emit("  ✗ No se pudo iniciar sesión extendida")
            return False

        # Paso 2: Security Access (Login) si se proporciona código
        if login_code > 0:
            self._emit(f"  → Login con código: {login_code}")
            # KWP2000 Security Access: 0x27 0x01 (seed request)
            resp = self.enviar_kwp(0x27, [0x01])
            if resp and resp[0] == 0x67:
                # Calcular key desde seed usando login_code
                seed = resp[2:]
                # En muchos módulos VAG, el key es simplemente el login code
                key_bytes = [
                    (login_code >> 8) & 0xFF,
                    login_code & 0xFF,
                ]
                resp = self.enviar_kwp(0x27, [0x02] + key_bytes)
                if not resp or resp[0] != 0x67:
                    self._emit("  ✗ Security Access denegado")
                    return False
                self._emit("  ✓ Security Access concedido")
            else:
                # Intentar login directo (algunos módulos VAG)
                login_bytes = [
                    (login_code >> 8) & 0xFF,
                    login_code & 0xFF,
                ]
                resp = self.enviar_kwp(0x27, [0x02] + login_bytes)

        # Paso 3: Escribir coding
        # KWP2000: 0x3B 0x9E + coding_bytes
        resp = self.enviar_kwp(0x3B, [0x9E] + coding_bytes)
        if resp and resp[0] == 0x7B:
            self._emit("  ✓ Codificación escrita correctamente (KWP)")
            return True

        # Intentar UDS: 0x2E 0x06 0x00 + coding_bytes
        resp = self.enviar_kwp(0x2E, [0x06, 0x00] + coding_bytes)
        if resp and resp[0] == 0x6E:
            self._emit("  ✓ Codificación escrita correctamente (UDS)")
            return True

        self._emit("  ✗ Error al escribir la codificación")
        return False

    # ══════════════════════════════════════════════════════════════════════════
    #  UTILIDAD: Diagnóstico rápido de un módulo
    # ══════════════════════════════════════════════════════════════════════════

    def diagnostico_rapido(self, module_addr: int) -> dict:
        """
        Realiza un diagnóstico rápido de un módulo:
        1. Abre canal TP 2.0
        2. Lee identificación
        3. Lee DTCs
        4. Lee coding
        5. Cierra canal

        Args:
            module_addr: Dirección lógica (ej: 0x17, 0x09, 0x46)

        Returns:
            dict con toda la información obtenida.
        """
        module_name = MODULE_LOGICAL_ADDRESSES.get(module_addr, f"0x{module_addr:02X}")
        self._emit(f"\n{'='*60}")
        self._emit(f"  DIAGNÓSTICO RÁPIDO: {module_name}")
        self._emit(f"{'='*60}\n")

        resultado = {
            "modulo": module_name,
            "addr": f"0x{module_addr:02X}",
            "canal_abierto": False,
            "identificacion": None,
            "dtcs": [],
            "coding": None,
            "errores": [],
        }

        try:
            # Abrir canal
            if not self.abrir_canal(module_addr):
                resultado["errores"].append("No se pudo abrir canal TP 2.0")
                return resultado
            resultado["canal_abierto"] = True

            # Leer identificación
            try:
                resultado["identificacion"] = self.leer_identificacion()
            except Exception as e:
                resultado["errores"].append(f"Error leyendo ID: {e}")

            # Leer DTCs
            try:
                resultado["dtcs"] = self.leer_dtcs()
            except Exception as e:
                resultado["errores"].append(f"Error leyendo DTCs: {e}")

            # Leer coding
            try:
                resultado["coding"] = self.leer_coding()
            except Exception as e:
                resultado["errores"].append(f"Error leyendo coding: {e}")

        finally:
            self.cerrar_canal()

        return resultado
