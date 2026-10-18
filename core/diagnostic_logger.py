# diagnostic_logger.py
import os
from datetime import datetime
import threading

import config

# Tamaño máximo del archivo de log antes de rotar (10 MB)
MAX_LOG_BYTES = 10 * 1024 * 1024


class DiagnosticLogger:
    """
    Gestiona el archivo de registro detallado (.txt) de AudiDiag Pro.
    Escribe de forma inmediata (flush) en disco cada acción del usuario,
    cada comando serie enviado ([TX]), cada respuesta recibida del vehículo ([RX])
    y el estado de cada comunicación para máxima trazabilidad y soporte técnico.
    """

    _instancia = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instancia is None:
                cls._instancia = super(DiagnosticLogger, cls).__new__(cls)
                cls._instancia._inicializado = False
            return cls._instancia

    def __init__(self):
        if getattr(self, "_inicializado", False):
            return
        self.log_path = config.LOG_FILE_PATH
        self.file_lock = threading.Lock()
        self._inicializado = True
        self._iniciar_archivo()

    def _iniciar_archivo(self):
        """Crea el encabezado de sesión en el archivo de texto."""
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header = (
                f"\n"
                f"{'='*80}\n"
                f"AudiDiag Pro — REGISTRO DETALLADO DE DIAGNÓSTICO Y COMUNICACIÓN CAN\n"
                f"Sesión iniciada: {ts}\n"
                f"Vehículo objetivo: Audi A6 C6 (4F) 2.7 TDI V6 (2010)\n"
                f"Archivo: {self.log_path}\n"
                f"{'='*80}\n"
            )
            with self.file_lock:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(header)
                    f.flush()
        except Exception as e:
            print(f"[DiagnosticLogger] Error al iniciar archivo de log: {e}")

    def _rotar_si_necesario(self):
        """Rota el log si supera MAX_LOG_BYTES, archivándolo con marca de fecha/hora."""
        try:
            if os.path.exists(self.log_path) and os.path.getsize(self.log_path) > MAX_LOG_BYTES:
                base, ext = os.path.splitext(self.log_path)
                sello = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                rotado = f"{base}_{sello}{ext}"
                contador = 1
                while os.path.exists(rotado):
                    rotado = f"{base}_{sello}_{contador}{ext}"
                    contador += 1
                os.rename(self.log_path, rotado)
        except Exception as e:
            print(f"[DiagnosticLogger] Error al rotar el log: {e}")

    def log(self, etiqueta: str, mensaje: str):
        """Escribe una línea formateada con timestamp y etiqueta."""
        self._rotar_si_necesario()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        linea = f"[{ts}] [{etiqueta:<7}] {mensaje}\n"
        try:
            with self.file_lock:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(linea)
                    f.flush()
        except Exception as e:
            print(f"[DiagnosticLogger] Error al escribir log: {e}")

    def log_user(self, accion: str):
        """Registra una acción iniciada por el usuario en la interfaz gráfica."""
        self.log("USUARIO", accion)

    def log_tx(self, comando: str, descripcion: str = ""):
        """Registra un comando enviado al adaptador OBD2."""
        desc = f" ({descripcion})" if descripcion else ""
        self.log("TX >>", f"{comando}{desc}")

    def log_rx(self, respuesta: str, estado: str = "OK"):
        """Registra la respuesta recibida del vehículo o adaptador."""
        resp_limpia = respuesta.replace("\r", " ").replace("\n", " ").strip() if respuesta else "<VACÍO / TIMEOUT>"
        self.log("RX <<", f"[{estado}] {resp_limpia}")

    def log_info(self, mensaje: str):
        self.log("INFO", mensaje)

    def log_alerta(self, mensaje: str):
        self.log("ALERTA", mensaje)

    def log_warning(self, mensaje: str):
        self.log("ALERTA", mensaje)

    def log_error(self, mensaje: str, detalle: str = ""):
        msg = f"{mensaje} | Detalle: {detalle}" if detalle else mensaje
        self.log("ERROR", msg)

    def log_transferencia(self, operacion: str, exitosa: bool, detalle: str = ""):
        estado = "ÉXITO ✓" if exitosa else "FALLO ✗"
        self.log("TRANSF", f"{operacion} -> {estado} | {detalle}")

    def obtener_ruta_log(self) -> str:
        return self.log_path


# Instancia global disponible para importar directamente
diag_logger = DiagnosticLogger()
