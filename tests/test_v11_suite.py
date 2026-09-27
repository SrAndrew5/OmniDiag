# test_v11_suite.py
# ══════════════════════════════════════════════════════════════════════════════
# Suite de Verificación Integral de AudiDiag Pro V11
# ══════════════════════════════════════════════════════════════════════════════

import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # Para probar interfaz sin pantalla activa

def test_dtc_database():
    print("\n[TEST 1] Verificando Base de Datos DTC Masiva...")
    from gestion.database_manager import DatabaseManager
    import sqlite3
    import config

    db = DatabaseManager()
    with sqlite3.connect(config.DATABASE_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM diccionario_dtc").fetchone()[0]
    print(f"  * Total codigos en catalogo: {total:,}")
    assert total >= 10000, f"Error: Se esperaban más de 10.000 códigos, pero hay {total}"

    muestras = ["P0672", "P0401", "P0299", "P2015", "01496", "00283", "01314", "U0100", "02096"]
    for cod in muestras:
        desc = db.buscar_descripcion(cod)
        assert "sin descripción" not in desc.lower(), f"Error: Código {cod} no tiene descripción: {desc}"
        print(f"  [OK] {cod:6s} -> {desc[:65]}...")
    print("  [OK] Test de Base de Datos DTC Superado.")


def test_service_wizards():
    print("\n[TEST 2] Verificando Wizards de Mantenimiento (Modo Simulado)...")
    from core.can_manager import CANManager
    from obd.vag_service_wizards import VAGServiceWizards

    can_mgr = CANManager()
    wizards = VAGServiceWizards(can_mgr)

    # 1. EPB
    ok, msg = wizards.epb_abrir_pinzas(simulado=True)
    assert ok, f"Fallo EPB abrir: {msg}"
    print(f"  [OK] EPB Abrir: {msg[:60]}...")

    ok, msg = wizards.epb_cerrar_pinzas(simulado=True)
    assert ok, f"Fallo EPB cerrar: {msg}"
    print(f"  [OK] EPB Cerrar: {msg[:60]}...")

    ok, msg = wizards.epb_test_funcional(simulado=True)
    assert ok, f"Fallo EPB test: {msg}"
    print(f"  [OK] EPB Test: {msg[:60]}...")

    # 2. SRI
    ok, msg = wizards.sri_reset_aceite(simulado=True)
    assert ok, f"Fallo SRI aceite: {msg}"
    print(f"  [OK] SRI Aceite: {msg[:60]}...")

    ok, msg = wizards.sri_reset_completo(es_longlife=True, simulado=True)
    assert ok, f"Fallo SRI LongLife: {msg}"
    print(f"  [OK] SRI LongLife: {msg[:60]}...")

    # 3. DPF
    datos_dpf = wizards.dpf_leer_estado(simulado=True)
    assert "error" not in datos_dpf and datos_dpf["hollin_calc_g"] > 0
    print(f"  [OK] DPF Telemetría: Hollín={datos_dpf['hollin_calc_g']}g, Cenizas={datos_dpf['ceniza_g']}g")

    ok, msg = wizards.dpf_forzar_regeneracion(simulado=True)
    assert ok, f"Fallo DPF regeneración: {msg}"
    print(f"  [OK] DPF Regeneración: {msg[:60]}...")

    # 4. Inyectores
    datos_inj = wizards.inyectores_leer_calibracion(simulado=True)
    assert "cilindros" in datos_inj and len(datos_inj["cilindros"]) == 6
    print(f"  [OK] Inyectores V6 TDI: 6 cilindros comprobados correctamente.")

    # 5. Batería BEM
    ok, msg = wizards.bateria_codificar("95", "VARTA", "1111111111", simulado=True)
    assert ok, f"Fallo BEM batería: {msg}"
    print(f"  [OK] BEM Batería: {msg[:60]}...")

    print("  [OK] Test de Wizards de Servicio Superado.")


def test_html_report_generator():
    print("\n[TEST 3] Verificando Generador de Informes HTML...")
    from gestion.report_generator import ReportGenerator

    rg = ReportGenerator()
    ruta = rg.generar_reporte_html(1)
    assert os.path.exists(ruta), f"No se generó el archivo HTML en {ruta}"
    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read()
    assert "AUDIDIAG" in contenido and "INFORME OFICIAL" in contenido
    print(f"  [OK] Informe HTML generado con éxito en: {ruta} ({len(contenido):,} bytes)")
    print("  [OK] Test de Informe HTML Superado.")


def test_gui_instantiation():
    print("\n[TEST 4] Verificando Instanciación de Interfaz Gráfica PyQt6...")
    from PyQt6.QtWidgets import QApplication
    from audi_diag_pro import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()

    assert win.stack.count() == 9, f"Se esperaban 9 páginas en el stack, hay {win.stack.count()}"
    assert len(win.btn_nav) == 9, f"Se esperaban 9 botones en la navegación, hay {len(win.btn_nav)}"

    # Verificar que el osciloscopio existe y recibe datos
    assert hasattr(win, "osciloscopio"), "Falta el osciloscopio en MainWindow"
    win.recibir_sensores([
        ("Régimen motor (RPM)", 2100.0, "RPM", 5000),
        ("Presión sobrealimentación", 1450.0, "mbar", 2500),
        ("Presión Common Rail", 850.0, "bar", 1800),
        ("Temperatura refrigerante", 89.0, "°C", 120),
    ])
    assert win.osciloscopio.ultimos_valores["RPM"] == 2100.0
    print("  [OK] Osciloscopio vectorial inicializado y alimentado con telemetría en tiempo real.")

    # Verificar tabla DTC con 5 columnas
    assert win.tabla_dtc.columnCount() == 5, f"Esperadas 5 columnas en tabla DTC, hay {win.tabla_dtc.columnCount()}"
    win.agregar_fallos_modulo("Motor (01)", [("P0672", "Bujía 2 defectuosa", {})])
    assert win.tabla_dtc.rowCount() >= 1
    assert "Crítica" in win.tabla_dtc.item(0, 3).text() or "Taller" in win.tabla_dtc.item(0, 3).text()
    print("  [OK] Tabla DTC con badge de Prioridad y Estado verificado.")

    print("  [OK] Test de Interfaz Gráfica Superado.")


if __name__ == "__main__":
    print("=" * 65)
    print("         INICIANDO SUITE DE TESTS AUDIDIAG PRO V11")
    print("=" * 65)
    test_dtc_database()
    test_service_wizards()
    test_html_report_generator()
    test_gui_instantiation()
    print("\n" + "=" * 65)
    print("       TODOS LOS TESTS DE V11 HAN SIDO SUPERADOS CON EXITO")
    print("=" * 65)
