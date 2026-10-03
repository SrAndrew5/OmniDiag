# -*- coding: utf-8 -*-
"""
test_kline_suite.py — Suite de Pruebas Unitarias para el Motor VAG K-Line
Verifica:
  1. Handshake y conexion KWP1281 / K-Line.
  2. Lectura de identificacion de centralitas (Polo 9N3 Modulo 46 Confort y 01 Motor).
  3. Lectura de averias (DTCs) y borrado en K-Line.
  4. Modificacion y persistencia de canales de adaptacion (Canal 04, 06, 07, 03).
  5. Instanciacion limpia de la interfaz DialogoPoloKLine.
"""

import sys
import unittest
from PyQt6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

# Mockear popups interactivos para ejecucion automatizada
QMessageBox.information = lambda *args, **kwargs: None
QMessageBox.warning = lambda *args, **kwargs: None
QMessageBox.critical = lambda *args, **kwargs: None
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

from obd.vag_kline import VAGKLineClient, POLO_9N3_CONFORT_CHANNELS
from ui.dialogo_polo_kline import DialogoPoloKLine


class TestVAGKLine(unittest.TestCase):

    def setUp(self):
        self.client = VAGKLineClient(port_name="MOCK")

    def test_01_conexion_handshake(self):
        ok = self.client.conectar(0x46)
        self.assertTrue(ok, "Fallo al conectar con Modulo 46 Confort")
        self.assertTrue(self.client.conectado)

    def test_02_identificacion_confort(self):
        self.client.conectar(0x46)
        ident = self.client.leer_identificacion()
        self.assertEqual(ident.get("referencia"), "6Q0 959 433 E")
        self.assertIn("Komfortgerat", ident.get("componente", ""))

    def test_03_lectura_averias(self):
        self.client.conectar(0x46)
        dtcs = self.client.leer_dtcs()
        self.assertGreaterEqual(len(dtcs), 1)
        codigos = [d["codigo"] for d in dtcs]
        self.assertIn("00928", codigos)

        # Probar borrado
        ok_borrado = self.client.borrar_dtcs()
        self.assertTrue(ok_borrado)
        self.assertEqual(len(self.client.leer_dtcs()), 0)

    def test_04_canales_adaptacion_polo(self):
        self.client.conectar(0x46)

        # Canal 06: Silenciar pitido
        val_orig = self.client.leer_canal_adaptacion(6)
        self.client.guardar_canal_adaptacion(6, 0)
        self.assertEqual(self.client.leer_canal_adaptacion(6), 0)

        # Canal 04: Auto-Unlock
        self.client.guardar_canal_adaptacion(4, 1)
        self.assertEqual(self.client.leer_canal_adaptacion(4), 1)

        # Canal 07: 1 Toque abre todo
        self.client.guardar_canal_adaptacion(7, 0)
        self.assertEqual(self.client.leer_canal_adaptacion(7), 0)

    def test_05_modulo_motor_dtcs(self):
        self.client.conectar(0x01)
        ident = self.client.leer_identificacion()
        self.assertEqual(ident.get("referencia"), "038 906 019 LA")
        dtcs = self.client.leer_dtcs()
        cods = [d["codigo"] for d in dtcs]
        self.assertIn("01650", cods)
        self.assertIn("00532", cods)

    def test_06_dialogo_ui(self):
        dlg = DialogoPoloKLine()
        dlg.combo_puerto.setCurrentText("MOCK")
        dlg._toggle_conexion()
        self.assertTrue(dlg.cliente.conectado)
        dlg._cambiar_canal(6, 0)
        self.assertEqual(dlg.cliente.leer_canal_adaptacion(6), 0)
        dlg._escanear_modulo(0x01)
        self.assertGreaterEqual(dlg.tabla_dtc.rowCount(), 2)


if __name__ == "__main__":
    print("=" * 65)
    print("         EJECUTANDO SUITE DE TESTS VAG K-LINE (POLO 9N3)")
    print("=" * 65)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestVAGKLine)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)