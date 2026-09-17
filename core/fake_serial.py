"""
FakeSerial — Simula un puerto serie ELM327 en memoria.
Compatible con el nuevo leer_respuesta() de connection.py que lee
carácter a carácter hasta encontrar el prompt '>'.
"""
import time

RESPUESTAS_FIJAS = {
    "0100": "40 00 BE 1F A8 13",
    "0101": "41 01 00 07 E5 00",   # MIL status
    "0104": "41 04 7F",            # Carga motor
    "0105": "41 05 57",            # Temp refrigerante
    "010A": "41 0A 32",            # Presión combustible
    "010B": "41 0B 64",            # Presión admisión
    "010C": "41 0C 1A F8",         # RPM
    "010D": "41 0D 3C",            # Velocidad
    "010F": "41 0F 46",            # Temp admisión
    "0110": "41 10 03 A0",         # MAF
    "0111": "41 11 CC",            # Mariposa
    "0120": "40 20 90 15 80 10",
    "0123": "41 23 03 20",         # Rail
    "0140": "40 40 00 00 00 01",
    "0142": "41 42 34 40",         # Voltaje
    "015C": "41 5C 5A",            # Temp aceite
    "0160": "40 60 00 00 00 00",
    "0180": "40 80 00 00 00 00",
    "04":   "44",                  # Clear DTCs genérico
    "0902": "49 02 01 57 41 55 5A 5A 5A 34 47 37 42 4E 30 30 30 30 30 30",  # VIN WAUZZZ4G7BN000000
    # UDS estándar
    "190209":   "59 02 FF 00",
    "14FFFFFF": "54",
    "220600":   "62 06 00 0A 00 FF 13 44 10 00 A2",
    "2701":     "67 01 CA FE",
}


class FakeSerial:
    """
    Imita serial.Serial para pruebas sin hardware.
    Soporta in_waiting y read(n) para el lector basado en prompt '>'.
    """

    def __init__(self, port, baudrate, timeout=1):
        self.port     = port
        self.baudrate = baudrate
        self.timeout  = timeout
        self._buffer  = b""
        print(f"[FakeSerial] Conexión simulada abierta en {port} a {baudrate} baudios.")

    @property
    def in_waiting(self) -> int:
        return len(self._buffer)

    def write(self, datos_bytes: bytes):
        comando = datos_bytes.decode(errors="ignore").strip().upper()
        # Eliminar espacios si los tiene el comando
        comando_limpio = comando.replace(" ", "")

        # 1. Comandos AT
        if comando_limpio.startswith("AT"):
            if comando_limpio == "ATZ":
                resp = "ELM327 v1.5\r\nOK"
            else:
                resp = "OK"
            self._buffer = (resp + "\r\n>").encode()
            return

        # 2. Respuestas fijas conocidas
        if comando_limpio in RESPUESTAS_FIJAS:
            self._buffer = (RESPUESTAS_FIJAS[comando_limpio] + "\r\n>").encode()
            return

        # 3. Protocolos UDS dinámicos
        # Servicio 0x2E: WriteDataByIdentifier (ej. 2E0600... para Long Coding)
        if comando_limpio.startswith("2E") and len(comando_limpio) >= 6:
            did = comando_limpio[2:6]
            self._buffer = f"6E {did[:2]} {did[2:]}\r\n>".encode()
            return

        # Servicio 0x22: ReadDataByIdentifier
        if comando_limpio.startswith("22") and len(comando_limpio) >= 6:
            did = comando_limpio[2:6]
            self._buffer = f"62 {did[:2]} {did[2:]} 00 00\r\n>".encode()
            return

        # Servicio 0x27: SecurityAccess (enviar key 2702...)
        if comando_limpio.startswith("2702"):
            self._buffer = b"67 02 00\r\n>"
            return

        # Servicio 0x31: RoutineControl (Actuadores 3101..., 3102...)
        if comando_limpio.startswith("31"):
            self._buffer = b"71 01 01\r\n>"
            return

        # Servicio 0x14: ClearDiagnosticInformation
        if comando_limpio.startswith("14"):
            self._buffer = b"54\r\n>"
            return

        # Servicio 0x19: ReadDTCInformation
        if comando_limpio.startswith("19"):
            self._buffer = b"59 02 FF 00\r\n>"
            return

        # Default: NO DATA
        self._buffer = b"NO DATA\r\n>"

    def read(self, n: int = 1) -> bytes:
        if not self._buffer:
            time.sleep(0.005)
            return b""
        chunk = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return chunk

    def read_all(self) -> bytes:
        data = self._buffer
        self._buffer = b""
        return data

    def readline(self) -> bytes:
        time.sleep(0.02)
        idx = self._buffer.find(b"\n")
        if idx >= 0:
            line = self._buffer[:idx + 1]
            self._buffer = self._buffer[idx + 1:]
            return line
        data = self._buffer
        self._buffer = b""
        return data

    def close(self):
        print("[FakeSerial] Conexión simulada cerrada.")