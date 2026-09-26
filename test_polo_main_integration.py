# -*- coding: utf-8 -*-
"""
test_polo_main_integration.py
Pruebas de Integración Nativa de VAG K-Line (VW Polo 9N3 1.9 TDI 2007)
en la Interfaz Principal y Controlador de OmniDiag / AudiDiag Pro.
"""

import sys
import os
import unittest
import time

# Forzar codificación UTF-8 para consola Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
import config
from audi_diag_pro import MainWindow
from ui.controlador import MotorDiagnostico, ADAPTACIONES_POLO_KLINE, ACTUADORES_POLO_KLINE
from obd.vag_dtc_smart_guide import obtener_ficha_dtc


class TestPoloMainIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.win = MainWindow()

    def _wait_worker(self, timeout_ms=5000):
        """Espera a que el worker termine bombeando eventos Qt para procesar señales entre hilos."""
        t0 = time.time()
        while self.win.worker.isRunning() and (time.time() - t0) * 1000 < timeout_ms:
            self.app.processEvents()
            time.sleep(0.02)
        self.win.worker.wait(500)
        for _ in range(5):
            self.app.processEvents()
            time.sleep(0.01)

    def test_01_selector_modo_polo_kline(self):
        """Verifica que el selector de modo configure el Virtual Cockpit para Polo 9N3."""
        # Índice 5 = Modo Simulado VW Polo 9N3 K-Line
        self.win.combo_modo.setCurrentIndex(5)
        self.assertEqual(config.VEHICLE_MODE, "VAG_KLINE")
        self.assertEqual(config.MODE, "simulado")
        self.assertTrue(self.win.es_modo_kline)
        self.assertFalse(self.win.es_modo_opel)

        # Telemetría Virtual Cockpit
        self.assertIn("6Q0959433E", self.win.lbl_vin.text())
        self.assertIn("Polo 9N3", self.win.lbl_vehiculo_desc.text())
        self.assertIn("K-Line", self.win.lbl_protocolo_sub.text())
        self.assertIn("K-LINE", self.win.lbl_red.text())

    def test_02_combos_modulos_polo(self):
        """Verifica que los combos de DTC, Adaptaciones y Actuadores se adapten al Polo 9N3."""
        self.win.combo_modo.setCurrentIndex(5)

        # Combo DTC
        dtc_items = [self.win.combo_dtc.itemText(i) for i in range(self.win.combo_dtc.count())]
        self.assertIn("Confort / BCM (46)", dtc_items)
        self.assertIn("Motor (01)", dtc_items)
        self.assertIn("ABS / Frenos (03)", dtc_items)
        self.assertIn("Cuadro de Instrumentos (17)", dtc_items)
        self.assertIn("Airbag (15)", dtc_items)

        # Combo Adaptaciones
        adapt_items = [self.win.combo_adapt.itemText(i) for i in range(self.win.combo_adapt.count())]
        self.assertIn("Confort / BCM (46)", adapt_items)
        self.assertIn("Motor (01)", adapt_items)

        # Verificar spinboxes de adaptación en Confort (46)
        self.assertIn("Auto-Lock (Cierre a 15 km/h)", self.win._adaptaciones_spin)
        self.assertIn("Auto-Unlock (Apertura al sacar llave)", self.win._adaptaciones_spin)
        self.assertIn("Mute Claxon / Pitido al cerrar", self.win._adaptaciones_spin)
        self.assertIn("Apertura Selectiva de Puertas", self.win._adaptaciones_spin)

    def test_03_conexion_worker_polo(self):
        """Prueba la conexión del WorkerThread en modo VAG_KLINE."""
        self.win.combo_modo.setCurrentIndex(5)
        self.win.iniciar_conexion()
        self._wait_worker()

        self.assertEqual(self.win.worker.hardware_tipo, "SIMULADO_KLINE")
        self.assertEqual(self.win.worker.vin, "6Q0959433E")

    def test_04_escaneo_dtcs_confort_y_motor(self):
        """Verifica que el escaneo devuelva los códigos exactos del Polo con descripción oficial."""
        # 1. Escaneo Confort (46)
        self.win.combo_dtc.setCurrentText("Confort / BCM (46)")
        self.win.escanear_modulo()
        self._wait_worker()

        self.assertGreaterEqual(self.win.tabla_dtc.rowCount(), 2)
        codigos_confort = [self.win.tabla_dtc.item(r, 1).text() for r in range(self.win.tabla_dtc.rowCount())]
        self.assertIn("00928", codigos_confort)
        self.assertIn("00932", codigos_confort)

        # 2. Escaneo Motor (01)
        self.win.combo_dtc.setCurrentText("Motor (01)")
        self.win.escanear_modulo()
        self._wait_worker()

        self.assertGreaterEqual(self.win.tabla_dtc.rowCount(), 2)
        codigos_motor = [self.win.tabla_dtc.item(r, 1).text() for r in range(self.win.tabla_dtc.rowCount())]
        self.assertIn("01650", codigos_motor)
        self.assertIn("00532", codigos_motor)

    def test_05_fichas_inteligentes_polo_dtcs(self):
        """Verifica que los fallos del Polo dispongan de ficha técnica con ubicación física exacta."""
        for cod in ("00928", "00932", "01650", "00532"):
            ficha = obtener_ficha_dtc(cod)
            self.assertTrue(ficha["encontrado"], f"Fallo {cod} no encontrado en base inteligente")
            self.assertGreater(len(ficha["ubicacion"]), 10)
            self.assertGreater(len(ficha["comprobacion"]), 20)

    def test_06_adaptacion_canales_padre(self):
        """Verifica lectura, modificación y persistencia de adaptaciones (Canal 06 Mute Beep, Canal 04 Auto-Unlock)."""
        # Lectura inicial de adaptaciones
        self.win.combo_adapt.setCurrentText("Confort / BCM (46)")
        self.win.leer_adaptaciones_modulo()
        self._wait_worker()

        # Silenciar pitido de bocina (Canal 06 = 0)
        self.win.escribir_adaptacion("Mute Claxon / Pitido al cerrar", 6, 0.0, confirmar=False)
        self._wait_worker()
        c6_val = self.win.worker.kline_client.leer_canal_adaptacion(6)
        self.assertEqual(c6_val, 0)

        # Activar Auto-Unlock al sacar llave (Canal 04 = 1)
        self.win.escribir_adaptacion("Auto-Unlock (Apertura al sacar llave)", 4, 1.0, confirmar=False)
        self._wait_worker()
        c4_val = self.win.worker.kline_client.leer_canal_adaptacion(4)
        self.assertEqual(c4_val, 1)

        # Apertura de todas las puertas con 1 solo toque (Canal 07 = 0)
        self.win.escribir_adaptacion("Apertura Selectiva de Puertas", 7, 0.0, confirmar=False)
        self._wait_worker()
        c7_val = self.win.worker.kline_client.leer_canal_adaptacion(7)
        self.assertEqual(c7_val, 0)

    def test_07_sensores_en_vivo_polo(self):
        """Verifica la lectura de telemetría y sensores del motor 1.9 TDI."""
        self.win.combo_modo.setCurrentIndex(5)
        self.win.leer_sensores()
        self._wait_worker()

        self.assertGreaterEqual(self.win.tabla_sensores.rowCount(), 6)
        sensores_leidos = [self.win.tabla_sensores.item(r, 0).text() for r in range(self.win.tabla_sensores.rowCount())]
        self.assertIn("RPM Motor", sensores_leidos)
        self.assertIn("Temp. Refrigerante (G62)", sensores_leidos)
        self.assertIn("Presión Turbo Actual", sensores_leidos)
        self.assertIn("Voltaje Batería / Borne 30", sensores_leidos)

    def test_08_auto_scan_polo_completo(self):
        """Verifica que el Auto-Scan completo recorra todos los módulos de la plataforma PQ24."""
        self.win.combo_modo.setCurrentIndex(5)
        self.win.auto_scan()
        self._wait_worker(timeout_ms=8000)

        # Debe haber fallos en Confort y Motor
        self.assertGreaterEqual(self.win.tabla_dtc.rowCount(), 4)
        modulos_en_tabla = set(self.win.tabla_dtc.item(r, 0).text() for r in range(self.win.tabla_dtc.rowCount()))
        self.assertIn("Confort / BCM (46)", modulos_en_tabla)
        self.assertIn("Motor (01)", modulos_en_tabla)

    def test_09_aislamiento_pestanas_mantenimiento(self):
        """Verifica que los Wizards de Mantenimiento se aíslen estrictamente según el vehículo."""
        # 1. Modo VW Polo 9N3 K-Line
        self.win.combo_modo.setCurrentIndex(5)
        tabs = self.win.tabs_mantenimiento
        self.assertEqual(tabs.count(), 10)

        # Solo visibles: 1 (SRI), 5 (Purga ABS), 7 (G85 Dirección)
        self.assertTrue(tabs.isTabVisible(1), "Tab 1 SRI debe ser visible en Polo")
        self.assertTrue(tabs.isTabVisible(5), "Tab 5 Purga ABS debe ser visible en Polo")
        self.assertTrue(tabs.isTabVisible(7), "Tab 7 G85 debe ser visible en Polo")

        # Ocultos en Polo (No aplican físicamente)
        self.assertFalse(tabs.isTabVisible(0), "Tab 0 EPB debe estar oculto en Polo")
        self.assertFalse(tabs.isTabVisible(2), "Tab 2 DPF debe estar oculto en Polo (sin filtro de partículas)")
        self.assertFalse(tabs.isTabVisible(3), "Tab 3 Inyectores V6 debe estar oculto en Polo")
        self.assertFalse(tabs.isTabVisible(4), "Tab 4 BEM Batería debe estar oculto en Polo")
        self.assertFalse(tabs.isTabVisible(6), "Tab 6 Caja Automática ATF debe estar oculto en Polo")
        self.assertFalse(tabs.isTabVisible(8), "Tab 8 Chapaletas V157 debe estar oculto en Polo")
        self.assertFalse(tabs.isTabVisible(9), "Tab 9 Menú Verde MMI debe estar oculto en Polo")

        self.assertIn("VW Polo 9N3", self.win.lbl_maint_titulo.text())

        # 2. Modo Audi A6 C6 (Restauración completa de los 10 wizards)
        self.win.combo_modo.setCurrentIndex(4)
        for i in range(10):
            self.assertTrue(tabs.isTabVisible(i), f"Tab {i} debe estar visible en Audi A6")
        self.assertIn("Wizards de Mantenimiento y Servicio (1 Clic)", self.win.lbl_maint_titulo.text())

        # 3. Modo Opel Corsa D (Solo SRI visible)
        self.win.combo_modo.setCurrentIndex(6)
        self.assertTrue(tabs.isTabVisible(1), "Tab 1 SRI debe ser visible en Opel Corsa")
        self.assertFalse(tabs.isTabVisible(0), "Tab 0 EPB debe estar oculto en Opel Corsa")
        self.assertFalse(tabs.isTabVisible(2), "Tab 2 DPF debe estar oculto en Opel Corsa")
        self.assertFalse(tabs.isTabVisible(6), "Tab 6 Caja ATF debe estar oculto en Opel Corsa")

    def test_10_aislamiento_long_coding_y_confort(self):
        """Verifica que la pantalla de Codificación no mezcle funciones de Audi con el Polo."""
        self.win.combo_modo.setCurrentIndex(5)

        # Subtítulo y Pestañas adaptadas
        self.assertIn("VW Polo 9N3", self.win.lbl_coding_titulo.text())
        self.assertIn("VW Polo 9N3", self.win.tabs_coding.tabText(0))
        self.assertFalse(self.win.tabs_coding.isTabVisible(1), "Tab 1 Editor Bit a Bit UDS debe estar oculto en Polo K-Line")

        # Botones exclusivos de Audi ocultos
        self.assertFalse(self.win.btn_needle.isVisible(), "Needle Sweep 1-Click debe ocultarse en Polo")
        self.assertFalse(self.win.btn_gw.isVisible(), "Lista Gateway 19 debe ocultarse en Polo")

        # Módulos de codificación en Polo
        modulos_coding = [self.win.combo_coding.itemText(i) for i in range(self.win.combo_coding.count())]
        self.assertIn("Confort / BCM (46)", modulos_coding)
        self.assertIn("Central Eléctrica / Luces (09)", modulos_coding)
        self.assertIn("Cuadro de Instrumentos (17)", modulos_coding)
        self.assertIn("Dirección Asistida TRW (44)", modulos_coding)
        self.assertIn("Motor 1.9 TDI (01)", modulos_coding)
        self.assertIn("Climatización (08)", modulos_coding)
        self.assertNotIn("Gateway CAN (19)", modulos_coding)
        self.assertNotIn("Caja de Cambios (02)", modulos_coding)
        self.assertNotIn("Freno de Mano EPB (53)", modulos_coding)

        # Catálogo de Confort del Polo: verificar que no haya opciones de Audi A6 (ej: plegado espejos)
        nombres_confort = [item["nombre"] for item, btn in self.win._confort_botones]
        self.assertTrue(any("Auto-Lock" in n for n in nombres_confort))
        self.assertTrue(any("Auto-Unlock" in n for n in nombres_confort))
        self.assertTrue(any("Bocina" in n or "Claxon" in n for n in nombres_confort))
        self.assertFalse(any("espejo" in n.lower() or "retrovisor" in n.lower() for n in nombres_confort),
                         "No deben aparecer opciones de espejos plegables del Audi en el Polo")

    def test_11_aislamiento_actuadores(self):
        """Verifica que el selector de Actuadores muestre únicamente componentes del Polo."""
        self.win.combo_modo.setCurrentIndex(5)
        modulos_actu = [self.win.combo_actu.itemText(i) for i in range(self.win.combo_actu.count())]
        self.assertIn("Confort / BCM (46)", modulos_actu)
        self.assertIn("Central Eléctrica / Luces (09)", modulos_actu)
        self.assertIn("Motor (01)", modulos_actu)
        self.assertIn("Cuadro de Instrumentos (17)", modulos_actu)
        self.assertIn("ABS / Frenos (03)", modulos_actu)
        self.assertIn("Climatización (08)", modulos_actu)
        self.assertNotIn("Caja de Cambios (02)", modulos_actu)
        self.assertNotIn("Freno de Mano EPB (53)", modulos_actu)

        # Seleccionar ABS / Frenos y verificar actuadores del bloque hidráulico
        self.win.combo_actu.setCurrentText("ABS / Frenos (03)")
        self.app.processEvents()

    def test_12_toggle_confort_polo_y_soft_coding(self):
        """Verifica el accionamiento de los botones de confort de Polo y grabación de Soft Coding."""
        self.win.combo_modo.setCurrentIndex(5)
        self.assertGreater(len(self.win._confort_botones), 0)

        item, btn = self.win._confort_botones[0]
        texto_ini = btn.text()
        self.win._toggle_funcion_confort(item, btn)
        self.assertNotEqual(btn.text(), texto_ini)

        # Escribir coding con 5 dígitos decimales
        self.win.txt_coding_nuevo.setText("00071")
        self.win.escribir_coding()
        self._wait_worker()
        self.assertIn("00071", self.win.txt_coding_actual.text())


if __name__ == "__main__":
    print("=" * 65)
    print("   TEST DE INTEGRACIÓN NATIVA POLO 9N3 K-LINE EN AUDIDIAG PRO")
    print("=" * 65)
    unittest.main()
