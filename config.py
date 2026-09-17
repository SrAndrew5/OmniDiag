import os
import sys

# ── Directorio raíz del proyecto (donde está este config.py o el .exe empaquetado)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Puerto serie ──────────────────────────────────────────────────────────────
SERIAL_PORT = "AUTO"
BAUD_RATE   = 38400

# ── Modo de funcionamiento ────────────────────────────────────────────────────
# "real"     → usa el puerto COM real del cable OBD2 (por defecto)
# "simulado" → usa FakeSerial sin hardware
MODE = "real"

# ── Tipo de vehículo / protocolo de bus ───────────────────────────────────────
# "VAG"            → Audi / VW / Seat / Skoda (VW TP 2.0 / KWP2000 / UDS)
# "OBD2_UNIVERSAL" → Opel Corsa y multimarca (ISO 15765-4 CAN 11-bit 500 kbps)
VEHICLE_MODE = "VAG"


# ── Carpetas de datos (rutas absolutas, siempre dentro del proyecto) ──────────
DATA_DIR                 = os.path.join(BASE_DIR, "datos")
BACKUP_FOLDER            = os.path.join(DATA_DIR, "backups")
HISTORICO_DTCS_FOLDER    = os.path.join(DATA_DIR, "historico_dtcs")
HISTORIAL_LECTURAS_FOLDER = os.path.join(DATA_DIR, "historial_lecturas")
EXPLORACIONES_FOLDER     = os.path.join(DATA_DIR, "exploraciones")
REPORTES_FOLDER          = os.path.join(DATA_DIR, "reportes")

# ── Base de datos SQLite ──────────────────────────────────────────────────────
DATABASE_PATH = os.path.join(DATA_DIR, "audidiag.db")

# ── Archivo de registro detallado (.txt) ──────────────────────────────────────
LOG_FILE_PATH = os.path.join(BASE_DIR, "audidiag_registro_detallado.txt")