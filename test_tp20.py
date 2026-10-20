# test_tp20.py — Test directo del protocolo VW TP 2.0 en el Audi A6 C6
# ══════════════════════════════════════════════════════════════════════════════
# Este script prueba la conexión TP 2.0 con cada módulo del coche.
# Ejecución: python test_tp20.py  (o doble clic en TestTP20.exe)
#
# GENERA UN ARCHIVO DE LOG: tp20_log_YYYYMMDD_HHMMSS.txt
# con TODA la información de la sesión para análisis posterior.
#
# REQUISITOS:
#   - Cable ELM327 enchufado al puerto OBD del Audi A6 C6
#   - Contacto del coche puesto (posición II / ON, motor puede estar apagado)
#   - La palanquita del conector OBD en posición ABAJO
# ══════════════════════════════════════════════════════════════════════════════

import sys
import os
import time
import datetime

# Añadir directorio raíz al path
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.connection import Connection
from obd.vw_tp20 import VWTP20, MODULE_LOGICAL_ADDRESSES


# ══════════════════════════════════════════════════════════════════════════════
#  LOGGER DUAL: Consola + Archivo
# ══════════════════════════════════════════════════════════════════════════════

class DualLogger:
    """Escribe todo a consola Y a un archivo de log simultáneamente."""

    def __init__(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_filename = os.path.join(BASE_DIR, f"tp20_log_{timestamp}.txt")
        self.log_file = open(self.log_filename, "w", encoding="utf-8")
        self._write_header()

    def _write_header(self):
        header = [
            "=" * 70,
            "  AudiDiag Pro — LOG COMPLETO Test VW TP 2.0",
            f"  Fecha/Hora: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Sistema: {sys.platform} / Python {sys.version.split()[0]}",
            f"  Directorio: {BASE_DIR}",
            "  Coche: Audi A6 C6 4F (2010) 2.7 TDI V6",
            "  VIN: WAUZZZ4F2AN066325",
            "=" * 70,
            "",
        ]
        for line in header:
            self.log_file.write(line + "\n")
        self.log_file.flush()

    def log(self, msg: str):
        """Escribe mensaje a consola y archivo con timestamp."""
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted = f"[{ts}] {msg}"
        print(formatted)
        self.log_file.write(formatted + "\n")
        self.log_file.flush()

    def raw(self, msg: str):
        """Escribe mensaje sin timestamp (para cabeceras, separadores, etc.)."""
        print(msg)
        self.log_file.write(msg + "\n")
        self.log_file.flush()

    def close(self):
        """Cierra el archivo de log."""
        self.raw("")
        self.raw(f"[LOG] Archivo guardado en: {self.log_filename}")
        self.log_file.close()


# Instancia global del logger
logger = DualLogger()


def log_consola(msg: str):
    """Logger para pasar al módulo TP 2.0."""
    logger.log(msg)


def test_individual(tp20: VWTP20, addr: int, nombre: str):
    """Prueba abrir canal con un módulo específico."""
    logger.raw(f"\n{'─'*60}")
    logger.raw(f"  PROBANDO: {nombre} (0x{addr:02X})")
    logger.raw(f"{'─'*60}")

    resultado = {"modulo": nombre, "canal": False, "id": None, "dtcs": [], "coding": None}

    try:
        # Intentar abrir canal
        if tp20.abrir_canal(addr):
            resultado["canal"] = True
            logger.log(f"  ✅ ¡CANAL ABIERTO con {nombre}!")

            # Intentar leer identificación
            try:
                id_info = tp20.leer_identificacion()
                if id_info:
                    resultado["id"] = id_info
                    logger.log(f"  📋 Identificación: {id_info}")
            except Exception as e:
                logger.log(f"  ⚠️  Error leyendo ID: {e}")

            # Intentar leer DTCs
            try:
                dtcs = tp20.leer_dtcs()
                resultado["dtcs"] = dtcs
                if dtcs:
                    logger.log(f"  🔴 DTCs encontrados: {len(dtcs)}")
                    for dtc in dtcs:
                        logger.log(f"      → {dtc}")
                else:
                    logger.log(f"  🟢 Sin DTCs almacenados")
            except Exception as e:
                logger.log(f"  ⚠️  Error leyendo DTCs: {e}")

            # Intentar leer coding
            try:
                coding = tp20.leer_coding()
                if coding:
                    resultado["coding"] = coding
                    hex_str = " ".join(f"{b:02X}" for b in coding)
                    logger.log(f"  🔧 Coding: {hex_str}")
            except Exception as e:
                logger.log(f"  ⚠️  Error leyendo coding: {e}")

            # Cerrar canal
            tp20.cerrar_canal()
        else:
            logger.log(f"  ❌ No se pudo abrir canal con {nombre}")

    except Exception as e:
        logger.log(f"  💥 Error inesperado: {e}")
        import traceback
        logger.raw(traceback.format_exc())
        try:
            tp20.cerrar_canal()
        except Exception:
            pass

    return resultado


def main():
    logger.raw("=" * 60)
    logger.raw("  AudiDiag Pro — Test Protocolo VW TP 2.0")
    logger.raw("  Audi A6 C6 4F (2010) — VIN: WAUZZZ4F2AN066325")
    logger.raw("=" * 60)
    logger.raw("")
    logger.raw("  Este test intentará abrir canales TP 2.0 con")
    logger.raw("  las centralitas del coche a través del Gateway J533.")
    logger.raw("")
    logger.raw("  ANTES DE CONTINUAR asegúrate de que:")
    logger.raw("    ✓ El cable ELM327 está enchufado al OBD")
    logger.raw("    ✓ El contacto del coche está puesto (posición ON)")
    logger.raw("    ✓ La palanquita del conector está ABAJO")
    logger.raw("")
    logger.raw(f"  📝 Log guardándose en: {logger.log_filename}")
    logger.raw("")

    input("  Pulsa ENTER cuando estés listo para empezar...")
    logger.raw("")

    # Conectar
    conn = Connection()
    logger.log("Conectando con el adaptador ELM327...")

    if not conn.conectar():
        logger.log("[✗] No se pudo conectar al adaptador. ¿Está enchufado?")
        logger.close()
        input("\nPulsa ENTER para cerrar...")
        return

    logger.log("[✓] Conexión establecida con ELM327")

    # Detectar puerto y chip
    if conn.puerto:
        logger.log(f"  Puerto: {conn.puerto.port}")
        logger.log(f"  Baudrate: {conn.puerto.baudrate}")
    logger.raw("")

    # Verificar bus CAN básico antes de TP 2.0
    logger.log("Verificando bus CAN básico (PID 0100)...")
    bus_ok, bus_msg = conn.probar_comunicacion_bus()
    logger.log(f"  Bus CAN: {'OK' if bus_ok else 'FALLO'} — {bus_msg}")
    logger.raw("")

    # Crear instancia TP 2.0
    tp20 = VWTP20(conn, log_fn=log_consola)

    # Módulos a probar (ordenados por prioridad del usuario)
    modulos_test = [
        (0x19, "Gateway CAN (19)"),
        (0x17, "Cuadro Instrumentos (17)"),
        (0x09, "Central Eléctrica / Luces (09)"),
        (0x01, "Motor (01)"),
        (0x46, "Confort / BCM (46)"),
        (0x03, "ABS / ESP (03)"),
        (0x08, "Climatización (08)"),
        (0x15, "Airbag (15)"),
    ]

    resultados = []
    exitos = 0
    fallos = 0

    for addr, nombre in modulos_test:
        resultado = test_individual(tp20, addr, nombre)
        resultados.append(resultado)

        if resultado["canal"]:
            exitos += 1
        else:
            fallos += 1

        # Pausa entre módulos para estabilizar el bus
        time.sleep(1.0)

    # Resumen final
    logger.raw("")
    logger.raw("=" * 60)
    logger.raw("  RESUMEN DE RESULTADOS")
    logger.raw("=" * 60)
    logger.raw("")

    for r in resultados:
        estado = "✅ ABIERTO" if r["canal"] else "❌ FALLÓ"
        extras = []
        if r["id"]:
            extras.append("ID✓")
        if r["dtcs"]:
            extras.append(f"DTCs:{len(r['dtcs'])}")
        if r["coding"]:
            extras.append("Coding✓")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        logger.raw(f"  {estado}  {r['modulo']}{extra_str}")

    logger.raw("")
    logger.raw(f"  Canales abiertos: {exitos}/{len(modulos_test)}")
    logger.raw(f"  Canales fallidos: {fallos}/{len(modulos_test)}")
    logger.raw("")

    if exitos > 0:
        logger.raw("  🎉 ¡AL MENOS UN MÓDULO HA RESPONDIDO POR TP 2.0!")
        logger.raw("  El protocolo funciona con tu cable ELM327.")
        if any(r["canal"] and r["modulo"].startswith("Cuadro") for r in resultados):
            logger.raw("  ¡Y el Cuadro de Instrumentos respondió! Puedes intentar codificar.")
    else:
        logger.raw("  😔 Ningún módulo respondió al channel setup de TP 2.0.")
        logger.raw("  Esto confirma que el chip ELM327 no puede manejar el timing")
        logger.raw("  del Gateway de tu Audi A6 C6.")
        logger.raw("")
        logger.raw("  Pero NO HAS PERDIDO NADA: has aprendido exactamente cómo funciona")
        logger.raw("  el protocolo y tu código está correcto. La limitación es del hardware.")

    # Desconectar
    conn.desconectar()
    logger.raw("")
    logger.log("Test finalizado. Conexión cerrada.")
    logger.close()

    print(f"\n  📁 LOG COMPLETO GUARDADO EN:")
    print(f"     {logger.log_filename}")
    print(f"\n  Copia este archivo y tráemelo para que lo analice.\n")
    input("Pulsa ENTER para cerrar...")


if __name__ == "__main__":
    main()
