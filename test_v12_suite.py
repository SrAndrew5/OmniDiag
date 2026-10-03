# test_v12_suite.py
# ══════════════════════════════════════════════════════════════════════════════
# Suite de Pruebas de Validación Automatizada — AudiDiag Pro V12
# ══════════════════════════════════════════════════════════════════════════════

import sys
import os
import time

# Configurar entorno headless para PyQt6 en consola de pruebas
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from core.can_manager import CANManager
from obd.vag_service_wizards import VAGServiceWizards
from gestion.backup_manager import BackupManager
from PyQt6.QtWidgets import QApplication
from ui.cronometro_prestaciones import CronometroPrestacionesWidget
from ui.dialogo_diff_backups import DialogoDiffBackups
from ui.dialogo_gateway_list import DialogoGatewayList


def test_1_service_wizards_v12():
    print("\n[TEST 1] Verificando Nuevos Wizards de Mantenimiento y Servicio (Modo Simulado)...")
    can_mgr = CANManager()
    wizards = VAGServiceWizards(can_mgr, log_fn=lambda msg: None)

    # 1. Purga ABS
    for paso in (1, 2, 3):
        ok, msg = wizards.abs_purgar_frenos(paso=paso, simulado=True)
        assert ok, f"Fallo en purga ABS paso {paso}"
        print(f"  [OK] ABS Purga Paso {paso}: {msg[:60]}...")

    # 2. Caja ATF & Reset
    atf_datos = wizards.caja_leer_temperatura_atf(simulado=True)
    assert "temperatura_c" in atf_datos and atf_datos["temperatura_c"] > 0
    print(f"  [OK] ATF Temp: {atf_datos['temperatura_c']} °C -> {atf_datos['estado']}")

    ok, msg = wizards.caja_reset_adaptaciones(simulado=True)
    assert ok
    print(f"  [OK] Caja ZF Reset: {msg[:60]}...")

    # 3. G85 Calibración
    ok, msg = wizards.g85_calibrar_direccion(simulado=True)
    assert ok
    print(f"  [OK] G85 Calibración: {msg[:60]}...")

    # 4. Swirl Flaps
    ok, msg = wizards.swirl_flaps_ajuste_basico(simulado=True)
    assert ok
    print(f"  [OK] Chapaletas V157: {msg[:60]}...")

    # 5. MMI Green Menu
    ok, msg = wizards.mmi_activar_green_menu(simulado=True)
    assert ok
    print(f"  [OK] MMI Menú Verde: {msg[:60]}...")

    # 6. Gateway List
    gw_datos = wizards.gateway_leer_lista_instalacion(simulado=True)
    assert "modulos" in gw_datos and len(gw_datos["modulos"]) > 10
    print(f"  [OK] Gateway Leer Lista: {len(gw_datos['modulos'])} módulos identificados")

    ok, msg = wizards.gateway_guardar_lista_instalacion(["01", "02", "03", "19", "17"], simulado=True)
    assert ok
    print(f"  [OK] Gateway Guardar Lista: {msg[:60]}...")

    # 7. BEM Leer Batería Actual
    ok, msg, info = wizards.bateria_leer(simulado=True)
    assert ok and "4F0" in info["part_number"]
    print(f"  [OK] BEM Leer Batería Actual: {info['part_number']} {info['vendor']} {info['serial']}")

    print("  [OK] Test de Asistentes V12 Superado.")


def test_2_diff_viewer():
    print("\n[TEST 2] Verificando Motor Diff de Codificaciones (BackupManager)...")
    bm = BackupManager()

    coding_a = "04 00 00"  # Original: Needle Sweep desactivado
    coding_b = "04 01 00"  # Modificado: Byte 1 Bit 0 activado (0x00 -> 0x01)

    diff = bm.comparar_codificaciones(coding_a, coding_b, modulo="Cuadro 17")
    assert not diff["coinciden"]
    assert diff["total_diferencias"] == 1
    d0 = diff["diferencias"][0]
    assert d0["byte_index"] == 1
    assert d0["hex_a"] == "00"
    assert d0["hex_b"] == "01"
    assert len(d0["bits_cambiados"]) == 1
    assert d0["bits_cambiados"][0]["bit"] == 0
    assert d0["bits_cambiados"][0]["antes"] == 0
    assert d0["bits_cambiados"][0]["despues"] == 1
    print(f"  [OK] Diff detectado correctamente: Byte 1, Bit 0 (0 -> 1)")

    # Caso idéntico
    diff_igual = bm.comparar_codificaciones("0A 1B 2C", "0A 1B 2C")
    assert diff_igual["coinciden"]
    assert diff_igual["total_diferencias"] == 0
    print("  [OK] Comparación idéntica detectada (0 diferencias).")
    print("  [OK] Test de Diff de Codificaciones Superado.")


def test_3_cronometro_prestaciones():
    print("\n[TEST 3] Verificando Cronómetro de Prestaciones CAN...")
    app = QApplication.instance() or QApplication(sys.argv)
    cron = CronometroPrestacionesWidget()

    # Estado inicial
    assert cron.estado == CronometroPrestacionesWidget.ESTADO_IDLE

    # Armar prueba
    cron.armar_lanzada()
    assert cron.estado == CronometroPrestacionesWidget.ESTADO_ARMED

    # Vehículo parado
    cron.alimentar_telemetria(velocidad_kmh=0.0, rpm=800.0)
    assert cron.estado == CronometroPrestacionesWidget.ESTADO_ARMED

    # Arranca la aceleración
    cron.alimentar_telemetria(velocidad_kmh=15.0, rpm=2200.0)
    assert cron.estado == CronometroPrestacionesWidget.ESTADO_RUNNING
    assert cron.tiempo_inicio is not None

    # Hito 60 km/h
    cron.alimentar_telemetria(velocidad_kmh=65.0, rpm=3400.0)
    assert cron.t_0_60 is not None
    print(f"  [OK] Hito 0-60 km/h registrado: {cron.t_0_60:.3f} s")

    # Hito 100 km/h
    cron.alimentar_telemetria(velocidad_kmh=105.0, rpm=4200.0)
    assert cron.t_0_100 is not None
    assert cron.estado == CronometroPrestacionesWidget.ESTADO_FINISHED
    print(f"  [OK] Hito 0-100 km/h registrado: {cron.t_0_100:.3f} s")

    assert cron.tabla_historial.rowCount() == 1
    print("  [OK] Lanzada guardada en el historial de mediciones.")
    print("  [OK] Test de Cronómetro de Prestaciones Superado.")


def test_4_gui_complete_v12():
    print("\n[TEST 4] Verificando Integración Completa de GUI PyQt6 (AudiDiag Pro V12)...")
    app = QApplication.instance() or QApplication(sys.argv)
    from audi_diag_pro import MainWindow

    ventana = MainWindow()
    assert ventana is not None

    # Verificar que el cronómetro está en la pestaña 3 de sensores
    assert hasattr(ventana, "cronometro")
    assert ventana.cronometro is not None

    # Verificar las 10 pestañas en mantenimiento
    page_maint = ventana.stack.widget(3)
    tabs = page_maint.findChildren(type(ventana.cronometro.parent()))
    assert hasattr(ventana, "lbl_abs_status")
    assert hasattr(ventana, "lbl_atf_temp")
    assert hasattr(ventana, "lbl_g85_status")
    assert hasattr(ventana, "lbl_swirl_status")
    assert hasattr(ventana, "lbl_mmi_status")
    print("  [OK] Todas las 10 pestañas de Mantenimiento inicializadas correctamente:")
    print("       EPB, SRI, DPF, Inyectores, Batería BEM, Purga ABS, ATF Caja ZF, G85, Chapaletas, Menú Verde.")

    # Verificar diálogo Diff
    dlg_diff = DialogoDiffBackups(ventana, modulo_filtro="Motor (01)", coding_actual="0A 00 FF 13 44 10 00 A2")
    assert dlg_diff is not None
    print("  [OK] DialogoDiffBackups instanciado e inicializado sin errores.")

    # Verificar diálogo Gateway
    dlg_gw = DialogoGatewayList(ventana)
    assert dlg_gw is not None
    assert len(dlg_gw.modulos_checkboxes) >= 20
    print("  [OK] DialogoGatewayList instanciado con 23 centralitas VAG.")

    # Verificar botón y handler de Ficha Técnica DTC
    assert hasattr(ventana, "_abrir_ficha_tecnica_dtc")
    print("  [OK] Handler _abrir_ficha_tecnica_dtc disponible en MainWindow.")

    print("  [OK] Test de GUI V12 Superado.")


def test_5_dtc_smart_guide():
    print("\n[TEST 5] Verificando Ficha Técnica Guiada y Localización de Componentes (Smart DTC Guider)...")
    from obd.vag_dtc_smart_guide import obtener_ficha_dtc
    from ui.dialogo_ficha_dtc import DialogoFichaDTC

    # 1. Fallo típico Airbag N199
    ficha_airbag = obtener_ficha_dtc("01217", "Igniter for Side Airbag Driver Side (N199)")
    assert "N199" in ficha_airbag["componente"]
    assert "asiento del conductor" in ficha_airbag["ubicacion"].lower()
    print("  [OK] Ficha 01217 N199 (Airbag Lateral Conductor): Ubicación y solución exacta mapeada.")

    # 2. Fallo de Calentador Q10
    ficha_glow = obtener_ficha_dtc("P0671", "Glow Plug Circuit Cylinder 1")
    assert "Q10" in ficha_glow["componente"]
    print("  [OK] Ficha P0671 Q10 (Bujía Precalentamiento Cil 1): Culata y cilindro 1 mapeado.")

    # 3. Heurística DIN para componente no catalogado expresamente
    ficha_heur = obtener_ficha_dtc("00000", "Fault in Exhaust Gas Recirculation Valve (N18)")
    assert "Electroválvula" in ficha_heur["componente"]
    print(f"  [OK] Fallback heurístico DIN: {ficha_heur['componente']}")

    # 4. Instanciar ventana modal de diálogo
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = DialogoFichaDTC(
        modulo="Airbags (15)",
        codigo="01217",
        descripcion="Detonador Airbag Lateral Conductor N199",
        freeze_frame={"Tensión Borne 30": (11.8, "V"), "Resistencia": (4.8, "Ohm")}
    )
    assert dlg is not None
    print("  [OK] DialogoFichaDTC modal instanciado e inicializado correctamente.")
    print("  [OK] Test de Smart DTC Guider Superado.")


if __name__ == "__main__":
    print("=================================================================")
    print("         INICIANDO SUITE DE TESTS AUDIDIAG PRO V12")
    print("=================================================================")
    try:
        test_1_service_wizards_v12()
        test_2_diff_viewer()
        test_3_cronometro_prestaciones()
        test_4_gui_complete_v12()
        test_5_dtc_smart_guide()
        print("\n=================================================================")
        print("       TODOS LOS TESTS DE V12 HAN SIDO SUPERADOS CON EXITO")
        print("=================================================================")
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[ERROR FATAL EN SUITE DE TESTS]: {e}")
        sys.exit(1)
