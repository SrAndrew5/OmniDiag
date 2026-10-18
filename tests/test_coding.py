import os
import sys
import unittest

# Asegurar que la raíz del proyecto esté en el path para los imports absolutos
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from obd.long_coding import LongCodingManager


class TestLongCoding(unittest.TestCase):
    """Tests unitarios formales del motor matemático de Long Coding."""

    def setUp(self):
        self.mgr = LongCodingManager()

    def test_hex_to_bytes(self):
        self.assertEqual(self.mgr.hex_to_bytes("010A3F"), [1, 10, 63])
        self.assertEqual(self.mgr.hex_to_bytes("01 0A 3F"), [1, 10, 63])

    def test_bytes_to_hex(self):
        self.assertEqual(self.mgr.bytes_to_hex([1, 10, 63]), "01 0A 3F")

    def test_activar_bit(self):
        self.assertEqual(
            self.mgr.cambiar_bit("010A3F", byte_index=1, bit_index=0, activar=True),
            "01 0B 3F",
        )

    def test_desactivar_bit(self):
        self.assertEqual(
            self.mgr.cambiar_bit("010B3F", byte_index=1, bit_index=3, activar=False),
            "01 03 3F",
        )

    def test_leer_bit(self):
        self.assertFalse(self.mgr.leer_bit("010A3F", byte_index=1, bit_index=0))
        self.assertTrue(self.mgr.leer_bit("010A3F", byte_index=1, bit_index=1))

    def test_bit_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            self.mgr.cambiar_bit("010A3F", byte_index=1, bit_index=8, activar=True)

    def test_byte_fuera_de_rango(self):
        with self.assertRaises(IndexError):
            self.mgr.cambiar_bit("010A3F", byte_index=9, bit_index=0, activar=True)

    def test_hex_impar_lanza_error(self):
        with self.assertRaises(ValueError):
            self.mgr.hex_to_bytes("010A3")


if __name__ == "__main__":
    unittest.main()
