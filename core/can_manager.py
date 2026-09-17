# core/can_manager.py
# ══════════════════════════════════════════════════════════════════════════════
# Manejador de bus CAN nativo para CANable / candleLight usando python-can.
# Soporta:
#   - gs_usb (driver nativo candleLight por WinUSB/libusb)
#   - slcan (puerto COM virtual de CANable)
#   - virtual (simulador local para pruebas sin coche)
# ══════════════════════════════════════════════════════════════════════════════

import time
import threading
import can
import serial.tools.list_ports
import config
from core.diagnostic_logger import diag_logger

# Configuración automática del backend libusb para Windows (CANable gs_usb)
try:
    import libusb_package
    import usb.backend.libusb1 as _libusb1
    _orig_get_backend = _libusb1.get_backend
    _libusb1.get_backend = lambda **kwargs: _orig_get_backend(
        find_library=lambda x: libusb_package.find_library('libusb-1.0')
    )
except Exception:
    pass


class CANManager:
    """
    Controlador del bus CAN a través de python-can.
    Proporciona envío y recepción de tramas CAN sin la latencia de chips ELM327.
    """

    def __init__(self, log_fn=None):
        self.bus = None
        self._log = log_fn or print
        self.bitrate = 500000  # 500 kbps (estándar bus diagnóstico Audi A6 C6)
        self.connected_interface = None
        self._lock = threading.Lock()

    def _emit(self, msg: str):
        try:
            self._log(msg)
        except Exception:
            print(msg)
        diag_logger.log_info(f"[CAN] {msg}")

    # ──────────────────────────────────────────────────────────────────────────
    #  CONEXIÓN Y DETECCIÓN
    # ──────────────────────────────────────────────────────────────────────────
    def conectar(self, interface_preference: str = "auto", bitrate: int = None) -> bool:
        """
        Conecta con el adaptador CANable probando los distintos interfaces disponibles.
        """
        if bitrate is not None:
            self.bitrate = bitrate

        self.desconectar()

        # Modo simulador
        if config.MODE == "simulado" or interface_preference == "virtual":
            return self._conectar_virtual()

        self._emit("Buscando interfaz CANable...")

        # 1. Intentar interfaz gs_usb (firmware candleLight nativo)
        if interface_preference in ("auto", "gs_usb"):
            try:
                self._emit(f"Probando conexión gs_usb (candleLight nativo a {self.bitrate // 1000} kbps)...")
                if self.bitrate in (95000, 95238):
                    # Frecuencia exacta Opel MSCAN Confort (95.238 kbps) para reloj 170MHz de CANable
                    self.bus = can.Bus(interface="gs_usb", channel=0, bitrate=500000)
                    self.bus.gs_usb.stop()
                    self.bus.gs_usb.set_timing(prop_seg=1, phase_seg1=13, phase_seg2=2, sjw=1, brp=105)
                    self.bus.gs_usb.start()
                elif self.bitrate == 125000:
                    self.bus = can.Bus(interface="gs_usb", channel=0, bitrate=500000)
                    self.bus.gs_usb.stop()
                    self.bus.gs_usb.set_timing(prop_seg=1, phase_seg1=13, phase_seg2=2, sjw=1, brp=80)
                    self.bus.gs_usb.start()
                elif self.bitrate == 33333:
                    self.bus = can.Bus(interface="gs_usb", channel=0, bitrate=500000)
                    self.bus.gs_usb.stop()
                    self.bus.gs_usb.set_timing(prop_seg=1, phase_seg1=13, phase_seg2=2, sjw=1, brp=300)
                    self.bus.gs_usb.start()
                else:
                    self.bus = can.Bus(
                        interface="gs_usb",
                        channel=0,
                        bitrate=self.bitrate
                    )
                self.connected_interface = "gs_usb"
                self._emit(f"¡Conectado exitosamente vía gs_usb ({self.bitrate // 1000} kbps)!")
                return True
            except Exception as e:
                self._emit(f"gs_usb no disponible ({e}). Probando modo slcan...")

        # 2. Intentar interfaz slcan (puerto serie virtual)
        if interface_preference in ("auto", "slcan"):
            puerto = self._buscar_puerto_canable()
            if puerto:
                try:
                    self._emit(f"Abriendo CANable en {puerto} vía slcan a {self.bitrate} bps...")
                    self.bus = can.Bus(
                        interface="slcan",
                        channel=puerto,
                        bitrate=self.bitrate,
                        rtscts=False
                    )
                    self.connected_interface = f"slcan:{puerto}"
                    self._emit(f"¡Conectado exitosamente en {puerto} vía slcan!")
                    return True
                except Exception as e:
                    self._emit(f"Fallo al abrir slcan en {puerto}: {e}")

        # 3. Fallback: probar puertos COM genéricos con slcan
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        for p in puertos:
            try:
                self._emit(f"Probando slcan en {p}...")
                self.bus = can.Bus(
                    interface="slcan",
                    channel=p,
                    bitrate=self.bitrate
                )
                self.connected_interface = f"slcan:{p}"
                self._emit(f"¡Conectado exitosamente en {p}!")
                return True
            except Exception:
                continue

        self._emit("No se detectó ningún adaptador CANable conectado.")
        return False

    def _conectar_virtual(self) -> bool:
        """Inicia un bus CAN virtual para desarrollo y simulación."""
        try:
            self._emit("Iniciando bus CAN virtual (modo simulación)...")
            self.bus = can.Bus("audi_virtual_can", interface="virtual")
            self.connected_interface = "virtual"
            self._emit("Bus virtual activo.")
            return True
        except Exception as e:
            self._emit(f"Error iniciando bus virtual: {e}")
            return False

    def _buscar_puerto_canable(self) -> str | None:
        """Busca en el Administrador de dispositivos de Windows un puerto de CANable/STM32."""
        for p in serial.tools.list_ports.comports():
            desc = f"{p.description} {p.manufacturer or ''} {p.hwid}".upper()
            if any(term in desc for term in ["CANABLE", "CANDLELIGHT", "STM32", "CAN", "SLCAN"]):
                return p.device
        return None

    def desconectar(self):
        """Cierra el bus CAN de forma limpia."""
        with self._lock:
            if self.bus is not None:
                b = self.bus
                self.bus = None
                self.connected_interface = None
                try:
                    b.__del__ = lambda: None
                    if hasattr(b, '_is_shutdown'):
                        b._is_shutdown = True
                    b.shutdown()
                except BaseException:
                    pass
                self._emit("Bus CAN desconectado.")

    @property
    def is_connected(self) -> bool:
        return self.bus is not None

    # ──────────────────────────────────────────────────────────────────────────
    #  ENVÍO Y RECEPCIÓN DE TRAMAS CAN
    # ──────────────────────────────────────────────────────────────────────────
    def send_frame(self, can_id: int, data: list[int] | bytes, is_extended: bool = False, timeout: float = 0.2) -> bool:
        """
        Transmite una trama CAN al bus en microsegundos.
        """
        if not self.bus:
            self._emit("Error: intento de enviar sin bus CAN conectado.")
            return False

        try:
            msg = can.Message(
                arbitration_id=can_id,
                data=bytes(data),
                is_extended_id=is_extended
            )
            with self._lock:
                self.bus.send(msg, timeout=timeout)
            diag_logger.log_tx(f"[{can_id:03X}] {' '.join(f'{b:02X}' for b in data)}", "CAN TX")
            return True
        except Exception as e:
            self._emit(f"Error al transmitir trama CAN 0x{can_id:03X}: {e}")
            diag_logger.log_error("Fallo CAN TX", str(e))
            return False

    def recv_frame(self, timeout: float = 0.5, expected_id: int = None) -> can.Message | None:
        """
        Lee una trama del bus CAN de forma segura. Si se especifica expected_id, descarta
        tramas de otros IDs hasta encontrar la deseada o agotar el timeout.
        """
        if not self.bus:
            return None

        start = time.perf_counter()
        while (time.perf_counter() - start) < timeout:
            remaining = timeout - (time.perf_counter() - start)
            if remaining <= 0:
                break

            try:
                with self._lock:
                    if not self.bus:
                        return None
                    msg = self.bus.recv(timeout=min(0.04, remaining))

                if msg is None:
                    continue

                diag_logger.log_rx(f"[{msg.arbitration_id:03X}] {' '.join(f'{b:02X}' for b in msg.data)}", estado="CAN RX")

                if expected_id is None or msg.arbitration_id == expected_id:
                    return msg

            except Exception as e:
                diag_logger.log_error("Fallo CAN RX", str(e))
                break

        return None

    def flush_rx(self):
        """Drena y descarta cualquier mensaje acumulado en el buffer de recepción."""
        if not self.bus:
            return
        with self._lock:
            if not self.bus:
                return
            try:
                for _ in range(50):
                    msg = self.bus.recv(timeout=0.001)
                    if msg is None:
                        break
            except Exception:
                pass
