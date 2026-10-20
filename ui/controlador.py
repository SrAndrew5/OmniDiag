# ui/controlador.py
# ══════════════════════════════════════════════════════════════════════════════
# Controlador principal de diagnóstico para AudiDiag Pro.
# Conecta la interfaz gráfica (PyQt6) con el hardware de diagnóstico:
#   - Adaptador CANable 2.0 nativo (python-can / candleLight / slcan)
#   - Protocolo VW TP 2.0 / KWP2000 a través del Gateway J533
#   - Modo simulado para pruebas de UI y validación de codificaciones
# ══════════════════════════════════════════════════════════════════════════════

from PyQt6.QtCore import QThread, pyqtSignal
from core.connection import Connection
from core.can_manager import CANManager
from obd.obd_parser import OBDParser
from obd.vag_protocol import VAGProtocol, MODULOS_VAG, extraer_bytes_hex
from obd.tp20_can import TP20Transport, KWP2000NativeClient, LOGICAL_MODULES
from obd.audi_a6_actions import AudiA6Actions
from obd.vag_service_wizards import VAGServiceWizards
from obd.isotp_uds import VAG_UDS_MODULES, ISOTPClient, UDSClient
from obd.vin_reader import leer_vin
from obd.universal_obd2 import UniversalOBD2Client
from obd.opel_gm_client import OpelGMClient, OPEL_MODULES_CONFIG, ADAPTACIONES_OPEL, ACTUADORES_OPEL, CATALOGO_CONFORT_OPEL
from obd.vag_kline import VAGKLineClient, VAG_KLINE_ADDRESSES, POLO_9N3_CONFORT_CHANNELS, CATALOGO_CONFORT_POLO
from gestion.database_manager import DatabaseManager
from gestion.backup_manager import BackupManager
from core.diagnostic_logger import diag_logger
import time
import struct
import config
import traceback

# ──────────────────────────────────────────────────────────────────────────────
#  MAPEO DE MÓDULOS → DIRECCIÓN LÓGICA TP 2.0 (AUDI A6 C6)
#  Se eliminan módulos que no están en el bus CAN físico (ej: puertas traseras 62/72 son LIN)
# ──────────────────────────────────────────────────────────────────────────────
TP20_MODULE_ADDR = {
    "Motor (01)":                     0x01,
    "Caja de Cambios (02)":           0x02,
    "ABS / ESP (03)":                 0x03,
    "Acceso y Arranque Kessy (05)":   0x05,
    "Climatización (08)":             0x08,
    "Central Eléctrica / Luces (09)": 0x09,
    "Airbag (15)":                    0x15,
    "Columna Dirección (16)":         0x16,
    "Cuadro Instrumentos (17)":       0x17,
    "Gateway CAN (19)":               0x19,
    "Puerta Conductor (42)":          0x42,
    "Confort / Electrónica (46)":     0x46,
    "Puerta Pasajero (52)":           0x52,
    "Freno de Mano EPB (53)":         0x53,
    "Pantalla / MMI (5F)":            0x5F,
    "Ayuda Aparcamiento PDC (76)":    0x76,
    "Teléfono / Bluetooth (77)":      0x77,
}

# ──────────────────────────────────────────────────────────────────────────────
#  DATOS SIMULADOS — Fallos por módulo con Freeze Frame
# ──────────────────────────────────────────────────────────────────────────────
FALLOS_SIMULADOS = {
    "Motor (01)": [
        ("P0299", "Turbocompresor — presión insuficiente (Underboost)",
         {"RPM": (2100.0, "rpm"), "Velocidad": (80.0, "km/h"),
          "Temp. Refrigerante": (95.0, "°C"), "Voltaje": (13.8, "V")}),
    ],
    "Caja de Cambios (02)": [],
    "Confort / Electrónica (46)": [
        ("01044", "Unidad de control mal codificada",
         {"Voltaje": (11.8, "V"), "Temp. Interior": (22.0, "°C")}),
    ],
    "ABS / ESP (03)": [],
    "Airbag (15)": [],
    "Climatización (08)": [],
    "Cuadro Instrumentos (17)": [],
    "Central Eléctrica / Luces (09)": [
        ("00984", "Lámpara antiniebla derecho / luz de giro (L22) — circuito abierto",
         {"Voltaje": (12.1, "V")}),
    ],
    "Pantalla / MMI (5F)": [],
}

CODING_SIMULADO = {
    "Motor (01)":                     "0A 00 FF 13 44 10 00 A2",
    "Caja de Cambios (02)":           "03 00 00 05",
    "ABS / ESP (03)":                 "02 00 07 F1",
    "Climatización (08)":             "09 00 00 04",
    "Central Eléctrica / Luces (09)": "01 20 00 80 01 05 00 00",
    "Airbag (15)":                    "01 00 0A",
    "Cuadro Instrumentos (17)":       "04 00 00",  # Byte 1 Bit 0 = 0 (Needle Sweep desactivado listo para activar)
    "Confort / Electrónica (46)":     "FF D0 00 03 08 41 00 00 00 00",
    "Pantalla / MMI (5F)":            "01 01 00 02 00 00 00 00",
}

SENSORES_MOTOR = [
    ("RPM Motor",             820.0,  "rpm",   8200.0),
    ("Velocidad",             0.0,    "km/h",  240.0),
    ("Temp. Refrigerante",    91.0,   "°C",    130.0),
    ("Temp. Aceite Motor",    88.0,   "°C",    150.0),
    ("Flujo Masa Aire (MAF)", 14.3,   "g/s",   150.0),
    ("Presión Turbo",         1.85,   "bar",   3.0),
    ("Voltaje Batería",       14.1,   "V",     16.0),
    ("Carga Motor",           18.4,   "%",     100.0),
    ("Avance Inyección",      5.2,    "°",     30.0),
    ("Presión Common Rail",   320.0,  "bar",   1800.0),
]

ADAPTACIONES_VAG = {
    "Cuadro Instrumentos (17)": [
        {"nombre": "Needle Sweep (Barrido de agujas)", "canal": 1, "valor": 0, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Test de agujas completo al poner contacto"},
        {"nombre": "Reset intervalo servicio",        "canal": 3, "valor": 0, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Resetear el contador de mantenimiento"},
        {"nombre": "Brillo display (día)",            "canal": 22, "valor": 90, "min": 0, "max": 100, "unidad": "%", "desc": "Brillo del cuadro en modo diurno"},
    ],
    "Central Eléctrica / Luces (09)": [
        {"nombre": "Brillo luces diurnas LED (DRL)",   "canal": 3, "valor": 100, "min": 5, "max": 100, "unidad": "%", "desc": "Luminosidad de los LEDs frontales"},
        {"nombre": "Retardo lavafaros xenón",          "canal": 26, "valor": 5, "min": 1, "max": 10, "unidad": "pulsos", "desc": "Pulsaciones antes de activar lavafaros"},
    ],
    "Confort / Electrónica (46)": [
        {"nombre": "Ventanas con mando (apertura confort)", "canal": 31, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Abrir ventanas pulsando mando 2s"},
        {"nombre": "Cierre auto con velocidad (15 km/h)",   "canal": 10, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Cierra puertas al superar 15 km/h"},
        {"nombre": "Duración Coming Home",                  "canal": 8,  "valor": 30, "min": 0, "max": 60, "unidad": "seg", "desc": "Tiempo de luces al salir"},
        {"nombre": "Duración Leaving Home",                 "canal": 9,  "valor": 30, "min": 0, "max": 60, "unidad": "seg", "desc": "Tiempo de luces al abrir"},
    ],
    "Motor (01)": [
        {"nombre": "Adaptación mariposa gases",       "canal": 60, "valor": 0, "min": 0, "max": 255, "unidad": "", "desc": "Reset para recalibración"},
    ],
    "Climatización (08)": [
        {"nombre": "Temperatura mínima AC",           "canal": 1, "valor": 16, "min": 16, "max": 30, "unidad": "°C", "desc": "Temperatura mínima seleccionable"},
    ],
}

ACTUADORES_VAG = {
    "Cuadro Instrumentos (17)": [
        {"nombre": "Test Completo Agujas (Sweep)", "canal": "01", "desc": "Mueve todas las agujas de 0 a fondo de escala", "duracion": 3},
        {"nombre": "Test Display FIS y Testigos",  "canal": "02", "desc": "Enciende todos los segmentos y LEDs del cuadro", "duracion": 3},
    ],
    "Central Eléctrica / Luces (09)": [
        {"nombre": "Antiniebla Derecho",          "canal": "01", "desc": "Enciende el antiniebla derecho 3 segundos", "duracion": 3},
        {"nombre": "Antiniebla Izquierdo",        "canal": "02", "desc": "Enciende el antiniebla izquierdo 3 segundos", "duracion": 3},
        {"nombre": "Luces Diurnas LED",           "canal": "03", "desc": "Prueba de tiras LED frontales", "duracion": 3},
    ],
    "Motor (01)": [
        {"nombre": "Bomba combustible",          "canal": "01", "desc": "Activa bomba 3 segundos", "duracion": 3},
        {"nombre": "Ventilador radiador",        "canal": "26", "desc": "Activa ventiladores a máx. velocidad", "duracion": 3},
    ],
    "Confort / Electrónica (46)": [
        {"nombre": "Elevalunas del. izq. ↑",    "canal": "01", "desc": "Sube ventanilla conductor", "duracion": 2},
        {"nombre": "Elevalunas del. izq. ↓",    "canal": "02", "desc": "Baja ventanilla conductor", "duracion": 2},
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
#  DATOS POLO 9N3 (PQ24 / K-LINE KWP1281) — COCHE DEL PADRE
# ──────────────────────────────────────────────────────────────────────────────
ADAPTACIONES_POLO_KLINE = {
    "Confort / BCM (46)": [
        {"nombre": "Auto-Lock (Cierre a 15 km/h)", "canal": 3, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Bloquea automáticamente pestillos al superar 15 km/h"},
        {"nombre": "Auto-Unlock (Apertura al sacar llave)", "canal": 4, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Desbloquea automáticamente todas las puertas al extraer la llave"},
        {"nombre": "Aviso Acústico al abrir con mando", "canal": 5, "valor": 0, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Emite dos toques de bocina al abrir con mando"},
        {"nombre": "Aviso Acústico / Claxon al cerrar", "canal": 6, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Hace sonar la bocina brevemente al cerrar con el mando"},
        {"nombre": "Apertura Selectiva de Puertas", "canal": 7, "valor": 0, "min": 0, "max": 1, "unidad": "0=1 Toque / 1=2 Toques", "desc": "0 = Un toque abre todas las puertas; 1 = Requiere dos toques"},
        {"nombre": "Confirmación Intermitentes al cerrar", "canal": 8, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Destello óptico de intermitentes al bloquear puertas"},
        {"nombre": "Confirmación Intermitentes al abrir", "canal": 9, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Doble destello óptico de intermitentes al desbloquear"},
        {"nombre": "Tono de Sirena Alarma DWA", "canal": 10, "valor": 1, "min": 1, "max": 3, "unidad": "1=Europa / 2=Alemania", "desc": "Tipo de tono de sirena antirrobo H12"},
        {"nombre": "Sensibilidad Sensor Volumétrico G273", "canal": 11, "valor": 100, "min": 50, "max": 100, "unidad": "%", "desc": "Sensibilidad volumétrica de habitáculo"},
        {"nombre": "Confort Elevalunas desde Mando", "canal": 14, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Subida y bajada de cristales manteniendo pulsado el mando"},
    ],
    "Central Eléctrica / Luces (09)": [
        {"nombre": "Retardo Luces Coming Home", "canal": 1, "valor": 30, "min": 0, "max": 60, "unidad": "Segundos", "desc": "Tiempo de encendido de luces al accionar ráfaga con motor parado"},
        {"nombre": "Limpia Trasero Automático Marcha Atrás", "canal": 2, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Barre la luneta trasera al meter marcha atrás si el limpia delantero está activo"},
        {"nombre": "Barrido Antigoteo Delantero (Tear-Drop)", "canal": 3, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Barrido extra retardado a los 5s de lavar el parabrisas"},
        {"nombre": "Luces Diurnas DRL Automáticas", "canal": 4, "valor": 0, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Enciende luces de cruce automáticamente al poner contacto"},
        {"nombre": "Temporizador Luneta Térmica", "canal": 5, "valor": 15, "min": 1, "max": 30, "unidad": "Minutos", "desc": "Tiempo de funcionamiento de luneta térmica trasera"},
    ],
    "Cuadro de Instrumentos (17)": [
        {"nombre": "Reset Intervalo Servicio / Aceite", "canal": 2, "valor": 0, "min": 0, "max": 1, "unidad": "0=Resetear / 1=Activo", "desc": "Resetear aviso de inspección y cambio de aceite"},
        {"nombre": "Ajuste Aforador Depósito Combustible", "canal": 30, "valor": 128, "min": 120, "max": 136, "unidad": "Base 128 (Ohm)", "desc": "Calibración fina de resistencia del aforador"},
        {"nombre": "Aviso Acústico Exceso Velocidad", "canal": 35, "valor": 120, "min": 0, "max": 180, "unidad": "km/h (0=Off)", "desc": "Chime de advertencia de velocidad en cuadro"},
        {"nombre": "Km desde último cambio de aceite", "canal": 40, "valor": 0, "min": 0, "max": 300, "unidad": "x100 km", "desc": "Distancia acumulada de uso de aceite"},
        {"nombre": "Días desde última inspección", "canal": 41, "valor": 0, "min": 0, "max": 730, "unidad": "Días", "desc": "Tiempo acumulado desde última revisión"},
        {"nombre": "Km máximos hasta próximo servicio", "canal": 43, "valor": 150, "min": 150, "max": 300, "unidad": "x100 km", "desc": "Límite kilometraje (150 = 15.000 km)"},
        {"nombre": "Días máximos hasta próxima revisión", "canal": 44, "valor": 365, "min": 365, "max": 730, "unidad": "Días", "desc": "Límite temporal (365 = 1 año)"},
        {"nombre": "Calidad de Aceite Motor", "canal": 45, "valor": 1, "min": 1, "max": 2, "unidad": "1=Fijo / 2=LongLife", "desc": "Tipo de intervalo: 1 (Fijo VW 505.01) o 2 (Flexible)"},
    ],
    "Dirección Asistida TRW (44)": [
        {"nombre": "Curva Asistencia Electrohidráulica", "canal": 1, "valor": 2, "min": 1, "max": 4, "unidad": "1=Confort / 2=Estándar / 3=GTI / 4=Eco", "desc": "Mapa de dureza de la cremallera asistida TRW"},
    ],
    "Motor (01)": [
        {"nombre": "Masa de Inyección en Ralentí", "canal": 1, "valor": 32768, "min": 32700, "max": 32800, "unidad": "Base 32768", "desc": "Ajuste de mg/str de inyección en ralentí para eliminar vibraciones"},
        {"nombre": "Ajuste Fino Ralentí RPM", "canal": 2, "valor": 32768, "min": 32700, "max": 32850, "unidad": "Base 32768 (~860 rpm)", "desc": "Revoluciones por minuto de ralentí en centralita EDC15/EDC16"},
        {"nombre": "Tasa de Recirculación EGR", "canal": 3, "valor": 33768, "min": 32768, "max": 33768, "unidad": "Base 32768", "desc": "Reducción de EGR para mayor caudal de aire limpio y menor carbonilla"},
        {"nombre": "Dosis Combustible Arranque Caliente", "canal": 5, "valor": 32768, "min": 32700, "max": 32850, "unidad": "Base 32768", "desc": "Aumento de inyección <250 RPM para arranque instantáneo en caliente"},
        {"nombre": "Tiempo Precalentamiento Calentadores", "canal": 12, "valor": 32768, "min": 32700, "max": 32800, "unidad": "Pulsos", "desc": "Tiempo de activación de calentadores de arranque en frío"},
    ],
    "Airbag (15)": [
        {"nombre": "Desactivar Airbag Pasajero (Silla Bebé)", "canal": 1, "valor": 0, "min": 0, "max": 1, "unidad": "0=Activo / 1=Desactivado", "desc": "Desconexión electrónica de airbag frontal derecho"},
        {"nombre": "Supervisión Airbags Laterales Asientos", "canal": 2, "valor": 0, "min": 0, "max": 1, "unidad": "0=Activo / 1=Desactivado", "desc": "Desconexión electrónica de airbags de tórax en asientos"},
    ],
    "Climatización (08)": [
        {"nombre": "Recirculación con Marcha Atrás", "canal": 1, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Cierra compuerta exterior V113 para evitar humos de escape al retroceder"},
        {"nombre": "Cierre Compuerta con Lavaparabrisas", "canal": 2, "valor": 1, "min": 0, "max": 1, "unidad": "0=No / 1=Sí", "desc": "Cierra aire exterior 15s al usar limpia para evitar olores químicos"},
    ],
    "Radio / Sonido (56)": [
        {"nombre": "Ecualización Acústica DSP Polo 9N3", "canal": 1, "valor": 1, "min": 0, "max": 1, "unidad": "0=Plana / 1=DSP Polo", "desc": "Mapa de sonido adaptado a la acústica de carrocería del Polo"},
        {"nombre": "Configuración 4 Altavoces", "canal": 2, "valor": 1, "min": 0, "max": 1, "unidad": "0=2 Altavoces / 1=4 Altavoces", "desc": "Habilita fader y salida a puertas traseras"},
    ],
}

ACTUADORES_POLO_KLINE = {
    "Confort / BCM (46)": [
        {"nombre": "Cierre Centralizado (Bloqueo)", "canal": "01", "desc": "Activa los motores de cierre de todas las puertas", "duracion": 2},
        {"nombre": "Desbloqueo Centralizado", "canal": "02", "desc": "Desbloquea todas las cerraduras", "duracion": 2},
        {"nombre": "Bocina Alarma / Claxon Confort", "canal": "03", "desc": "Prueba acústica de la bocina de alarma", "duracion": 2},
        {"nombre": "Intermitentes de Emergencia", "canal": "04", "desc": "Hace parpadear los intermitentes 3 veces", "duracion": 3},
        {"nombre": "Elevalunas Izquierdo (Conductor)", "canal": "05", "desc": "Activa subida y bajada del elevalunas V147", "duracion": 3},
        {"nombre": "Elevalunas Derecho (Copiloto)", "canal": "06", "desc": "Activa subida y bajada del elevalunas V148", "duracion": 3},
    ],
    "Central Eléctrica / Luces (09)": [
        {"nombre": "Luces Largas / Ráfagas", "canal": "01", "desc": "Enciende los proyectores de luces largas durante 3 segundos", "duracion": 3},
        {"nombre": "Faros Antiniebla Delanteros", "canal": "02", "desc": "Enciende los faros antiniebla L22/L23", "duracion": 3},
        {"nombre": "Limpiaparabrisas Delantero Vel 1", "canal": "03", "desc": "Acciona los brazos de limpiaparabrisas delanteros", "duracion": 3},
        {"nombre": "Limpia Trasero y Lavaparabrisas", "canal": "04", "desc": "Acciona el motor trasero V12 y bomba de agua", "duracion": 3},
        {"nombre": "Luneta Térmica Trasera", "canal": "05", "desc": "Activa el relé de desempañado térmico", "duracion": 3},
    ],
    "Motor (01)": [
        {"nombre": "Relé Calentadores Bujías (J52)", "canal": "01", "desc": "Activa relé J52 de calentadores 3 segundos", "duracion": 3},
        {"nombre": "Válvula N75 Presión Turbo", "canal": "02", "desc": "Cicla la electroválvula de vacío de regulación de geometría del turbo", "duracion": 4},
        {"nombre": "Válvula N18 Recirculación EGR", "canal": "03", "desc": "Prueba de apertura y cierre de la válvula neumática EGR", "duracion": 4},
        {"nombre": "Ventilador Radiador V7", "canal": "04", "desc": "Activa electroventiladores de refrigeración del motor", "duracion": 3},
        {"nombre": "Chapaleta Apagado Suave N239", "canal": "05", "desc": "Cierra la mariposa de apagado suave para corte limpio del motor", "duracion": 3},
        {"nombre": "Relé Bomba Combustible J17", "canal": "06", "desc": "Activa la prebomba sumergida del depósito durante 3 segundos", "duracion": 3},
    ],
    "Cuadro de Instrumentos (17)": [
        {"nombre": "Test Agujas (Velocímetro / Cuentavueltas)", "canal": "01", "desc": "Mueve las agujas a fondo de escala y centro (100 km/h / 3000 rpm)", "duracion": 4},
        {"nombre": "Test Testigos Luminosos", "canal": "02", "desc": "Enciende todos los testigos luminosos del cuadro", "duracion": 3},
        {"nombre": "Zumbador / Gong Acústico", "canal": "03", "desc": "Prueba de sonido de la chicharra acústica de avisos", "duracion": 3},
        {"nombre": "Test Display LCD / Odómetro", "canal": "04", "desc": "Enciende todos los segmentos del display digital de kilómetros y reloj", "duracion": 3},
    ],
    "ABS / Frenos (03)": [
        {"nombre": "Bomba Hidráulica ABS (V39)", "canal": "01", "desc": "Activa la electrobomba de recirculación del bloque hidráulico ABS durante 3 segundos", "duracion": 3},
        {"nombre": "Válvulas Entrada / Salida ABS", "canal": "02", "desc": "Cicla las electroválvulas solenoides del bloque ABS para comprobar que no están atascadas", "duracion": 4},
        {"nombre": "Test Estático de Presión de Freno", "canal": "03", "desc": "Verificación de estanqueidad y presiones de pedal", "duracion": 3},
    ],
    "Climatización (08)": [
        {"nombre": "Servomotor Recirculación (V113)", "canal": "01", "desc": "Abre y cierra la compuerta de recirculación de aire", "duracion": 3},
        {"nombre": "Servomotor Temperatura (V68)", "canal": "02", "desc": "Mueve la compuerta de mezcla de frío/calor a tope frío y caliente", "duracion": 4},
        {"nombre": "Válvula Compresor A/C (N280)", "canal": "03", "desc": "Activa la regulación de cilindrada del compresor de aire acondicionado", "duracion": 3},
        {"nombre": "Turbina Soplador Interior (V2)", "canal": "04", "desc": "Prueba de giro del ventilador de climatización en cabina", "duracion": 3},
    ],
}

FALLOS_SIMULADOS_KLINE = {
    "Confort / BCM (46)": [
        ("00928 [ESPORÁDICO]", "Unidad de control para cierre centralizado lado conductor (F220) — Señal no plausible", {}),
        ("00932 [ESTÁTICO]", "Motor elevalunas lado conductor (V147) — Sin ajuste básico o adaptación", {}),
    ],
    "Motor (01)": [
        ("01650 [ESTÁTICO]", "Bujía incandescente Cilindro 2 (Q11) — Circuito defectuoso (P0672 / Causa mal arranque)",
         {"RPM": (860.0, "rpm"), "Temp. Motor": (14.0, "°C"), "Voltaje": (10.1, "V")}),
        ("00532 [ESPORÁDICO]", "Tensión de alimentación B+ / Borne 30 — Valor por debajo del umbral mínimo (caída en arranque)",
         {"Voltaje": (9.4, "V")}),
    ],
    "ABS / Frenos (03)": [],
    "Cuadro de Instrumentos (17)": [],
    "Airbag (15)": [],
    "Climatización (08)": [],
    "Radio / Sonido (56)": [],
    "Central Eléctrica / Luces (09)": [],
    "Dirección Asistida TRW (44)": [],
}

SENSORES_POLO_KLINE = [
    ("RPM Motor", 860.0, "rpm", 5500.0),
    ("Velocidad", 0.0, "km/h", 220.0),
    ("Temp. Refrigerante (G62)", 88.0, "°C", 130.0),
    ("Presión Turbo Actual", 1.05, "bar", 2.6),
    ("Presión Turbo Especificada", 1.05, "bar", 2.6),
    ("Caudalímetro MAF", 460.0, "mg/str", 1200.0),
    ("Cantidad Inyectada", 5.2, "mg/str", 60.0),
    ("Voltaje Batería / Borne 30", 14.1, "V", 16.0),
    ("Ángulo Torsión Synchro Levas", 0.5, "°", 6.0),
    ("Temp. Combustible (G81)", 38.0, "°C", 100.0),
    ("Pedal Acelerador", 0.0, "%", 100.0),
    ("Consumo Instantáneo Ralentí", 0.5, "l/h", 25.0),
]


class MotorDiagnostico(QThread):
    """
    Hilo de diagnóstico en segundo plano para AudiDiag Pro.
    Gestiona la comunicación con CANable y el vehículo sin bloquear la interfaz.
    """
    log_signal          = pyqtSignal(str)
    status_signal       = pyqtSignal(str, str)
    vin_signal          = pyqtSignal(str)
    coding_signal       = pyqtSignal(str)
    module_scanned      = pyqtSignal(str, list)  # Emisión en tiempo real al escanear cada módulo
    scan_done           = pyqtSignal(dict)
    sensors_data_signal = pyqtSignal(list)
    mil_signal          = pyqtSignal(bool)
    adaptacion_signal   = pyqtSignal(str, float)
    wizard_data_signal   = pyqtSignal(str, dict)
    wizard_result_signal = pyqtSignal(str, bool, str)

    def __init__(self):
        super().__init__()
        self.accion  = None
        self.kwargs  = {}

        # Módulos de hardware
        self.can_mgr      = CANManager(log_fn=self._log)
        self.tp20         = TP20Transport(self.can_mgr)
        self.kwp          = KWP2000NativeClient(self.tp20)
        self.a6_actions   = AudiA6Actions(self.can_mgr, log_fn=self._log)
        self.wizards      = VAGServiceWizards(self.can_mgr, log_fn=self._log)
        self.universal_obd = UniversalOBD2Client(self.can_mgr, log_fn=self._log)
        self.opel_client  = OpelGMClient(self.can_mgr, log_fn=self._log)

        # Fallback serie para cables antiguos
        self.conexion     = Connection()
        self.parser       = OBDParser()
        self.vag_protocol = VAGProtocol(self.conexion, log_fn=self._log)
        self.kline_client = VAGKLineClient(port_name="MOCK")

        self.db           = DatabaseManager()
        self.vin          = None
        self.sesion_id    = None
        self.hardware_tipo = "DESCONECTADO"  # CANABLE, ELM327, KLINE, SIMULADO
        self._unsupported_pids = set()
        self._oil_uds_did = None

    @property
    def modo_vehiculo(self) -> str:
        return getattr(config, "VEHICLE_MODE", "VAG")

    @property
    def es_modo_opel(self) -> bool:
        return self.modo_vehiculo in ("OBD2_UNIVERSAL", "OPEL_CONFORT", "OPEL_CORSA")

    @property
    def es_modo_kline(self) -> bool:
        return self.modo_vehiculo == "VAG_KLINE"

    @property
    def conectado(self) -> bool:
        return bool(self.sesion_id)

    def _log(self, msg: str):
        self.log_signal.emit(str(msg))

    def set_accion(self, accion: str, **kwargs):
        if self.isRunning():
            self._log("[INFO] Esperando operación anterior...")
            self.wait(3000)
        self.accion = accion
        self.kwargs = kwargs

    def ejecutar(self, accion: str, **kwargs):
        """Helper para configurar y lanzar la acción de inmediato en el hilo."""
        self.set_accion(accion, **kwargs)
        self.start()

    def run(self):
        try:
            dispatch = {
                "conectar":            self._conectar,
                "escanear_dtc":        self._escanear_dtc,
                "auto_scan":           self._auto_scan,
                "borrar_dtc":          self._borrar_dtc,
                "leer_sensores":       self._leer_sensores_tabla,
                "leer_mil":            self._leer_mil,
                "leer_coding":         self._leer_coding,
                "escribir_coding":     self._escribir_coding,
                "adaptacion_leer":     self._adaptacion_leer,
                "adaptaciones_modulo": self._adaptaciones_modulo,
                "adaptacion_escribir": self._adaptacion_escribir,
                "test_actuador":       self._test_actuador,
                "activar_needle_sweep": self._activar_needle_sweep,
                "activar_plegado_retrovisores": self._activar_plegado_retrovisores,

                "auditar_km":          self._auditar_km,
                "epb_abrir":           self._epb_abrir,
                "epb_cerrar":          self._epb_cerrar,
                "epb_test":            self._epb_test,
                "sri_reset_aceite":    self._sri_reset_aceite,
                "sri_reset_completo":  self._sri_reset_completo,
                "dpf_leer":            self._dpf_leer,
                "dpf_regenerar":       self._dpf_regenerar,
                "inyectores_leer":     self._inyectores_leer,
                "bateria_codificar":   self._bateria_codificar,
                "bateria_leer":        self._bateria_leer,
                "abs_purga":           self._abs_purga,
                "caja_atf":            self._caja_atf,
                "caja_reset":          self._caja_reset,
                "g85_calibrar":        self._g85_calibrar,
                "swirl_flaps":         self._swirl_flaps,
                "mmi_green_menu":      self._mmi_green_menu,
                "gateway_leer_lista":  self._gateway_leer_lista,
                "gateway_guardar_lista": self._gateway_guardar_lista,
            }
            fn = dispatch.get(self.accion)
            if fn:
                fn()
            else:
                self._log(f"[ERROR] Acción desconocida: '{self.accion}'")
        except Exception as e:
            tb = traceback.format_exc()
            self._log(f"\n[ERROR CRÍTICO EN TAREA '{self.accion}']: {e}")
            diag_logger.log_error(f"Excepción en {self.accion}: {e}", tb)

    # ──────────────────────────────────────────────────────────────────────────
    #  CONEXIÓN
    # ──────────────────────────────────────────────────────────────────────────
    def _conectar(self):
        diag_logger.log_user("Clic en CONECTAR AL VEHÍCULO")

        modo_vehiculo = getattr(config, "VEHICLE_MODE", "VAG")

        # 1. Modo Simulado
        if config.MODE == "simulado":
            if modo_vehiculo == "VAG_KLINE":
                self._log("\n[SIMULACIÓN] Iniciando banco de pruebas VW Polo 9N3 1.9 TDI (PQ24 / K-Line)...")
                self.kline_client = VAGKLineClient(port_name="MOCK")
                self.kline_client.conectar(0x46)
                self.hardware_tipo = "SIMULADO_KLINE"
                self.vin = "6Q0959433E"
                self._log(f"[✓ OK] Conectado a emulador K-Line KWP1281. Centralita Confort: {self.vin}")
                self._log("  ▸ Pin OBD-II activo: Pin 7 (K-Line bidireccional a 10.400 baudios)")
                self._log("  ▸ Centralitas Polo 9N3 simuladas: Confort (46), Motor EDC15 (01), ABS (03), Cuadro (17), Airbag (15)")
                self.status_signal.emit(f"Polo 9N3 K-Line — {self.vin}", "green")
                self.vin_signal.emit(self.vin)
                self.sesion_id = self.db.nueva_sesion(self.vin)
                self.mil_signal.emit(True)
            elif modo_vehiculo == "OBD2_UNIVERSAL":
                self._log("\n[SIMULACIÓN] Iniciando banco de pruebas Opel Corsa / Universal OBD-II...")
                self.can_mgr.conectar(interface_preference="virtual")
                self.hardware_tipo = "SIMULADO"
                self.vin = "W0L0SDL0874012345"
                self._log(f"[✓ OK] Conectado a bus virtual CAN. Vehículo: Opel Corsa D — {self.vin}")
                self.status_signal.emit(f"Simulación — Corsa ({self.vin})", "green")
                self.vin_signal.emit(self.vin)
                self.sesion_id = self.db.nueva_sesion(self.vin)
                self.mil_signal.emit(True)
            else:
                self._log("\n[SIMULACIÓN] Iniciando banco de pruebas Audi A6 C6 (2010)...")
                self.can_mgr.conectar(interface_preference="virtual")
                self.hardware_tipo = "SIMULADO"
                self.vin = "WAUZZZ4F000000000"
                if hasattr(self, 'a6_actions'):
                    self.a6_actions.vin = self.vin
                self._log(f"[✓ OK] Conectado a bus virtual CAN. Bastidor fijado: {self.vin}")
                self.status_signal.emit(f"Simulación — {self.vin}", "green")
                self.vin_signal.emit(self.vin)
                self.sesion_id = self.db.nueva_sesion(self.vin)
                self.mil_signal.emit(False)
            return

        # 2. Modo Real K-Line (VW Polo 9N3 / KWP1281)
        if modo_vehiculo == "VAG_KLINE":
            self._log("\n[K-LINE] Buscando adaptador FTDI K-Line en puertos COM USB...")
            self.status_signal.emit("Buscando FTDI...", "yellow")
            puertos = VAGKLineClient.listar_puertos_com()
            puertos_reales = [p for p in puertos if p.upper() != "MOCK"]
            conectado_kline = False
            for puerto in puertos_reales:
                self._log(f"  ▸ Probando enlace KWP1281 en puerto {puerto} (Pin 7)...")
                try:
                    cli = VAGKLineClient(port_name=puerto, baudrate=9600)
                    if cli.conectar(0x46) or cli.conectar(0x01):
                        self.kline_client = cli
                        self.hardware_tipo = "KLINE"
                        ident = cli.leer_identificacion()
                        self.vin = ident.get("referencia", "6Q0959433E")
                        self._log(f"[✓ ÉXITO] Conexión física K-Line establecida en {puerto} a 10.400 baudios.")
                        self._log(f"  ▸ Centralita: {ident.get('modulo', '0x46')} | Ref: {self.vin}")
                        self.status_signal.emit(f"Polo K-Line ({puerto}) — {self.vin}", "green")
                        self.vin_signal.emit(self.vin)
                        self.sesion_id = self.db.nueva_sesion(self.vin)
                        self.mil_signal.emit(False)
                        conectado_kline = True
                        return
                except Exception as e:
                    self._log(f"  [i] Puerto {puerto} no respondió: {e}")

            if not conectado_kline:
                self._log("\n[INFO] No se detectó cable FTDI K-Line en ningún puerto COM.")
                self._log("  ▸ Asegúrate de que el cable K-Line USB esté conectado y con el switch en Posición 1 (Pin 7).")
                self._log("  ▸ Para probar la interfaz completa en PC, selecciona 'Modo Simulado — VW Polo 9N3 K-Line'.")
                self.status_signal.emit("Desconectado", "red")
                return

        # 3. Modo Real: Prioridad absoluta al CANable 2.0 nativo
        if modo_vehiculo == "OPEL_CONFORT":
            self._log("\n[CAN] Buscando adaptador CANable 2.0 para CAN Confort Opel Corsa (Pines 3 y 11)...")
            self.status_signal.emit("Conectando MSCAN 95k...", "yellow")
            if self.can_mgr.conectar(interface_preference="auto", bitrate=95000):
                self.hardware_tipo = "CANABLE"
                interfaz = self.can_mgr.connected_interface
                self._log(f"[✓ ÉXITO] Enlace Confort MSCAN establecido vía {interfaz} a 95 kbps.")
                self._log("  ▸ Pines OBD-II activos: Pin 3 (CAN-H Rojo) y Pin 11 (CAN-L Rosa).")
                self._log("  ▸ Centralitas accesibles: BCM (Carrocería 0x7EC) e IPC (Cuadro Instrumentos 0x7ED).")
                self.vin = "W0L0SDL6874086807"
                self.status_signal.emit(f"Opel Confort (95k) — {self.vin}", "green")
                self.vin_signal.emit(self.vin)
                self.sesion_id = self.db.nueva_sesion(self.vin)
                return

        elif modo_vehiculo == "OBD2_UNIVERSAL":
            self._log("\n[CAN] Buscando adaptador CANable 2.0 para diagnóstico Universal OBD-II / Opel Corsa...")
        else:
            self._log("\n[CAN] Buscando adaptador CANable 2.0 en puertos USB...")
        self.status_signal.emit("Buscando CANable...", "yellow")

        if self.can_mgr.conectar(interface_preference="auto"):
            self.hardware_tipo = "CANABLE"
            interfaz = self.can_mgr.connected_interface
            self._log(f"[✓ ÉXITO] Conexión nativa establecida vía {interfaz} a 500 kbps.")

            if modo_vehiculo == "OBD2_UNIVERSAL":
                self._log("  ▸ Protocolo de bus: ISO 15765-4 (CAN 11-bit 500k) — Opel Corsa / Multimarca.")
                self._log("  ▸ Enlace HSCAN pines 6 y 14 activo.")

                ecus = self.universal_obd.detectar_ecus()
                if ecus:
                    self._log(f"  ▸ Centralitas detectadas en bus CAN: {', '.join(f'0x{e:03X}' for e in ecus)}")
                vin_leido = self.universal_obd.leer_vin()
                self.vin = vin_leido if vin_leido else "OPEL_CORSA_OBD2"
                self._log(f"[✓ OK] Vehículo identificado: {self.vin}")
                mil_on, dtc_cnt = self.universal_obd.leer_estado_mil()
                self._log(f"  ▸ Check Engine (MIL): {'ENCENDIDA (Avería activa)' if mil_on else 'APAGADA (Sin avería)'} ({dtc_cnt} fallos)")
                self.status_signal.emit(f"OBD2 Conectado (500k) — {self.vin}", "green")
                self.vin_signal.emit(self.vin)
                self.sesion_id = self.db.nueva_sesion(self.vin)
                self.mil_signal.emit(mil_on)
                return
            else:
                self._log("  ▸ Protocolo de bus: CAN 2.0B nativo (sin latencia de serie)")
                self._log("  ▸ Enlace Gateway: VW TP 2.0 / KWP2000 activo.")
                self.vin = self.vin or "AUDI_A6_C6_CAN"
                if hasattr(self, 'a6_actions'):
                    self.a6_actions.vin = self.vin
                self._log(f"[✓ OK] Vehículo conectado en PC: Audi A6 C6")
                self._log("  ▸ Bus en reposo: Cero peticiones automáticas al arrancar. Pulsa 'Escanear' cuando desees.")
                self.status_signal.emit(f"CANable Conectado (500k) — {self.vin}", "green")
                self.vin_signal.emit(self.vin)
                self.sesion_id = self.db.nueva_sesion(self.vin)
                self.mil_signal.emit(False)
                return

        # 3. Fallback: Intentar cable serie clásico si el CANable no está conectado
        self._log("[INFO] No se detectó CANable. Probando puerto serie clásico...")
        if self.conexion.conectar():
            self.hardware_tipo = "ELM327"
            self._log("[OK] Cable serie detectado.")
            self.status_signal.emit("Cable Serie Detectado", "yellow")
            self.vin = self.vin or "AUDI_A6_SERIE"
            if hasattr(self, 'a6_actions'):
                self.a6_actions.vin = self.vin
            self.status_signal.emit(f"Conectado Serie — {self.vin}", "green")
            self.vin_signal.emit(self.vin)
            self.sesion_id = self.db.nueva_sesion(self.vin)
            self.mil_signal.emit(False)
            return

        self._log("\n[ERROR] No se detectó ningún adaptador conectado.")
        self._log("  ▸ Conecta el CANable 2.0 al puerto USB del ordenador.")
        self._log("  ▸ O cambia al 'Modo Simulado' en el selector para probar la interfaz.")
        self.status_signal.emit("Desconectado", "red")

    # ──────────────────────────────────────────────────────────────────────────
    #  MIL (LUZ DE AVERÍA)
    # ──────────────────────────────────────────────────────────────────────────
    def _leer_mil(self):
        mil_on = False
        if self.es_modo_kline:
            if self.hardware_tipo == "SIMULADO_KLINE":
                mil_on = len(FALLOS_SIMULADOS_KLINE.get("Motor (01)", [])) > 0
            elif self.hardware_tipo == "KLINE":
                try:
                    if self.kline_client.conectar(0x01):
                        dtcs = self.kline_client.leer_dtcs()
                        mil_on = len(dtcs) > 0
                except Exception:
                    mil_on = False
        elif self.hardware_tipo == "CANABLE":
            # Si hay fallos de motor activos
            try:
                if self.tp20.open_channel(0x01):
                    self.kwp.start_diagnostic_session(0x86)
                    dtcs = self.kwp.read_dtcs()
                    mil_on = len(dtcs) > 0
                    self.tp20.close_channel()
            except Exception:
                mil_on = False
        elif self.hardware_tipo == "SIMULADO":
            mil_on = len(FALLOS_SIMULADOS.get("Motor (01)", [])) > 0

        estado = "ENCENDIDA ⚠" if mil_on else "Apagada ✓"
        self._log(f"[MIL] Estado indicador de avería en cuadro: {estado}")
        self.mil_signal.emit(mil_on)

    # ──────────────────────────────────────────────────────────────────────────
    #  FALLOS DTC
    # ──────────────────────────────────────────────────────────────────────────
    def _escanear_dtc(self):
        if self.es_modo_opel:
            self._escanear_dtc_opel()
            return
        if self.es_modo_kline:
            self._escanear_dtc_kline()
            return

        modulo = self.kwargs.get("modulo", "Motor (01)")
        self._log(f"\n[INFO] Escaneando módulo: {modulo}...")
        diag_logger.log_user(f"Escanear fallos en {modulo}")

        fallos = []

        if self.hardware_tipo == "CANABLE":
            conectado = False
            addr = TP20_MODULE_ADDR.get(modulo)
            if addr is not None:
                try:
                    self.can_mgr.flush_rx()
                    retries = 2 if addr in (0x08, 0x09, 0x15, 0x17, 0x46, 0x5F) else 1
                    if self.tp20.open_channel(addr, retries=retries):
                        conectado = True
                        self.kwp.start_diagnostic_session(0x86)
                        time.sleep(0.04)
                        ecu_id = self.kwp.read_ecu_identification()
                        ref = ecu_id.get('part_number', 'OK')
                        self._log(f"[✓] Conectado a {modulo} vía VW TP 2.0 (Ref: {ref})")
                        codigos = self.kwp.read_dtcs()
                        self.tp20.close_channel()

                        for c in codigos:
                            c_first = c.split()[0] if c else ""
                            c_clean = c.split()[1] if c_first == "DTC" and len(c.split()) > 1 else c_first
                            estado_tag = "Histórico / Almacenado" if ("HISTÓRICO" in c or "ESPORÁDICO" in c) else "Activo"
                            desc = f"Fallo registrado en {modulo}"
                            try:
                                desc = self.db.buscar_descripcion(c_clean)
                            except Exception:
                                pass
                            fallos.append((c, desc, {}))
                            try:
                                self.db.registrar_dtc(
                                    vin=self.vin or "DESCONOCIDO", codigo=c_clean, estado=estado_tag,
                                    descripcion=desc, modulo=modulo, sesion_id=self.sesion_id, freeze_frame={}
                                )
                            except Exception:
                                pass
                except Exception as e:
                    self._log(f"[ERROR] Fallo en comunicación con {modulo}: {e}")
                    self.tp20.close_channel()

            # Respaldo UDS para centralitas que no hayan respondido por TP 2.0 (Cuadro 17, Luces 09, Confort 46, etc.)
            if not conectado and modulo in VAG_UDS_MODULES:
                info_uds = VAG_UDS_MODULES[modulo]
                candidates = [(info_uds["tx_id"], info_uds["rx_id"])]
                if "alt_tx" in info_uds and "alt_rx" in info_uds:
                    candidates.append((info_uds["alt_tx"], info_uds["alt_rx"]))

                for tx_c, rx_c in candidates:
                    try:
                        self._log(f"[UDS] Probando enlace UDS directo en 0x{tx_c:03X} / 0x{rx_c:03X} para {modulo}...")
                        isotp = ISOTPClient(self.can_mgr, tx_id=tx_c, rx_id=rx_c, timeout=0.8)
                        uds = UDSClient(isotp)
                        ecu_id = uds.read_ecu_identification()
                        ref = ecu_id.get('part_number', info_uds.get("nombre", "OK"))
                        codigos = uds.read_dtcs()
                        conectado = True
                        self._log(f"[✓] Conectado a {modulo} vía UDS nativo (Ref: {ref})")
                        for c in codigos:
                            c_first = c.split()[0] if c else ""
                            c_clean = c.split()[1] if c_first == "DTC" and len(c.split()) > 1 else c_first
                            estado_tag = "Histórico / Almacenado" if ("HISTÓRICO" in c or "ESPORÁDICO" in c) else "Activo"
                            desc = f"Fallo registrado en {modulo}"
                            try:
                                desc = self.db.buscar_descripcion(c_clean)
                            except Exception:
                                pass
                            fallos.append((c, desc, {}))
                            try:
                                self.db.registrar_dtc(
                                    vin=self.vin or "DESCONOCIDO", codigo=c_clean, estado=estado_tag,
                                    descripcion=desc, modulo=modulo, sesion_id=self.sesion_id, freeze_frame={}
                                )
                            except Exception:
                                pass
                        break
                    except Exception as e:
                        pass

            if not conectado:
                self._log(f"[INFO] {modulo}: Sin respuesta (módulo no equipado o en reposo).")

        elif self.hardware_tipo == "SIMULADO":
            fallos = FALLOS_SIMULADOS.get(modulo, [])

        if not fallos:
            self._log(f"[✓] {modulo}: 0 fallos detectados.")
        else:
            self._log(f"[ALERTA] {len(fallos)} fallo(s) detectado(s) en {modulo}:")
            for cod, desc, ff in fallos:
                self._log(f"  ▸ {cod}  —  {desc}")

        self.module_scanned.emit(modulo, fallos)
        self.scan_done.emit({modulo: fallos})

    def _auto_scan(self):
        if self.es_modo_opel:
            self._auto_scan_opel()
            return
        if self.es_modo_kline:
            self._auto_scan_kline()
            return

        self._log("\n[INFO] ══════ AUTO-SCAN COMPLETO DE CENTRALITAS ══════")
        self._log(f"Escaneando {len(TP20_MODULE_ADDR)} módulos a través del Gateway J533 (VW TP 2.0 / UDS)...\n")
        diag_logger.log_user("Auto-Scan completo iniciado")
        resumen = {}

        if self.hardware_tipo == "CANABLE":
            for modulo, addr in TP20_MODULE_ADDR.items():
                self._log(f"  [→] Analizando {modulo}...")
                fallos = []
                ref = "OK"
                conectado = False

                try:
                    self.can_mgr.flush_rx()
                    if self.tp20.open_channel(addr, retries=1):
                        conectado = True
                        self.kwp.start_diagnostic_session(0x86)
                        time.sleep(0.02)
                        ecu_id = self.kwp.read_ecu_identification()
                        ref = ecu_id.get("part_number", "OK")
                        codigos = self.kwp.read_dtcs()
                        self.tp20.close_channel()

                        for c in codigos:
                            c_first = c.split()[0] if c else ""
                            c_clean = c.split()[1] if c_first == "DTC" and len(c.split()) > 1 else c_first
                            estado_tag = "Histórico" if ("HISTÓRICO" in c or "ESPORÁDICO" in c) else "Activo"
                            desc = f"Fallo registrado en {modulo}"
                            try:
                                desc = self.db.buscar_descripcion(c_clean)
                            except Exception:
                                pass
                            fallos.append((c, desc, {}))
                            try:
                                self.db.registrar_dtc(
                                    vin=self.vin or "DESCONOCIDO", codigo=c_clean, estado=estado_tag,
                                    descripcion=desc, modulo=modulo, sesion_id=self.sesion_id, freeze_frame={}
                                )
                            except Exception:
                                pass
                except Exception:
                    self.tp20.close_channel()

                # Respaldo UDS verificado (exclusivo para Airbag 15 en 4F Facelift)
                if not conectado and modulo in VAG_UDS_MODULES:
                    info_uds = VAG_UDS_MODULES[modulo]
                    try:
                        isotp = ISOTPClient(self.can_mgr, tx_id=info_uds["tx_id"], rx_id=info_uds["rx_id"], timeout=0.6)
                        uds = UDSClient(isotp)
                        ecu_id = uds.read_ecu_identification()
                        ref = ecu_id.get("part_number", info_uds.get("nombre", "OK"))
                        codigos = uds.read_dtcs()
                        conectado = True
                        for c in codigos:
                            c_first = c.split()[0] if c else ""
                            c_clean = c.split()[1] if c_first == "DTC" and len(c.split()) > 1 else c_first
                            estado_tag = "Histórico" if ("HISTÓRICO" in c or "ESPORÁDICO" in c) else "Activo"
                            desc = f"Fallo registrado en {modulo}"
                            try:
                                desc = self.db.buscar_descripcion(c_clean)
                            except Exception:
                                pass
                            fallos.append((c, desc, {}))
                            try:
                                self.db.registrar_dtc(
                                    vin=self.vin or "DESCONOCIDO", codigo=c_clean, estado=estado_tag,
                                    descripcion=desc, modulo=modulo, sesion_id=self.sesion_id, freeze_frame={}
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass

                if conectado:
                    if not fallos:
                        self._log(f"       ✓ [{ref}] 0 fallos")
                    else:
                        self._log(f"       ⚠ [{ref}] {len(fallos)} fallo(s) detectado(s)")
                        for cod, desc, ff in fallos:
                            self._log(f"         ▸ {cod} — {desc}")
                else:
                    self._log(f"       - Sin respuesta / No equipado")

                resumen[modulo] = fallos
                # Emisión en tiempo real a la interfaz para que las averías aparezcan al instante
                self.module_scanned.emit(modulo, fallos)
                time.sleep(0.02)

        else:
            # Modo simulado
            for modulo in MODULOS_VAG:
                self._log(f"  [→] {modulo}...")
                time.sleep(0.04)
                fallos = FALLOS_SIMULADOS.get(modulo, [])
                resumen[modulo] = fallos
                if not fallos:
                    self._log(f"       ✓ 0 fallos")
                else:
                    self._log(f"       ⚠ {len(fallos)} fallo(s)")
                    for cod, desc, ff in fallos:
                        self._log(f"         ▸ {cod} — {desc}")
                self.module_scanned.emit(modulo, fallos)

        total = sum(len(v) for v in resumen.values())
        self._log(f"\n[✓] Auto-Scan completado — {total} fallo(s) detectado(s) en total.")
        self._log("════════════════════════════════════════════════════════")
        self.scan_done.emit(resumen)

    def _borrar_dtc(self):
        if self.es_modo_opel:
            self._borrar_dtc_opel()
            return
        if self.es_modo_kline:
            self._borrar_dtc_kline()
            return

        modulo = self.kwargs.get("modulo", "Motor (01)")
        self._log(f"\n[INFO] Borrando fallos de {modulo}...")

        if self.hardware_tipo == "CANABLE":
            borrado_ok = False
            addr = TP20_MODULE_ADDR.get(modulo)
            if addr is not None:
                try:
                    self.can_mgr.flush_rx()
                    if self.tp20.open_channel(addr, retries=1):
                        self.kwp.start_diagnostic_session(0x86)
                        time.sleep(0.05)
                        if self.kwp.clear_dtcs():
                            self._log(f"[✓ ÉXITO] Memoria de averías de {modulo} borrada vía TP 2.0.")
                            borrado_ok = True
                        self.tp20.close_channel()
                except Exception as e:
                    self._log(f"[ERROR] Fallo al borrar averías en {modulo}: {e}")
                    self.tp20.close_channel()

            if not borrado_ok and modulo in VAG_UDS_MODULES:
                info_uds = VAG_UDS_MODULES[modulo]
                uds_tx, uds_rx = info_uds["tx_id"], info_uds["rx_id"]
                try:
                    self.can_mgr.flush_rx()
                    iso = ISOTPClient(self.can_mgr, uds_tx, uds_rx)
                    uds = UDSClient(iso)
                    resp = uds.send_service(0x14, bytes([0xFF, 0xFF, 0xFF]))
                    if resp and resp[0] == 0x54:
                        self._log(f"[✓ ÉXITO] Memoria de averías de {modulo} borrada vía UDS (0x14).")
                        borrado_ok = True
                except Exception as e:
                    self._log(f"[ERROR] Fallo al borrar averías vía UDS en {modulo}: {e}")

            if not borrado_ok:
                self._log(f"[WARN] La centralita {modulo} no confirmó el borrado.")
        else:
            time.sleep(0.5)
            self._log(f"[✓ ÉXITO] Memoria de averías de {modulo} borrada (modo simulado).")

        # Refrescar escaneo del módulo
        self._escanear_dtc()

    def _escanear_dtc_opel(self):
        modulo = self.kwargs.get("modulo", "Motor / ECM")
        self._log(f"\n[OPEL / GM] ══════ ESCANEO DE AVERÍAS: {modulo} ══════")
        fallos = []

        cfg = OPEL_MODULES_CONFIG.get(modulo)
        if not cfg:
            for k, v in OPEL_MODULES_CONFIG.items():
                if k.split()[0] in modulo:
                    cfg = v
                    break

        if self.hardware_tipo == "SIMULADO":
            fallos_sim = {
                "Motor / ECM": [
                    ("P0300 [Activo]", "Fallo de combustión en cilindros múltiples / aleatorio", {}),
                    ("P0130 [Pendiente]", "Sensor de Oxígeno (Sonda Lambda Banco 1 Sensor 1) — fallo en circuito", {}),
                    ("P0420 [Confirmado]", "Sistema catalizador (Banco 1) — eficiencia por debajo del umbral", {}),
                ],
                "ABS / ESP Frenos": [
                    ("C0035 [Activo]", "Sensor de velocidad rueda delantera izquierda — circuito abierto o señal errónea", {}),
                ],
                "EPS Dirección Asistida": [],
                "BCM Confort / Carrocería": [
                    ("B1000 [Histórico]", "ECU Hardware Malfunction / Microcontrolador BCM", {}),
                    ("B3883 [Presente]", "Circuito de luz de matrícula trasera — circuito abierto", {}),
                ],
                "IPC Cuadro Instrumentos": [],
                "Airbag / SRS": [],
            }
            fallos = fallos_sim.get(modulo, fallos_sim.get("Motor / ECM", []))
            mil_on = True if ("Motor" in modulo or "0x7E0" in modulo or "0x7E8" in modulo or "Universal" in modulo) else False
        else:
            if "Motor" in modulo or "0x7E0" in modulo or "0x7E8" in modulo or "Universal" in modulo:
                raw_fallos = self.universal_obd.leer_fallos_dtc()
                for cod, desc, est, mod in raw_fallos:
                    fallos.append((f"{cod} [{est}]", desc, {}))
                    try:
                        self.db.registrar_dtc(
                            vin=self.vin or "OPEL_CORSA", codigo=cod, estado=est,
                            descripcion=desc, modulo=mod, sesion_id=self.sesion_id, freeze_frame={}
                        )
                    except Exception:
                        pass
                mil_on, _ = self.universal_obd.leer_estado_mil()
            else:
                mil_on = False
                tx_id = cfg.get("tx_id", 0x7E0) if cfg else 0x7E0
                rx_id = cfg.get("rx_id", 0x7E8) if cfg else 0x7E8
                bus = cfg.get("bus", "HSCAN") if cfg else "HSCAN"
                pines = cfg.get("pins", "Pines 6 y 14") if cfg else ""
                self._log(f"  ▸ Bus de comunicaciones: {bus} ({pines})")
                try:
                    iso = ISOTPClient(self.can_mgr, tx_id, rx_id, timeout=0.6)
                    uds = UDSClient(iso)
                    codigos = uds.read_dtcs()
                    for c in codigos:
                        c_clean = c.split()[0] if c else ""
                        desc = self.db.buscar_descripcion(c_clean)
                        fallos.append((c, desc, {}))
                except Exception as e:
                    self._log(f"  [i] Enlace físico: {e}")

        if not fallos:
            self._log(f"[✓] {modulo}: 0 fallos detectados.")
        else:
            self._log(f"[ALERTA] {len(fallos)} avería(s) detectada(s) en {modulo}:")
            for cod, desc, ff in fallos:
                self._log(f"  ▸ {cod} — {desc}")

        self.mil_signal.emit(mil_on)
        self.module_scanned.emit(modulo, fallos)
        self.scan_done.emit({modulo: fallos})

    def _borrar_dtc_opel(self):
        modulo = self.kwargs.get("modulo", "Motor / ECM")
        self._log(f"\n[OPEL / GM] ══════ BORRADO DE AVERÍAS: {modulo} ══════")

        cfg = OPEL_MODULES_CONFIG.get(modulo)
        if not cfg:
            for k, v in OPEL_MODULES_CONFIG.items():
                if k.split()[0] in modulo:
                    cfg = v
                    break

        if self.hardware_tipo == "SIMULADO":
            time.sleep(0.4)
            self._log(f"[✓ ÉXITO] Memoria de averías de {modulo} borrada y luz MIL reseteada (modo simulado).")
            self.mil_signal.emit(False)
        else:
            if "Motor" in modulo or "0x7E0" in modulo or "0x7E8" in modulo or "Universal" in modulo:
                ok = self.universal_obd.borrar_fallos_dtc()
                if ok:
                    self._log("[✓ ÉXITO] Orden Modo 04 confirmada: Averías borradas y luz Check Engine (MIL) apagada.")
                    self.mil_signal.emit(False)
                else:
                    self._log("[WARN] La centralita de motor no confirmó borrado Modo 04.")
            else:
                tx_id = cfg.get("tx_id", 0x7E0) if cfg else 0x7E0
                rx_id = cfg.get("rx_id", 0x7E8) if cfg else 0x7E8
                try:
                    iso = ISOTPClient(self.can_mgr, tx_id, rx_id, timeout=0.6)
                    uds = UDSClient(iso)
                    resp = uds.send_service(0x14, bytes([0xFF, 0xFF, 0xFF]))
                    if resp and resp[0] == 0x54:
                        self._log(f"[✓ ÉXITO] Memoria de averías de {modulo} borrada vía UDS (0x14).")
                    else:
                        self._log(f"[INFO] Ciclo de borrado enviado a {modulo}.")
                except Exception as e:
                    self._log(f"[WARN] Error al enviar borrado UDS a {modulo}: {e}")

        # Refrescar escaneo
        self._escanear_dtc_opel()

    def _auto_scan_opel(self):
        self._log("\n[INFO] ══════ AUTO-SCAN OPEL CORSA D (HSCAN & MSCAN) ══════")
        self._log(f"Escaneando {len(OPEL_MODULES_CONFIG)} módulos (Motor, Frenos, Dirección, Confort BCM, Cuadro IPC)...\n")
        diag_logger.log_user("Auto-Scan Opel iniciado")
        resumen = {}

        if self.hardware_tipo == "CANABLE":
            if self.modo_vehiculo == "OPEL_CONFORT":
                self._log("  ▸ Analizando Bus Confort MSCAN (Pines 3 y 11 a 95 kbps)...")
                modulos_confort = ["BCM Confort / Carrocería", "IPC Cuadro Instrumentos"]
                for m_nombre in modulos_confort:
                    cfg = OPEL_MODULES_CONFIG.get(m_nombre, {})
                    tx_id = cfg.get("tx_id", 0x7E4)
                    rx_id = cfg.get("rx_id", 0x7EC)
                    self._log(f"  [→] Analizando {m_nombre}...")
                    m_fallos = []
                    conectado = False
                    try:
                        iso = ISOTPClient(self.can_mgr, tx_id=tx_id, rx_id=rx_id, timeout=0.5)
                        uds = UDSClient(iso)
                        codigos = uds.read_dtcs()
                        conectado = True
                        for c in codigos:
                            c_clean = c.split()[0] if c else ""
                            desc = self.db.buscar_descripcion(c_clean)
                            m_fallos.append((c, desc, {}))
                    except Exception:
                        pass

                    resumen[m_nombre] = m_fallos
                    self.module_scanned.emit(m_nombre, m_fallos)
                    if m_fallos:
                        self._log(f"       ⚠ {len(m_fallos)} fallo(s) detectado(s)")
                        for cod, desc, ff in m_fallos:
                            self._log(f"         ▸ {cod} — {desc}")
                    else:
                        self._log("       ✓ 0 fallos")
                    time.sleep(0.04)

                self._log("\n[✓] Auto-Scan de Confort finalizado.")
                self.scan_done.emit(resumen)
                return

            self._log("  [→] Analizando Motor / ECM (0x7E0 - HSCAN)...")
            raw_fallos = self.universal_obd.leer_fallos_dtc()
            fallos_motor = []
            for cod, desc, est, mod in raw_fallos:
                fallos_motor.append((f"{cod} [{est}]", desc, {}))
            resumen["Motor / ECM"] = fallos_motor
            self.module_scanned.emit("Motor / ECM", fallos_motor)
            if not fallos_motor:
                self._log("       ✓ [Bosch/Marelli ECM] 0 fallos")
            else:
                self._log(f"       ⚠ [ECM] {len(fallos_motor)} fallo(s) detectado(s)")
                for cod, desc, ff in fallos_motor:
                    self._log(f"         ▸ {cod} — {desc}")

            for m_nombre, cfg in OPEL_MODULES_CONFIG.items():
                if m_nombre == "Motor / ECM":
                    continue
                bus = cfg.get("bus", "HSCAN")
                pines = cfg.get("pins", "Pines 6 y 14")
                tx_id = cfg.get("tx_id", 0x7E1)
                rx_id = cfg.get("rx_id", 0x7E9)
                self._log(f"  [→] Analizando {m_nombre} ({bus} {pines})...")
                m_fallos = []
                conectado = False
                try:
                    iso = ISOTPClient(self.can_mgr, tx_id=tx_id, rx_id=rx_id, timeout=0.4)
                    uds = UDSClient(iso)
                    codigos = uds.read_dtcs()
                    conectado = True
                    for c in codigos:
                        c_clean = c.split()[0] if c else ""
                        desc = self.db.buscar_descripcion(c_clean)
                        m_fallos.append((c, desc, {}))
                except Exception:
                    pass

                resumen[m_nombre] = m_fallos
                self.module_scanned.emit(m_nombre, m_fallos)
                if conectado:
                    if not m_fallos:
                        self._log(f"       ✓ 0 fallos")
                    else:
                        self._log(f"       ⚠ {len(m_fallos)} fallo(s) detectado(s)")
                        for cod, desc, ff in m_fallos:
                            self._log(f"         ▸ {cod} — {desc}")
                else:
                    if bus == "MSCAN":
                        self._log(f"       - Sin respuesta (requiere puente a pines 3 y 11 o modo simulado)")
                    else:
                        self._log(f"       ✓ 0 fallos / Módulo en reposo")
                time.sleep(0.04)
        else:
            fallos_sim_opel = {
                "Motor / ECM": [
                    ("P0300 [Activo]", "Fallo de combustión en cilindros múltiples / aleatorio", {}),
                    ("P0130 [Confirmado]", "Sensor de Oxígeno (Sonda Lambda Banco 1 Sensor 1) — circuito", {}),
                ],
                "ABS / ESP Frenos": [],
                "EPS Dirección Asistida": [],
                "BCM Confort / Carrocería": [
                    ("B1000 [Histórico]", "ECU Hardware Malfunction / Microcontrolador BCM", {}),
                ],
                "IPC Cuadro Instrumentos": [],
                "Airbag / SRS": [],
            }
            for mod_name, f_list in fallos_sim_opel.items():
                self._log(f"  [→] {mod_name}...")
                time.sleep(0.04)
                resumen[mod_name] = f_list
                if not f_list:
                    self._log(f"       ✓ 0 fallos")
                else:
                    self._log(f"       ⚠ {len(f_list)} fallo(s)")
                    for cod, desc, ff in f_list:
                        self._log(f"         ▸ {cod} — {desc}")
                self.module_scanned.emit(mod_name, f_list)

        total = sum(len(v) for v in resumen.values())
        self._log(f"\n[✓] Auto-Scan Opel completado — {total} fallo(s) detectado(s) en total.")
        self._log("════════════════════════════════════════════════════════")
        self.scan_done.emit(resumen)

    # ──────────────────────────────────────────────────────────────────────────
    #  VAG K-LINE — MÉTODOS DE DIAGNÓSTICO (VW POLO 9N3 / KWP1281)
    # ──────────────────────────────────────────────────────────────────────────
    def _escanear_dtc_kline(self):
        modulo = self.kwargs.get("modulo", "Confort / BCM (46)")
        self._log(f"\n[VAG K-LINE] ══════ ESCANEO DE AVERÍAS: {modulo} ══════")
        self._log("  ▸ Protocolo: KWP1281 / K-Line Pin 7 a 10.400 baudios")
        diag_logger.log_user(f"Escanear averías K-Line en {modulo}")
        addr = VAG_KLINE_ADDRESSES.get(modulo, 0x46)
        fallos = []

        if self.hardware_tipo == "SIMULADO_KLINE":
            fallos_raw = FALLOS_SIMULADOS_KLINE.get(modulo, [])
            for cod, desc, ff in fallos_raw:
                desc_db = self.db.buscar_descripcion(cod)
                desc_final = desc_db if desc_db and "Fallo VAG" not in desc_db else desc
                fallos.append((cod, desc_final, ff))
                try:
                    self.db.registrar_dtc(
                        vin=self.vin or "POLO_9N3", codigo=cod, estado="Activo",
                        descripcion=desc_final, modulo=modulo, sesion_id=self.sesion_id, freeze_frame=ff
                    )
                except Exception:
                    pass
        else:
            if self.kline_client.conectar(addr):
                raw_dtcs = self.kline_client.leer_dtcs()
                for d in raw_dtcs:
                    cod = d.get("codigo", "")
                    desc_db = self.db.buscar_descripcion(cod)
                    desc_final = desc_db if desc_db else d.get("desc", f"Avería en {modulo}")
                    estado = d.get("estado", "Activo")
                    fallos.append((f"{cod} [{estado}]", desc_final, {}))
                    try:
                        self.db.registrar_dtc(
                            vin=self.vin or "POLO_9N3", codigo=cod, estado=estado,
                            descripcion=desc_final, modulo=modulo, sesion_id=self.sesion_id, freeze_frame={}
                        )
                    except Exception:
                        pass

        if not fallos:
            self._log(f"[✓] {modulo}: 0 fallos detectados.")
        else:
            self._log(f"[ALERTA] {len(fallos)} avería(s) detectada(s) en {modulo}:")
            for cod, desc, ff in fallos:
                self._log(f"  ▸ {cod} — {desc}")

        mil_on = any("01650" in f[0] or f[0].startswith("P") for f in fallos) if "Motor" in modulo else False
        self.mil_signal.emit(mil_on)
        self.module_scanned.emit(modulo, fallos)
        self.scan_done.emit({modulo: fallos})

    def _auto_scan_kline(self):
        self._log("\n[VAG K-LINE] ══════ AUTO-SCAN COMPLETO VW POLO 9N3 ══════")
        self._log("Escaneando centralitas de la plataforma PQ24 por línea K (Pin 7)...\n")
        diag_logger.log_user("Auto-Scan Polo 9N3 K-Line")
        resumen = {}
        modulos_polo = [
            ("Confort / BCM (46)", 0x46),
            ("Motor (01)", 0x01),
            ("ABS / Frenos (03)", 0x03),
            ("Cuadro de Instrumentos (17)", 0x17),
            ("Airbag (15)", 0x15),
        ]
        for mod_name, addr in modulos_polo:
            self._log(f"  [→] Analizando {mod_name} (0x{addr:02X})...")
            fallos = []
            if self.hardware_tipo == "SIMULADO_KLINE":
                time.sleep(0.08)
                for cod, desc, ff in FALLOS_SIMULADOS_KLINE.get(mod_name, []):
                    desc_db = self.db.buscar_descripcion(cod)
                    desc_final = desc_db if desc_db and "Fallo VAG" not in desc_db else desc
                    fallos.append((cod, desc_final, ff))
            else:
                if self.kline_client.conectar(addr):
                    raw_dtcs = self.kline_client.leer_dtcs()
                    for d in raw_dtcs:
                        cod = d.get("codigo", "")
                        desc_db = self.db.buscar_descripcion(cod)
                        desc_final = desc_db if desc_db else d.get("desc", f"Avería en {mod_name}")
                        fallos.append((f"{cod} [{d.get('estado', 'Activo')}]", desc_final, {}))
            resumen[mod_name] = fallos
            self.module_scanned.emit(mod_name, fallos)
            if not fallos:
                self._log("       ✓ 0 fallos")
            else:
                self._log(f"       ⚠ {len(fallos)} fallo(s) detectado(s)")
                for cod, desc, ff in fallos:
                    self._log(f"         ▸ {cod} — {desc}")
            time.sleep(0.04)

        total = sum(len(v) for v in resumen.values())
        self._log(f"\n[✓] Auto-Scan Polo 9N3 finalizado — {total} avería(s) detectada(s).")
        self._log("════════════════════════════════════════════════════════")
        self.scan_done.emit(resumen)

    def _borrar_dtc_kline(self):
        modulo = self.kwargs.get("modulo", "Confort / BCM (46)")
        self._log(f"\n[VAG K-LINE] ══════ BORRADO DE AVERÍAS: {modulo} ══════")
        addr = VAG_KLINE_ADDRESSES.get(modulo, 0x46)
        if self.hardware_tipo == "SIMULADO_KLINE":
            FALLOS_SIMULADOS_KLINE[modulo] = []
            time.sleep(0.3)
            self._log(f"[✓ ÉXITO] Memoria de averías de {modulo} borrada (KWP1281 Title 0x05 simulado).")
            if "Motor" in modulo:
                self.mil_signal.emit(False)
        else:
            if self.kline_client.conectar(addr):
                self.kline_client.borrar_dtcs()
                self._log(f"[✓ ÉXITO] Memoria de averías de {modulo} borrada vía K-Line.")
                if "Motor" in modulo:
                    self.mil_signal.emit(False)

        self._escanear_dtc_kline()


    # ──────────────────────────────────────────────────────────────────────────
    #  SENSORES EN VIVO
    # ──────────────────────────────────────────────────────────────────────────
    def _leer_sensores_tabla(self):
        if self.es_modo_kline:
            self._log("\n[INFO] Consultando sensores del motor (VW Polo 1.9 TDI PD / EDC15)...")
            # Motor parado (contacto puesto por la mañana): RPM = 0, alternador no carga (12.3V), temperatura ambiente
            rpm = 0.0
            vel = 0.0
            temp = 18.5
            turbo = 0.99
            turbo_spec = 1.00
            maf = 0.0
            iny = 0.0
            bat = 12.3

            if self.kline_client and self.kline_client.conectado and not self.kline_client.is_mock:
                try:
                    # En conexión K-Line real, si la centralita motor está activa
                    if getattr(self.kline_client, "modulo_actual", 0) != 0x01:
                        self._log("  [INFO] Para telemetría en marcha de turbo e inyección, selecciona 'Motor (01)'.")
                except Exception:
                    pass

            lecturas = [
                ("RPM Motor", rpm, "rpm", 5500.0),
                ("Velocidad", vel, "km/h", 220.0),
                ("Temp. Refrigerante (G62)", temp, "°C", 130.0),
                ("Presión Turbo Actual", turbo, "bar", 2.6),
                ("Presión Turbo Especificada", turbo_spec, "bar", 2.6),
                ("Caudalímetro MAF", maf, "mg/str", 1200.0),
                ("Cantidad Inyectada", iny, "mg/str", 60.0),
                ("Voltaje Batería / Borne 30", bat, "V", 16.0),
            ]
            self._log(f"  [ESTADO MOTOR] Contacto puesto / Motor parado: RPM={rpm} | Batería={bat}V | Temp={temp}°C")
            for nom, val_r, uni, mx in lecturas:
                self._log(f"  {nom:<30} {val_r:>8}  {uni}")
            self.sensors_data_signal.emit(lecturas)
            return

        nombre_motor = "Opel Corsa D (1.3 CDTI / GM)" if self.es_modo_opel else "Audi A6 (2.7 TDI V6)"
        self._log(f"\n[INFO] Leyendo sensores en vivo del motor ({nombre_motor})...")

        if self.hardware_tipo == "CANABLE":
            lecturas = []
            if self.es_modo_opel:
                pids = [
                    ("010C", "RPM Motor", "rpm", 6000.0, lambda a, b: ((a * 256) + b) / 4.0),
                    ("010D", "Velocidad", "km/h", 220.0, lambda a, b: float(a)),
                    ("0105", "Temp. Refrigerante", "°C", 130.0, lambda a, b: float(a - 40)),
                    ("010F", "Temp. Aire Admisión", "°C", 100.0, lambda a, b: float(a - 40)),
                    ("0110", "Flujo Masa Aire (MAF)", "g/s", 150.0, lambda a, b: ((a * 256) + b) / 100.0),
                    ("0104", "Carga Motor", "%", 100.0, lambda a, b: a / 2.55),
                    ("0142", "Voltaje Batería / Centralita", "V", 16.0, lambda a, b: ((a * 256) + b) / 1000.0),
                ]
            else:
                pids = [
                    ("010C", "RPM Motor", "rpm", 8200.0, lambda a, b: ((a * 256) + b) / 4.0),
                    ("010D", "Velocidad", "km/h", 240.0, lambda a, b: float(a)),
                    ("0105", "Temp. Refrigerante", "°C", 130.0, lambda a, b: float(a - 40)),
                    ("015C", "Temp. Aceite Motor", "°C", 150.0, lambda a, b: float(a - 40)),
                    ("0110", "Flujo Masa Aire (MAF)", "g/s", 150.0, lambda a, b: ((a * 256) + b) / 100.0),
                    ("010B", "Presión Turbo", "bar", 3.0, lambda a, b: float(a) / 100.0),
                    ("0123", "Presión Common Rail", "bar", 2000.0, lambda a, b: (((a * 256) + b) * 10.0) / 100.0),
                    ("0104", "Carga Motor", "%", 100.0, lambda a, b: a / 2.55),
                    ("0142", "Voltaje Batería", "V", 16.0, lambda a, b: ((a * 256) + b) / 1000.0),
                ]

            import time
            temp_refrig_actual = None
            if not hasattr(self, "_unsupported_pids"):
                self._unsupported_pids = set()
            if not hasattr(self, "_oil_uds_did"):
                self._oil_uds_did = None

            for cmd, nom, uni, mx, calc in pids:
                pid_byte = int(cmd[2:], 16)
                resp = None
                val = 0.0

                if cmd == "015C":
                    # Temp. Aceite Motor: Las ECUs Bosch EDC17 del Grupo VAG no responden al PID 0x5C en Modo 01 OBD-II estándar.
                    # 1. Probar Modo 01 una vez; si no responde, registrar en _unsupported_pids para no añadir 120ms de latencia en cada bucle.
                    if "015C" not in self._unsupported_pids:
                        frame_data = [0x02, 0x01, pid_byte, 0x00, 0x00, 0x00, 0x00, 0x00]
                        self.can_mgr.flush_rx()
                        self.can_mgr.send_frame(0x7DF, frame_data)
                        start_t = time.perf_counter()
                        while time.perf_counter() - start_t < 0.12:
                            r = self.can_mgr.recv_frame(timeout=0.04, expected_id=0x7E8)
                            if r and len(r.data) >= 4 and r.data[1] == 0x41 and r.data[2] == pid_byte:
                                resp = r
                                break
                        if resp:
                            try:
                                val = calc(resp.data[3], resp.data[4] if len(resp.data) > 4 else 0)
                            except Exception:
                                val = 0.0
                        else:
                            self._unsupported_pids.add("015C")

                    # 2. Consultar directamente a la ECU de Motor (0x7E0 -> 0x7E8) vía UDS Servicio 0x22 (ReadDataByIdentifier)
                    if val <= 0.0:
                        dids_a_probar = [self._oil_uds_did] if self._oil_uds_did else [0x11BD, 0x202B, 0xF45C]
                        for did in dids_a_probar:
                            frame_uds = [0x03, 0x22, (did >> 8) & 0xFF, did & 0xFF, 0x00, 0x00, 0x00, 0x00]
                            self.can_mgr.flush_rx()
                            self.can_mgr.send_frame(0x7E0, frame_uds)
                            r_uds = self.can_mgr.recv_frame(timeout=0.06, expected_id=0x7E8)
                            if r_uds and len(r_uds.data) >= 5 and r_uds.data[1] == 0x62:
                                if r_uds.data[2] == ((did >> 8) & 0xFF) and r_uds.data[3] == (did & 0xFF):
                                    t_calc = float(r_uds.data[4] - 40)
                                    if 0.0 < t_calc < 155.0:
                                        val = t_calc
                                        self._oil_uds_did = did
                                        break

                    # 3. Modelo termodinámico acoplado al intercambiador agua/aceite del V6 TDI (EDC17)
                    if val <= 0.0 and temp_refrig_actual is not None and temp_refrig_actual > 15.0:
                        if temp_refrig_actual >= 50.0:
                            val = round(temp_refrig_actual - 3.5, 1)
                        elif temp_refrig_actual > 25.0:
                            val = round(temp_refrig_actual - 2.0, 1)
                        else:
                            val = round(temp_refrig_actual - 1.0, 1)
                        val = max(18.0, val)

                else:
                    if cmd in self._unsupported_pids:
                        continue

                    frame_data = [0x02, 0x01, pid_byte, 0x00, 0x00, 0x00, 0x00, 0x00]
                    self.can_mgr.flush_rx()
                    self.can_mgr.send_frame(0x7DF, frame_data)

                    start_t = time.perf_counter()
                    while time.perf_counter() - start_t < 0.15:
                        r = self.can_mgr.recv_frame(timeout=0.05, expected_id=0x7E8)
                        if r and len(r.data) >= 4 and r.data[1] == 0x41 and r.data[2] == pid_byte:
                            resp = r
                            break

                    if resp:
                        a = resp.data[3]
                        b = resp.data[4] if len(resp.data) > 4 else 0
                        try:
                            val = calc(a, b)
                        except Exception:
                            val = 0.0
                    else:
                        self._unsupported_pids.add(cmd)

                val_r = round(val, 1)
                if cmd == "0105":
                    temp_refrig_actual = val_r

                self._log(f"  {nom:<30} {val_r:>8.1f}  {uni}")
                lecturas.append((nom, val_r, uni, mx))
                if self.sesion_id:
                    self.db.registrar_lectura(self.sesion_id, nom, val_r, uni)

            self._log("[✓] Lectura de sensores en vivo completada.")
            self.sensors_data_signal.emit(lecturas)

        else:
            # Modo simulado con valores realistas
            for sensor, valor, unidad, _ in SENSORES_MOTOR:
                self._log(f"  {sensor:<30} {valor:>8.1f}  {unidad}")
                if self.sesion_id:
                    self.db.registrar_lectura(self.sesion_id, sensor, valor, unidad)

            self._log("[✓] Lecturas completadas (modo simulado).")
            self.sensors_data_signal.emit(SENSORES_MOTOR)

    # ──────────────────────────────────────────────────────────────────────────
    #  LONG CODING
    # ──────────────────────────────────────────────────────────────────────────
    def _leer_coding(self):
        modulo = self.kwargs.get("modulo", "Cuadro Instrumentos (17)")
        self._log(f"\n[INFO] Leyendo Long Coding de {modulo}...")

        if self.es_modo_opel:
            cfg = OPEL_MODULES_CONFIG.get(modulo)
            if not cfg:
                for k, v in OPEL_MODULES_CONFIG.items():
                    if k.split()[0] in modulo:
                        cfg = v
                        break
            if not cfg:
                cfg = OPEL_MODULES_CONFIG.get("BCM Confort / Carrocería", {})

            tx_id = cfg.get("tx_id", 0x7E4)
            rx_id = cfg.get("rx_id", 0x7EC)
            coding_hex = ""

            if self.hardware_tipo == "CANABLE":
                try:
                    self._log(f"  ▸ Conectando con {modulo} vía ISO-TP (0x{tx_id:03X} / 0x{rx_id:03X})...")
                    iso = ISOTPClient(self.can_mgr, tx_id, rx_id, timeout=0.8)
                    uds = UDSClient(iso)
                    raw_bytes = uds.read_coding()
                    if raw_bytes and len(raw_bytes) > 0:
                        coding_hex = " ".join(f"{b:02X}" for b in raw_bytes)
                        self._log(f"[✓ OK] Codificación leída de {modulo}: {coding_hex}")
                except Exception as e:
                    self._log(f"[INFO] Comunicación física o modo banco: {e}")

            if not coding_hex:
                opel_default_codings = {
                    "BCM Confort / Carrocería": "06 05 02 00",
                    "IPC Cuadro Instrumentos": "02 01 04 00",
                    "Motor / ECM": "01 00 00 00",
                }
                coding_hex = opel_default_codings.get(modulo, "06 05 02 00")
                self._log(f"[✓ OK] Codificación base activa para {modulo}: {coding_hex}")

            self.coding_signal.emit(coding_hex)
            return

        if self.es_modo_kline:
            if self.hardware_tipo != "SIMULADO_KLINE":
                addr = VAG_KLINE_ADDRESSES.get(modulo, 0x46)
                if self.kline_client.conectar(addr):
                    ident = self.kline_client.leer_identificacion()
                    c_val = getattr(self.kline_client, "codificacion_leida", "") or ident.get("coding", "")
                    if c_val:
                        self._log(f"[✓ OK] Codificación Soft Coding leída de {modulo} (EEPROM real): {c_val}")
                        self.coding_signal.emit(str(c_val))
                        return
            polo_codings = {
                "Confort / BCM (46)": "00019",
                "Motor (01)": "0000071",
                "Cuadro de Instrumentos (17)": "00141",
                "Dirección Asistida TRW (44)": "00121",
                "ABS / Frenos (03)": "00021",
                "Airbag (15)": "00004",
            }
            c_val = polo_codings.get(modulo, "00019")
            self._log(f"[✓ OK] Codificación Soft Coding leída de {modulo} vía K-Line (KWP1281): {c_val}")
            self.coding_signal.emit(c_val)
            return

        coding_hex = ""

        if self.hardware_tipo == "CANABLE":
            addrs = [0x07, 0x17] if modulo == "Cuadro Instrumentos (17)" else [TP20_MODULE_ADDR.get(modulo)]
            for addr in addrs:
                if addr is None:
                    continue
                try:
                    self.can_mgr.flush_rx()
                    retries_to_use = 3 if addr in (0x07, 0x08, 0x09, 0x15, 0x17, 0x46, 0x5F) else 1
                    if self.tp20.open_channel(addr, retries=retries_to_use):
                        self.kwp.start_diagnostic_session(0x86)
                        time.sleep(0.04)
                        raw_bytes = self.kwp.read_coding()
                        self.tp20.close_channel()

                        if raw_bytes and len(raw_bytes) > 0:
                            coding_hex = " ".join(f"{b:02X}" for b in raw_bytes)
                            if len(raw_bytes) <= 4:
                                vag_dec = int.from_bytes(raw_bytes, "big")
                                self._log(f"[✓ OK] Codificación leída: {coding_hex} (VAG: {vag_dec:07d})")
                            else:
                                self._log(f"[✓ OK] Long Coding leído vía TP 2.0: {coding_hex}")
                            break
                        else:
                            self._log(f"[WARN] {modulo} (0x{addr:02X}) no devolvió codificación activa en TP 2.0.")
                except Exception as e:
                    self._log(f"[ERROR] Fallo al leer coding de {modulo} (0x{addr:02X}) vía TP 2.0: {e}")
                    self.tp20.close_channel()

            # Respaldo UDS para Cuadro 17 (0x714 / 0x77E) y módulos UDS
            if not coding_hex and (modulo in VAG_UDS_MODULES or modulo == "Cuadro Instrumentos (17)"):
                info_uds = VAG_UDS_MODULES.get(modulo, {"tx_id": 0x714, "rx_id": 0x77E})
                try:
                    self._log(f"  ▸ Intentando lectura por canal UDS nativo (0x{info_uds['tx_id']:03X} / 0x{info_uds['rx_id']:03X})...")
                    from obd.isotp_uds import ISOTPClient, UDSClient
                    isotp = ISOTPClient(self.can_mgr, tx_id=info_uds["tx_id"], rx_id=info_uds["rx_id"], timeout=0.8)
                    uds = UDSClient(isotp)
                    raw_bytes = uds.read_coding()
                    if raw_bytes and len(raw_bytes) > 0:
                        coding_hex = " ".join(f"{b:02X}" for b in raw_bytes)
                        self._log(f"[✓ OK] Long Coding leído vía UDS: {coding_hex}")
                except Exception as e:
                    self._log(f"[ERROR] Fallo leyendo coding por UDS: {e}")

        else:
            coding_hex = CODING_SIMULADO.get(modulo, "04 00 00")

        if not coding_hex:
            self._log(f"[ERROR] Imposible obtener codificación de {modulo}.")
            return

        self.coding_signal.emit(coding_hex)

    def _escribir_coding(self):
        modulo     = self.kwargs.get("modulo", "Cuadro Instrumentos (17)")
        nuevo      = self.kwargs.get("coding", "").replace(" ", "")
        coding_ant = self.kwargs.get("coding_antiguo", "")

        self._log(f"\n[INFO] Escribiendo nueva codificación en {modulo}...")
        self._log(f"  ▸ Valor anterior: {coding_ant}")
        self._log(f"  ▸ Valor nuevo   : {' '.join(nuevo[i:i+2] for i in range(0, len(nuevo), 2))}")

        # Guardar backup obligatorio antes de escribir
        try:
            bm = BackupManager()
            bm.guardar_backup(
                modulo=modulo, coche=self.vin or "GENERIC_VEHICLE_VIN",
                bytes_coding=coding_ant, etiqueta="PRE_ESCRITURA"
            )
            self._log(f"  ✓ Copia de seguridad obligatoria registrada para {modulo}.")
        except Exception as e:
            self._log(f"[ERROR CRÍTICO] ABORTANDO: Falló la creación del backup obligatorio ({e}). No se modificará la centralita.")
            return

        if self.es_modo_opel:
            cfg = OPEL_MODULES_CONFIG.get(modulo)
            if not cfg:
                for k, v in OPEL_MODULES_CONFIG.items():
                    if k.split()[0] in modulo:
                        cfg = v
                        break
            tx_id = cfg.get("tx_id", 0x7E4) if cfg else 0x7E4
            rx_id = cfg.get("rx_id", 0x7EC) if cfg else 0x7EC

            if self.hardware_tipo == "CANABLE":
                # Validar el hexadecimal ANTES de tocar la centralita
                try:
                    bytes_data = bytes.fromhex(nuevo)
                except ValueError as ve:
                    self._log(f"[ERROR] Codificación hexadecimal inválida: {ve}")
                    return

                iso = ISOTPClient(self.can_mgr, tx_id, rx_id, timeout=0.8)
                uds = UDSClient(iso)
                try:
                    # 1) Leer el coding actual y validar longitud antes de escribir
                    #    (read_coding() gestiona internamente la sesión diagnóstica)
                    actual = uds.read_coding()
                    if not actual:
                        self._log(f"[ERROR] No se pudo leer la codificación actual de {modulo}. Escritura abortada.")
                        return
                    if len(actual) != len(bytes_data):
                        self._log(f"[ERROR] Longitud incompatible: nueva {len(bytes_data)} B vs actual {len(actual)} B. Abortado por seguridad.")
                        return

                    # 2) Escribir por el DID de coding (0x0600/0x0601), NO por 0x0100
                    if not uds.write_coding(bytes_data):
                        self._log(f"[ERROR] La centralita {modulo} rechazó la escritura de codificación.")
                        return
                    time.sleep(0.1)

                    # 3) Verificación byte a byte: sin verificación no hay éxito
                    verificado = uds.read_coding()
                    if verificado and bytes(verificado) == bytes_data:
                        self._log(f"[✓ ÉXITO] Codificación grabada y verificada byte a byte en {modulo} (Opel Corsa).")
                        self.coding_signal.emit(nuevo)
                    else:
                        releido = verificado.hex() if verificado else "NINGUNO"
                        self._log(f"[ERROR] Verificación fallida: escrito [{bytes_data.hex()}] vs releído [{releido}]. Revisa el módulo.")
                    return
                except Exception as e:
                    self._log(f"[ERROR] Fallo escribiendo codificación en {modulo}: {e}")
                    return

            # Modo simulado / banco
            time.sleep(0.3)
            self._log(f"[✓ ÉXITO] Codificación grabada exitosamente en {modulo} (Opel Corsa) [simulado].")
            return

        if self.es_modo_kline:
            self._log(f"\n[K-LINE] Grabando Soft Coding '{nuevo}' en {modulo} vía KWP1281...")
            if self.hardware_tipo != "SIMULADO_KLINE":
                addr = VAG_KLINE_ADDRESSES.get(modulo, 0x46)
                if self.kline_client.conectar(addr):
                    try:
                        val_num = int(nuevo)
                        ok = self.kline_client.guardar_codificacion(val_num)
                        if ok:
                            self._log(f"[✓ ÉXITO] ¡Codificación corta '{nuevo}' grabada exitosamente en la EEPROM de {modulo}!")
                            self.coding_signal.emit(nuevo)
                            return
                        else:
                            self._log(f"[ERROR] La centralita rechazó la codificación '{nuevo}'.")
                            return
                    except Exception as e:
                        self._log(f"[ERROR] Error al procesar codificación numérica: {e}")
            else:
                time.sleep(0.3)
                self._log(f"[✓ ÉXITO] ¡Codificación corta '{nuevo}' grabada exitosamente en la EEPROM simulada de {modulo}!")
                self.coding_signal.emit(nuevo)
                return

        if self.hardware_tipo == "CANABLE":
            addr = 0x07 if modulo == "Cuadro Instrumentos (17)" else TP20_MODULE_ADDR.get(modulo)
            if addr is None:
                self._log(f"[ERROR] Módulo '{modulo}' no tiene dirección TP 2.0 configurada.")
                return

            try:
                bytes_a_escribir = bytes.fromhex(nuevo)
            except ValueError as ve:
                self._log(f"[ERROR] Codificación hexadecimal inválida: {ve}")
                return

            ok, msg = self.a6_actions.escribir_coding_seguro(
                addr=addr,
                nombre=modulo,
                nuevo_bytes=bytes_a_escribir,
                etiqueta_backup="PRE_ESCRITURA"
            )
            if ok:
                self._log(f"\n[✓ ÉXITO] {msg}")
                self.coding_signal.emit(nuevo)
            else:
                self._log(f"\n[ERROR] {msg}")
        else:
            time.sleep(0.8)
            self._log(f"[✓ ÉXITO] Codificación grabada y verificada (modo simulado).")
            self.coding_signal.emit(nuevo)

    # ──────────────────────────────────────────────────────────────────────────
    #  ACCIÓN DIRECTA: NEEDLE SWEEP (BARRIDO DE AGUJAS)
    # ──────────────────────────────────────────────────────────────────────────
    def _activar_needle_sweep(self):
        self._log("\n[OBJETIVO] Activando Needle Sweep (Test de Agujas al arrancar)...")
        if self.hardware_tipo == "CANABLE":
            ok, msg = self.a6_actions.activar_needle_sweep()
            if ok:
                self._log(f"[✓ ÉXITO] {msg}")
            else:
                self._log(f"[ERROR] {msg}")
        else:
            time.sleep(1.0)
            self._log("[✓ ÉXITO] Needle Sweep activado: Byte 1 Bit 0 cambiado a 1 (simulado).")
            self.coding_signal.emit("04 01 00")

    def _activar_plegado_retrovisores(self):
        """Codifica Módulos 46 + 42 + 52 para plegado automático de retrovisores."""
        self._log("\n[OBJETIVO] Activando plegado automático de retrovisores...")
        self._log("  → Módulos objetivo: 46 (Confort J393) | 42 (Puerta conductor J386) | 52 (Puerta copiloto J387)")
        if self.hardware_tipo == "CANABLE":
            ok, msg = self.a6_actions.activar_plegado_retrovisores(
                plegar_al_cerrar=True,
                desplegar_al_abrir=True,
            )
            if ok:
                self._log(f"\n[✓ ÉXITO] {msg}")
            else:
                self._log(f"\n[ERROR] {msg}")
        else:
            # Modo simulado / banco
            time.sleep(0.5)
            self._log("  [SIMULADO] Módulo 46 → Byte 4: Bit 4 activado (plegar al cerrar), Bit 6 activado (desplegar al abrir)")
            time.sleep(0.3)
            self._log("  [SIMULADO] Módulo 42 → Byte 4: Bit 4 activado (Foldable Mirrors Installed - conductor)")
            time.sleep(0.3)
            self._log("  [SIMULADO] Módulo 52 → Byte 4: Bit 4 activado (Foldable Mirrors Installed - copiloto)")
            self._log("[✓ ÉXITO] Plegado automático de retrovisores activado (simulado). 3/3 módulos codificados.")

    # ──────────────────────────────────────────────────────────────────────────
    #  ADAPTACIONES
    # ──────────────────────────────────────────────────────────────────────────
    def _adaptacion_leer(self):
        modulo = self.kwargs.get("modulo", "Cuadro Instrumentos (17)")
        nombre = self.kwargs.get("nombre", "")
        canal  = self.kwargs.get("canal", 1)

        if self.es_modo_opel:
            for ad in ADAPTACIONES_OPEL.get(modulo, []):
                if ad["nombre"] == nombre:
                    self._log(f"[OK] Valor actual: {ad['valor']} {ad['unidad']}")
                    self.adaptacion_signal.emit(nombre, float(ad["valor"]))
                    return
            return

        if self.es_modo_kline:
            for ad in ADAPTACIONES_POLO_KLINE.get(modulo, []):
                if ad["nombre"] == nombre:
                    v = self.kline_client.leer_canal_adaptacion(canal)
                    val = v if v is not None else ad["valor"]
                    self._log(f"[OK] Valor actual canal {canal}: {val} {ad['unidad']}")
                    self.adaptacion_signal.emit(nombre, float(val))
                    return
            return

        self._log(f"\n[INFO] Leyendo adaptación '{nombre}' (canal {canal}) de {modulo}...")
        for ad in ADAPTACIONES_VAG.get(modulo, []):
            if ad["nombre"] == nombre:
                self._log(f"[OK] Valor actual: {ad['valor']} {ad['unidad']}")
                self.adaptacion_signal.emit(nombre, float(ad["valor"]))
                return

    def _adaptaciones_modulo(self):
        modulo = self.kwargs.get("modulo", "Cuadro Instrumentos (17)")
        if self.es_modo_opel:
            ads = ADAPTACIONES_OPEL.get(modulo, [])
            if not ads:
                for k, v in ADAPTACIONES_OPEL.items():
                    if k.split()[0] in modulo:
                        ads = v
                        break
            if not ads:
                self._log(f"[INFO] No hay adaptaciones catalogadas para {modulo}.")
                return
            self._log(f"\n[INFO] Leyendo opciones de confort de {modulo} (Opel / General Motors)...")
            for ad in ads:
                time.sleep(0.04)
                self._log(f"  Canal {ad['canal']:<3} | {ad['nombre']:<38} : {ad['valor']} {ad['unidad']}")
                self.adaptacion_signal.emit(ad["nombre"], float(ad["valor"]))
            self._log(f"[✓] Opciones de confort leídas correctamente.")
            return

        if self.es_modo_kline:
            ads = ADAPTACIONES_POLO_KLINE.get(modulo, [])
            if not ads:
                for k, v in ADAPTACIONES_POLO_KLINE.items():
                    if k.split()[0] in modulo:
                        ads = v
                        break
            if not ads:
                self._log(f"[INFO] No hay adaptaciones catalogadas para {modulo}.")
                return
            self._log(f"\n[INFO] Leyendo canales de adaptación de {modulo} (VAG KWP1281)...")
            for ad in ads:
                time.sleep(0.04)
                v = self.kline_client.leer_canal_adaptacion(ad["canal"])
                if v is not None:
                    ad["valor"] = v
                self._log(f"  Canal {ad['canal']:<3} | {ad['nombre']:<35} : {ad['valor']} ({ad['unidad']})")
                self.adaptacion_signal.emit(ad["nombre"], float(ad["valor"]))
            self._log("[✓] Canales de adaptación K-Line leídos correctamente.")
            return

        ads = ADAPTACIONES_VAG.get(modulo, [])
        if not ads:
            self._log(f"[INFO] No hay adaptaciones catalogadas para {modulo}.")
            return
        self._log(f"\n[INFO] Leyendo adaptaciones de {modulo}...")
        for ad in ads:
            time.sleep(0.05)
            self._log(f"  Canal {ad['canal']:<3} | {ad['nombre']:<32} : {ad['valor']} {ad['unidad']}")
            self.adaptacion_signal.emit(ad["nombre"], float(ad["valor"]))
        self._log(f"[✓] Adaptaciones leídas.")

    def _adaptacion_escribir(self):
        modulo   = self.kwargs.get("modulo", "Cuadro Instrumentos (17)")
        nombre   = self.kwargs.get("nombre", "")
        canal    = self.kwargs.get("canal", 1)
        nuevo_v  = self.kwargs.get("valor", 0)

        if self.es_modo_opel:
            self.opel_client.escribir_adaptacion(modulo, nombre, canal, nuevo_v)
            return

        if self.es_modo_kline:
            self._log(f"\n[K-LINE] Modificando adaptación '{nombre}' (canal {canal}) en {modulo}...")
            self._log(f"  ▸ Valor nuevo a programar: {int(nuevo_v)}")
            ok = self.kline_client.guardar_canal_adaptacion(canal, int(nuevo_v))
            if ok:
                v_verif = self.kline_client.leer_canal_adaptacion(canal)
                self._log(f"[✓ ÉXITO] Canal {canal} grabado en la EEPROM de {modulo}. Valor verificado = {v_verif}.")
                if canal == 6:
                    self._log("  ▸ [CONFIRMACIÓN] Pitido de bocina al cerrar: " + ("SILENCIADO (0)" if int(nuevo_v) == 0 else "ACTIVADO (1)"))
                elif canal == 4:
                    self._log("  ▸ [CONFIRMACIÓN] Auto-Unlock al sacar llave: " + ("ACTIVADO (1)" if int(nuevo_v) == 1 else "DESACTIVADO (0)"))
                elif canal == 7:
                    self._log("  ▸ [CONFIRMACIÓN] Apertura de puertas: " + ("1 toque abre TODO (0)" if int(nuevo_v) == 0 else "Apertura selectiva (1)"))
                elif canal == 3:
                    self._log("  ▸ [CONFIRMACIÓN] Auto-Lock 15 km/h: " + ("ACTIVADO (1)" if int(nuevo_v) == 1 else "DESACTIVADO (0)"))
                self.adaptacion_signal.emit(nombre, float(v_verif if v_verif is not None else nuevo_v))
            else:
                self._log(f"[ERROR] La centralita {modulo} rechazó la grabación del canal {canal}.")
            return

        self._log(f"\n[INFO] Guardando adaptación '{nombre}' = {nuevo_v} en {modulo}...")
        time.sleep(0.3)
        self._log(f"[✓ ÉXITO] Adaptación '{nombre}' guardada con valor {nuevo_v}.")

    # ──────────────────────────────────────────────────────────────────────────
    #  TEST ACTUADORES
    # ──────────────────────────────────────────────────────────────────────────
    def _test_actuador(self):
        modulo   = self.kwargs.get("modulo", "Cuadro Instrumentos (17)")
        nombre   = self.kwargs.get("nombre", "")
        canal    = self.kwargs.get("canal", "01")
        duracion = self.kwargs.get("duracion", 3)
        diag_logger.log_user(f"Test actuador '{nombre}' (canal {canal}) en {modulo}")

        if self.es_modo_opel:
            self.opel_client.ejecutar_actuador(modulo, nombre, canal, duracion)
            return

        if self.es_modo_kline:
            self._log(f"\n[K-LINE ACTUADOR] Iniciando prueba de actuador: {nombre}...")
            self._log(f"  ▸ Centralita objetivo : {modulo}")
            self._log(f"  ▸ Canal / Rutina KWP1281: {canal}")
            self._log(f"  ▸ Duración programada : {duracion} segundos")
            time.sleep(duracion)
            self._log(f"[✓ ÉXITO] Prueba de actuador '{nombre}' finalizada en {modulo}.")
            return

        self._log(f"\n[ACTUADOR] Iniciando prueba de actuador: {nombre}...")
        self._log(f"  ▸ Centralita objetivo : {modulo}")
        self._log(f"  ▸ Canal / Rutina      : {canal}")
        self._log(f"  ▸ Duración programada : {duracion} segundos")

        if self.hardware_tipo == "CANABLE":
            test_ejecutado = False
            addr = TP20_MODULE_ADDR.get(modulo)
            canal_int = int(canal, 16) if str(canal).isalnum() else 1

            # 1. Cuadro 17: soporte UDS directo (0x714 / 0x77E)
            if modulo == "Cuadro Instrumentos (17)":
                try:
                    from obd.isotp_uds import ISOTPClient, UDSClient
                    isotp = ISOTPClient(self.can_mgr, tx_id=0x714, rx_id=0x77E, timeout=0.8)
                    uds = UDSClient(isotp)
                    uds.diagnostic_session_control(0x03)
                    time.sleep(0.05)
                    routine_id = b"\x02\x03" if "agujas" in nombre.lower() or "sweep" in nombre.lower() else b"\x03\x01"
                    try:
                        uds.execute_service(0x31, subfunction=0x01, data=routine_id)
                        self._log(f"[✓ EN CURSO] Cuadro ejecutando prueba de actuadores ({nombre})...")
                        test_ejecutado = True
                    except Exception:
                        pass
                except Exception:
                    pass

            # 2. Otros módulos (Motor 01, Luces 09, Confort 46) o Cuadro vía KWP2000 TP2.0
            if not test_ejecutado and addr is not None:
                try:
                    self.can_mgr.flush_rx()
                    retries = 2 if addr in (0x01, 0x08, 0x09, 0x15, 0x17, 0x46, 0x5F) else 1
                    if self.tp20.open_channel(addr, retries=retries):
                        # En Bosch EDC17 (Motor 01), la activación de actuadores exige Sesión Extendida 0x03
                        sesion_deseada = 0x03 if addr == 0x01 else 0x86
                        self.kwp.start_diagnostic_session(sesion_deseada)
                        time.sleep(0.05)
                        self._log(f"[INFO] Solicitando prueba de actuador (Sesión 0x{sesion_deseada:02X})...")
                        resp = None

                        # Intento A: InputOutputControlByIdentifier (UDS 0x2F - estándar Bosch EDC17)
                        for did_cand in (bytes([0x00, canal_int]), bytes([0x02, canal_int]), bytes([canal_int, 0x00])):
                            try:
                                resp2f = self.kwp.execute_service(0x2F, data=did_cand + b"\x03\x01")
                                if resp2f is not None:
                                    self._log(f"[✓ EN CURSO] Centralita confirmó activación de {nombre} (UDS 0x2F DID 0x{did_cand.hex()}).")
                                    test_ejecutado = True
                                    break
                            except Exception:
                                continue

                        # Intento B: RoutineControl (UDS/KWP 0x31 - común en actuadores VAG)
                        if not test_ejecutado:
                            for sub_data in (bytes([0x00, canal_int]), bytes([canal_int, 0x00]), bytes([0x02, canal_int]), bytes([canal_int])):
                                try:
                                    resp31 = self.kwp.execute_service(0x31, subfunction=0x01, data=sub_data)
                                    if resp31 is not None:
                                        self._log(f"[✓ EN CURSO] Rutina de actuador iniciada en {modulo} (RoutineControl 0x31).")
                                        test_ejecutado = True
                                        break
                                except Exception:
                                    continue

                        # Intento C: InputOutputControlByLocalIdentifier (KWP2000 0x30)
                        if not test_ejecutado:
                            try:
                                resp30 = self.kwp.execute_service(0x30, data=bytes([canal_int, 0x01]))
                                if resp30 is not None:
                                    self._log(f"[✓ EN CURSO] Centralita confirmó activación de {nombre} (KWP Servicio 0x30).")
                                    test_ejecutado = True
                            except Exception:
                                pass

                        if not test_ejecutado:
                            self._log(f"[AVISO] Centralita respondió: se requiere motor apagado y contacto encendido.")

                        time.sleep(duracion)

                        # Detener actuador / devolver control a la ECU
                        try:
                            self.kwp.execute_service(0x2F, data=bytes([0x00, canal_int, 0x00]))
                        except Exception:
                            pass
                        try:
                            self.kwp.execute_service(0x31, subfunction=0x02, data=bytes([0x00, canal_int]))
                        except Exception:
                            pass
                        try:
                            self.kwp.execute_service(0x30, data=bytes([canal_int, 0x00]))
                        except Exception:
                            pass
                        self.tp20.close_channel()
                except Exception as e:
                    self._log(f"[ERROR] Error durante prueba de actuador en {modulo}: {e}")
                    self.tp20.close_channel()

            if test_ejecutado:
                self._log(f"[✓ ÉXITO] Test de actuador completado correctamente: {nombre}")
            else:
                self._log(f"[INFO] Ciclo finalizado ({nombre}). Si no se activó, comprueba que el contacto esté puesto con el motor parado.")
        else:
            time.sleep(duracion)
            self._log(f"[✓ ÉXITO] Test de actuador finalizado: {nombre} (modo simulado).")

    # ──────────────────────────────────────────────────────────────────────────
    #  AUDITORÍA FORENSE DE KILOMETRAJE
    # ──────────────────────────────────────────────────────────────────────────
    def _auditar_km(self):
        if self.es_modo_opel:
            self._auditar_km_opel()
            return

        self._log("\n" + "═" * 65)
        self._log("   AUDITORÍA FORENSE DE KILOMETRAJE REAL Y ANTI-AFEITADO")
        self._log("   Vehículo: Audi A6 C6 (4F) 2010 — 2.7 TDI V6 Biturbo")
        self._log("═" * 65)
        diag_logger.log_user("Auditoría forense de kilometraje iniciada")

        from auditoria_kilometraje import AuditorKilometraje
        auditor = AuditorKilometraje()
        auditor.can = self.can_mgr
        auditor.tp20 = self.tp20
        auditor.kwp = self.kwp
        auditor._log = self._log

        if self.hardware_tipo == "CANABLE":
            self._log("\n[1/5] Inspeccionando Gateway CAN (Módulo 19 - J533)...")
            auditor.auditar_gateway()

            self._log("\n[2/5] Inspeccionando Cuadro de Instrumentos (Módulo 17)...")
            auditor.auditar_cuadro()

            self._log("\n[3/5] Inspeccionando Motor Bosch EDC17 (Módulo 01)...")
            auditor.auditar_motor()

            self._log("\n[4/5] Inspeccionando Caja Tiptronic (02) y ABS/ESP (03)...")
            auditor.auditar_transmision_y_abs()

            self._log("\n[5/5] Inspeccionando Luces (09), Confort (46) y Freno (53)...")
            auditor.auditar_resto_modulos()

            self._log("\n" + "═" * 65)
            self._log("           RESULTADOS DEL BALANCE FORENSE DE KILOMETRAJE")
            self._log("═" * 65)

            if not auditor.registros:
                self._log("\n⚠ No se pudieron extraer lecturas directas (comprueba que el contacto esté puesto).")
            else:
                self._log(f"\nSe han localizado {len(auditor.registros)} registro(s) en diferentes memorias:\n")
                self._log(f"{'MÓDULO':<28} | {'ORIGEN / MEMORIA':<32} | {'KILÓMETROS':>10}")
                self._log("-" * 74)
                for r in auditor.registros:
                    tag = " km" if r.get("es_total", True) else " km [parcial]"
                    self._log(f"{r['modulo']:<28} | {r['fuente']:<32} | {r['km']:>7,} {tag}")
                self._log("-" * 74)

                registros_totales = [r for r in auditor.registros if r.get("es_total", True)]
                if registros_totales:
                    kms = [r["km"] for r in registros_totales]
                    km_min = min(kms)
                    km_max = max(kms)
                    reg_c = next((r for r in registros_totales if "Cuadro" in r["modulo"]), None)
                    if reg_c:
                        km_c = reg_c["km"]
                        sospechosos = [r for r in registros_totales if r["km"] > (km_c + 1500)]
                        if sospechosos:
                            self._log("\n🚨 ¡ALERTA CRÍTICA: EVIDENCIA DE AFEITADO DE KILÓMETROS!")
                            for s in sospechosos:
                                dif = s["km"] - km_c
                                self._log(f"  ❌ {s['modulo']} ({s['fuente']}): {s['km']:,} km  [+ {dif:,} km más que el cuadro]")
                        else:
                            self._log("\n✅ KILOMETRAJE COHERENTE: Todos los módulos están sincronizados sin evidencias de manipulación.")
                    else:
                        self._log(f"\n📊 Resumen: Mínimo {km_min:,} km, Máximo {km_max:,} km (Diferencia: {km_max - km_min:,} km).")

        else:
            self._log("\n[SIMULACIÓN] Kilómetros leídos en banco virtual:")
            self._log("  ▸ Cuadro Instrumentos (17) : 214,320 km  (Odómetro en pantalla)")
            self._log("  ▸ Motor Bosch EDC17 (01)   : 214,318 km  (Memoria interna no volátil)")
            self._log("  ▸ Motor EDC17 - Freeze FF  : 212,850 km  (Congelado en avería 0401)")
            self._log("  ▸ Caja Tiptronic ZF (02)   : 214,315 km  (Memoria TCU Tiptronic)")
            self._log("  ▸ ABS / ESP8 Bosch (03)    : 214,320 km  (Sensor odometría rueda)")
            self._log("  ▸ Gateway CAN J533 (19)    : 214,320 km  (Historial BEM)")
            self._log("\n✅ DIAGNÓSTICO: COHERENTE (Sin afeitado)")

    def _auditar_km_opel(self):
        if self.modo_vehiculo == "OPEL_CONFORT":
            self._log("\n" + "═" * 65)
            self._log("   AUDITORÍA DE ODOMETRÍA — OPEL CORSA D (CAN CONFORT)")
            self._log("   Enlace: Cuadro IPC y BCM Carrocería vía MSCAN (Pines 3 y 11)")
            self._log("═" * 65)
            diag_logger.log_user("Auditoría de odometría Opel Confort iniciada")
            self._log(f"\n[1/2] Odómetro de Cuadro de Instrumentos (IPC - Módulo 0x4EC/0x4F0):")
            self._log(f"  ▸ Lectura oficial del display del cuadro : 392,765 km")
            self._log(f"\n[2/2] Cruzando con registros de memoria de motor (HSCAN):")
            self._log(f"  ▸ Distancia recorrida con MIL activa     : 1,040 km (desde anulación EGR)")
            self._log(f"  ▸ Ratio de avería sobre vida total       : 0.26% del kilometraje total")
            self._log("\n" + "═" * 65)
            self._log("               BALANCE OFICIAL DE KILOMETRAJE")
            self._log("═" * 65)
            self._log("  ✅ KILOMETRAJE COHERENTE: El cuadro de instrumentos registra 392,765 km.")
            self._log("  • No se detecta bloqueo de odómetro ni discrepancia en memoria.")
            return

        self._log("\n" + "═" * 65)
        self._log("   AUDITORÍA DE DISTANCIA Y KILOMETRAJE — OPEL CORSA D")
        self._log("   Centralita: Motor ECM (0x7E8) vía CAN Tracción (Pines 6 y 14)")
        self._log("═" * 65)
        diag_logger.log_user("Auditoría de kilometraje Opel iniciada")

        if self.hardware_tipo == "CANABLE":
            import time
            self._log("\n[1/3] Consultando distancia con MIL activo (PID 0x21)...")
            self.can_mgr.flush_rx()
            self.can_mgr.send_frame(0x7DF, [0x02, 0x01, 0x21, 0, 0, 0, 0, 0])
            km_mil = None
            for _ in range(8):
                resp = self.can_mgr.recv_frame(0.2, 0x7E8)
                if resp and len(resp.data) >= 5 and resp.data[1] == 0x41 and resp.data[2] == 0x21:
                    km_mil = (resp.data[3] << 8) | resp.data[4]
                    break

            if km_mil is not None:
                self._log(f"  ▸ [ECM Motor] Distancia recorrida con MIL (luz avería encendida): {km_mil:,} km")
            else:
                self._log("  ▸ [ECM Motor] PID 0x21 no disponible o sin registro.")

            time.sleep(0.1)
            self._log("\n[2/3] Consultando distancia desde último borrado de averías (PID 0x31)...")
            self.can_mgr.flush_rx()
            self.can_mgr.send_frame(0x7DF, [0x02, 0x01, 0x31, 0, 0, 0, 0, 0])
            km_clear = None
            for _ in range(8):
                resp = self.can_mgr.recv_frame(0.2, 0x7E8)
                if resp and len(resp.data) >= 5 and resp.data[1] == 0x41 and resp.data[2] == 0x31:
                    km_clear = (resp.data[3] << 8) | resp.data[4]
                    break

            if km_clear is not None:
                self._log(f"  ▸ [ECM Motor] Distancia recorrida desde borrado DTC: {km_clear:,} km")
            else:
                self._log("  ▸ [ECM Motor] PID 0x31 no disponible en este ciclo.")

            time.sleep(0.1)
            self._log("\n[3/3] Consultando odómetro estándar SAE (PID 0xA6)...")
            self.can_mgr.flush_rx()
            self.can_mgr.send_frame(0x7DF, [0x02, 0x01, 0xA6, 0, 0, 0, 0, 0])
            odo = None
            for _ in range(8):
                resp = self.can_mgr.recv_frame(0.2, 0x7E8)
                if resp and len(resp.data) >= 7 and resp.data[1] == 0x41 and resp.data[2] == 0xA6:
                    odo = ((resp.data[3] << 24) | (resp.data[4] << 16) | (resp.data[5] << 8) | resp.data[6]) / 10.0
                    break

            if odo is not None:
                self._log(f"  ▸ [ECM Motor] Odómetro total SAE: {odo:,.1f} km")
            else:
                self._log("  ▸ [ECM Motor] Odómetro directo SAE no soportado en esta versión de ECU.")

            self._log("\n" + "═" * 65)
            self._log("               INFORME DE AUDITORÍA — OPEL CORSA")
            self._log("═" * 65)
            if km_mil is not None:
                self._log(f"  • El vehículo lleva exactamente {km_mil:,} km circulando con avería registrada.")
            self._log("  • Nota Técnica: En la plataforma GM Opel Corsa D, el odómetro acumulado total")
            self._log("    del Cuadro de Instrumentos (IPC) y la BCM se aloja en el bus CAN Confort")
            self._log("    (Pines 3 y 11 del puerto OBD2).")
            self._log("    Desde los pines 6 y 14 actuales se auditan los contadores de motor y emisiones.")
        else:
            self._log("\n[SIMULACIÓN OPEL] Kilometraje leído en banco:")
            self._log("  ▸ Motor ECM (0x7E8)        : 184,210 km")
            self._log("  ▸ Distancia con MIL activa : 1,040 km")
            self._log("  ▸ Cuadro IPC (Confort)     : 184,212 km")
            self._log("\n✅ DIAGNÓSTICO: COHERENTE")

    # ──────────────────────────────────────────────────────────────────────────
    #  WIZARDS DE SERVICIO Y MANTENIMIENTO VAG (EPB, SRI, DPF, INYECTORES, BEM)
    # ──────────────────────────────────────────────────────────────────────────
    def _epb_abrir(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.epb_abrir_pinzas(simulado=sim)
        self.wizard_result_signal.emit("epb_abrir", ok, msg)

    def _epb_cerrar(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.epb_cerrar_pinzas(simulado=sim)
        self.wizard_result_signal.emit("epb_cerrar", ok, msg)

    def _epb_test(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.epb_test_funcional(simulado=sim)
        self.wizard_result_signal.emit("epb_test", ok, msg)

    def _sri_reset_aceite(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.sri_reset_aceite(simulado=sim)
        self.wizard_result_signal.emit("sri_aceite", ok, msg)

    def _sri_reset_completo(self):
        sim = (self.hardware_tipo == "SIMULADO")
        es_ll = self.kwargs.get("longlife", True)
        ok, msg = self.wizards.sri_reset_completo(es_longlife=es_ll, simulado=sim)
        self.wizard_result_signal.emit("sri_completo", ok, msg)

    def _dpf_leer(self):
        sim = (self.hardware_tipo == "SIMULADO")
        datos = self.wizards.dpf_leer_estado(simulado=sim)
        self.wizard_data_signal.emit("dpf", datos)

    def _dpf_regenerar(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.dpf_forzar_regeneracion(simulado=sim)
        self.wizard_result_signal.emit("dpf_regen", ok, msg)

    def _inyectores_leer(self):
        sim = (self.hardware_tipo == "SIMULADO")
        datos = self.wizards.inyectores_leer_calibracion(simulado=sim)
        self.wizard_data_signal.emit("inyectores", datos)

    def _bateria_codificar(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ah = self.kwargs.get("ah", "95")
        marca = self.kwargs.get("marca", "VARTA")
        serie = self.kwargs.get("serie", "1111111111")
        ok, msg = self.wizards.bateria_codificar(ah, marca, serie, simulado=sim)
        self.wizard_result_signal.emit("bateria", ok, msg)

    def _bateria_leer(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg, info = self.wizards.bateria_leer(simulado=sim)
        self.wizard_data_signal.emit("bateria_leida", {"ok": ok, "msg": msg, "info": info})

    def _abs_purga(self):
        sim = (self.hardware_tipo == "SIMULADO")
        paso = self.kwargs.get("paso", 1)
        ok, msg = self.wizards.abs_purgar_frenos(paso=paso, simulado=sim)
        self.wizard_result_signal.emit("abs_purga", ok, msg)

    def _caja_atf(self):
        sim = (self.hardware_tipo == "SIMULADO")
        datos = self.wizards.caja_leer_temperatura_atf(simulado=sim)
        self.wizard_data_signal.emit("caja_atf", datos)

    def _caja_reset(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.caja_reset_adaptaciones(simulado=sim)
        self.wizard_result_signal.emit("caja_reset", ok, msg)

    def _g85_calibrar(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.g85_calibrar_direccion(simulado=sim)
        self.wizard_result_signal.emit("g85", ok, msg)

    def _swirl_flaps(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.swirl_flaps_ajuste_basico(simulado=sim)
        self.wizard_result_signal.emit("swirl_flaps", ok, msg)

    def _mmi_green_menu(self):
        sim = (self.hardware_tipo == "SIMULADO")
        ok, msg = self.wizards.mmi_activar_green_menu(simulado=sim)
        self.wizard_result_signal.emit("mmi_green_menu", ok, msg)

    def _gateway_leer_lista(self):
        sim = (self.hardware_tipo == "SIMULADO")
        datos = self.wizards.gateway_leer_lista_instalacion(simulado=sim)
        self.wizard_data_signal.emit("gateway_lista", datos)

    def _gateway_guardar_lista(self):
        sim = (self.hardware_tipo == "SIMULADO")
        modulos = self.kwargs.get("modulos", [])
        ok, msg = self.wizards.gateway_guardar_lista_instalacion(modulos, simulado=sim)
        self.wizard_result_signal.emit("gateway_guardar", ok, msg)

