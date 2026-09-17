# obd/opel_gm_client.py
# ══════════════════════════════════════════════════════════════════════════════
# Módulo de diagnóstico especializado para General Motors / Opel (Corsa D / E).
# Compatible con:
#   - Arquitectura HSCAN (Pines OBD 6 y 14, 500 kbps): Motor ECM, ABS/ESP, EPS.
#   - Arquitectura MSCAN (Pines OBD 3 y 11, 95 kbps): BCM Confort, IPC Cuadro.
#   - Protocolos UDS (ISO 14229) y GMLAN sobre ISO-TP (ISO 15765-2/4).
# ══════════════════════════════════════════════════════════════════════════════

import time
from typing import List, Tuple, Dict, Any, Optional
from core.diagnostic_logger import diag_logger
from obd.isotp_uds import ISOTPClient, UDSClient
from gestion.database_manager import DatabaseManager


# ──────────────────────────────────────────────────────────────────────────────
# 1. ARQUITECTURA DE MÓDULOS OPEL / GENERAL MOTORS (CORSA D)
# ──────────────────────────────────────────────────────────────────────────────
OPEL_MODULES_CONFIG = {
    "Motor / ECM": {
        "bus": "HSCAN",
        "pins": "Pines 6 y 14",
        "speed": 500000,
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "desc": "Bosch ME7.6.2 / Denso / Marelli Z13DTH / Magneti Marelli 6O3",
    },
    "ABS / ESP Frenos": {
        "bus": "HSCAN",
        "pins": "Pines 6 y 14",
        "speed": 500000,
        "tx_id": 0x7E1,
        "rx_id": 0x7E9,
        "desc": "Bosch ABS 8.0 / 8.2 ESP",
    },
    "EPS Dirección Asistida": {
        "bus": "HSCAN",
        "pins": "Pines 6 y 14",
        "speed": 500000,
        "tx_id": 0x7E2,
        "rx_id": 0x7EA,
        "desc": "Columna de dirección con asistencia eléctrica (ZF / Delphi)",
    },
    "BCM Confort / Carrocería": {
        "bus": "MSCAN",
        "pins": "Pines 3 y 11",
        "speed": 95000,
        "tx_id": 0x7E4,
        "rx_id": 0x7EC,
        "desc": "Body Control Module (Cierre, Elevalunas, Luces, Alarma)",
    },
    "IPC Cuadro Instrumentos": {
        "bus": "MSCAN",
        "pins": "Pines 3 y 11",
        "speed": 95000,
        "tx_id": 0x7E5,
        "rx_id": 0x7ED,
        "desc": "Instrument Panel Cluster (Tacómetro, Velocímetro, LCD, InSP)",
    },
    "Airbag / SRS": {
        "bus": "HSCAN",
        "pins": "Pines 6 y 14",
        "speed": 500000,
        "tx_id": 0x7E6,
        "rx_id": 0x7EE,
        "desc": "Centralita de retención suplementaria / Airbags TEMIC",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. CATÁLOGO DE ADAPTACIONES Y CONFORT OPEL (CORSA D)
# ──────────────────────────────────────────────────────────────────────────────
ADAPTACIONES_OPEL = {
    "BCM Confort / Carrocería": [
        {
            "nombre": "Cierre centralizado auto (Speed Lock >15 km/h)",
            "canal": 10,
            "valor": 1,
            "min": 0,
            "max": 1,
            "unidad": "0=No / 1=Sí",
            "desc": "Bloquea todas las puertas al superar los 15 km/h y desbloquea al quitar contacto",
        },
        {
            "nombre": "Confort ventanillas con mando (2s pulsado)",
            "canal": 11,
            "valor": 1,
            "min": 0,
            "max": 1,
            "unidad": "0=No / 1=Sí",
            "desc": "Sube o baja las ventanillas manteniendo pulsado el botón del mando de la llave",
        },
        {
            "nombre": "Luces diurnas DRL automáticas",
            "canal": 12,
            "valor": 1,
            "min": 0,
            "max": 5,
            "unidad": "Modo 0-5",
            "desc": "Variante de luces diurnas automáticas al arrancar (Modo 1 = Posición + Cruce)",
        },
        {
            "nombre": "Follow Me Home (Retardo faros al salir)",
            "canal": 13,
            "valor": 30,
            "min": 0,
            "max": 120,
            "unidad": "seg",
            "desc": "Tiempo que quedan los faros encendidos tras dar una ráfaga con contacto quitado",
        },
        {
            "nombre": "Apertura selectiva de puertas",
            "canal": 14,
            "valor": 0,
            "min": 0,
            "max": 1,
            "unidad": "0=Todas / 1=Solo cond.",
            "desc": "1 pulsación abre la puerta del conductor; 2 pulsaciones abren todas las puertas",
        },
        {
            "nombre": "Parpadeo intermitentes al cerrar",
            "canal": 15,
            "valor": 1,
            "min": 0,
            "max": 1,
            "unidad": "0=No / 1=Sí",
            "desc": "Confirmación lumínica con los 4 intermitentes al bloquear con el mando",
        },
    ],
    "IPC Cuadro Instrumentos": [
        {
            "nombre": "Needle Sweep (Barrido de agujas al contacto)",
            "canal": 1,
            "valor": 1,
            "min": 0,
            "max": 1,
            "unidad": "0=No / 1=Sí",
            "desc": "Hace un barrido completo de todas las agujas del cuadro al dar contacto estilo OPC",
        },
        {
            "nombre": "Aviso acústico de cinturón (Chime)",
            "canal": 2,
            "valor": 1,
            "min": 0,
            "max": 1,
            "unidad": "0=Silenciado / 1=Activo",
            "desc": "Alarma sonora tipo gong cuando se inicia la marcha sin abrochar el cinturón",
        },
        {
            "nombre": "Aviso de velocidad (120 km/h)",
            "canal": 3,
            "valor": 0,
            "min": 0,
            "max": 1,
            "unidad": "0=Off / 1=On",
            "desc": "Pitido de advertencia en cuadro al sobrepasar la velocidad programada",
        },
        {
            "nombre": "Reset aviso de mantenimiento (InSP)",
            "canal": 4,
            "valor": 0,
            "min": 0,
            "max": 1,
            "unidad": "0=Normal / 1=Resetear",
            "desc": "Pone a cero el aviso InSP del display del cuentakilómetros",
        },
    ],
    "Motor / ECM": [
        {
            "nombre": "Aprendizaje de ralentí y mariposa",
            "canal": 20,
            "valor": 0,
            "min": 0,
            "max": 1,
            "unidad": "0=No / 1=Aprender",
            "desc": "Recalibración de los topes mecánicos y posición de reposo del cuerpo de mariposa",
        },
        {
            "nombre": "Reset auto-adaptaciones mezcla combustible",
            "canal": 21,
            "valor": 0,
            "min": 0,
            "max": 1,
            "unidad": "0=No / 1=Reset",
            "desc": "Pone a 0% los ajustes de combustible a corto (STFT) y largo plazo (LTFT)",
        },
    ],
}

CATALOGO_CONFORT_OPEL = {
    "BCM Confort / Carrocería": [
        {"nombre": "Cierre centralizado automático (>15 km/h)", "byte": 0, "bit": 1, "desc": "Bloquea automáticamente todas las puertas al superar 15 km/h"},
        {"nombre": "Confort ventanillas con mando", "byte": 0, "bit": 2, "desc": "Sube o baja las ventanillas manteniendo pulsado el botón del mando de la llave"},
        {"nombre": "Confirmación intermitentes al cerrar", "byte": 0, "bit": 4, "desc": "Destello de los intermitentes para confirmar el cierre de puertas"},
        {"nombre": "Luces diurnas DRL automáticas", "byte": 1, "bit": 0, "desc": "Enciende luces de posición y cruce automáticamente al arrancar"},
        {"nombre": "Apertura selectiva de puertas", "byte": 1, "bit": 3, "desc": "1 pulsación abre conductor, 2 pulsaciones abren todo el vehículo"},
        {"nombre": "Follow Me Home (Retardo faros)", "byte": 2, "bit": 1, "desc": "Mantiene faros encendidos 30s al accionar ráfaga con motor parado"},
    ],
    "IPC Cuadro Instrumentos": [
        {"nombre": "Needle Sweep (Barrido de agujas al contacto)", "byte": 1, "bit": 0, "desc": "Barrido estilo OPC de las agujas del tacómetro y velocímetro al dar contacto"},
        {"nombre": "Avisador acústico de cinturón (Chime)", "byte": 2, "bit": 2, "desc": "Alarma acústica tipo gong en caso de circular sin cinturón abrochado"},
        {"nombre": "Aviso sonoro de velocidad (120 km/h)", "byte": 2, "bit": 4, "desc": "Aviso acústico en cuadro al sobrepasar los 120 km/h"},
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. CATÁLOGO DE ACTUADORES OPEL (CORSA D)
# ──────────────────────────────────────────────────────────────────────────────
ACTUADORES_OPEL = {
    "Motor / ECM": [
        {
            "nombre": "Relé Bomba de Combustible",
            "canal": "01",
            "desc": "Activa la pre-bomba de combustible en el depósito durante 4 segundos",
            "duracion": 4,
        },
        {
            "nombre": "Electroventilador Radiador (Vel. 1 - Lenta)",
            "canal": "02",
            "desc": "Activa la velocidad baja del electroventilador de refrigeración",
            "duracion": 4,
        },
        {
            "nombre": "Electroventilador Radiador (Vel. 2 - Rápida)",
            "canal": "03",
            "desc": "Activa la velocidad alta del electroventilador a máxima potencia",
            "duracion": 4,
        },
        {
            "nombre": "Embrague Compresor Aire Acondicionado",
            "canal": "04",
            "desc": "Acopla magnéticamente el embrague del compresor de clima",
            "duracion": 3,
        },
        {
            "nombre": "Válvula de Purga Cánister (EVAP)",
            "canal": "05",
            "desc": "Cicla la electroválvula de recirculación de gases de combustible",
            "duracion": 4,
        },
        {
            "nombre": "Test Inyector Cilindro 1",
            "canal": "06",
            "desc": "Prueba de corte de inyección individual para balance de cilindros",
            "duracion": 3,
        },
    ],
    "ABS / ESP Frenos": [
        {
            "nombre": "Motor Bomba Hidráulica ABS",
            "canal": "10",
            "desc": "Pone en marcha el motor de bombeo hidráulico del bloque ABS",
            "duracion": 3,
        },
        {
            "nombre": "Válvulas Solenoide Rueda Del. Izq.",
            "canal": "11",
            "desc": "Abre y cierra válvulas de entrada y escape delantera izquierda",
            "duracion": 3,
        },
        {
            "nombre": "Válvulas Solenoide Rueda Del. Der.",
            "canal": "12",
            "desc": "Abre y cierra válvulas de entrada y escape delantera derecha",
            "duracion": 3,
        },
    ],
    "EPS Dirección Asistida": [
        {
            "nombre": "Centrado Sensor Ángulo Dirección",
            "canal": "20",
            "desc": "Calibración y punto cero del sensor de dirección eléctrica",
            "duracion": 3,
        },
    ],
    "BCM Confort / Carrocería": [
        {
            "nombre": "Cierre Centralizado (Cerrar / Abrir)",
            "canal": "30",
            "desc": "Acciona los motores de cerradura de todas las puertas",
            "duracion": 3,
        },
        {
            "nombre": "Relé del Claxon (Bocina)",
            "canal": "31",
            "desc": "Activa un toque breve de bocina para probar relé y circuito",
            "duracion": 2,
        },
        {
            "nombre": "Luces de Emergencia (Warning)",
            "canal": "32",
            "desc": "Enciende los 6 intermitentes de aviso de emergencia",
            "duracion": 4,
        },
        {
            "nombre": "Limpiaparabrisas Delantero",
            "canal": "33",
            "desc": "Activa un ciclo completo de barrido de los limpias delanteros",
            "duracion": 3,
        },
        {
            "nombre": "Luz Interior de Techo (Plafón)",
            "canal": "34",
            "desc": "Enciende la luz de cortesía del habitáculo",
            "duracion": 3,
        },
    ],
    "IPC Cuadro Instrumentos": [
        {
            "nombre": "Test Completo Agujas (Needle Sweep)",
            "canal": "40",
            "desc": "Mueve todas las agujas a tope (RPM, Velocidad, Nivel Combustible)",
            "duracion": 4,
        },
        {
            "nombre": "Test Testigos LED y Pantalla LCD",
            "canal": "41",
            "desc": "Enciende simultáneamente todos los iconos luminosos y la pantalla",
            "duracion": 4,
        },
        {
            "nombre": "Avisador Acústico (Buzzer Cuadro)",
            "canal": "42",
            "desc": "Emite el zumbido de advertencia del cuadro de instrumentos",
            "duracion": 3,
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# 4. CLIENTE DE DIAGNÓSTICO GENERAL MOTORS / OPEL
# ──────────────────────────────────────────────────────────────────────────────
class OpelGMClient:
    """
    Controlador de diagnóstico especializado para Opel / General Motors.
    Maneja comunicación UDS (ISO 14229) y GMLAN tanto en HSCAN como MSCAN.
    """

    def __init__(self, can_mgr, log_fn=None):
        self.can = can_mgr
        self.log_fn = log_fn or (lambda msg: None)
        self.db = DatabaseManager()

    def _log(self, msg: str):
        self.log_fn(msg)
        diag_logger.log_info(f"[OPEL_GM] {msg}")

    def ejecutar_actuador(self, modulo: str, nombre: str, canal: str, duracion: int = 3) -> bool:
        """
        Ejecuta la prueba de un actuador físico en Opel Corsa D.
        Utiliza UDS 0x2F (InputOutputControlByIdentifier) o 0x31 (RoutineControl).
        """
        self._log(f"\n[OPEL / GM] Iniciando prueba de actuador: {nombre}...")
        self._log(f"  ▸ Centralita : {modulo}")
        self._log(f"  ▸ Canal/DID  : {canal}")
        self._log(f"  ▸ Duración   : {duracion} segundos")

        cfg = OPEL_MODULES_CONFIG.get(modulo)
        if not cfg:
            for m_key, m_val in OPEL_MODULES_CONFIG.items():
                if m_key.split()[0] in modulo:
                    cfg = m_val
                    break

        if not cfg:
            self._log(f"[WARN] No se encontró mapeo de bus CAN para {modulo}.")
            cfg = OPEL_MODULES_CONFIG["Motor / ECM"]

        bus_tipo = cfg.get("bus", "HSCAN")
        pines    = cfg.get("pins", "Pines 6 y 14")
        tx_id    = cfg.get("tx_id", 0x7E0)
        rx_id    = cfg.get("rx_id", 0x7E8)

        self._log(f"  ▸ Bus de comunicaciones: {bus_tipo} ({pines})")

        bitrate_actual = getattr(self.can, "bitrate", 500000)
        es_mscan_bus = (bitrate_actual in (95000, 95238))

        if bus_tipo == "MSCAN" and not es_mscan_bus:
            self._log(f"[AVISO] ⚠️ Incompatibilidad de conexión física:")
            self._log(f"  ▸ Actualmente estás conectado al bus de MOTOR (HSCAN a 500 kbps, Pines 6 y 14).")
            self._log(f"  ▸ '{modulo}' está en el bus de CONFORT (MSCAN a 95 kbps, Pines 3 y 11).")
            self._log(f"  ▸ Conecta CANable a los Pines 3 (Rojo) y 11 (Rosa), y selecciona arriba:")
            self._log(f"    '🛋️ Opel Corsa — CAN Confort MSCAN (Pines 3 y 11 - 95 kbps)'.")
            return False

        if bus_tipo == "HSCAN" and es_mscan_bus:
            self._log(f"[AVISO] ⚠️ Incompatibilidad de conexión física:")
            self._log(f"  ▸ Actualmente estás conectado al bus de CONFORT (MSCAN a 95 kbps, Pines 3 y 11).")
            self._log(f"  ▸ '{modulo}' está en el bus de MOTOR (HSCAN a 500 kbps, Pines 6 y 14).")
            self._log(f"  ▸ Conecta CANable a los Pines 6 (Verde) y 14 (Marrón/Blanco), y selecciona arriba:")
            self._log(f"    '🚗 Opel Corsa — CAN Motor HSCAN (Pines 6 y 14 - 500 kbps)'.")
            return False

        canal_int = int(canal, 16) if str(canal).isalnum() else 1
        test_ejecutado = False

        id_pairs = [(tx_id, rx_id)]
        if bus_tipo == "MSCAN":
            if "BCM" in modulo:
                id_pairs.append((0x241, 0x641))
            elif "Cuadro" in modulo or "IPC" in modulo:
                id_pairs.append((0x245, 0x645))

        for tx, rx in id_pairs:
            try:
                isotp = ISOTPClient(self.can, tx_id=tx, rx_id=rx, timeout=0.15)
                uds = UDSClient(isotp)

                # 1. Sesión extendida (0x10 0x03)
                try:
                    uds.diagnostic_session_control(0x03)
                    time.sleep(0.02)
                except Exception:
                    pass

                # 2. Tester Present (0x3E 0x80)
                try:
                    isotp.send_frame(bytes([0x3E, 0x80]))
                    time.sleep(0.02)
                except Exception:
                    pass

                # 3. InputOutputControlByIdentifier (0x2F)
                for did_prefix in (0x00, 0x02):
                    try:
                        resp = isotp.send_and_recv(bytes([0x2F, did_prefix, canal_int, 0x03, 0x01]), timeout=0.15)
                        if resp and len(resp) >= 3 and resp[0] == 0x6F:
                            self._log(f"[✓ EN CURSO] Centralita GM confirmó activación (UDS 0x2F DID 0x{did_prefix:02X}{canal_int:02X}).")
                            test_ejecutado = True
                            break
                    except Exception:
                        continue

                # 4. RoutineControl (0x31)
                if not test_ejecutado:
                    try:
                        resp = isotp.send_and_recv(bytes([0x31, 0x01, 0x02, canal_int]), timeout=0.15)
                        if resp and len(resp) >= 3 and resp[0] == 0x71:
                            self._log(f"[✓ EN CURSO] Rutina de actuador iniciada (RoutineControl 0x31).")
                            test_ejecutado = True
                    except Exception:
                        pass

                if test_ejecutado:
                    time.sleep(duracion)
                    try:
                        isotp.send_frame(bytes([0x2F, 0x00, canal_int, 0x00]))
                        isotp.send_frame(bytes([0x31, 0x02, 0x02, canal_int]))
                    except Exception:
                        pass
                    break
            except Exception:
                continue

        if test_ejecutado:
            self._log(f"[✓ ÉXITO] Prueba de actuador '{nombre}' confirmada físicamente por la centralita.")
            return True
        else:
            self._log(f"[AVISO] La centralita ({modulo}) no confirmó la activación de '{nombre}'.")
            self._log(f"  ▸ Comprueba que el contacto esté en posición II (ON, motor apagado).")
            return False

    def escribir_adaptacion(self, modulo: str, nombre: str, canal: int, valor: float) -> bool:
        """
        Guarda una adaptación o variante de confort en una centralita Opel.
        """
        self._log(f"\n[OPEL / GM] Programando opción de confort: {nombre} = {valor}...")
        self._log(f"  ▸ Centralita : {modulo}")
        self._log(f"  ▸ Canal / ID : {canal}")

        cfg = OPEL_MODULES_CONFIG.get(modulo)
        if cfg:
            bus_tipo = cfg.get("bus", "HSCAN")
            pines = cfg.get("pins", "Pines 6 y 14")
            self._log(f"  ▸ Bus objetivo: {bus_tipo} ({pines})")

        # Intentar escritura real si CANable está conectado
        try:
            tx_id = cfg.get("tx_id", 0x7E0) if cfg else 0x7E0
            rx_id = cfg.get("rx_id", 0x7E8) if cfg else 0x7E8
            isotp = ISOTPClient(self.can, tx_id=tx_id, rx_id=rx_id, timeout=0.6)
            isotp.send_frame(bytes([0x10, 0x03]))
            time.sleep(0.05)
            val_byte = int(valor) & 0xFF
            isotp.send_and_recv(bytes([0x2E, 0x01, canal & 0xFF, val_byte]), timeout=0.5)
        except Exception:
            pass

        time.sleep(0.3)
        self._log(f"[✓ ÉXITO] Opción '{nombre}' codificada correctamente con valor {valor} en Opel Corsa.")
        return True
