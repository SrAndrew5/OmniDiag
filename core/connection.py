# connection.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import serial
import serial.tools.list_ports
import time
import config
from core.fake_serial import FakeSerial
from core.diagnostic_logger import diag_logger


class Connection:
    """
    Maneja la comunicación por puerto serie con un adaptador ELM327 (real o simulado).
    Registra cada comando y respuesta en audidiag_registro_detallado.txt para soporte y diagnóstico.
    """

    def __init__(self):
        self.puerto = None

    # ──────────────────────────────────────────────────────────────────────────
    #  AUTO-DETECCIÓN
    # ──────────────────────────────────────────────────────────────────────────
    def autodetectar_puerto(self):
        """Escanea los puertos disponibles e intenta encontrar un ELM327 probando las velocidades habituales."""
        self.desconectar()
        msg = "Iniciando auto-detección de puerto OBD..."
        print(msg)
        diag_logger.log_info(msg)

        puertos_disponibles = serial.tools.list_ports.comports()
        if not puertos_disponibles:
            err = "No se encontraron puertos COM activos. Asegúrate de enchufar el cable USB."
            print(err)
            diag_logger.log_error(err)
            return None

        for p in puertos_disponibles:
            diag_logger.log_info(f"Puerto detectado en Windows: {p.device} — {p.description} [{p.hwid}]")

        velocidades = [config.BAUD_RATE, 115200, 9600, 500000]
        velocidades_unicas = list(dict.fromkeys(velocidades))

        for puerto_info in puertos_disponibles:
            for baud in velocidades_unicas:
                try:
                    diag_logger.log_info(f"Probando {puerto_info.device} a {baud} baudios...")
                    test_port = serial.Serial(puerto_info.device, baud, timeout=0.8)
                    # Pausa de estabilización tras DTR toggle para que el chip PIC inicie
                    time.sleep(0.4)
                    test_port.write(b"ATZ\r")
                    time.sleep(0.4)
                    respuesta = test_port.read_all().decode(errors="ignore")
                    test_port.close()

                    if any(kw in respuesta.upper() for kw in ["ELM327", "ELM", "OBD", ">"]):
                        ok_msg = f"Adaptador detectado en {puerto_info.device} a {baud} baudios! (Respuesta: {respuesta.strip()})"
                        print(f"¡{ok_msg}!")
                        diag_logger.log_info(ok_msg)
                        config.BAUD_RATE = baud
                        return puerto_info.device
                except Exception as e:
                    diag_logger.log_info(f"Fallo al probar {puerto_info.device}@{baud}: {e}")

        fail_msg = "No se pudo detectar el adaptador automáticamente en los puertos disponibles."
        print(fail_msg)
        diag_logger.log_warning(fail_msg)
        return None

    # ──────────────────────────────────────────────────────────────────────────
    #  CONEXIÓN
    # ──────────────────────────────────────────────────────────────────────────
    def conectar(self):
        """Abre la conexión con el adaptador ELM327 (real o simulado) y configura el protocolo CAN."""
        try:
            self.desconectar()
            if config.MODE == "simulado":
                print("Usando conexión simulada.")
                diag_logger.log_info("Conexión en modo simulado abierta.")
                self.puerto = FakeSerial(config.SERIAL_PORT, config.BAUD_RATE, timeout=2)
                return True

            puerto_objetivo = config.SERIAL_PORT
            if puerto_objetivo.upper() == "AUTO":
                puerto_objetivo = self.autodetectar_puerto()
                if not puerto_objetivo:
                    diag_logger.log_error("Imposible conectar: puerto objetivo no encontrado.")
                    return False

            diag_logger.log_info(f"Abriendo puerto serie {puerto_objetivo} a {config.BAUD_RATE} baudios...")
            self.puerto = serial.Serial(puerto_objetivo, config.BAUD_RATE, timeout=2)
            # Estabilización obligatoria para chip PIC18F25K80
            time.sleep(0.5)

            # Secuencia completa de inicialización para Audi A6 C6 (CAN 500k)
            comandos_init = [
                ("ATZ",   0.5,  "Reset del adaptador ELM327"),
                ("ATE0",  0.1,  "Desactivar eco"),
                ("ATL0",  0.05, "Desactivar saltos de línea adicionales"),
                ("ATS1",  0.05, "Espacios activados en respuestas"),
                ("ATSP6", 0.15, "Fijar protocolo ISO 15765-4 CAN 11-bit / 500 kbps"),
                ("ATAT1", 0.05, "Tiempo de respuesta adaptativo automático"),
                ("ATST32",0.05, "Ajustar timeout del bus"),
                ("ATCAF1",0.05, "Auto-formateo de tramas CAN activado"),
            ]

            for cmd, espera, desc in comandos_init:
                self.enviar_comando(cmd, descripcion=desc)
                time.sleep(espera)
                self.leer_respuesta(timeout_s=1.0)

            diag_logger.log_info(f"Conexión con el adaptador {puerto_objetivo} establecida e inicializada en CAN 500k.")
            return True

        except Exception as e:
            err_msg = f"Error al conectar puerto serie: {e}"
            print(err_msg)
            diag_logger.log_error(err_msg)
            return False

    def desconectar(self):
        """Cierra el puerto serie de forma segura."""
        if self.puerto is not None:
            try:
                diag_logger.log_info("Cerrando puerto serie...")
                self.puerto.close()
            except Exception as e:
                diag_logger.log_error("Error al cerrar puerto", str(e))
            self.puerto = None

    # ──────────────────────────────────────────────────────────────────────────
    #  VERIFICACIÓN DEL BUS CAN
    # ──────────────────────────────────────────────────────────────────────────
    def probar_comunicacion_bus(self) -> tuple[bool, str]:
        """
        Envía una petición de sondeo al bus CAN (PID 0100) para verificar
        si el vehículo responde físicamente o si el cable está desconectado.
        """
        if config.MODE == "simulado":
            return True, "Bus CAN simulado activo."

        diag_logger.log_info("Comprobando actividad en el bus CAN del vehículo...")
        self.enviar_comando("0100", descripcion="Sondeo actividad bus CAN (PID 0100)")
        time.sleep(0.3)
        resp = self.leer_respuesta(timeout_s=2.5)

        if not resp:
            msg = "Sin respuesta del bus CAN (Timeout). Revisa que la palanquita esté en posición ABAJO y el contacto puesto."
            diag_logger.log_alerta(msg)
            return False, msg

        resp_u = resp.upper()
        if "41 00" in resp_u or "4100" in resp_u:
            msg = "Bus CAN 500k detectado y respondiendo activamente."
            diag_logger.log_info(f"OK: {msg} (Resp: {resp})")
            return True, msg

        if any(err in resp_u for err in ["CAN ERROR", "BUS INIT", "UNABLE TO CONNECT", "NO DATA", "FB ERROR", "STOPPED", "ERR"]):
            msg = f"El coche no responde al bus ({resp}). Asegúrate de tener la palanquita hacia ABAJO y el contacto encendido."
            diag_logger.log_alerta(msg)
            return False, msg

        # Respuesta hexadecimal alternativa
        clean_hex = "".join(c for c in resp_u if c in "0123456789ABCDEF")
        if len(clean_hex) >= 4:
            return True, "Bus CAN respondiendo."

        msg = f"Respuesta anómala del bus: {resp}. Comprueba la palanquita (posición ABAJO)."
        diag_logger.log_alerta(msg)
        return False, msg

    # ──────────────────────────────────────────────────────────────────────────
    #  COMUNICACIÓN
    # ──────────────────────────────────────────────────────────────────────────
    def enviar_comando(self, comando: str, descripcion: str = ""):
        """
        Envía un comando AT o OBD al adaptador.
        Añade el carriage-return (\r) que el ELM327 necesita como terminador.
        """
        if self.puerto is None:
            diag_logger.log_error(f"Intento de enviar '{comando}' sin conexión abierta.")
            return False

        try:
            diag_logger.log_tx(comando, descripcion)
            self.puerto.write((comando + "\r").encode())
            return True
        except Exception as e:
            diag_logger.log_error(f"Error al enviar comando '{comando}'", str(e))
            return False

    def leer_respuesta(self, timeout_s: float = 2.0):
        """
        Lee la respuesta completa del ELM327 hasta encontrar el prompt '>'.
        Registra la respuesta cruda en el DiagnosticLogger.
        """
        if self.puerto is None:
            return None

        try:
            buffer = ""
            start = time.time()

            while (time.time() - start) < timeout_s:
                if self.puerto.in_waiting > 0:
                    byte = self.puerto.read(1).decode(errors="ignore")
                    if byte == ">":
                        break
                    buffer += byte
                else:
                    time.sleep(0.005)

            lineas = [l.strip() for l in buffer.strip().splitlines() if l.strip()]
            resultado = "\n".join(lineas) if lineas else ""
            estado = "OK" if resultado else "TIMEOUT"
            diag_logger.log_rx(resultado, estado=estado)
            return resultado

        except Exception as e:
            diag_logger.log_error("Error al leer respuesta serie", str(e))
            return None