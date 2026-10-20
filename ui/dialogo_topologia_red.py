# ui/dialogo_topologia_red.py
# ══════════════════════════════════════════════════════════════════════════════
# TOPOLOGÍA Y REVISIÓN DE CONEXIÓN DE TODAS LAS CENTRALITAS EN RED CAN
# Diagnóstico de pasarela Gateway J533, estado de conexión TP 2.0,
# identificación de hardware VAG y extracción automática de Long Coding.
# ══════════════════════════════════════════════════════════════════════════════

import json
import time
from datetime import datetime
from typing import Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QFrame, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from obd.tp20_can import TP20Transport, KWP2000NativeClient


# Catálogo completo de centralitas para Audi A6 C6 (4F) y plataforma VAG
CATALOGO_RED_AUDI_A6 = [
    {"addr": 0x01, "dec": "01", "nombre": "Motor (ECU / ECM)", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x02, "dec": "02", "nombre": "Transmisión / Cambio (TCU)", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x03, "dec": "03", "nombre": "Frenos ABS / ESP 8.0", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x05, "dec": "05", "nombre": "Acceso y Arranque Kessy (J518)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x06, "dec": "55", "nombre": "Regulación Faros Xenón (LWR)", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x07, "dec": "17", "nombre": "Cuadro de Instrumentos J285 (Facelift)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x08, "dec": "08", "nombre": "Climatizador Climatronic", "bus": "Confort", "en_gateway": True},
    {"addr": 0x09, "dec": "09", "nombre": "Central Eléctrica / Luces (J519)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x15, "dec": "15", "nombre": "Airbag (SRS)", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x16, "dec": "16", "nombre": "Columna Dirección (J527)", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x17, "dec": "17", "nombre": "Cuadro Instrumentos (Dirección Estándar)", "bus": "Confort", "en_gateway": False},
    {"addr": 0x19, "dec": "19", "nombre": "Pasarela Gateway CAN (J533)", "bus": "Sistema", "en_gateway": True},
    {"addr": 0x1F, "dec": "61", "nombre": "Gestión de Batería BEM (J644)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x20, "dec": "09", "nombre": "Red de a Bordo Conductor (ILM Fahrer)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x21, "dec": "46", "nombre": "Central Confort BCM (J393)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x22, "dec": "42", "nombre": "Puerta Conductor (J386)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x23, "dec": "52", "nombre": "Puerta Copiloto (J387)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x24, "dec": "62", "nombre": "Puerta Trasera Izquierda (J388)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x25, "dec": "72", "nombre": "Puerta Trasera Derecha (J389)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x28, "dec": "29", "nombre": "Red de a Bordo Pasajero (ILM Beifahrer)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x2A, "dec": "16", "nombre": "Electrónica Columna Volante", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x2C, "dec": "08", "nombre": "Climatizador Digital (J255)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x2D, "dec": "76", "nombre": "Aparcamiento Parktronic (J446)", "bus": "Confort", "en_gateway": True},
    {"addr": 0x31, "dec": "05", "nombre": "Bloqueo Columna ELV / FBSAUDIC6", "bus": "Confort", "en_gateway": True},
    {"addr": 0x34, "dec": "34", "nombre": "Suspensión Neumática (AAS)", "bus": "Tren Motriz", "en_gateway": False},
    {"addr": 0x47, "dec": "47", "nombre": "Sistema de Sonido (DSP / BOSE)", "bus": "Infotainment", "en_gateway": False},
    {"addr": 0x4D, "dec": "4D", "nombre": "Módulo Techo / Alarma Habitáculo", "bus": "Confort", "en_gateway": True},
    {"addr": 0x53, "dec": "53", "nombre": "Freno de Mano Eléctrico EPB (J540)", "bus": "Tren Motriz", "en_gateway": True},
    {"addr": 0x55, "dec": "55", "nombre": "Regulación Faros Dinámicos", "bus": "Tren Motriz", "en_gateway": False},
    {"addr": 0x5F, "dec": "5F", "nombre": "MMI 3G Electrónica Información", "bus": "Infotainment", "en_gateway": True},
    {"addr": 0x76, "dec": "76", "nombre": "Ayuda Aparcamiento PDC", "bus": "Confort", "en_gateway": False},
    {"addr": 0x77, "dec": "77", "nombre": "Teléfono / Interfaz Bluetooth", "bus": "Infotainment", "en_gateway": False},
]

# Datos de simulación para banco/pruebas sin coche
SIMULACION_A6_C6 = {
    0x01: {"ref": "4F7910401L", "comp": "2.7L V6 TDI EDC17", "coding": "01 05 00 2C 19 0F 01 20"},
    0x02: {"ref": "4F5910156M", "comp": "V30 09L 2.7 TDI RdW", "coding": "00 00 01"},
    0x03: {"ref": "4F0910517AL", "comp": "ESP8 quattro H04 0240", "coding": "00 04 40 1"},
    0x06: {"ref": "8P0907357H", "comp": "Dynamische LWR H02 0010", "coding": "00 00 01"},
    0x07: {"ref": "4F0920933Q", "comp": "KOMBIINSTR. H06 0520", "coding": "0F 5F 0A 05 02 00 00 08 05 01 00"},
    0x19: {"ref": "4F0907468M", "comp": "GW-BEM 4CAN-M H09 0035", "coding": "00 03 03"},
    0x1F: {"ref": "4F0907468M", "comp": "GW-BEM 4CAN-M (BEM)", "coding": "00 00 00"},
    0x20: {"ref": "4F0910279N", "comp": "ILM Fahrer H14 0280", "coding": "00 00 01"},
    0x21: {"ref": "4F0910289N", "comp": "Komfortgeraet H29 0250", "coding": "06 00 F1"},
    0x22: {"ref": "4F0959793R", "comp": "TSG FA H12 0210", "coding": "01 1C 02 20 50 40 41 00 01"},
    0x23: {"ref": "4F0959792R", "comp": "TSG BF H12 0210", "coding": "01 1C 02 20 50 40 41 00 01"},
    0x24: {"ref": "4F0959795N", "comp": "TSG HL H10 0210", "coding": "00 00 00"},
    0x25: {"ref": "4F0959795N", "comp": "TSG HR H10 0210", "coding": "00 00 00"},
    0x28: {"ref": "4F0910280", "comp": "ILM Beifahrer H12 0210", "coding": "00 00 00"},
    0x2A: {"ref": "4F0910549A", "comp": "Lenksaeulenmodul H07 0040", "coding": "00 07 F9"},
    0x2C: {"ref": "4F0910043B", "comp": "KLIMABETAETIGUNG H03 0020", "coding": "00 00 00"},
    0x2D: {"ref": "4L0910283B", "comp": "Parkhilfe 4-Kanal H02 0040", "coding": "00 01 01"},
    0x31: {"ref": "4F0910852B", "comp": "FBSAUDIC6 ELV H24 0170", "coding": "00 00 00"},
    0x53: {"ref": "4F0910801D", "comp": "aEPB  C0040", "coding": "00 00 03 1"},
}


class ScannerRedWorker(QThread):
    """
    Hilo de escaneo rápido de la topología CAN en segundo plano.
    No bloquea la interfaz de usuario y emite progreso en tiempo real.
    """
    progreso_signal = pyqtSignal(int, int, str)       # actual, total, mensaje
    modulo_detectado = pyqtSignal(dict)              # resultado de una centralita
    finalizado_signal = pyqtSignal(list)             # lista completa al terminar
    error_signal = pyqtSignal(str)

    def __init__(self, can_mgr):
        super().__init__()
        self.can_mgr = can_mgr
        self._cancelar = False

    def cancelar(self):
        self._cancelar = True

    def run(self):
        resultados = []
        total = len(CATALOGO_RED_AUDI_A6)

        # Determinar si hay bus CAN real conectado
        es_real = bool(self.can_mgr and getattr(self.can_mgr, "is_connected", False))

        tp20 = None
        kwp = None
        if es_real:
            tp20 = TP20Transport(self.can_mgr, timeout=0.8, debug=False)
            kwp = KWP2000NativeClient(tp20)

        for idx, mod in enumerate(CATALOGO_RED_AUDI_A6, 1):
            if self._cancelar:
                break

            addr = mod["addr"]
            nom = mod["nombre"]
            self.progreso_signal.emit(idx, total, f"Sondeando 0x{addr:02X} — {nom}...")

            item_res = {
                "addr_hex": f"0x{addr:02X}",
                "addr_dec": mod["dec"],
                "nombre": nom,
                "bus": mod["bus"],
                "en_gateway": mod["en_gateway"],
                "online": False,
                "canal": "-",
                "ref_vag": "-",
                "componente": "-",
                "coding": "-",
                "sw_version": ""
            }

            if es_real:
                try:
                    # Intento de apertura de canal rápido (setup_timeout 0.4s)
                    if tp20.open_channel(addr, attempts=2, setup_timeout=0.4):
                        item_res["online"] = True
                        item_res["canal"] = f"TX 0x{tp20.tx_addr:03X} / RX 0x{tp20.rx_addr:03X}"

                        # Lectura de identificación oficial
                        try:
                            ident = kwp.read_ecu_identification()
                            item_res["ref_vag"] = ident.get("part_number", "-").strip() or "-"
                            item_res["componente"] = ident.get("component", "-").strip() or "-"
                            item_res["sw_version"] = ident.get("sw_version", "").strip()
                            raw_coding = ident.get("coding", b"")
                            if raw_coding:
                                item_res["coding"] = " ".join(f"{b:02X}" for b in raw_coding)
                        except Exception:
                            pass

                        # Si no obtuvo codificación por 0x1A, probar UDS DID 0x0600
                        if item_res["coding"] == "-":
                            try:
                                resp_uds = kwp.execute_service(0x22, data=b"\x06\x00")
                                if resp_uds and len(resp_uds) >= 3:
                                    item_res["coding"] = " ".join(f"{b:02X}" for b in resp_uds[2:])
                            except Exception:
                                pass

                        tp20.close_channel()
                        time.sleep(0.02)
                except Exception:
                    try:
                        tp20.close_channel()
                    except Exception:
                        pass
            else:
                # Simulación realista basada en el Audi A6 C6
                time.sleep(0.04)
                if addr in SIMULACION_A6_C6:
                    sim = SIMULACION_A6_C6[addr]
                    item_res["online"] = True
                    item_res["canal"] = f"TX 0x{0x700 + addr:03X} / RX 0x300"
                    item_res["ref_vag"] = sim["ref"]
                    item_res["componente"] = sim["comp"]
                    item_res["coding"] = sim["coding"]

            resultados.append(item_res)
            self.modulo_detectado.emit(item_res)

        if tp20:
            try:
                tp20.close_channel()
            except Exception:
                pass

        self.finalizado_signal.emit(resultados)


class DialogoTopologiaRed(QDialog):
    """
    Ventana interactiva de Revisión de Conexión y Topología de Red CAN.
    Muestra qué módulos están dados de alta, si comunican, su referencia oficial y Long Coding.
    """
    def __init__(self, parent=None, can_mgr=None):
        super().__init__(parent)
        self.can_mgr = can_mgr
        self.worker = None
        self.resultados_scan = []

        self.setWindowTitle("AudiDiag Pro — Topología y Estado de Conexión de Red CAN")
        self.resize(1100, 680)
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0D13;
                color: #F8FAFC;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #CBD5E1;
            }
            QTableWidget {
                background-color: #11141C;
                border: 1px solid #1E2330;
                gridline-color: #1E2330;
                color: #F8FAFC;
                selection-background-color: #E0001B;
                selection-color: #FFFFFF;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #171A24;
                color: #94A3B8;
                font-weight: 800;
                font-size: 11px;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #282E3E;
            }
            QPushButton {
                background-color: #171A24;
                border: 1px solid #282E3E;
                border-radius: 6px;
                padding: 8px 16px;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #242A3A;
                border-color: #3D465E;
            }
            QPushButton[class="btn-accion"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E0001B, stop:1 #B00015);
                border: none;
                color: #FFFFFF;
            }
            QPushButton[class="btn-accion"]:hover {
                background: #FF0026;
            }
            QProgressBar {
                background-color: #171A24;
                border: 1px solid #282E3E;
                border-radius: 4px;
                height: 12px;
                text-align: center;
                color: transparent;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E0001B, stop:1 #FF0026);
                border-radius: 3px;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(20, 20, 20, 20)
        lyt.setSpacing(14)

        # ── Encabezado ──
        f_head = QFrame()
        f_head.setStyleSheet("background-color: #11141C; border: 1px solid #1E2330; border-radius: 8px; padding: 12px;")
        h_lyt = QVBoxLayout(f_head)
        h_lyt.setContentsMargins(10, 8, 10, 8)
        h_lyt.setSpacing(4)

        lbl_tit = QLabel("🌐  TOPOLOGÍA Y REVISIÓN DE CONEXIÓN DE RED CAN (TODOS LOS MÓDULOS)")
        lbl_tit.setStyleSheet("font-size: 15px; font-weight: 900; color: #FFFFFF; letter-spacing: 0.5px;")
        h_lyt.addWidget(lbl_tit)

        lbl_sub = QLabel(
            "Verifica la presencia de cada centralita en la lista de instalación del Gateway J533, "
            "comprueba la conexión TP 2.0 en tiempo real y extrae la Referencia Oficial, Componente y Long Coding."
        )
        lbl_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        lbl_sub.setWordWrap(True)
        h_lyt.addWidget(lbl_sub)
        lyt.addWidget(f_head)

        # ── Tarjeta de Resumen Estadístico ──
        f_stats = QHBoxLayout()
        f_stats.setSpacing(14)

        self.card_online = self._crear_stat_card("ONLINE / CONECTADOS", "—", "#10B981")
        self.card_offline = self._crear_stat_card("OFFLINE / NO EQUIPADOS", "—", "#94A3B8")
        self.card_gateway = self._crear_stat_card("EN LISTA GATEWAY", "—", "#00E5FF")
        self.card_coding = self._crear_stat_card("CON LONG CODING", "—", "#F59E0B")

        f_stats.addWidget(self.card_online)
        f_stats.addWidget(self.card_offline)
        f_stats.addWidget(self.card_gateway)
        f_stats.addWidget(self.card_coding)
        lyt.addLayout(f_stats)

        # ── Barra de Progreso y Estado ──
        f_prog = QVBoxLayout()
        f_prog.setSpacing(4)
        self.lbl_estado_progreso = QLabel("Pulsa 'Iniciar Escaneo de Red' para verificar las 32 centralitas.")
        self.lbl_estado_progreso.setStyleSheet("color: #CBD5E1; font-size: 12px; font-weight: 600;")
        f_prog.addWidget(self.lbl_estado_progreso)

        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        f_prog.addWidget(self.pbar)
        lyt.addLayout(f_prog)

        # ── Tabla de Resultados ──
        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels([
            "Dir (Hex/Dec)", "Módulo / Sistema", "En Gateway", "Conexión TP 2.0",
            "Referencia VAG", "Componente", "Long Coding"
        ])
        header = self.tabla.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._al_hacer_doble_clic)
        lyt.addWidget(self.tabla, stretch=1)

        # ── Barra Inferior de Acciones ──
        f_pie = QHBoxLayout()
        f_pie.setSpacing(12)

        self.btn_iniciar = QPushButton("⚡  Iniciar Escaneo Rápido de Red")
        self.btn_iniciar.setProperty("class", "btn-accion")
        self.btn_iniciar.setFixedHeight(42)
        self.btn_iniciar.clicked.connect(self.iniciar_escaneo)
        f_pie.addWidget(self.btn_iniciar)

        self.btn_copiar = QPushButton("📋  Copiar Reporte")
        self.btn_copiar.setFixedHeight(42)
        self.btn_copiar.clicked.connect(self._copiar_reporte)
        f_pie.addWidget(self.btn_copiar)

        self.btn_exportar = QPushButton("💾  Exportar JSON")
        self.btn_exportar.setFixedHeight(42)
        self.btn_exportar.clicked.connect(self._exportar_json)
        f_pie.addWidget(self.btn_exportar)

        f_pie.addStretch()

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setFixedHeight(42)
        btn_cerrar.clicked.connect(self.accept)
        f_pie.addWidget(btn_cerrar)

        lyt.addLayout(f_pie)

    def _crear_stat_card(self, titulo: str, valor: str, color_valor: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("background-color: #11141C; border: 1px solid #1E2330; border-radius: 8px;")
        card.setFixedHeight(64)
        c_lyt = QVBoxLayout(card)
        c_lyt.setContentsMargins(14, 8, 14, 8)
        c_lyt.setSpacing(2)

        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet("font-size: 10px; font-weight: 800; color: #94A3B8; letter-spacing: 0.8px;")
        c_lyt.addWidget(lbl_t)

        lbl_v = QLabel(valor)
        lbl_v.setObjectName(f"val_{titulo}")
        lbl_v.setStyleSheet(f"font-size: 20px; font-weight: 900; color: {color_valor}; font-family: Consolas;")
        c_lyt.addWidget(lbl_v)
        return card

    def _set_stat_val(self, card: QFrame, valor: str):
        lbl = card.findChild(QLabel, "")
        for child in card.findChildren(QLabel):
            if child.text() != "ONLINE / CONECTADOS" and child.text() != "OFFLINE / NO EQUIPADOS" and child.text() != "EN LISTA GATEWAY" and child.text() != "CON LONG CODING":
                child.setText(valor)
                break

    def iniciar_escaneo(self):
        """Inicia el barrido en segundo plano."""
        if self.worker and self.worker.isRunning():
            return

        self.tabla.setRowCount(0)
        self.resultados_scan.clear()
        self.pbar.setValue(0)
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setText("⏳  Escaneando Red CAN...")

        self.worker = ScannerRedWorker(self.can_mgr)
        self.worker.progreso_signal.connect(self._actualizar_progreso)
        self.worker.modulo_detectado.connect(self._agregar_fila)
        self.worker.finalizado_signal.connect(self._finalizar_escaneo)
        self.worker.start()

    def _actualizar_progreso(self, actual: int, total: int, mensaje: str):
        pct = int((actual / total) * 100)
        self.pbar.setValue(pct)
        self.lbl_estado_progreso.setText(f"[{actual}/{total}]  {mensaje}")

    def _agregar_fila(self, item: dict):
        self.resultados_scan.append(item)
        row = self.tabla.rowCount()
        self.tabla.insertRow(row)

        # 0: Dir
        it_dir = QTableWidgetItem(f"{item['addr_hex']} ({item['addr_dec']})")
        it_dir.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.tabla.setItem(row, 0, it_dir)

        # 1: Nombre
        it_nom = QTableWidgetItem(item["nombre"])
        it_nom.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold if item["online"] else QFont.Weight.Normal))
        if not item["online"]:
            it_nom.setForeground(QColor("#64748B"))
        self.tabla.setItem(row, 1, it_nom)

        # 2: En Gateway
        en_gw = "🟢 Sí" if item["en_gateway"] else "⚪ No"
        it_gw = QTableWidgetItem(en_gw)
        it_gw.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabla.setItem(row, 2, it_gw)

        # 3: Conexión
        if item["online"]:
            it_con = QTableWidgetItem(f"🟢 ONLINE  ({item['canal']})")
            it_con.setForeground(QColor("#10B981"))
        else:
            it_con = QTableWidgetItem("🔴 Sin Respuesta")
            it_con.setForeground(QColor("#EF4444"))
        self.tabla.setItem(row, 3, it_con)

        # 4: Referencia VAG
        it_ref = QTableWidgetItem(item["ref_vag"])
        it_ref.setFont(QFont("Consolas", 10))
        if item["ref_vag"] != "-":
            it_ref.setForeground(QColor("#00E5FF"))
        self.tabla.setItem(row, 4, it_ref)

        # 5: Componente
        it_comp = QTableWidgetItem(item["componente"])
        self.tabla.setItem(row, 5, it_comp)

        # 6: Long Coding
        it_cod = QTableWidgetItem(item["coding"])
        it_cod.setFont(QFont("Consolas", 10))
        if item["coding"] != "-":
            it_cod.setForeground(QColor("#F59E0B"))
        self.tabla.setItem(row, 6, it_cod)

        self._actualizar_estadisticas()

    def _actualizar_estadisticas(self):
        total_online = sum(1 for r in self.resultados_scan if r["online"])
        total_offline = sum(1 for r in self.resultados_scan if not r["online"])
        total_gw = sum(1 for r in self.resultados_scan if r["en_gateway"])
        total_coding = sum(1 for r in self.resultados_scan if r["coding"] != "-")

        self._set_stat_val(self.card_online, str(total_online))
        self._set_stat_val(self.card_offline, str(total_offline))
        self._set_stat_val(self.card_gateway, str(total_gw))
        self._set_stat_val(self.card_coding, str(total_coding))

    def _finalizar_escaneo(self, resultados: list):
        self.pbar.setValue(100)
        online_count = sum(1 for r in resultados if r["online"])
        self.lbl_estado_progreso.setText(
            f"✓ Escaneo finalizado con éxito: {online_count} centralitas ONLINE detectadas en el bus CAN."
        )
        self.btn_iniciar.setEnabled(True)
        self.btn_iniciar.setText("⚡  Repetir Escaneo de Red")
        self._actualizar_estadisticas()

    def _copiar_reporte(self):
        """Copia el reporte en formato Markdown al portapapeles."""
        if not self.resultados_scan:
            QMessageBox.information(self, "Aviso", "Primero realiza un escaneo de la red.")
            return

        lineas = [
            "# INVENTARIO Y TOPOLOGÍA DE RED CAN — AUDI A6 C6 (4F)",
            f"Fecha de escaneo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "| DIR | MÓDULO / SISTEMA | EN GATEWAY | CONEXIÓN TP 2.0 | REFERENCIA VAG | COMPONENTE | LONG CODING |",
            "|---|---|---|---|---|---|---|"
        ]
        for r in self.resultados_scan:
            gw_txt = "SÍ" if r["en_gateway"] else "NO"
            con_txt = "ONLINE" if r["online"] else "OFFLINE"
            lineas.append(
                f"| {r['addr_hex']} ({r['addr_dec']}) | {r['nombre']} | {gw_txt} | {con_txt} | "
                f"{r['ref_vag']} | {r['componente']} | `{r['coding']}` |"
            )

        texto_completo = "\n".join(lineas)
        QApplication.clipboard().setText(texto_completo)
        QMessageBox.information(
            self,
            "Copiado al Portapapeles",
            "Se ha copiado el informe técnico completo de la red CAN en formato Markdown al portapapeles."
        )

    def _exportar_json(self):
        """Guarda los resultados completos en un archivo JSON en datos/."""
        if not self.resultados_scan:
            QMessageBox.information(self, "Aviso", "Primero realiza un escaneo de la red.")
            return

        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        dir_datos = root / "datos"
        dir_datos.mkdir(parents=True, exist_ok=True)
        nombre_arch = dir_datos / f"inventario_red_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(nombre_arch, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "vehiculo": "Audi A6 C6 Facelift (2010)",
                "total_modulos": len(self.resultados_scan),
                "online": sum(1 for r in self.resultados_scan if r["online"]),
                "resultados": self.resultados_scan
            }, f, indent=4)

        QMessageBox.information(
            self,
            "Informe Exportado",
            f"Informe guardado exitosamente en:\n{nombre_arch}"
        )

    def _al_hacer_doble_clic(self, index):
        """Permite ver el detalle o copiar el Long Coding de la centralita pulsada."""
        row = index.row()
        if 0 <= row < len(self.resultados_scan):
            mod = self.resultados_scan[row]
            if mod["coding"] != "-":
                QApplication.clipboard().setText(mod["coding"])
                QMessageBox.information(
                    self,
                    "Long Coding Copiado",
                    f"Centralita: {mod['nombre']} ({mod['addr_hex']})\n\n"
                    f"Codificación: {mod['coding']}\n\n"
                    "¡Copiado al portapapeles para pegarlo en el editor si lo deseas!"
                )
