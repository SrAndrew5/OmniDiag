# -*- coding: utf-8 -*-
"""
tests/test_needle_sweep_mock.py
Verifica el flujo completo de activar_needle_sweep():
- Lectura exitosa vía 0x1A 0x9E + escritura + verificación
- Aborto por seguridad si la fuente de lectura no es 0x1A 0x9E
- Aborto si el cuadro no devuelve codificación
- Flujo de rollback verificado ante fallo de verificación
"""
import unittest
from unittest.mock import MagicMock
from obd.audi_a6_actions import AudiA6Actions


class FakeKWP:
    def __init__(self, initial_coding: bytes, read_source: str = "0x1A 0x9E"):
        self.coding = bytearray(initial_coding)
        self.last_read_source = read_source
        self.write_calls = []
        self.sessions = []
        self.simulate_write_rejection = False
        self.simulate_verification_mismatch = False

    def start_diagnostic_session(self, session_type):
        self.sessions.append(session_type)
        return True

    def read_coding(self):
        if self.simulate_verification_mismatch and len(self.write_calls) == 1:
            # Devuelve algo que no coincide tras la primera escritura
            return bytes([0xFF, 0xFF, 0xFF])
        return bytes(self.coding)

    def write_coding(self, new_bytes: bytes) -> bool:
        if self.simulate_write_rejection:
            return False
        self.write_calls.append(bytes(new_bytes))
        self.coding = bytearray(new_bytes)
        return True


class TestNeedleSweepMock(unittest.TestCase):
    def setUp(self):
        self.fake_can = MagicMock()
        self.actions = AudiA6Actions(self.fake_can, log_fn=lambda m: None, vin="WAUZZZ4F000000000")
        self.actions.tp20.open_channel = MagicMock(return_value=True)
        self.actions.tp20.close_channel = MagicMock(return_value=True)

    def test_needle_sweep_exitoso(self):
        # Byte 1 Bit 0 apagado (0x00) -> Debe encenderlo (0x01)
        fake_kwp = FakeKWP(initial_coding=b"\x04\x00\x00", read_source="0x1A 0x9E")
        self.actions.kwp = fake_kwp

        ok, msg = self.actions.activar_needle_sweep()
        self.assertTrue(ok)
        self.assertIn("activado y verificado", msg)
        self.assertEqual(len(fake_kwp.write_calls), 1)
        self.assertEqual(fake_kwp.write_calls[0], b"\x04\x01\x00")

    def test_needle_sweep_aborta_si_fuente_no_es_0x1A_0x9E(self):
        # Si vino de un DID 0x22 u otra heurística, DEBE abortar con 0 escrituras
        fake_kwp = FakeKWP(initial_coding=b"\x04\x00\x00", read_source="0x22 0x0600")
        self.actions.kwp = fake_kwp

        ok, msg = self.actions.activar_needle_sweep()
        self.assertFalse(ok)
        self.assertIn("ABORTADO POR SEGURIDAD", msg)
        self.assertEqual(len(fake_kwp.write_calls), 0)

    def test_needle_sweep_ya_activo(self):
        # Si Byte 1 Bit 0 ya está en 1 -> No escribe nada y retorna True
        fake_kwp = FakeKWP(initial_coding=b"\x04\x01\x00", read_source="0x1A 0x9E")
        self.actions.kwp = fake_kwp

        ok, msg = self.actions.activar_needle_sweep()
        self.assertTrue(ok)
        self.assertIn("ya estaba activo", msg)
        self.assertEqual(len(fake_kwp.write_calls), 0)

    def test_needle_sweep_rollback_si_verificacion_falla(self):
        # Si la verificación no coincide, ejecuta rollback a la original
        fake_kwp = FakeKWP(initial_coding=b"\x04\x00\x00", read_source="0x1A 0x9E")
        fake_kwp.simulate_verification_mismatch = True
        self.actions.kwp = fake_kwp

        ok, msg = self.actions.activar_needle_sweep()
        self.assertFalse(ok)
        # Se intentó escribir el nuevo valor y luego se escribió el rollback
        self.assertGreaterEqual(len(fake_kwp.write_calls), 2)
        # La última escritura fue el rollback a b"\x04\x00\x00"
        self.assertEqual(fake_kwp.write_calls[-1], b"\x04\x00\x00")


    def test_codificar_bits_modulo_fuera_de_rango_aborta_sin_rellenar_ceros(self):
        # Si la centralita tiene 3 bytes y se pide modificar el Byte 5, debe abortar sin escribir nada
        fake_kwp = FakeKWP(initial_coding=b"\x04\x00\x00", read_source="0x1A 0x9E")
        self.actions.kwp = fake_kwp

        ok, msg = self.actions._codificar_bits_modulo(
            addr=0x17,
            nombre="Cuadro Instrumentos (17)",
            bits_activar=[(5, 0, True)],
            etiqueta_backup="TEST_OUT_OF_BOUNDS"
        )
        self.assertFalse(ok)
        self.assertIn("ABORTADO POR SEGURIDAD", msg)
        self.assertIn("No se extenderá la longitud artificialmente", msg)
        self.assertEqual(len(fake_kwp.write_calls), 0)

    def test_escribir_coding_seguro_longitud_distinta_aborta(self):
        # Si se intenta escribir una longitud distinta (ej: 4 bytes cuando el módulo tiene 3), aborta sin escribir
        fake_kwp = FakeKWP(initial_coding=b"\x04\x00\x00", read_source="0x1A 0x9E")
        self.actions.kwp = fake_kwp

        ok, msg = self.actions.escribir_coding_seguro(
            addr=0x17,
            nombre="Cuadro Instrumentos (17)",
            nuevo_bytes=b"\x04\x01\x00\xFF",
            etiqueta_backup="TEST_LEN_MISMATCH"
        )
        self.assertFalse(ok)
        self.assertIn("ABORTADO POR SEGURIDAD", msg)
        self.assertIn("Longitud incompatible", msg)
        self.assertEqual(len(fake_kwp.write_calls), 0)

    def test_escribir_coding_seguro_idempotente_sin_escrituras(self):
        # Si la codificación nueva es idéntica a la actual, retorna True con 0 escrituras
        fake_kwp = FakeKWP(initial_coding=b"\x04\x01\x00", read_source="0x1A 0x9E")
        self.actions.kwp = fake_kwp

        ok, msg = self.actions.escribir_coding_seguro(
            addr=0x17,
            nombre="Cuadro Instrumentos (17)",
            nuevo_bytes=b"\x04\x01\x00",
            etiqueta_backup="TEST_IDEMPOTENT"
        )
        self.assertTrue(ok)
        self.assertIn("Sin cambios", msg)
        self.assertEqual(len(fake_kwp.write_calls), 0)

    def test_escribir_coding_seguro_rollback_fallido(self):
        # Si la verificación falla Y además el rollback es rechazado por la ECU
        fake_kwp = FakeKWP(initial_coding=b"\x04\x00\x00", read_source="0x1A 0x9E")
        fake_kwp.simulate_verification_mismatch = True
        self.actions.kwp = fake_kwp

        # Simulamos que tras el primer write_coding, el siguiente write_coding (rollback) es rechazado
        original_write = fake_kwp.write_coding
        def write_side_effect(new_bytes):
            if len(fake_kwp.write_calls) == 1:
                # El segundo write (rollback) falla
                return False
            return original_write(new_bytes)
        fake_kwp.write_coding = write_side_effect

        ok, msg = self.actions.escribir_coding_seguro(
            addr=0x17,
            nombre="Cuadro Instrumentos (17)",
            nuevo_bytes=b"\x04\x01\x00",
            etiqueta_backup="TEST_ROLLBACK_FAIL"
        )
        self.assertFalse(ok)
        self.assertIn("CRÍTICO", msg)


if __name__ == "__main__":
    unittest.main()
