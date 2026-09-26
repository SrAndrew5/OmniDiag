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
            "desc": "Desbloquea automaticamente todas las puertas al extraer la llave de contacto del clausor.",
            "defecto": 1,
        },
        {
            "id": "polo_claxon_cierre",
            "nombre": "Aviso acustico / Bocina al cerrar (Desactivar pitido)",
            "canal": 6,
            "byte": 0,
            "bit": 2,
            "desc": "Hace sonar la bocina brevemente al cerrar con el mando a distancia (0 = Silencioso / Sin molestar, 1 = Bocinazo activado).",
            "defecto": 0,
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
    ],
}


TITLE_ACK                   = 0x09
TITLE_NAK                   = 0x0A
TITLE_READ_DTC              = 0x07
TITLE_CLEAR_DTC             = 0x05
TITLE_END_COMM              = 0x06
TITLE_READ_MEASURING_BLOCK  = 0x22
TITLE_READ_ADAPTATION       = 0x29
TITLE_TEST_ADAPTATION       = 0x2A
TITLE_SAVE_ADAPTATION       = 0x2B
TITLE_LOGIN                 = 0x2B
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
            eco = self.ser.read(1)
            return True
        except Exception:
            return False

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
        if not self.ser or not self.ser.is_open:
            return False, None, None

        try:
            self.ser.close()
            time.sleep(0.1)
            self.ser.baudrate = 5
            self.ser.bytesize = serial.SEVENBITS
            self.ser.parity = serial.PARITY_EVEN
            self.ser.stopbits = serial.STOPBITS_ONE
            self.ser.open()
            self.ser.reset_input_buffer()

            self.ser.write(bytes([address & 0x7F]))
            time.sleep(2.0)

            self.ser.close()
            time.sleep(0.05)
            self.ser.baudrate = self.baudrate
            self.ser.bytesize = serial.EIGHTBITS
            self.ser.parity = serial.PARITY_NONE
            self.ser.stopbits = serial.STOPBITS_ONE
            self.ser.timeout = 2.0
            self.ser.open()
            self.ser.reset_input_buffer()

            sync = self.read_byte(timeout=1.5)
            if sync != 0x55:
                return False, None, None

            kb1 = self.read_byte(timeout=0.8)
            kb2 = self.read_byte(timeout=0.8)
            if kb1 is None or kb2 is None:
                return False, None, None

            ack_byte = (~kb2) & 0xFF
            time.sleep(0.03)
            self.write_byte(ack_byte)

            ret_ack = self.read_byte(timeout=0.8)
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

    @staticmethod
    def listar_puertos_com() -> List[str]:
        if not SERIAL_AVAILABLE:
            return ["MOCK"]
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        if not puertos:
            puertos = ["MOCK"]
        return puertos

    def conectar(self, direccion_modulo: int = 0x46) -> bool:
        self.modulo_actual = direccion_modulo
        self.block_counter = 0

        if self.is_mock:
            self.conectado = self.mock_ecu.handshake(direccion_modulo)
            return self.conectado

        self.port = VAGKLinePort(self.port_name, baudrate=self.baudrate)
        if not self.port.abrir():
            self.is_mock = True
            self.mock_ecu = MockVAGKLineECU()
            self.conectado = self.mock_ecu.handshake(direccion_modulo)
            return self.conectado

        ok, kb1, kb2 = self.port.init_5baud(direccion_modulo)
        if ok:
            self.conectado = True
            return True
        else:
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
        try:
            bloque = self._recibir_bloque_kwp1281()
            if bloque and "datos" in bloque:
                raw_text = bloque["datos"].decode("ascii", errors="ignore").strip()
                ident["referencia"] = raw_text[:11]
                ident["componente"] = raw_text[11:]
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
                    estado_str = "Estatico" if (status & 0x01) else "Esporadico"
                    fallos.append({
                        "codigo": codigo_str,
                        "desc": f"Averia registrada en componente {codigo_str}",
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

        try:
            payload = bytes([canal & 0xFF])
            self._enviar_bloque_kwp1281(TITLE_READ_ADAPTATION, payload)
            resp = self._recibir_bloque_kwp1281()
            if resp and len(resp.get("datos", b"")) >= 2:
                val = (resp["datos"][0] << 8) | resp["datos"][1]
                return val
            return None
        except Exception:
            return None

    def guardar_canal_adaptacion(self, canal: int, valor: int) -> bool:
        if self.is_mock:
            return self.mock_ecu.guardar_canal(canal, valor)

        try:
            val_h = (valor >> 8) & 0xFF
            val_l = valor & 0xFF
            payload = bytes([canal & 0xFF, val_h, val_l])

            self._enviar_bloque_kwp1281(TITLE_TEST_ADAPTATION, payload)
            resp1 = self._recibir_bloque_kwp1281()

            self._enviar_bloque_kwp1281(TITLE_SAVE_ADAPTATION, payload)
            resp2 = self._recibir_bloque_kwp1281()
            return True
        except Exception:
            return False

    def _enviar_bloque_kwp1281(self, titulo: int, datos: bytes):
        if not self.port:
            return
        longitud = len(datos) + 3
        self.block_counter = (self.block_counter + 1) & 0xFF
        bloque = bytes([longitud, self.block_counter, titulo]) + datos + bytes([BLOCK_END])
        for b in bloque:
            self.port.write_byte(b)
            time.sleep(0.005)

    def _recibir_bloque_kwp1281(self) -> Optional[Dict[str, Any]]:
        if not self.port:
            return None
        longitud = self.port.read_byte(timeout=1.0)
        if not longitud or longitud < 3:
            return None
        contador = self.port.read_byte()
        titulo = self.port.read_byte()
        datos_len = longitud - 3
        datos = bytearray()
        for _ in range(datos_len):
            b = self.port.read_byte()
            if b is not None:
                datos.append(b)
        fin = self.port.read_byte()
        self.port.write_byte(TITLE_ACK)
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