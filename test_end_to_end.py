"""
test_end_to_end.py — Prueba integral de todo el stack de AudiDiag Pro
Comprueba que ninguna llamada lance excepciones no capturadas.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
config.MODE = "simulado"
from core.connection import Connection
from obd.vag_protocol import VAGProtocol, MODULOS_VAG
from obd.long_coding import LongCodingManager
from gestion.database_manager import DatabaseManager
from gestion.backup_manager import BackupManager
from gestion.report_generator import ReportGenerator

print("=" * 60)
print("INICIANDO TEST END-TO-END AUDIDIAG PRO")
print("=" * 60)

# 1. Conexión
conn = Connection()
assert conn.conectar(), "Fallo al conectar"
print("[PASS] 1. Conexión establecida (FakeSerial).")

# 2. VAGProtocol
vag = VAGProtocol(conn, log_fn=lambda m: None)
for mod in MODULOS_VAG:
    assert vag.inicializar_modulo(mod), f"Fallo init {mod}"
print(f"[PASS] 2. Inicializados los {len(MODULOS_VAG)} módulos.")

# 3. UDS Comandos
dtc_resp = vag.leer_dtcs_uds()
print(f"[PASS] 3. Lectura DTCs UDS: {dtc_resp}")

coding_leido = vag.leer_coding_uds()
print(f"[PASS] 4. Lectura Coding UDS: {coding_leido}")

# 4. Escritura Coding con Backup (el caso que petó con Confort / Electrónica (46))
modulo_critico = "Confort / Electrónica (46)"
res_escribir = vag.escribir_coding_uds(
    nombre_modulo=modulo_critico,
    vin="WAUZZZ4G7BN000000",
    nuevo_coding="FF D0 00 03 08 41 00 00 00 01",
    coding_antiguo="FF D0 00 03 08 41 00 00 00 00",
)
print(f"[PASS] 5. Escritura coding ({modulo_critico}): {res_escribir}")
assert "correctamente" in res_escribir.lower() or "ok" in res_escribir.lower(), f"Escritura falló: {res_escribir}"

# 5. Backup Manager
bm = BackupManager()
backups = bm.listar_backups(modulo=modulo_critico)
assert len(backups) > 0, "No se encontró el backup guardado"
ultimo_backup = bm.cargar_backup(backups[0])
assert ultimo_backup["modulo"] == modulo_critico, "Datos del backup corruptos"
print(f"[PASS] 6. Backup verificado: {backups[0]}")

# 6. Database Manager + Freeze Frame
db = DatabaseManager()
sid = db.nueva_sesion("WAUZZZ4G7BN000000")
dtc_id = db.registrar_dtc(
    vin="WAUZZZ4G7BN000000",
    codigo="P0299",
    estado="Activo",
    descripcion="Turbocompresor — presión insuficiente",
    modulo="Motor (01)",
    sesion_id=sid,
    freeze_frame={"RPM": (2100.0, "rpm"), "Velocidad": (80.0, "km/h")}
)
ff = db.obtener_freeze_frame(dtc_id)
assert len(ff) == 2, "Freeze frame no guardado correctamente"
print(f"[PASS] 7. Database y Freeze Frame OK (DTC ID: {dtc_id}, FF rows: {len(ff)})")

# 7. Report Generator
rg = ReportGenerator()
rep_path = rg.generar_reporte_txt(sid)
assert os.path.exists(rep_path), "Fichero de reporte no existe"
print(f"[PASS] 8. Generación de informe OK: {rep_path}")

# 8. LongCodingManager
lcm = LongCodingManager()
original = "0A 00 FF"
modificado = lcm.cambiar_bit(original, 0, 0, activar=True)
assert lcm.leer_bit(modificado, 0, 0) == True
print(f"[PASS] 9. LongCodingManager bit-edit OK: {original} -> {modificado}")

print("=" * 60)
print("¡TODOS LOS TESTS COMPLETADOS CON ÉXITO SIN NINGÚN ERROR!")
print("=" * 60)
