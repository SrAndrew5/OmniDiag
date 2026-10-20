"""
test_cuadro_coding.py — Verificación exhaustiva de direccionamiento y coding para Cuadro 17
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
config.MODE = "simulado"
from core.connection import Connection
from obd.vag_protocol import VAGProtocol, MODULOS_VAG
from obd.long_coding import LongCodingManager
from obd.vag_a6_features import CATALOGO_CONFORT_A6

print("--- TEST CUADRO INSTRUMENTOS (17) Y NEEDLE SWEEP ---")

# 1. Verificar mapeo CAN
assert "Cuadro Instrumentos (17)" in MODULOS_VAG
tx, rx, desc, log_addr = MODULOS_VAG["Cuadro Instrumentos (17)"]
assert tx == "714", f"TX incorrecto: {tx}"
assert rx == "77E", f"RX incorrecto: {rx}"
assert log_addr == 0x17
print(f"[OK] Cuadro 17: TX={tx}, RX_Filter={rx}, LogicalAddr=0x{log_addr:02X}")

# 2. Verificar Central Eléctrica / Luces (09)
tx9, rx9, desc9, log9 = MODULOS_VAG["Central Eléctrica / Luces (09)"]
assert tx9 == "70E", f"TX 09 incorrecto: {tx9}"
assert rx9 == "778", f"RX 09 incorrecto: {rx9}"
print(f"[OK] Central Eléctrica 09: TX={tx9}, RX_Filter={rx9}")

# 3. Verificar Needle Sweep en catálogo
features_17 = CATALOGO_CONFORT_A6.get("Cuadro Instrumentos (17)", [])
needle = next((f for f in features_17 if f["id"] == "needle_sweep"), None)
assert needle is not None, "Needle sweep no está en catálogo"
assert needle["byte"] == 1
assert needle["bit"] == 0
print(f"[OK] Catálogo: Needle sweep en Byte {needle['byte']}, Bit {needle['bit']}")

# 4. Probar manipulación de bit 0 en Byte 1
lcm = LongCodingManager()
# Ejemplo coding típico cuadro A6 C6 Facelift: 17 00 00
coding_original = "17 00 00"
coding_activo = lcm.cambiar_bit(coding_original, byte_index=1, bit_index=0, activar=True)
assert coding_activo == "17 01 00", f"Error activando bit: {coding_activo}"
assert lcm.leer_bit(coding_activo, 1, 0) is True
print(f"[OK] Activación Needle Sweep: {coding_original} -> {coding_activo}")

coding_desactivo = lcm.cambiar_bit(coding_activo, byte_index=1, bit_index=0, activar=False)
assert coding_desactivo == "17 00 00"
assert lcm.leer_bit(coding_desactivo, 1, 0) is False
print(f"[OK] Desactivación Needle Sweep: {coding_activo} -> {coding_desactivo}")

# 5. Probar flujo con VAGProtocol
conn = Connection()
assert conn.conectar()
vag = VAGProtocol(conn, log_fn=lambda m: None)
assert vag.inicializar_modulo("Cuadro Instrumentos (17)")
coding = vag.leer_coding_uds()
assert coding is not None
print(f"[OK] Lectura coding simulado Cuadro 17: {coding}")

res = vag.escribir_coding_uds(
    nombre_modulo="Cuadro Instrumentos (17)",
    vin="WAUZZZ4F2AN066325",
    nuevo_coding="17 01 00",
    coding_antiguo="17 00 00"
)
assert "correctamente" in res.lower() or "ok" in res.lower()
print(f"[OK] Resultado escritura: {res}")

print("--- TODOS LOS TESTS DE CUADRO 17 SUPERADOS ---")
