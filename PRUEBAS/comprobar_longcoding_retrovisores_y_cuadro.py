"""
PRUEBAS/comprobar_longcoding_retrovisores_y_cuadro.py
══════════════════════════════════════════════════════════════════════════════
Script de diagnóstico y lectura forense de Long Coding (100% SOLO LECTURA).
Inspecciona:
  - 0x17: Cuadro de Instrumentos (Needle Sweep / Staging)
  - 0x46: Centralita Confort (Lógica de plegado con mando)
  - 0x42: Puerta Conductor (Motor plegable y plegado confort)
  - 0x52: Puerta Copiloto (Motor plegable y plegado confort)
══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time
import logging
import datetime
import struct

# Configurar stdout para evitar errores de codificación en consolas Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Asegurar que Python encuentra los módulos del proyecto raíz
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.can_manager import CANManager
from obd.tp20_can import TP20Transport, KWP2000NativeClient

# ── CONFIGURACIÓN DEL LOGGER ──────────────────────────────────────────────
log_dir = os.path.join(BASE_DIR, "datos", "reportes")
os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = os.path.join(log_dir, f"diagnostico_coding_{timestamp}.log")

logger = logging.getLogger("DiagnosticoCoding")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Archivo de log permanente
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Consola en tiempo real
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# ── CLASE WRAPPER PARA INTERCEPTAR TRÁFICO ────────────────────────────────
class LoggedKWPClient(KWP2000NativeClient):
    """Hereda de KWP2000NativeClient para interceptar y registrar todo el tráfico."""
    
    def execute_service(self, service_id: int, subfunction: int = None, data: bytes = b"") -> bytes:
        req_hex = f"{service_id:02X}"
        if subfunction is not None:
            req_hex += f" {subfunction:02X}"
        if data:
            req_hex += " " + " ".join(f"{b:02X}" for b in data)
        
        logger.info(f"  [TX -> ECU] Enviando: {req_hex}")
        
        try:
            resp = super().execute_service(service_id, subfunction, data)
            resp_hex = f"{service_id + 0x40:02X} " + " ".join(f"{b:02X}" for b in resp)
            logger.info(f"  [RX <- ECU] Recibido: {resp_hex}")
            return resp
        except Exception as e:
            logger.error(f"  [RX <- ECU] ERROR: {str(e)}")
            raise e


# ── SCRIPT PRINCIPAL ──────────────────────────────────────────────────────
def main():
    logger.info("=" * 70)
    logger.info(" INICIANDO ESCANEO DE LONG CODING (MODO ESTRICTO SOLO LECTURA)")
    logger.info(f" Archivo de Log: {log_filename}")
    logger.info("=" * 70)

    # 1. Conexión con CANable 2.0
    can_mgr = CANManager(log_fn=lambda m: None)
    logger.info("[1/2] Conectando con adaptador CANable 2.0 (500 kbps)...")
    
    pref = "auto"
    if len(sys.argv) > 1 and sys.argv[1] in ("virtual", "gs_usb", "slcan", "auto"):
        pref = sys.argv[1]

    if not can_mgr.conectar(interface_preference=pref, bitrate=500000):
        logger.error("❌ No se detectó ningún adaptador CANable conectado.")
        logger.error("   Verifica: cable USB enchufado, driver WinUSB/gs_usb y contacto del coche puesto.")
        return

    interfaz = getattr(can_mgr, "connected_interface", "desconocida")
    logger.info(f"✅ Conectado exitosamente vía {interfaz} (500 kbps).")
    logger.info("ℹ️ Recuerda: Puerta cerrada del todo y contacto en Posición II (motor apagado).\n")

    # 2. Inicializar Transporte y Cliente con logs
    tp20 = TP20Transport(can_mgr, timeout=1.2)
    kwp = LoggedKWPClient(tp20)

    # 3. Módulos a escanear
    modulos_a_escanear = [
        (0x17, "Cuadro de Instrumentos J285 (17)"),
        (0x46, "Centralita de Confort J393 (46)"),
        (0x42, "Puerta Conductor J386 (42)"),
        (0x52, "Puerta Copiloto J387 (52)")
    ]

    for addr, nombre in modulos_a_escanear:
        logger.info(f"\n{'─' * 60}")
        logger.info(f"[*] ESCANEANDO: {nombre} (0x{addr:02X})")
        logger.info(f"{'─' * 60}")
        
        try:
            t_start = time.perf_counter()
            # Abrir canal TP2.0
            if not tp20.open_channel(addr, retries=2):
                elapsed_ms = (time.perf_counter() - t_start) * 1000
                logger.error(f"  ❌ Sin respuesta del módulo 0x{addr:02X} (Timeout {elapsed_ms:.1f} ms).")
                continue
            
            # Iniciar sesión de diagnóstico
            kwp.start_diagnostic_session(0x86)
            time.sleep(0.08)
            
            # Leer Coding
            coding = kwp.read_coding()
            
            if coding:
                coding_bytes = list(coding)
                coding_hex = " ".join(f"{b:02X}" for b in coding_bytes)
                logger.info(f"  ✅ Coding leído con éxito ({len(coding_bytes)} bytes): {coding_hex}")
                logger.info(f"  ℹ️ Fuente de lectura: {kwp.last_read_source}")
                
                # ── ANÁLISIS ESPECÍFICO SEGÚN MÓDULO ──
                # MÓDULO 17: CUADRO DE INSTRUMENTOS
                if addr == 0x17 and len(coding_bytes) > 1:
                    b1 = coding_bytes[1]
                    logger.info(f"  🔍 [Cuadro 17] Byte 1: 0x{b1:02X} (Binario: {b1:08b})")
                    logger.info(f"     - Bit 0 (Needle Sweep / Barrido de agujas): {'[ACTIVO]' if (b1 & (1<<0)) else '[DESACTIVADO]'}")
                    logger.info(f"     - Bit 3 (Lap Timer / Cronómetro FIS)     : {'[ACTIVO]' if (b1 & (1<<3)) else '[DESACTIVADO]'}")
                
                # MÓDULO 46: CONFORT
                elif addr == 0x46:
                    if len(coding_bytes) > 7:
                        b7 = coding_bytes[7]
                        logger.info(f"  🔍 [Confort 46] Byte 7: 0x{b7:02X} (Binario: {b7:08b})")
                        logger.info(f"     - Bit 7 (Espejos plegables instalados) : {'[ACTIVO]' if (b7 & (1<<7)) else '[DESACTIVADO]'}")
                    if len(coding_bytes) > 4:
                        b4 = coding_bytes[4]
                        logger.info(f"  🔍 [Confort 46] Byte 4: 0x{b4:02X} (Binario: {b4:08b})")
                        logger.info(f"     - Bit 4 (Plegar al cerrar con mando)   : {'[ACTIVO]' if (b4 & (1<<4)) else '[DESACTIVADO]'}")
                        logger.info(f"     - Bit 6 (Desplegar al abrir con mando) : {'[ACTIVO]' if (b4 & (1<<6)) else '[DESACTIVADO]'}")

                # MÓDULOS 42 Y 52: PUERTAS CONDUCTOR Y COPILOTO
                elif addr in (0x42, 0x52) and len(coding_bytes) > 4:
                    b4 = coding_bytes[4]
                    logger.info(f"  🔍 [Puerta 0x{addr:02X}] Byte 4: 0x{b4:02X} (Binario: {b4:08b})")
                    logger.info(f"     - Bit 4 (Foldable Mirrors Installed)  : {'[ACTIVO]' if (b4 & (1<<4)) else '[DESACTIVADO]'}")
                    logger.info(f"     - Bit 6 (Comfort Mirror Folding Active): {'[ACTIVO]' if (b4 & (1<<6)) else '[DESACTIVADO]'}")
            else:
                logger.warning(f"  ⚠️ No se pudo leer la codificación del módulo 0x{addr:02X}.")
                
        except Exception as e:
            logger.error(f"  ❌ Excepción procesando módulo 0x{addr:02X}: {e}")
        
        finally:
            tp20.close_channel()
            time.sleep(0.15)  # Pausa de estabilización en Gateway J533

    can_mgr.desconectar()
    logger.info("\n" + "=" * 70)
    logger.info(" ESCANEO FINALIZADO.")
    logger.info(f" Log completo guardado en: {log_filename}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
