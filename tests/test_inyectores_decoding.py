import unittest
from unittest.mock import MagicMock
from obd.vag_service_wizards import VAGServiceWizards

class TestInyectoresDecoding(unittest.TestCase):
    def test_mwb_formula_47_decoding(self):
        can_mgr = MagicMock()
        wizards = VAGServiceWizards(can_mgr)
        
        # Simular KWP execute_service respondiendo exactamente con las tramas del coche del usuario:
        # Cil 1: 0x48, Formula 47 (0x2F), a=1, b=0xA1(161 -> +33ms), 0x93(147 -> +19ms), 0x95(149 -> +21ms)
        fake_responses = {
            72: bytes([0x48, 0x2F, 0x01, 0xA1, 0x2F, 0x01, 0x93, 0x2F, 0x01, 0x95, 0x25, 0x00, 0x00]),
            73: bytes([0x49, 0x2F, 0x01, 0x99, 0x2F, 0x01, 0x8F, 0x2F, 0x01, 0x90, 0x25, 0x00, 0x00]),
            74: bytes([0x4A, 0x2F, 0x01, 0x9A, 0x2F, 0x01, 0x9E, 0x2F, 0x01, 0x9A, 0x25, 0x00, 0x00]),
            75: bytes([0x4B, 0x2F, 0x01, 0x9D, 0x2F, 0x01, 0x90, 0x2F, 0x01, 0x99, 0x25, 0x00, 0x00]),
            76: bytes([0x4C, 0x2F, 0x01, 0xA5, 0x2F, 0x01, 0x95, 0x2F, 0x01, 0x95, 0x25, 0x00, 0x00]),
            77: bytes([0x4D, 0x2F, 0x01, 0x88, 0x2F, 0x01, 0x90, 0x2F, 0x01, 0x95, 0x25, 0x00, 0x00]),
        }
        
        wizards.tp20 = MagicMock()
        wizards.tp20.open_channel.return_value = True
        wizards.kwp = MagicMock()
        wizards.kwp.execute_service.side_effect = lambda sid, subfunction: fake_responses.get(subfunction, b'')
        
        resultado = wizards.inyectores_leer_calibracion(simulado=False)
        cilindros = resultado.get("cilindros", {})
        
        self.assertEqual(len(cilindros), 6)
        
        # Verificar Cilindro 1
        c1 = cilindros[1]
        self.assertEqual(c1["bar300"], 33.0)
        self.assertEqual(c1["bar600"], 19.0)
        self.assertEqual(c1["bar1000"], 21.0)
        self.assertIn("Sin riesgo de goteo", c1["estado"])
        
        # Verificar Cilindro 6
        c6 = cilindros[6]
        self.assertEqual(c6["bar300"], 8.0)
        self.assertEqual(c6["bar600"], 16.0)
        self.assertEqual(c6["bar1000"], 21.0)
        self.assertIn("Sin riesgo de goteo", c6["estado"])

if __name__ == '__main__':
    unittest.main()
