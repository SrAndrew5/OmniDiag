# -*- coding: utf-8 -*-
"""
obd/vag_kline.py
Motor de Comunicacion K-Line para el Grupo VAG (Volkswagen, Audi, SEAT, Skoda)
Soporta:
  1. Protocolo KWP1281 (Volkswagen Propietario - 5-Baud Init, 9600/10400 8N1).
  2. Protocolo KWP2000 sobre K-Line (ISO 14230-4).
  3. Lectura y Borrado de Averias (DTCs oficiales VAG).
  4. Canales de Adaptacion (Canal 04 Auto-Unlock, Canal 06 Mute Beep, Canal 07).
  5. Bloques de Valores de Medicion en Vivo (Measuring Blocks).
  6. Modo Emulador / Simulador Virtual Offline (Polo 9N3 1.9 TDI).
"""

import time
import os
import sys
import struct
from typing import Dict, List, Optional, Tuple, Any

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

VAG_KLINE_ADDRESSES = {
    "Motor (01)":                     0x01,
    "Caja de Cambios (02)":           0x02,
    "ABS / Frenos (03)":              0x03,
    "Climatizacion (08)":             0x08,
    "Central Electrica / Luces (09)": 0x09,
    "Airbag (15)":                    0x15,
    "Cuadro de Instrumentos (17)":    0x17,
    "Inmovilizador (25)":             0x25,
    "Confort / BCM (46)":             0x46,
    "Radio / Sonido (56)":            0x56,
}

POLO_9N3_CONFORT_CHANNELS = {
    3: {
        "nombre": "Auto-Lock (Cierre a 15 km/h)",
        "desc": "Bloquea automaticamente todos los pestillos al superar 15 km/h.",
        "defecto": 1,
        "opciones": {0: "Desactivado", 1: "Activado (Seguridad antiasalto)"}
    },
    4: {
        "nombre": "Auto-Unlock (Apertura al sacar llave)",
        "desc": "Desbloquea automaticamente todas las puertas al extraer la llave del clausor.",
        "defecto": 0,
        "opciones": {0: "Desactivado (Doble tiron manual)", 1: "Activado (Recomendado)"}
    },
    5: {
        "nombre": "Aviso Acustico al abrir con mando",
        "desc": "Emite doble confirmacion acustica al abrir con mando a distancia.",
        "defecto": 0,
        "opciones": {0: "Desactivado (Silencioso)", 1: "Activado"}
    },
    6: {
        "nombre": "Aviso Acustico / Claxon al cerrar",
        "desc": "Hace sonar la bocina del coche brevemente al cerrar con el mando a distancia.",
        "defecto": 1,
        "opciones": {0: "Silencioso (Recomendado - Sin pitido)", 1: "Bocinazo Activado"}
    },
    7: {
        "nombre": "Apertura Selectiva de Puertas",
        "desc": "1 toque abre solo conductor; 2 toques abren todo. Si es 0, 1 toque abre todo.",
        "defecto": 1,
        "opciones": {0: "1 Toque abre todas las puertas", 1: "Apertura Selectiva (2 Toques)"}
    },
    8: {
        "nombre": "Destello Intermitentes al cerrar",
        "desc": "Parpadeo de los intermitentes para confirmar que todas las puertas estan cerradas y bloqueadas.",
        "defecto": 1,
        "opciones": {0: "Desactivado", 1: "Activado (Confirmacion visual)"}
    },
    9: {
        "nombre": "Destello Intermitentes al abrir",
        "desc": "Doble parpadeo de intermitentes para confirmar el desbloqueo del vehiculo con mando.",
        "defecto": 1,
        "opciones": {0: "Desactivado", 1: "Activado (Confirmacion visual)"}
    },
    10: {
        "nombre": "Tono de Alarma Antirrobo DWA",
        "desc": "Tipo de tono acustico emitido por la sirena de alarma H12.",
        "defecto": 1,
        "opciones": {1: "Resto de Europa (Modulacion continua)", 2: "Alemania (Intermitente)", 3: "Gran Bretana"}
    },
    11: {
        "nombre": "Sensibilidad Sensor Volumetrico Alarma",
        "desc": "Sensibilidad de deteccion del sensor de movimiento interior G273 (50% a 100%).",
        "defecto": 100,
        "opciones": {50: "50% (Minima - Para mascotas)", 75: "75% (Media)", 100: "100% (Maxima de fabrica)"}
    },
    14: {
        "nombre": "Confort Elevalunas desde Mando",
        "desc": "Sube o baja las ventanillas manteniendo pulsado el boton de cerrar o abrir en el mando.",
        "defecto": 1,
        "opciones": {0: "Desactivado", 1: "Activado (Subida/Bajada confort)"}
    },
}

CATALOGO_CONFORT_POLO = {
    "Confort / BCM (46)": [
        {
            "id": "polo_autolock",
            "nombre": "Auto-Lock (Cierre a >15 km/h)",
            "canal": 3,
            "byte": 0,
            "bit": 0,
            "desc": "Bloquea automaticamente todos los pestillos de las puertas al superar 15 km/h para evitar robos o aperturas en marcha.",
            "defecto": 1,
        },
        {
            "id": "polo_autounlock",
            "nombre": "Auto-Unlock (Apertura al sacar llave)",
            "canal": 4,
            "byte": 0,
            "bit": 1,
            "desc": "Desbloquea automaticamente todas las puertas al extraer la llave de contacto del bombin.",
            "defecto": 1,
        },
        {
            "id": "polo_claxon_cierre",
            "nombre": "Aviso acustico / Bocina al cerrar",
            "canal": 6,
            "byte": 0,
            "bit": 2,
            "desc": "Hace sonar la bocina brevemente al cerrar con el mando a distancia (0 = Silencioso / Sin molestar, 1 = Bocinazo activado).",
            "defecto": 1,
        },
        {
            "id": "polo_apertura_selectiva",
            "nombre": "Apertura selectiva de puertas",
            "canal": 7,
            "byte": 0,
            "bit": 3,
            "desc": "1 pulsacion abre solo la puerta del conductor; 2 pulsaciones abren todo el vehiculo (0 = 1 toque abre todo).",
            "defecto": 0,
        },
        {
            "id": "polo_aviso_abrir",
            "nombre": "Aviso acustico al abrir con mando",
            "canal": 5,
            "byte": 0,
            "bit": 4,
            "desc": "Emite dos toques de claxon al pulsar el boton de desbloqueo con el mando a distancia.",
            "defecto": 0,
        },
        {
            "id": "polo_blink_cierre",
            "nombre": "Confirmacion de intermitentes al cerrar",
            "canal": 8,
            "byte": 0,
            "bit": 5,
            "desc": "Destello optico de intermitentes de emergencia al bloquear las cerraduras.",
            "defecto": 1,
        },
        {
            "id": "polo_blink_abrir",
            "nombre": "Confirmacion de intermitentes al abrir",
            "canal": 9,
            "byte": 0,
            "bit": 6,
            "desc": "Doble destello optico de intermitentes de emergencia al desbloquear con el mando.",
            "defecto": 1,
        },
        {
            "id": "polo_confort_ventanillas",
            "nombre": "Subida/Bajada confort ventanillas con mando",
            "canal": 14,
            "byte": 0,
            "bit": 7,
            "desc": "Permite abrir o cerrar las ventanillas manteniendo pulsados los botones del mando a distancia.",
            "defecto": 1,
        },
        {
            "id": "polo_tono_alarma",
            "nombre": "Tono modulado continuo de alarma DWA",
            "canal": 10,
            "byte": 1,
            "bit": 0,
            "desc": "Configura la modulacion de frecuencia de la sirena antirrobo H12 (1 = Continuo Europeo / 2 = Intermitente).",
            "defecto": 1,
        },
        {
            "id": "polo_alarma_volumetrica",
            "nombre": "Proteccion interior volumetrica (Sensor G273)",
            "canal": 11,
            "byte": 1,
            "bit": 1,
            "desc": "Supervision volumetrica por ultrasonidos del habitaculo ante rotura de lunas o intrusion.",
            "defecto": 1,
        },
    ],
    "Central Electrica / Luces (09)": [
        {
            "id": "polo_limpia_marcha_atras",
            "nombre": "Limpia trasero automatico al meter marcha atras",
            "canal": 2,
            "byte": 0,
            "bit": 0,
            "desc": "Activa un barrido del limpiaparabrisas trasero al poner la marcha atras si el limpia delantero esta funcionando.",
            "defecto": 1,
        },
        {
            "id": "polo_barrido_antigoteo",
            "nombre": "Barrido antigoteo delantero (Tear-Drop Wipe)",
            "canal": 3,
            "byte": 0,
            "bit": 1,
            "desc": "Realiza un barrido adicional a los 5 segundos de usar el lavaparabrisas para retirar la gota residual.",
            "defecto": 1,
        },
        {
            "id": "polo_coming_home",
            "nombre": "Retardo de luces Follow Me Home (30 segundos)",
            "canal": 1,
            "byte": 0,
            "bit": 2,
            "desc": "Mantiene encendidas las luces de cruce durante 30s al accionar la palanca de rafagas antes de bajar del coche.",
            "defecto": 1,
        },
        {
            "id": "polo_drl_luces",
            "nombre": "Luces diurnas DRL automaticas",
            "canal": 4,
            "byte": 0,
            "bit": 3,
            "desc": "Enciende automaticamente las luces de posicion/cruce al poner el contacto para mayor visibilidad.",
            "defecto": 0,
        },
        {
            "id": "polo_tiempo_luneta",
            "nombre": "Temporizador extendido de luneta termica (15 min)",
            "canal": 5,
            "byte": 0,
            "bit": 4,
            "desc": "Regula el tiempo de calentamiento de la luneta trasera y retrovisores termicos antes del apagado automatico.",
            "defecto": 1,
        },
    ],
    "Cuadro de Instrumentos (17)": [
        {
            "id": "polo_aviso_cinturon",
            "nombre": "Avisador acustico y testigo de cinturon",
            "canal": 2,
            "byte": 1,
            "bit": 0,
            "desc": "Alerta sonora tipo gong y testigo luminoso en el cuadro cuando el cinturon del conductor no esta abrochado.",
            "defecto": 1,
        },
        {
            "id": "polo_desgaste_pastillas",
            "nombre": "Testigo de desgaste de pastillas de freno",
            "canal": 3,
            "byte": 1,
            "bit": 1,
            "desc": "Supervision activa del sensor de espesor de las pastillas de freno delanteras.",
            "defecto": 1,
        },
        {
            "id": "polo_nivel_limpia",
            "nombre": "Aviso de nivel bajo lavaparabrisas",
            "canal": 4,
            "byte": 1,
            "bit": 2,
            "desc": "Aviso en cuadro cuando el deposito de agua del limpiaparabrisas esta por debajo del minimo.",
            "defecto": 1,
        },
        {
            "id": "polo_aviso_velocidad",
            "nombre": "Alerta acustica de limite 120 km/h",
            "canal": 35,
            "byte": 1,
            "bit": 3,
            "desc": "Emite un pitido y mensaje en el cuadro de instrumentos al sobrepasar los 120 km/h en autopista.",
            "defecto": 0,
        },
        {
            "id": "polo_calib_aforador",
            "nombre": "Calibracion y compensacion aforador combustible",
            "canal": 30,
            "byte": 1,
            "bit": 4,
            "desc": "Ajuste fino de la resistencia en Ohmios del sensor de nivel de deposito de combustible (Base 128).",
            "defecto": 1,
        },
    ],
    "Direccion Asistida TRW (44)": [
        {
            "id": "polo_direccion_deportiva",
            "nombre": "Tacto Deportivo GTI (Asistencia firme)",
            "canal": 1,
            "byte": 2,
            "bit": 0,
            "desc": "Configura la curva electrohidraulica TRW a mapa deportivo (00140) con menor asistencia y mayor tacto de carretera.",
            "defecto": 0,
        },
        {
            "id": "polo_direccion_confort",
            "nombre": "Tacto Confort Urbano (Asistencia suave)",
            "canal": 2,
            "byte": 2,
            "bit": 1,
            "desc": "Configura la curva electrohidraulica TRW a maxima asistencia (00112) para maniobrar y aparcar sin esfuerzo.",
            "defecto": 1,
        },
        {
            "id": "polo_direccion_estandar",
            "nombre": "Tacto Estandar Progresivo de Fabrica (00121)",
            "canal": 3,
            "byte": 2,
            "bit": 2,
            "desc": "Curva original equilibrada con asistencia dependiente de la velocidad del vehiculo.",
            "defecto": 0,
        },
        {
            "id": "polo_direccion_eco",
            "nombre": "Modo Eco (Bajo consumo electrico de bomba)",
            "canal": 4,
            "byte": 2,
            "bit": 3,
            "desc": "Limita los picos de amperaje de la electrobomba TRW en maniobras para proteger el alternador.",
            "defecto": 0,
        },
    ],
    "Motor 1.9 TDI (01)": [
        {
            "id": "polo_reduccion_egr",
            "nombre": "Optimizacion EGR (Mayor aire limpio / Menos carbonilla)",
            "canal": 3,
            "byte": 3,
            "bit": 0,
            "desc": "Ajusta la tasa de recirculacion EGR en EDC15 para reducir entrada de hollin a los colectores de admision.",
            "defecto": 1,
        },
        {
            "id": "polo_arranque_caliente",
            "nombre": "Mejora arranque en caliente (Dosis combustible)",
            "canal": 5,
            "byte": 3,
            "bit": 1,
            "desc": "Incrementa la dosis de inyeccion por debajo de 250 RPM para eliminar el tipico retardo de arranque en caliente de los 1.9 TDI.",
            "defecto": 1,
        },
        {
            "id": "polo_calentadores_frio",
            "nombre": "Precalentamiento extendido de bujias de arranque",
            "canal": 12,
            "byte": 3,
            "bit": 2,
            "desc": "Alarga el tiempo de calentamiento de las bujias de incandescencia Q10-Q13 a temperaturas de invierno.",
            "defecto": 1,
        },
        {
            "id": "polo_ajuste_ralenti",
            "nombre": "Ajuste suave de revoluciones de ralenti (880 RPM)",
            "canal": 2,
            "byte": 3,
            "bit": 3,
            "desc": "Ajusta las RPM de ralenti para amortiguar vibraciones de cabina transmitidas por los tacos de motor.",
            "defecto": 0,
        },
    ],
    "Airbag (15)": [
        {
            "id": "polo_desactivar_airbag_pasajero",
            "nombre": "Desconexion electronica Airbag Pasajero (Silla Bebe)",
            "canal": 1,
            "byte": 4,
            "bit": 0,
            "desc": "Desactiva de forma segura el modulo de airbag de acompanante para montar sillas infantiles a contramarcha.",
            "defecto": 0,
        },
        {
            "id": "polo_desactivar_airbag_lateral",
            "nombre": "Supervision Airbags Laterales Asientos",
            "canal": 2,
            "byte": 4,
            "bit": 1,
            "desc": "Mantiene activa la vigilancia de los detonadores laterales N199/N200 integrados en los respaldos.",
            "defecto": 1,
        },
    ],
    "Climatizacion (08)": [
        {
            "id": "polo_recirculacion_marcha_atras",
            "nombre": "Recirculacion automatica al engranar marcha atras",
            "canal": 1,
            "byte": 5,
            "bit": 0,
            "desc": "Cierra la compuerta exterior V113 al dar marcha atras para evitar que los gases del tubo de escape entren al habitaculo.",
            "defecto": 1,
        },
        {
            "id": "polo_recirculacion_lavaparabrisas",
            "nombre": "Cierre compuerta con lavaparabrisas",
            "canal": 2,
            "byte": 5,
            "bit": 1,
            "desc": "Cierra la trampilla de aire exterior durante 15s al accionar el limpiaparabrisas para evitar olor a alcohol en cabina.",
            "defecto": 1,
        },
    ],
    "Radio / Sonido (56)": [
        {
            "id": "polo_dsp_acustica",
            "nombre": "Ecualizacion acustica DSP especifica Polo 9N3",
            "canal": 1,
            "byte": 6,
            "bit": 0,
            "desc": "Activa el mapa de compensacion tonal interno de la radio RCD200 disenado para la cabina del Polo.",
            "defecto": 1,
        },
        {
            "id": "polo_cuatro_altavoces",
            "nombre": "Configuracion de 4 altavoces (Delanteros + Traseros)",
            "canal": 2,
            "byte": 6,
            "bit": 1,
            "desc": "Habilita el balance y fader de audio para vehiculos equipados con altavoces en las puertas traseras.",
            "defecto": 1,
        },
    ],
}


TITLE_ACK                   = 0x09
TITLE_NAK                   = 0x0A
TITLE_READ_DTC              = 0x07
TITLE_CLEAR_DTC             = 0x05
TITLE_END_COMM              = 0x06
TITLE_SOFTWARE_CODING       = 0x10
TITLE_READ_ADAPTATION       = 0x21
TITLE_TEST_ADAPTATION       = 0x22
TITLE_READ_MEASURING_BLOCK  = 0x29
TITLE_SAVE_ADAPTATION       = 0x2A
TITLE_LOGIN                 = 0x2B
TITLE_ADAPTATION_RESP       = 0xE6
TITLE_MEASURING_RESP        = 0xE7
BLOCK_END                   = 0x03


class VAGKLinePort:
    def __init__(self, port_name: str, baudrate: int = 9600, timeout: float = 1.2):
        self.port_name = port_name
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None
        self.is_connected = False

    def abrir(self) -> bool:
        if not SERIAL_AVAILABLE:
            return False
        try:
            self.ser = serial.Serial(
                port=self.port_name,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.timeout
            )
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.is_connected = True
            return True
        except Exception:
            self.is_connected = False
            return False

    def cerrar(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.is_connected = False

    def write_byte(self, b: int) -> bool:
        if not self.ser or not self.ser.is_open:
            return False
        try:
            self.ser.write(bytes([b & 0xFF]))
            # En la línea K física (Pin 7 half-duplex) se produce un eco en RX.
            # Consumir el eco inmediatamente si está disponible sin bloquear la UI.
            time.sleep(0.002)
            if self.ser.in_waiting > 0:
                self.ser.read(1)
            return True
        except Exception:
            return False

    def write_byte_and_read_ack(self, b: int, timeout: float = 0.5) -> bool:
        """
        Envía un byte a la K-Line en half-duplex, descarta el eco local
        y espera la confirmación oficial del ECU (complemento a 1: ~b & 0xFF)
        según la especificación de transporte KWP1281 / ISO 9141.
        """
        if not self.ser or not self.ser.is_open:
            return False
        try:
            self.ser.write(bytes([b & 0xFF]))
            time.sleep(0.002)
            if self.ser.in_waiting > 0:
                self.ser.read(1)  # Descartar eco local TX->RX
            comp = self.read_byte(timeout=timeout)
            expected = (~b) & 0xFF
            return (comp == expected)
        except Exception:
            return False

    def read_byte_and_send_ack(self, timeout: float = 1.0) -> Optional[int]:
        """
        Lee un byte enviado por el ECU y responde de inmediato con el complemento a 1 (~b & 0xFF)
        para confirmar su recepción y mantener sincronizado el bus K-Line.
        """
        if not self.ser or not self.ser.is_open:
            return None
        try:
            b = self.read_byte(timeout=timeout)
            if b is None:
                return None
            time.sleep(0.002)  # Pausa R6 (1-2 ms estándar VAG)
            comp = (~b) & 0xFF
            self.ser.write(bytes([comp]))
            time.sleep(0.002)
            if self.ser.in_waiting > 0:
                self.ser.read(1)  # Descartar eco local del complemento
            return b
        except Exception:
            return None

    def read_byte(self, timeout: Optional[float] = None) -> Optional[int]:
        if not self.ser or not self.ser.is_open:
            return None
        orig_timeout = self.ser.timeout
        if timeout is not None:
            self.ser.timeout = timeout
        try:
            data = self.ser.read(1)
            if data:
                return data[0]
            return None
        finally:
            if timeout is not None:
                self.ser.timeout = orig_timeout

    def init_5baud(self, address: int) -> Tuple[bool, Optional[int], Optional[int]]:
        """
        Inicialización lenta a 5 baudios (Slow Init) para KWP1281 / K-Line.
        Utiliza bit-banging sobre la señal de BREAK de la UART para máxima compatibilidad
        con drivers FTDI en Windows (donde SetCommState falla con WindowsError 87 al pedir baudrate=5).
        """
        if not self.ser or not self.ser.is_open:
            return False, None, None

        try:
            # 1. Asegurar estado idle de la línea K (Mark = nivel alto / inactivo)
            self.ser.break_condition = False
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.2)  # Pausa inicial de reposo

            # 2. Generación de los 10 bits a 5 baudios (200 ms por bit exactos):
            # Formato VAG KWP1281: 1 Start bit (0/Space), 7 Data bits (LSB first), 1 Odd Parity (Impar), 1 Stop bit (1/Mark)
            parity = True  # Para paridad impar oficial VAG KWP1281 (odd parity)
            for i in range(7):
                bit = (address >> i) & 1
                parity ^= (bit == 1)
            parity_bit = 1 if parity else 0
            secuencia_bits = [0] + [(address >> i) & 1 for i in range(7)] + [parity_bit, 1]

            t_next = time.perf_counter()
            for bit in secuencia_bits:
                # En UART: bit 0 (Space) = TX a nivel bajo (Break activo)
                #          bit 1 (Mark)  = TX a nivel alto (Break inactivo)
                self.ser.break_condition = (bit == 0)
                t_next += 0.200
                while time.perf_counter() < t_next:
                    pass

            # 3. Tras el stop bit, desactivar break y limpiar residuos de eco/framing
            self.ser.break_condition = False
            time.sleep(0.05)
            self.ser.reset_input_buffer()

            # 4. Escuchar respuesta del ECU (Byte de sincronización 0x55)
            # Primero a 9600 baudios, con fallback dinámico a 10400 (EDC15 TDI)
            sync = self.read_byte(timeout=1.8)
            if sync != 0x55:
                nueva_vel = 10400 if self.baudrate == 9600 else 9600
                self.ser.baudrate = nueva_vel
                self.ser.reset_input_buffer()
                sync = self.read_byte(timeout=1.0)
                if sync == 0x55:
                    self.baudrate = nueva_vel

            if sync != 0x55:
                return False, None, None

            # 5. Lectura de las KeyBytes (KB1 y KB2)
            kb1 = self.read_byte(timeout=0.8)
            kb2 = self.read_byte(timeout=0.8)
            if kb1 is None or kb2 is None:
                return False, None, None

            # 6. Responder con el complemento a 1 de KB2 (~KB2)
            ack_byte = (~kb2) & 0xFF
            time.sleep(0.025)
            self.ser.write(bytes([ack_byte]))
            time.sleep(0.005)
            if self.ser.in_waiting > 0:
                self.ser.read(1)  # Descartar eco en bus half-duplex

            # 7. Leer confirmación de dirección del ECU
            addr_ack = self.read_byte(timeout=0.8)

            time.sleep(0.02)
            return True, kb1, kb2

        except Exception:
            return False, None, None


class MockVAGKLineECU:
    def __init__(self):
        self.canales_confort = {
            3: 1,  # Auto-Lock: Activado
            4: 0,  # Auto-Unlock: Desactivado
            6: 1,  # Beep al cerrar: Activado
            7: 1,  # Apertura selectiva: Activado
        }
        self.fallos_confort = [
            {"codigo": "00928", "desc": "Unidad de cierre centralizado puerta conductor (F220) - Senal inverosimil", "estado": "Esporadico"},
            {"codigo": "00932", "desc": "Motor elevalunas lado conductor (V147) - Sin ajuste basico", "estado": "Estatico"}
        ]
        self.fallos_motor = [
            {"codigo": "01650", "desc": "Bujia incandescente Cilindro 2 (Q11) - Circuito defectuoso (P0672)", "estado": "Estatico (Causa mal arranque)"},
            {"codigo": "00532", "desc": "Tension de alimentacion B+ - Valor por debajo del umbral", "estado": "Esporadico (Caida al arrancar)"}
        ]
        self.dtcs_actuales = {0x46: list(self.fallos_confort), 0x01: list(self.fallos_motor)}

    def handshake(self, addr: int) -> bool:
        time.sleep(0.15)
        return addr in (0x01, 0x03, 0x09, 0x15, 0x17, 0x46)

    def get_ident(self, addr: int) -> Dict[str, str]:
        time.sleep(0.05)
        if addr == 0x46:
            return {
                "modulo": "Confort / Electronica (46)",
                "referencia": "6Q0 959 433 E",
                "componente": "04 4H Komfortgerat 0001",
                "codificacion": "00067",
                "taller": "WSC 00789",
                "protocolo": "KWP1281 (K-Line Pin 7)"
            }
        elif addr == 0x01:
            return {
                "modulo": "Motor (01) - 1.9 TDI PD",
                "referencia": "038 906 019 LA",
                "componente": "1.9l R4 EDC 0000SG 1544",
                "codificacion": "00002",
                "taller": "WSC 31414",
                "protocolo": "KWP1281 / KWP2000"
            }
        else:
            return {
                "modulo": f"Modulo (0x{addr:02X})",
                "referencia": "6Q0 920 802 D",
                "componente": "KOMBIINSTRUMENT VDO V01",
                "codificacion": "00141",
                "taller": "WSC 00000",
                "protocolo": "KWP1281"
            }

    def leer_dtcs(self, addr: int) -> List[Dict[str, str]]:
        time.sleep(0.1)
        return self.dtcs_actuales.get(addr, [])

    def borrar_dtcs(self, addr: int) -> bool:
        time.sleep(0.08)
        self.dtcs_actuales[addr] = []
        return True

    def leer_canal(self, canal: int) -> int:
        time.sleep(0.05)
        return self.canales_confort.get(canal, 0)

    def guardar_canal(self, canal: int, valor: int) -> bool:
        time.sleep(0.08)
        self.canales_confort[canal] = valor
        return True


KWP1281_SYMPTOMS = {
    0x01: "Cortocircuito a masa",
    0x02: "Cortocircuito a positivo",
    0x03: "Sin señal o circuito abierto",
    0x04: "Fallo mecánico",
    0x06: "Cortocircuito entre líneas de señal",
    0x07: "Señal demasiado baja",
    0x08: "Señal no plausible (inverosímil)",
    0x10: "Límite de adaptación excedido",
    0x23: "Sin ajuste básico o adaptación no realizada",
    0x24: "Fallo eléctrico en el circuito",
}


class VAGKLineClient:
    def __init__(self, port_name: str = "MOCK", baudrate: int = 9600):
        self.port_name = port_name
        self.baudrate = baudrate
        self.is_mock = (port_name.upper() == "MOCK") or not SERIAL_AVAILABLE
        self.port: Optional[VAGKLinePort] = None
        self.mock_ecu = MockVAGKLineECU() if self.is_mock else None
        self.modulo_actual = 0x46
        self.conectado = False
        self.block_counter = 0
        self.ultimo_error = ""

    @staticmethod
    def listar_puertos_com() -> List[str]:
        if not SERIAL_AVAILABLE:
            return ["MOCK"]
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        if not puertos:
            puertos = ["MOCK"]
        return puertos

    def conectar(self, direccion_modulo: int = 0x46) -> bool:
        # 1. Si ya estamos conectados al módulo solicitado, reutilizar la sesión activa
        if self.conectado and self.modulo_actual == direccion_modulo:
            if self.is_mock or (self.port and self.port.is_connected):
                return True

        # 2. Si estábamos conectados a otro módulo, cerrar la sesión KWP1281 anterior
        if self.conectado:
            self.desconectar()
            time.sleep(0.3)

        self.modulo_actual = direccion_modulo
        self.block_counter = 0
        self.ultimo_error = ""

        if self.is_mock:
            self.conectado = self.mock_ecu.handshake(direccion_modulo)
            return self.conectado

        # Cerrar puerto anterior si quedaba abierto
        if self.port and self.port.is_connected:
            self.port.cerrar()

        self.port = VAGKLinePort(self.port_name, baudrate=self.baudrate)
        if not self.port.abrir():
            self.ultimo_error = (
                f"No se pudo abrir el puerto serie {self.port_name}. "
                "Comprueba que el cable USB esté conectado y ningún otro programa lo esté usando."
            )
            self.conectado = False
            return False

        ok, kb1, kb2 = self.port.init_5baud(direccion_modulo)
        if ok:
            self.conectado = True
            return True
        else:
            self.ultimo_error = (
                f"La centralita (0x{direccion_modulo:02X}) no respondió al saludo lento (5 baudios). "
                "Asegúrate de tener el contacto puesto con la llave y el cable bien encajado en el puerto OBD."
            )
            self.port.cerrar()
            self.conectado = False
            return False

    def desconectar(self):
        if not self.is_mock and self.port and self.conectado:
            try:
                self._enviar_bloque_kwp1281(TITLE_END_COMM, b"")
            except Exception:
                pass
            self.port.cerrar()
        self.conectado = False

    def leer_identificacion(self) -> Dict[str, str]:
        if self.is_mock:
            return self.mock_ecu.get_ident(self.modulo_actual)

        ident = {
            "modulo": f"Modulo 0x{self.modulo_actual:02X}",
            "referencia": "Desconocida",
            "componente": "VAG ECU K-Line",
            "codificacion": "N/A",
            "protocolo": "KWP1281"
        }
        textos = []
        try:
            # Drenar los bloques de identificación que el ECU envía tras el saludo inicial
            for _ in range(8):
                bloque = self._recibir_bloque_kwp1281(timeout=0.8)
                if not bloque:
                    break
                titulo = bloque.get("titulo")
                datos = bloque.get("datos", b"")
                if titulo == 0xF6 and len(datos) == 5 and datos[0] == 0:
                    coding = (datos[1] * 256 + datos[2]) // 2
                    wsc = datos[3] * 256 + datos[4]
                    ident["codificacion"] = f"{coding:05d}"
                    ident["taller"] = f"WSC {wsc:05d}"
                    self.codificacion_leida = f"{coding:05d}"
                elif titulo == 0xF6 or (datos and all(32 <= b <= 126 or b in (10, 13) for b in datos)):
                    texto = datos.decode("ascii", errors="ignore").strip()
                    if texto:
                        textos.append(texto)
                elif titulo in (TITLE_ACK, TITLE_NAK):
                    break
                # Confirmar al ECU para que envíe el siguiente bloque de datos
                self._enviar_bloque_kwp1281(TITLE_ACK, b"")

            if textos:
                ident["referencia"] = textos[0][:11].strip()
                ident["componente"] = " ".join(textos[1:]) if len(textos) > 1 else textos[0]
        except Exception:
            pass
        return ident

    def leer_dtcs(self) -> List[Dict[str, str]]:
        if self.is_mock:
            return self.mock_ecu.leer_dtcs(self.modulo_actual)

        fallos = []
        try:
            self._enviar_bloque_kwp1281(TITLE_READ_DTC, b"")
            resp = self._recibir_bloque_kwp1281()
            if resp and resp["titulo"] == 0xFC:
                datos = resp["datos"]
                for i in range(0, len(datos) - 2, 3):
                    c_high, c_low, status = datos[i], datos[i+1], datos[i+2]
                    codigo_int = (c_high << 8) | c_low
                    codigo_str = f"{codigo_int:05d}"
                    es_esporadico = bool(status & 0x80)
                    estado_str = "Esporadico" if es_esporadico else "Estatico"
                    sintoma_code = status & 0x3F
                    sintoma_desc = KWP1281_SYMPTOMS.get(sintoma_code, "")
                    desc_sintoma = f" — {sintoma_desc}" if sintoma_desc else ""
                    fallos.append({
                        "codigo": codigo_str,
                        "desc": f"Averia registrada en componente {codigo_str}{desc_sintoma}",
                        "estado": estado_str
                    })
        except Exception:
            pass
        return fallos

    def borrar_dtcs(self) -> bool:
        if self.is_mock:
            return self.mock_ecu.borrar_dtcs(self.modulo_actual)

        try:
            self._enviar_bloque_kwp1281(TITLE_CLEAR_DTC, b"")
            resp = self._recibir_bloque_kwp1281()
            return True
        except Exception:
            return False

    def leer_canal_adaptacion(self, canal: int) -> Optional[int]:
        if self.is_mock:
            return self.mock_ecu.leer_canal(canal)

        if canal == 7 and self.modulo_actual == 0x46:
            cod_str = getattr(self, "codificacion_leida", "")
            if cod_str.isdigit():
                # En VAG: Si el coding es impar (termina en +1), la apertura selectiva está desactivada (0 = 1 toque abre todo)
                return 0 if (int(cod_str) % 2 != 0) else 1

        try:
            payload = bytes([canal & 0xFF])
            self._enviar_bloque_kwp1281(TITLE_READ_ADAPTATION, payload)
            resp = self._recibir_bloque_kwp1281(timeout=1.2)
            if resp:
                datos = resp.get("datos", b"")
                # Respuesta de adaptación KWP1281 (0xE6):
                # Byte 0 = Canal, Byte 1 = Val High, Byte 2 = Val Low
                if resp.get("titulo") == TITLE_ADAPTATION_RESP and len(datos) >= 3:
                    val = (datos[1] << 8) | datos[2]
                    return val
                elif len(datos) >= 2:
                    val = (datos[0] << 8) | datos[1]
                    return val
            return None
        except Exception:
            return None

    def guardar_codificacion(self, coding: int, wsc: int = 788) -> bool:
        """
        Graba una nueva codificación corta (Soft Coding) oficial VAG vía KWP1281 (Título 0x10).
        """
        if self.is_mock:
            return True
        try:
            c_val = coding * 2
            payload = bytes([(c_val >> 8) & 0xFF, c_val & 0xFF, (wsc >> 8) & 0xFF, wsc & 0xFF])
            self._enviar_bloque_kwp1281(TITLE_SOFTWARE_CODING, payload)
            resp = self._recibir_bloque_kwp1281(timeout=1.2)
            if not resp or resp.get("titulo") == TITLE_NAK:
                return False
            return True
        except Exception:
            return False

    def guardar_canal_adaptacion(self, canal: int, valor: int, wsc: int = 789) -> bool:
        self.ultimo_error = ""
        if self.is_mock:
            return self.mock_ecu.guardar_canal(canal, valor)

        # En el Polo 9N3 (centralitas 6Q0 959 433), la apertura selectiva se regula en la
        # Codificación Corta (Soft Coding) de Confort (46) según especificación oficial VW:
        # Base 00018 (4 puertas) + 00001 (1 toque abre todo) = 00019
        if canal == 7:
            nuevo_coding = 19 if valor == 0 else 18
            ok_code = self.guardar_codificacion(nuevo_coding, wsc=788)
            if ok_code:
                return True
            else:
                self.ultimo_error = f"No se pudo guardar la codificación {nuevo_coding:05d} en Confort."
                return False

        try:
            val_h = (valor >> 8) & 0xFF
            val_l = valor & 0xFF

            # 1. Leer el canal previamente (0x21) para cargarlo en el búfer activo de la ECU
            self._enviar_bloque_kwp1281(TITLE_READ_ADAPTATION, bytes([canal & 0xFF]))
            resp_read = self._recibir_bloque_kwp1281(timeout=1.0)
            if not resp_read or resp_read.get("titulo") == TITLE_NAK:
                self.ultimo_error = (
                    f"La centralita rechazó abrir el Canal {canal:02d} (NAK). "
                    "Verifica que el canal esté disponible en esta versión de centralita."
                )
                return False

            time.sleep(0.04)

            # 2. Intentar Test de Adaptación (0x22) con el nuevo valor
            payload_test = bytes([canal & 0xFF, val_h, val_l])
            self._enviar_bloque_kwp1281(TITLE_TEST_ADAPTATION, payload_test)
            resp_test = self._recibir_bloque_kwp1281(timeout=0.8)
            # Nota: Algunos módulos Confort no requieren o no aceptan 0x22, pasando directo a 0x2A.

            time.sleep(0.04)

            # 3. Guardar Adaptación (0x2A): Formato directo de 3 bytes [Canal, Val High, Val Low] oficial PQ24
            payload_save_simple = bytes([canal & 0xFF, val_h, val_l])
            self._enviar_bloque_kwp1281(TITLE_SAVE_ADAPTATION, payload_save_simple)
            resp_save = self._recibir_bloque_kwp1281(timeout=1.2)

            # Fallback opcional con WSC si la centralita lo requiere
            if not resp_save or resp_save.get("titulo") in (TITLE_NAK, TITLE_END_COMM):
                time.sleep(0.05)
                wsc_h = (wsc >> 16) & 0xFF
                wsc_m = (wsc >> 8) & 0xFF
                wsc_l = wsc & 0xFF
                payload_save_wsc = bytes([canal & 0xFF, val_h, val_l, wsc_h, wsc_m, wsc_l])
                self._enviar_bloque_kwp1281(TITLE_SAVE_ADAPTATION, payload_save_wsc)
                resp_save = self._recibir_bloque_kwp1281(timeout=1.2)

            if not resp_save or resp_save.get("titulo") == TITLE_NAK:
                self.ultimo_error = (
                    "La centralita rechazó la orden de guardado (NAK). "
                    "En los módulos Confort (46) del Grupo VAG, las puertas del coche "
                    "deben estar completamente cerradas y el contacto puesto para desbloquear "
                    "la escritura en la memoria EEPROM."
                )
                return False

            time.sleep(0.05)

            # 5. Confirmar releyendo el canal desde la EEPROM
            val_comprobado = self.leer_canal_adaptacion(canal)
            if val_comprobado is not None and val_comprobado == valor:
                return True
            elif val_comprobado is not None:
                self.ultimo_error = f"El valor verificado ({val_comprobado}) no coincide con el nuevo valor ({valor})."
                return False

            return True
        except Exception as e:
            self.ultimo_error = f"Excepción durante la comunicación K-Line: {e}"
            return False

    def _enviar_bloque_kwp1281(self, titulo: int, datos: bytes) -> bool:
        if not self.port:
            return False
        longitud = len(datos) + 3
        self.block_counter = (self.block_counter + 1) & 0xFF
        bytes_a_enviar = [longitud, self.block_counter, titulo] + list(datos)
        for b in bytes_a_enviar:
            self.port.write_byte_and_read_ack(b, timeout=0.5)
            time.sleep(0.002)
        # El byte de fin de bloque (BLOCK_END = 0x03) NO se complementa en KWP1281
        self.port.write_byte(BLOCK_END)
        return True

    def _recibir_bloque_kwp1281(self, timeout: float = 1.2) -> Optional[Dict[str, Any]]:
        if not self.port:
            return None
        longitud = self.port.read_byte_and_send_ack(timeout=timeout)
        if not longitud or longitud < 3:
            return None
        contador = self.port.read_byte_and_send_ack(timeout=0.6)
        titulo = self.port.read_byte_and_send_ack(timeout=0.6)
        if contador is None or titulo is None:
            return None
        datos_len = longitud - 3
        datos = bytearray()
        for _ in range(datos_len):
            b = self.port.read_byte_and_send_ack(timeout=0.5)
            if b is not None:
                datos.append(b)
        fin = self.port.read_byte(timeout=0.5)  # 0x03 fin de bloque (sin complemento)
        return {"titulo": titulo, "datos": bytes(datos)}


if __name__ == "__main__":
    print("="*65)
    print("       INICIANDO MOTOR VAG K-LINE (POLO 9N3 / GRUPO VAG)")
    print("="*65)

    cliente = VAGKLineClient(port_name="MOCK")

    print("\n[1] Conectando con Confort / Electronica (46) del VW Polo 9N3...")
    if cliente.conectar(0x46):
        print("    [OK EXITO] Conexion establecida a 10.400 baudios via K-Line.")
        
        ident = cliente.leer_identificacion()
        print(f"    Referencia ECU:  {ident.get('referencia')}")
        print(f"    Componente:      {ident.get('componente')}")
        print(f"    Codificacion:    {ident.get('codificacion')}")

        print("\n[2] Leyendo averias registradas en Confort...")
        dtcs = cliente.leer_dtcs()
        for d in dtcs:
            print(f"    * Codigo {d['codigo']}: {d['desc']} ({d['estado']})")

        print("\n[3] Comprobando Canales de Confort del Padre (Polo 9N3):")
        for canal, info in POLO_9N3_CONFORT_CHANNELS.items():
            val_actual = cliente.leer_canal_adaptacion(canal)
            print(f"    * Canal {canal:02d} [{info['nombre']}]: Actual = {val_actual} ({info['opciones'].get(val_actual, 'Desconocido')})")

        print("\n[4] APLICANDO CAMBIOS PEDIDOS POR EL PADRE:")
        print("    -> Desactivando pitido de bocina (Canal 06 = 0)...")
        cliente.guardar_canal_adaptacion(6, 0)
        nuevo_c6 = cliente.leer_canal_adaptacion(6)
        print(f"       Confirmacion: Canal 06 = {nuevo_c6} ({POLO_9N3_CONFORT_CHANNELS[6]['opciones'].get(nuevo_c6)})")

        print("    -> Activando desbloqueo automatico al sacar llave (Canal 04 = 1)...")
        cliente.guardar_canal_adaptacion(4, 1)
        nuevo_c4 = cliente.leer_canal_adaptacion(4)
        print(f"       Confirmacion: Canal 04 = {nuevo_c4} ({POLO_9N3_CONFORT_CHANNELS[4]['opciones'].get(nuevo_c4)})")

        print("    -> Apertura de todas las puertas con 1 solo toque (Canal 07 = 0)...")
        cliente.guardar_canal_adaptacion(7, 0)
        nuevo_c7 = cliente.leer_canal_adaptacion(7)
        print(f"       Confirmacion: Canal 07 = {nuevo_c7} ({POLO_9N3_CONFORT_CHANNELS[7]['opciones'].get(nuevo_c7)})")

        cliente.desconectar()
        print("\n[OK PRUEBA COMPLETADA] Todos los canales adaptados y guardados con exito.")
    else:
        print("    [ERROR] No se pudo conectar.")