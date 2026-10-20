import sys
import os
import csv
from datetime import datetime
import config

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QTextEdit, QFrame, QComboBox,
    QLineEdit, QSizePolicy, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QScrollArea, QCheckBox, QDoubleSpinBox,
    QListWidget, QListWidgetItem, QSplitter, QGridLayout, QTabWidget,
    QDialog, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPointF, QRectF, QSize
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QPolygonF

from ui.estilos import ESTILO_PRINCIPAL
from ui.controlador import (
    MotorDiagnostico, ADAPTACIONES_VAG, ACTUADORES_VAG, TP20_MODULE_ADDR,
    ADAPTACIONES_OPEL, ACTUADORES_OPEL, OPEL_MODULES_CONFIG, CATALOGO_CONFORT_OPEL,
    ADAPTACIONES_POLO_KLINE, ACTUADORES_POLO_KLINE, POLO_9N3_CONFORT_CHANNELS,
    CATALOGO_CONFORT_POLO
)
from gestion.report_generator import ReportGenerator
from gestion.database_manager import DatabaseManager
from gestion.backup_manager import BackupManager
from obd.long_coding import LongCodingManager
from obd.vag_a6_features import CATALOGO_CONFORT_A6
from core.diagnostic_logger import diag_logger
from ui.osciloscopio import OsciloscopioWidget
from ui.dialogo_diff_backups import DialogoDiffBackups
from ui.dialogo_gateway_list import DialogoGatewayList
from ui.dialogo_topologia_red import DialogoTopologiaRed
from ui.cronometro_prestaciones import CronometroPrestacionesWidget
from ui.dialogo_ficha_dtc import DialogoFichaDTC
from ui.dialogo_polo_kline import DialogoPoloKLine
import webbrowser



class AudiRingsWidget(QWidget):
    """Widget vectorial con los 4 Anillos Oficiales entrelazados de Audi, centrados con precisión."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setFixedWidth(130)

    def sizeHint(self) -> QSize:
        return QSize(130, 30)

    def minimumSizeHint(self) -> QSize:
        return QSize(130, 30)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = 10.5
        dx = 16.5
        total_span = 3 * dx + 2 * r
        x_start = (self.width() - total_span) / 2.0 + r
        cy = self.height() / 2.0

        pen = QPen(QColor("#E2E8F0"), 2.2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for i in range(4):
            painter.drawEllipse(QPointF(x_start + i * dx, cy), r, r)


class AudiRSBadge(QWidget):
    """Emblema oficial de competición Audi RS: rombo rojo dinámico + tipografía RS plata."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 20)

    def sizeHint(self) -> QSize:
        return QSize(46, 20)

    def minimumSizeHint(self) -> QSize:
        return QSize(46, 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rombo rojo RS inclinado (paralelogramo de competición)
        poly = QPolygonF([
            QPointF(6, 1),
            QPointF(20, 1),
            QPointF(14, 19),
            QPointF(0, 19)
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FF0026"))
        painter.drawPolygon(poly)

        # Texto "RS" en plata / blanco itálica de competición
        painter.setPen(QColor("#FFFFFF"))
        font = painter.font()
        font.setFamily("Arial")
        font.setPointSize(10)
        font.setBold(True)
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(QRectF(16, 0, 30, 20), Qt.AlignmentFlag.AlignCenter, "RS")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudiDiag Pro — Advanced VAG Diagnostics")
        self.setMinimumSize(1024, 650)
        self.showMaximized()
        self.setStyleSheet(ESTILO_PRINCIPAL)

        # Worker (hilo de fondo)
        self.worker = MotorDiagnostico()
        self.worker.log_signal.connect(self.escribir_consola)
        self.worker.status_signal.connect(self.actualizar_estado)
        self.worker.vin_signal.connect(self.recibir_vin)
        self.worker.coding_signal.connect(self.recibir_coding)
        self.worker.module_scanned.connect(self.agregar_fallos_modulo)
        self.worker.scan_done.connect(self.recibir_scan)
        self.worker.sensors_data_signal.connect(self.recibir_sensores)
        self.worker.mil_signal.connect(self.actualizar_mil)
        self.worker.adaptacion_signal.connect(self.recibir_adaptacion)
        self.worker.wizard_data_signal.connect(self._recibir_wizard_datos)
        self.worker.wizard_result_signal.connect(self._recibir_wizard_resultado)

        # Estado
        self._coding_actual_leido = ""
        self._coding_checkboxes   = []   # [[QCheckBox x8], ...]
        self._confort_botones     = []   # [(item_dict, QPushButton), ...]
        self._grabando_csv        = False
        self._csv_file            = None
        self._csv_writer          = None
        self._dtcs_datos          = []   # [(modulo, cod, desc, ff), ...]
        self._adaptaciones_spin   = {}   # {nombre: QDoubleSpinBox}
        self._db                  = DatabaseManager()

        # ── Layout raíz ──
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # ── Fila superior: sidebar + páginas ──
        superior = QHBoxLayout()
        superior.setContentsMargins(0, 0, 0, 0)
        superior.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)
        self._lyt_sb = QVBoxLayout(self.sidebar)
        self._lyt_sb.setContentsMargins(0, 14, 0, 14)
        self._lyt_sb.setSpacing(3)

        # Cabecera de Marca Oficial Audi RS (Sin solapamientos, maquetación vertical limpia)
        header_brand = QFrame()
        header_brand.setObjectName("header_brand")
        header_brand.setFixedHeight(94)
        h_lyt = QVBoxLayout(header_brand)
        h_lyt.setContentsMargins(10, 8, 10, 8)
        h_lyt.setSpacing(4)

        # 1. Anillos Audi oficiales entrelazados
        self.audi_rings = AudiRingsWidget()
        h_lyt.addWidget(self.audi_rings, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 2. AUDIDIAG + Rombo Rojo RS oficial
        fila_logo = QHBoxLayout()
        fila_logo.setSpacing(6)
        fila_logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl_logo = QLabel("AUDIDIAG")
        lbl_logo.setObjectName("lbl_brand_title")
        self.rs_badge = AudiRSBadge()
        fila_logo.addWidget(lbl_logo)
        fila_logo.addWidget(self.rs_badge)
        h_lyt.addLayout(fila_logo)

        # 3. Subtítulo técnico
        lbl_sub = QLabel("PERFORMANCE & DIAGNOSTICS")
        lbl_sub.setObjectName("lbl_brand_sub")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        h_lyt.addWidget(lbl_sub)

        self._lyt_sb.addWidget(header_brand)

        self.btn_nav = []
        nav_items = [
            ("⚡  Conexión",          0),
            ("🔍  Fallos DTC",         1),
            ("📊  Sensores en Vivo",   2),
            ("🛠  Mantenimiento",      3),
            ("🔧  Long Coding",        4),
            ("🔩  Adaptaciones",       5),
            ("▶   Test Actuadores",   6),
            ("📋  Historial",          7),
            ("📄  Informes",           8),
        ]
        for texto, idx in nav_items:
            btn = QPushButton(texto)
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _, i=idx, b=None: None)  # placeholder
            self._lyt_sb.addWidget(btn)
            self.btn_nav.append(btn)

        # Reconectar con índice real
        for i, btn in enumerate(self.btn_nav):
            btn.clicked.connect(lambda _, i=i: self.cambiar_pagina(i))

        self._lyt_sb.addStretch()

        # Caja de estado inferior con punto de luz (Audi RS Pod)
        frame_status = QFrame()
        frame_status.setObjectName("frame_status_box")
        frame_status.setFixedHeight(44)
        fs_lyt = QHBoxLayout(frame_status)
        fs_lyt.setContentsMargins(12, 6, 12, 6)
        fs_lyt.setSpacing(8)

        self.dot_status = QLabel("●")
        self.dot_status.setFixedSize(14, 14)
        self.dot_status.setStyleSheet("color: #FF0026; font-size: 14px; font-weight: bold;")
        fs_lyt.addWidget(self.dot_status)

        self.lbl_status = QLabel("Desconectado")
        self.lbl_status.setObjectName("lbl_status")
        self.lbl_status.setStyleSheet("color: #CBD5E1; font-weight: 800; font-size: 12px;")
        fs_lyt.addWidget(self.lbl_status)
        fs_lyt.addStretch()

        self._lyt_sb.addWidget(frame_status)

        superior.addWidget(self.sidebar)

        # Páginas
        self.stack = QStackedWidget()
        superior.addWidget(self.stack)

        raiz.addLayout(superior, stretch=3)

        # ── Consola fija inferior ──
        self.frame_consola = QFrame()
        self.frame_consola.setObjectName("frame_consola")
        self.frame_consola.setFixedHeight(160)
        lyt_c = QVBoxLayout(self.frame_consola)
        lyt_c.setContentsMargins(6, 3, 6, 4)
        lyt_c.setSpacing(2)

        fila_ct = QHBoxLayout()
        lbl_ct = QLabel("CONSOLA  ›  Log del sistema")
        lbl_ct.setObjectName("lbl_consola_titulo")
        fila_ct.addWidget(lbl_ct)
        fila_ct.addStretch()

        btn_log = QPushButton("📄  Abrir Registro Detallado (.txt)")
        btn_log.setStyleSheet(
            "font-size: 11px; font-weight: 700; padding: 4px 12px; "
            "background-color: #171922; color: #CBD5E1; "
            "border: 1px solid #2E3342; border-radius: 6px;"
        )
        btn_log.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_log.setToolTip("Abre el archivo audidiag_registro_detallado.txt para ver cada byte transmitido y recibido")
        btn_log.clicked.connect(self.abrir_archivo_log)
        fila_ct.addWidget(btn_log)

        lyt_c.addLayout(fila_ct)


        self.consola = QTextEdit()
        self.consola.setReadOnly(True)
        self.consola.append("AudiDiag Pro — Listo. Conecta el adaptador ELM327 y pulsa Iniciar.")
        lyt_c.addWidget(self.consola)

        raiz.addWidget(self.frame_consola, stretch=0)

        # ── Construir páginas ──
        self._crear_pagina_conexion()
        self._crear_pagina_dtc()
        self._crear_pagina_sensores()
        self._crear_pagina_mantenimiento()
        self._crear_pagina_coding()
        self._crear_pagina_adaptaciones()
        self._crear_pagina_actuadores()
        self._crear_pagina_historial()
        self._crear_pagina_informes()

        self.cambiar_pagina(0)

    @property
    def es_modo_opel(self) -> bool:
        return getattr(config, "VEHICLE_MODE", "VAG") in ("OBD2_UNIVERSAL", "OPEL_CONFORT", "OPEL_CORSA")

    @property
    def es_modo_kline(self) -> bool:
        return getattr(config, "VEHICLE_MODE", "VAG") == "VAG_KLINE"

    # ══════════════════════════════════════════════════════════════════════════
    #  NAVEGACIÓN
    # ══════════════════════════════════════════════════════════════════════════
    def cambiar_pagina(self, index: int):
        if self.stack.currentIndex() == index and hasattr(self, "_anim_iniciada"):
            return
        self._anim_iniciada = True

        target = self.stack.widget(index)
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.btn_nav):
            btn.setChecked(i == index)

        # Transición nítida sin ghosting: al terminar se libera el efecto para texto 100% nítido
        eff = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity")
        anim.setDuration(160)
        anim.setStartValue(0.4)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda t=target: t.setGraphicsEffect(None))
        anim.start()
        self._page_anim = anim

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS DE UI
    # ══════════════════════════════════════════════════════════════════════════
    def _titulo(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setProperty("class", "titulo")
        return lbl

    def _subtitulo(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setProperty("class", "subtitulo")
        lbl.setWordWrap(True)
        return lbl

    def _separador(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        return f

    def _section_header(self, texto: str) -> QLabel:
        lbl = QLabel(texto.upper())
        lbl.setObjectName("section_header")
        return lbl

    def _combo_modulos(self, obj_name="combo_modulo") -> QComboBox:
        cb = QComboBox()
        cb.setObjectName(obj_name)
        cb.addItems(list(TP20_MODULE_ADDR.keys()))
        cb.setFixedHeight(40)
        return cb

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 0 — CONEXIÓN
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_conexion(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(50, 40, 50, 40)
        lyt.setSpacing(20)

        lyt.addWidget(self._titulo("Conexión con el Vehículo"))
        lyt.addWidget(self._subtitulo(
            "Conecta el adaptador CANable 2.0 / OBD2 al conector de diagnosis (bajo el volante a la izquierda) "
            "y pon el contacto del vehículo (Klemme 15 ON). Luego pulsa Iniciar."
        ))

        # ── Cuadro Virtual Cockpit de Estado en Vivo (Audi RS) ──
        card_cockpit = QFrame()
        card_cockpit.setObjectName("card_cockpit")
        card_lyt = QVBoxLayout(card_cockpit)
        card_lyt.setContentsMargins(22, 16, 22, 18)
        card_lyt.setSpacing(12)

        # Barra superior del cuadro
        fila_tag = QHBoxLayout()
        lbl_tag = QLabel("AUDI VIRTUAL COCKPIT  ·  TELEMETRÍA Y CONTROL DE RED RS")
        lbl_tag.setStyleSheet("color: #FF0026; font-size: 11px; font-weight: 900; letter-spacing: 1.5px;")
        fila_tag.addWidget(lbl_tag)
        fila_tag.addStretch()
        self.lbl_red = QLabel("BUS CAN: 500 kbps")
        self.lbl_red.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 800; font-family: Consolas;")
        fila_tag.addWidget(self.lbl_red)
        card_lyt.addLayout(fila_tag)

        card_lyt.addWidget(self._separador())

        # Fila principal con 3 columnas
        fila_telemetria = QHBoxLayout()
        fila_telemetria.setSpacing(24)

        # Columna 1: Testigo MIL
        col_mil = QVBoxLayout()
        col_mil.setSpacing(4)
        col_mil.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_mil_t = QLabel("TESTIGO MOTOR (MIL)")
        lbl_mil_t.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        col_mil.addWidget(lbl_mil_t, alignment=Qt.AlignmentFlag.AlignCenter)
        self.lbl_mil = QLabel("MIL\n✓")
        self.lbl_mil.setObjectName("mil_off")
        self.lbl_mil.setFixedSize(64, 64)
        self.lbl_mil.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_mil.addWidget(self.lbl_mil, alignment=Qt.AlignmentFlag.AlignCenter)
        lbl_mil_sub = QLabel("Inyección / Emisiones")
        lbl_mil_sub.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        col_mil.addWidget(lbl_mil_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        fila_telemetria.addLayout(col_mil)

        fila_telemetria.addSpacing(16)

        # Columna 2: Identificación del Vehículo (VIN)
        col_vin = QVBoxLayout()
        col_vin.setSpacing(4)
        lbl_vin_t = QLabel("NÚMERO DE BASTIDOR IDENTIFICADO (VIN)")
        lbl_vin_t.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        col_vin.addWidget(lbl_vin_t)
        self.lbl_vin = QLabel("— No conectado —")
        self.lbl_vin.setStyleSheet(
            "font-size: 21px; font-weight: 900; color: #FFFFFF; "
            "font-family: Consolas, monospace; letter-spacing: 2px;"
        )
        col_vin.addWidget(self.lbl_vin)
        self.lbl_vehiculo_desc = QLabel("Audi A6 C6 2.7 TDI V6 Common Rail (190 CV) · Facelift 2010")
        self.lbl_vehiculo_desc.setStyleSheet("color: #94A3B8; font-size: 12.5px; font-weight: 600;")
        col_vin.addWidget(self.lbl_vehiculo_desc)
        fila_telemetria.addLayout(col_vin, stretch=1)

        fila_telemetria.addSpacing(16)

        # Columna 3: Sesión Diagnóstica Activa
        col_sesion = QVBoxLayout()
        col_sesion.setSpacing(4)
        lbl_sesion_t = QLabel("SESIÓN DIAGNÓSTICA")
        lbl_sesion_t.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 800; letter-spacing: 0.5px;")
        col_sesion.addWidget(lbl_sesion_t)
        self.lbl_sesion_num = QLabel("—")
        self.lbl_sesion_num.setStyleSheet("color: #FF0026; font-size: 20px; font-weight: 900; font-family: Consolas;")
        col_sesion.addWidget(self.lbl_sesion_num)
        self.lbl_protocolo_sub = QLabel("TP 2.0 CAN Nativo (KWP2000)")
        self.lbl_protocolo_sub.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600;")
        col_sesion.addWidget(self.lbl_protocolo_sub)
        fila_telemetria.addLayout(col_sesion)

        card_lyt.addLayout(fila_telemetria)
        lyt.addWidget(card_cockpit)

        # ── Selector de Tipo de Conexión / Adaptador ──
        box_modo = QFrame()
        box_modo.setObjectName("card_modo")
        lyt_m = QVBoxLayout(box_modo)
        lyt_m.setContentsMargins(22, 16, 22, 16)
        lyt_m.setSpacing(10)

        lbl_modo_t = QLabel("CONFIGURACIÓN DE ADAPTADOR Y PROTOCOLO DE DIAGNOSIS")
        lbl_modo_t.setStyleSheet("font-size: 11px; font-weight: 800; color: #CBD5E1; letter-spacing: 1.2px;")
        lyt_m.addWidget(lbl_modo_t)

        self.combo_modo = QComboBox()
        self.combo_modo.addItems([
            "🔌  Audi A6 C6 — CANable 2.0 (Nativo 500 kbps TP 2.0 / KWP2000)",
            "🚗  VW Polo (2007) — Cable K-Line FTDI (Pin 7 KWP1281)",
            "🚗  Opel Corsa — CAN Motor HSCAN (Pines 6 y 14 - 500 kbps)",
            "🛋️  Opel Corsa — CAN Confort MSCAN (Pines 3 y 11 - 95 kbps)",
            "💻  Modo Simulado — Audi A6 C6 (Sin cable conectado)",
            "💻  Modo Simulado — VW Polo 9N3 K-Line (Sin cable conectado)",
            "💻  Modo Simulado — Opel Corsa D (Sin cable conectado)",
        ])
        self.combo_modo.currentIndexChanged.connect(self._al_cambiar_modo_vehiculo)
        self.combo_modo.setFixedHeight(44)
        self.combo_modo.setStyleSheet(
            "background-color: #11141C; color: #F1F5F9; border: 1px solid #232836; "
            "border-radius: 7px; padding: 6px 12px; font-size: 13.5px; font-weight: 700;"
        )
        lyt_m.addWidget(self.combo_modo)

        lyt.addWidget(box_modo)

        # ── Botón de Conexión ──
        btn = QPushButton("⚡   INICIAR CONEXIÓN CON EL VEHÍCULO")
        btn.setProperty("class", "btn-accion")
        btn.setFixedHeight(52)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.iniciar_conexion)
        lyt.addWidget(btn)

        # ── Botón de Topología y Revisión de Red ──
        btn_topologia = QPushButton("🌐   REVISIÓN DE RED CAN — TOPOLOGÍA Y ESTADO DE TODOS LOS MÓDULOS")
        btn_topologia.setProperty("class", "btn-secundario")
        btn_topologia.setFixedHeight(44)
        btn_topologia.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_topologia.setToolTip(
            "Verifica la conexión con todas las centralitas, su presencia en el Gateway J533, "
            "referencia de hardware oficial y Long Coding."
        )
        btn_topologia.clicked.connect(self.abrir_dialogo_topologia_red)
        lyt.addWidget(btn_topologia)

        lyt.addStretch()
        self.stack.addWidget(page)

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 1 — FALLOS DTC
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_dtc(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(30, 30, 30, 20)
        lyt.setSpacing(12)

        lyt.addWidget(self._titulo("Escáner de Fallos (DTC)"))

        # Fila de controles
        fila = QHBoxLayout()
        self.combo_dtc = self._combo_modulos("combo_dtc")
        fila.addWidget(self.combo_dtc)

        btn_scan = QPushButton("🔍  Escanear Módulo")
        btn_scan.setProperty("class", "btn-accion")
        btn_scan.setFixedHeight(40)
        btn_scan.clicked.connect(self.escanear_modulo)
        fila.addWidget(btn_scan)

        btn_auto = QPushButton("🔎  Auto-Scan Completo")
        btn_auto.setProperty("class", "btn-secundario")
        btn_auto.setFixedHeight(40)
        btn_auto.clicked.connect(self.auto_scan)
        fila.addWidget(btn_auto)

        btn_topologia_dtc = QPushButton("🌐  Topología Red")
        btn_topologia_dtc.setProperty("class", "btn-secundario")
        btn_topologia_dtc.setFixedHeight(40)
        btn_topologia_dtc.setToolTip("Revisa el estado de conexión de todas las centralitas en el bus CAN y su Long Coding.")
        btn_topologia_dtc.clicked.connect(self.abrir_dialogo_topologia_red)
        fila.addWidget(btn_topologia_dtc)

        btn_borrar = QPushButton("🗑  Borrar Fallos")
        btn_borrar.setProperty("class", "btn-peligro")
        btn_borrar.setFixedHeight(40)
        btn_borrar.clicked.connect(self.borrar_fallos)
        fila.addWidget(btn_borrar)

        btn_km = QPushButton("⏱  Auditar Km Real")
        btn_km.setProperty("class", "btn-secundario")
        btn_km.setFixedHeight(40)
        btn_km.clicked.connect(self.lanzar_auditoria_km)
        fila.addWidget(btn_km)

        btn_ficha = QPushButton("📋  Ficha Técnica Guiada")
        btn_ficha.setProperty("class", "btn-accion")
        btn_ficha.setFixedHeight(40)
        btn_ficha.setToolTip("Abre la ficha técnica con la ubicación física exacta del componente averiado y los pasos de solución de taller.")
        btn_ficha.clicked.connect(self._abrir_ficha_tecnica_dtc)
        fila.addWidget(btn_ficha)

        fila.addStretch()
        lyt.addLayout(fila)

        # Tabla de fallos
        self.tabla_dtc = QTableWidget(0, 5)
        self.tabla_dtc.setHorizontalHeaderLabels(["Módulo", "Código", "Descripción", "Prioridad", "Estado"])
        self.tabla_dtc.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_dtc.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_dtc.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_dtc.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_dtc.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_dtc.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_dtc.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_dtc.setAlternatingRowColors(True)
        self.tabla_dtc.verticalHeader().setVisible(False)
        self.tabla_dtc.itemSelectionChanged.connect(self._mostrar_freeze_frame)
        self.tabla_dtc.doubleClicked.connect(self._abrir_ficha_tecnica_dtc)
        lyt.addWidget(self.tabla_dtc, stretch=3)

        # Panel Freeze Frame
        lyt.addWidget(self._section_header("Freeze Frame — Datos en el momento del fallo"))
        self.frame_ff = QFrame()
        self.frame_ff.setObjectName("panel_freeze")
        self.frame_ff.setFixedHeight(90)
        self._lyt_ff = QHBoxLayout(self.frame_ff)
        self._lyt_ff.setContentsMargins(10, 8, 10, 8)
        self._lbl_ff = QLabel("Selecciona un fallo de la tabla para ver el Freeze Frame.")
        self._lbl_ff.setStyleSheet("color: #CBD5E1; font-style: italic; font-size: 12.5px;")
        self._lyt_ff.addWidget(self._lbl_ff)
        lyt.addWidget(self.frame_ff, stretch=0)

        self.stack.addWidget(page)

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 2 — SENSORES EN VIVO
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_sensores(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(30, 30, 30, 20)
        lyt.setSpacing(12)

        lyt.addWidget(self._titulo("Sensores en Vivo"))

        # Controles
        fila = QHBoxLayout()
        btn_leer = QPushButton("▶  Leer Sensores Ahora")
        btn_leer.setProperty("class", "btn-accion")
        btn_leer.setFixedHeight(42)
        btn_leer.clicked.connect(self.leer_sensores)
        fila.addWidget(btn_leer)

        self.btn_auto_sensores = QPushButton("🔄  Monitoreo Continuo: OFF")
        self.btn_auto_sensores.setProperty("class", "btn-secundario")
        self.btn_auto_sensores.setFixedHeight(42)
        self.btn_auto_sensores.clicked.connect(self.toggle_monitoreo_sensores)
        fila.addWidget(self.btn_auto_sensores)

        self.btn_grabar = QPushButton("⏺  Iniciar Grabación CSV")
        self.btn_grabar.setProperty("class", "btn-secundario")
        self.btn_grabar.setFixedHeight(42)
        self.btn_grabar.clicked.connect(self.toggle_grabacion)
        fila.addWidget(self.btn_grabar)

        self.lbl_grabando = QLabel("")
        self.lbl_grabando.setStyleSheet("color: #E0001B; font-weight: 800; font-size: 12px;")
        fila.addWidget(self.lbl_grabando)
        fila.addStretch()
        lyt.addLayout(fila)

        # Pestañas: Tabla Numérica y Osciloscopio Vectorial
        tabs_sensores = QTabWidget()
        tabs_sensores.setObjectName("tabs_sensores")

        # Tab 1: Tabla de Sensores
        tab_tabla = QWidget()
        lyt_tab1 = QVBoxLayout(tab_tabla)
        lyt_tab1.setContentsMargins(0, 8, 0, 0)
        self.tabla_sensores = QTableWidget(0, 4)
        self.tabla_sensores.setHorizontalHeaderLabels(["Sensor", "Valor", "Unidad", "Nivel"])
        self.tabla_sensores.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_sensores.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_sensores.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_sensores.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tabla_sensores.setColumnWidth(3, 180)
        self.tabla_sensores.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_sensores.setAlternatingRowColors(True)
        self.tabla_sensores.verticalHeader().setVisible(False)
        self.tabla_sensores.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        lyt_tab1.addWidget(self.tabla_sensores)
        tabs_sensores.addTab(tab_tabla, "📊  Tabla Numérica y Niveles")

        # Tab 2: Osciloscopio Vectorial en Vivo (60 FPS)
        tab_scope = QWidget()
        lyt_tab2 = QVBoxLayout(tab_scope)
        lyt_tab2.setContentsMargins(0, 8, 0, 0)
        lyt_tab2.setSpacing(8)

        bar_scope = QHBoxLayout()
        bar_scope.setSpacing(12)
        lbl_sc_title = QLabel("Canales Activos:")
        lbl_sc_title.setStyleSheet("font-weight: bold; color: #CBD5E1; font-size: 11.5px;")
        bar_scope.addWidget(lbl_sc_title)

        self.osciloscopio = OsciloscopioWidget()

        for canal, cfg in self.osciloscopio.CANALES_CONFIG.items():
            chk = QCheckBox(canal)
            chk.setChecked(True)
            chk.setStyleSheet(f"color: {cfg['color'].name()}; font-weight: 700; font-size: 11.5px;")
            chk.toggled.connect(lambda checked, c=canal: self.osciloscopio.toggle_canal(c, checked))
            bar_scope.addWidget(chk)

        bar_scope.addStretch()

        btn_pause_scope = QPushButton("⏸  Pausar Traza")
        btn_pause_scope.setProperty("class", "btn-secundario")
        btn_pause_scope.setFixedHeight(30)
        btn_pause_scope.clicked.connect(lambda: btn_pause_scope.setText("▶  Reanudar" if self.osciloscopio.toggle_pausa() else "⏸  Pausar Traza"))
        bar_scope.addWidget(btn_pause_scope)

        btn_clear_scope = QPushButton("🗑  Limpiar Gráfica")
        btn_clear_scope.setProperty("class", "btn-secundario")
        btn_clear_scope.setFixedHeight(30)
        btn_clear_scope.clicked.connect(self.osciloscopio.limpiar)
        bar_scope.addWidget(btn_clear_scope)

        lyt_tab2.addLayout(bar_scope)
        lyt_tab2.addWidget(self.osciloscopio, stretch=1)
        tabs_sensores.addTab(tab_scope, "📈  Osciloscopio Vectorial en Tiempo Real (60 FPS)")

        # Tab 3: Cronómetro de Prestaciones en Vivo y Banco Virtual CAN
        self.cronometro = CronometroPrestacionesWidget()
        tabs_sensores.addTab(self.cronometro, "⏱  Prestaciones y Aceleración (0-100 km/h)")

        lyt.addWidget(tabs_sensores, stretch=1)

        self.stack.addWidget(page)

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 3 — WIZARDS DE MANTENIMIENTO Y SERVICIO (1 CLIC)
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_mantenimiento(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(30, 24, 30, 16)
        lyt.setSpacing(10)

        self.lbl_maint_titulo = self._titulo("Wizards de Mantenimiento y Servicio (1 Clic)")
        lyt.addWidget(self.lbl_maint_titulo)
        self.lbl_maint_subtitulo = self._subtitulo(
            "Operaciones automatizadas y guiadas de taller para Grupo VAG / Audi A6 C6 (4F Facelift): "
            "freno de mano eléctrico, reseteo de intervalos de servicio, monitor DPF, salud de inyectores Common Rail y registro de batería."
        )
        lyt.addWidget(self.lbl_maint_subtitulo)

        self.tabs_mantenimiento = QTabWidget()
        self.tabs_mantenimiento.setObjectName("tabs_mantenimiento")
        tabs_maint = self.tabs_mantenimiento

        # ── TAB 1: FRENO DE MANO ELÉCTRICO (EPB) ──
        tab_epb = QWidget()
        lyt_epb = QVBoxLayout(tab_epb)
        lyt_epb.setContentsMargins(20, 20, 20, 20)
        lyt_epb.setSpacing(14)

        card_epb = QFrame()
        card_epb.setObjectName("card_modo")
        c_lyt = QVBoxLayout(card_epb)
        c_lyt.setContentsMargins(20, 16, 20, 16)
        c_lyt.setSpacing(12)

        lbl_epb_desc = QLabel(
            "<b>Freno de Estacionamiento Eléctrico (Módulo 53 — J540):</b><br>"
            "Antes de desmontar las pinzas traseras para sustituir las pastillas de freno, el motor eléctrico "
            "debe retraerse electrónicamente. Una vez montadas las pastillas nuevas, pulsa 'Cerrar Pinzas y Calibrar' "
            "para que la centralita mida y memorice el nuevo espesor de trabajo."
        )
        lbl_epb_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_epb_desc.setWordWrap(True)
        c_lyt.addWidget(lbl_epb_desc)

        self.lbl_epb_status = QLabel("Estado del EPB: Pinzas en posición de trabajo (Cerradas / Listas)")
        self.lbl_epb_status.setStyleSheet("color: #00FF88; font-weight: 800; font-size: 13px;")
        c_lyt.addWidget(self.lbl_epb_status)

        fila_epb_btns = QHBoxLayout()
        fila_epb_btns.setSpacing(12)

        btn_abrir_epb = QPushButton("🔓  Abrir Pinzas (Modo Cambio de Pastillas)")
        btn_abrir_epb.setProperty("class", "btn-peligro")
        btn_abrir_epb.setFixedHeight(44)
        btn_abrir_epb.clicked.connect(self._wizard_epb_abrir)
        fila_epb_btns.addWidget(btn_abrir_epb)

        btn_cerrar_epb = QPushButton("🔒  Cerrar Pinzas y Calibrar Espesor")
        btn_cerrar_epb.setProperty("class", "btn-accion")
        btn_cerrar_epb.setFixedHeight(44)
        btn_cerrar_epb.clicked.connect(self._wizard_epb_cerrar)
        fila_epb_btns.addWidget(btn_cerrar_epb)

        btn_test_epb = QPushButton("🔄  Test Funcional (3 Ciclos)")
        btn_test_epb.setProperty("class", "btn-secundario")
        btn_test_epb.setFixedHeight(44)
        btn_test_epb.clicked.connect(self._wizard_epb_test)
        fila_epb_btns.addWidget(btn_test_epb)

        c_lyt.addLayout(fila_epb_btns)
        lyt_epb.addWidget(card_epb)
        lyt_epb.addStretch()
        tabs_maint.addTab(tab_epb, "🚗  Freno de Mano EPB (53)")

        # ── TAB 2: RESET DE INTERVALOS DE SERVICIO (SRI) ──
        tab_sri = QWidget()
        lyt_sri = QVBoxLayout(tab_sri)
        lyt_sri.setContentsMargins(20, 20, 20, 20)
        lyt_sri.setSpacing(14)

        card_sri = QFrame()
        card_sri.setObjectName("card_modo")
        s_lyt = QVBoxLayout(card_sri)
        s_lyt.setContentsMargins(20, 16, 20, 16)
        s_lyt.setSpacing(12)

        lbl_sri_desc = QLabel(
            "<b>Reset de Recordatorio de Servicio e Inspección (Módulo 17 — Cuadro J285):</b><br>"
            "Apaga instantáneamente el aviso de 'Servicio pendiente' en la pantalla del cuadro y en el MMI. "
            "Permite seleccionar entre intervalo estándar fijo de 15.000 km / 1 año o intervalo flexible LongLife de 30.000 km / 2 años."
        )
        lbl_sri_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_sri_desc.setWordWrap(True)
        s_lyt.addWidget(lbl_sri_desc)

        fila_sri_btns = QHBoxLayout()
        fila_sri_btns.setSpacing(12)

        btn_sri_aceite = QPushButton("⚡  Reset de Aceite Rápido (1 Clic)")
        btn_sri_aceite.setProperty("class", "btn-accion")
        btn_sri_aceite.setFixedHeight(44)
        btn_sri_aceite.clicked.connect(lambda: self.worker.ejecutar("sri_reset_aceite"))
        fila_sri_btns.addWidget(btn_sri_aceite)

        btn_sri_ll = QPushButton("📅  Inspección LongLife (30.000 km / 2 Años)")
        btn_sri_ll.setProperty("class", "btn-secundario")
        btn_sri_ll.setFixedHeight(44)
        btn_sri_ll.clicked.connect(lambda: self.worker.ejecutar("sri_reset_completo", longlife=True))
        fila_sri_btns.addWidget(btn_sri_ll)

        btn_sri_fijo = QPushButton("📅  Inspección Fija (15.000 km / 1 Año)")
        btn_sri_fijo.setProperty("class", "btn-secundario")
        btn_sri_fijo.setFixedHeight(44)
        btn_sri_fijo.clicked.connect(lambda: self.worker.ejecutar("sri_reset_completo", longlife=False))
        fila_sri_btns.addWidget(btn_sri_fijo)

        s_lyt.addLayout(fila_sri_btns)
        lyt_sri.addWidget(card_sri)
        lyt_sri.addStretch()
        tabs_maint.addTab(tab_sri, "🛢  Reset Servicio SRI (17)")

        # ── TAB 3: FILTRO DE PARTÍCULAS (DPF) ──
        tab_dpf = QWidget()
        lyt_dpf = QVBoxLayout(tab_dpf)
        lyt_dpf.setContentsMargins(20, 20, 20, 20)
        lyt_dpf.setSpacing(14)

        card_dpf = QFrame()
        card_dpf.setObjectName("card_modo")
        d_lyt = QVBoxLayout(card_dpf)
        d_lyt.setContentsMargins(20, 16, 20, 16)
        d_lyt.setSpacing(14)

        fila_dpf_head = QHBoxLayout()
        btn_leer_dpf = QPushButton("🔍  Consultar Nivel y Saturación DPF")
        btn_leer_dpf.setProperty("class", "btn-accion")
        btn_leer_dpf.setFixedHeight(42)
        btn_leer_dpf.clicked.connect(lambda: self.worker.ejecutar("dpf_leer"))
        fila_dpf_head.addWidget(btn_leer_dpf)

        btn_regen_dpf = QPushButton("🔥  Regeneración Forzada de Emergencia")
        btn_regen_dpf.setProperty("class", "btn-peligro")
        btn_regen_dpf.setFixedHeight(42)
        btn_regen_dpf.clicked.connect(self._wizard_dpf_regenerar)
        fila_dpf_head.addWidget(btn_regen_dpf)
        d_lyt.addLayout(fila_dpf_head)

        # Barras de telemetría DPF
        d_grid = QGridLayout()
        d_grid.setSpacing(12)

        # 1. Hollín
        d_grid.addWidget(QLabel("Masa de Hollín Calculada:"), 0, 0)
        self.bar_dpf_hollin = QProgressBar()
        self.bar_dpf_hollin.setRange(0, 45)
        self.bar_dpf_hollin.setValue(12)
        self.bar_dpf_hollin.setFixedHeight(24)
        d_grid.addWidget(self.bar_dpf_hollin, 0, 1)
        self.lbl_dpf_hollin = QLabel("12.3 g / 45.0 g máx")
        self.lbl_dpf_hollin.setStyleSheet("font-weight:bold; color:#00E5FF; font-family:Consolas;")
        d_grid.addWidget(self.lbl_dpf_hollin, 0, 2)

        # 2. Cenizas
        d_grid.addWidget(QLabel("Cenizas de Aceite Acumuladas:"), 1, 0)
        self.bar_dpf_ceniza = QProgressBar()
        self.bar_dpf_ceniza.setRange(0, 60)
        self.bar_dpf_ceniza.setValue(24)
        self.bar_dpf_ceniza.setFixedHeight(24)
        d_grid.addWidget(self.bar_dpf_ceniza, 1, 1)
        self.lbl_dpf_ceniza = QLabel("24.5 g / 60.0 g vida útil")
        self.lbl_dpf_ceniza.setStyleSheet("font-weight:bold; color:#FFB347; font-family:Consolas;")
        d_grid.addWidget(self.lbl_dpf_ceniza, 1, 2)

        # 3. Km desde última regen
        d_grid.addWidget(QLabel("Distancia desde última regeneración:"), 2, 0)
        self.lbl_dpf_km = QLabel("345 km")
        self.lbl_dpf_km.setStyleSheet("font-weight:bold; color:#FFFFFF; font-family:Consolas; font-size:14px;")
        d_grid.addWidget(self.lbl_dpf_km, 2, 1)

        # 4. Diagnóstico final
        d_grid.addWidget(QLabel("Evaluación Técnica del Filtro:"), 3, 0)
        self.lbl_dpf_eval = QLabel("CORRECTO — Saturación baja. No requiere intervención.")
        self.lbl_dpf_eval.setStyleSheet("font-weight:bold; color:#00FF88; font-size:13px;")
        d_grid.addWidget(self.lbl_dpf_eval, 3, 1, 1, 2)

        d_lyt.addLayout(d_grid)
        lyt_dpf.addWidget(card_dpf)
        lyt_dpf.addStretch()
        tabs_maint.addTab(tab_dpf, "💨  Filtro DPF (01)")

        # ── TAB 4: INYECTORES COMMON RAIL V6 TDI ──
        tab_inj = QWidget()
        lyt_inj = QVBoxLayout(tab_inj)
        lyt_inj.setContentsMargins(20, 20, 20, 20)
        lyt_inj.setSpacing(14)

        card_inj = QFrame()
        card_inj.setObjectName("card_modo")
        i_lyt = QVBoxLayout(card_inj)
        i_lyt.setContentsMargins(20, 16, 20, 16)
        i_lyt.setSpacing(12)

        fila_inj_head = QHBoxLayout()
        btn_leer_inj = QPushButton("🧪  Analizar Calibración de Inyectores (Canales 72 a 77)")
        btn_leer_inj.setProperty("class", "btn-accion")
        btn_leer_inj.setFixedHeight(42)
        btn_leer_inj.clicked.connect(lambda: self.worker.ejecutar("inyectores_leer"))
        fila_inj_head.addWidget(btn_leer_inj)
        fila_inj_head.addStretch()
        i_lyt.addLayout(fila_inj_head)

        lbl_inj_criterio = QLabel(
            "<b>Criterio Oficial de Diagnóstico Audi Common Rail 2.7 / 3.0 V6 TDI:</b><br>"
            "• <b>Verde (Óptimo)</b>: Compensación entre -30 ms y +10 ms.<br>"
            "• <b>Amarillo (Desgaste)</b>: Compensación entre -31 ms y -44 ms.<br>"
            "• <b>Rojo Crítico (&lt; -45 ms)</b>: Desgaste severo de aguja (Goteo continuo de combustible). Riesgo para el pistón.<br>"
            "• <b>Naranja (+15 ms)</b>: Obstrucción parcial de orificios de tobera o carbonilla."
        )
        lbl_inj_criterio.setStyleSheet("color: #94A3B8; font-size: 11.5px; background: #11141C; padding: 10px; border-radius: 6px;")
        lbl_inj_criterio.setWordWrap(True)
        i_lyt.addWidget(lbl_inj_criterio)

        # Cuadrícula para los 6 cilindros
        grid_inj = QGridLayout()
        grid_inj.setSpacing(10)
        self.cards_cilindros = {}

        for cyl in range(1, 7):
            f_cyl = QFrame()
            f_cyl.setStyleSheet("background-color: #171A24; border: 1px solid #282E3E; border-radius: 6px; padding: 6px;")
            fc_lyt = QVBoxLayout(f_cyl)
            fc_lyt.setContentsMargins(8, 6, 8, 6)
            fc_lyt.setSpacing(4)

            lbl_c_title = QLabel(f"CILINDRO {cyl}  (Canal {71 + cyl})")
            lbl_c_title.setStyleSheet("font-weight: 800; color: #FFFFFF; font-size: 12px;")
            fc_lyt.addWidget(lbl_c_title)

            lbl_v = QLabel("300 bar: -8.0 ms\n600 bar: -4.0 ms\n1000 bar: -2.0 ms")
            lbl_v.setStyleSheet("font-family: Consolas; font-size: 11.5px; color: #CBD5E1;")
            fc_lyt.addWidget(lbl_v)

            lbl_st = QLabel("●  ÓPTIMO")
            lbl_st.setStyleSheet("color: #00FF88; font-weight: bold; font-size: 12px;")
            fc_lyt.addWidget(lbl_st)

            self.cards_cilindros[cyl] = {"frame": f_cyl, "valores": lbl_v, "status": lbl_st}
            row = (cyl - 1) // 3
            col = (cyl - 1) % 3
            grid_inj.addWidget(f_cyl, row, col)

        i_lyt.addLayout(grid_inj)
        lyt_inj.addWidget(card_inj)
        lyt_inj.addStretch()
        tabs_maint.addTab(tab_inj, "💉  Inyectores V6 TDI (01)")

        # ── TAB 5: REGISTRO DE BATERÍA BEM ──
        tab_bem = QWidget()
        lyt_bem = QVBoxLayout(tab_bem)
        lyt_bem.setContentsMargins(20, 20, 20, 20)
        lyt_bem.setSpacing(14)

        card_bem = QFrame()
        card_bem.setObjectName("card_modo")
        b_lyt = QVBoxLayout(card_bem)
        b_lyt.setContentsMargins(20, 16, 20, 16)
        b_lyt.setSpacing(12)

        lbl_bem_desc = QLabel(
            "<b>Registro y Codificación BEM de Batería Nueva (Gateway J533 — Módulo 19):</b><br>"
            "Al sustituir la batería del Audi A6 C6, es imprescindible registrar su capacidad y tecnología en el Gateway J533 "
            "para reiniciar el mapa de envejecimiento de la centralita de gestión de energía J644. "
            "De lo contrario, el alternador continuará aplicando curvas de carga de batería gastada y desconectará módulos de confort."
        )
        lbl_bem_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_bem_desc.setWordWrap(True)
        b_lyt.addWidget(lbl_bem_desc)

        grid_bem = QGridLayout()
        grid_bem.setSpacing(12)

        grid_bem.addWidget(QLabel("Capacidad / Tipo de Batería:"), 0, 0)
        self.combo_bem_ah = QComboBox()
        self.combo_bem_ah.addItems(["95 Ah (AGM / Estándar)", "105 Ah (AGM)", "110 Ah", "100 Ah", "80 Ah"])
        self.combo_bem_ah.setFixedHeight(36)
        grid_bem.addWidget(self.combo_bem_ah, 0, 1)

        grid_bem.addWidget(QLabel("Fabricante (Vendor):"), 1, 0)
        self.combo_bem_marca = QComboBox()
        self.combo_bem_marca.addItems(["VARTA", "MOLL", "BANNER", "EXIDE", "BOSCH"])
        self.combo_bem_marca.setFixedHeight(36)
        grid_bem.addWidget(self.combo_bem_marca, 1, 1)

        grid_bem.addWidget(QLabel("Número de Serie (10 dígitos):"), 2, 0)
        self.txt_bem_serie = QLineEdit("1111111111")
        self.txt_bem_serie.setFixedHeight(36)
        self.txt_bem_serie.setStyleSheet("font-family: Consolas; font-weight: bold;")
        grid_bem.addWidget(self.txt_bem_serie, 2, 1)

        b_lyt.addLayout(grid_bem)

        fila_btns_bem = QHBoxLayout()
        fila_btns_bem.setSpacing(12)

        btn_leer_bem = QPushButton("📖  Leer Batería Registrada Actualmente")
        btn_leer_bem.setProperty("class", "btn-secundario")
        btn_leer_bem.setFixedHeight(44)
        btn_leer_bem.clicked.connect(self._wizard_bateria_leer)
        fila_btns_bem.addWidget(btn_leer_bem)

        btn_cod_bem = QPushButton("💾  Grabar y Registrar Batería Nueva en Gateway")
        btn_cod_bem.setProperty("class", "btn-peligro")
        btn_cod_bem.setFixedHeight(44)
        btn_cod_bem.clicked.connect(self._wizard_bateria_codificar)
        fila_btns_bem.addWidget(btn_cod_bem)

        b_lyt.addLayout(fila_btns_bem)

        self.lbl_bem_res = QLabel("")
        self.lbl_bem_res.setStyleSheet("font-weight: bold; font-size: 12.5px; color: #00FF88;")
        b_lyt.addWidget(self.lbl_bem_res)

        lyt_bem.addWidget(card_bem)
        lyt_bem.addStretch()
        tabs_maint.addTab(tab_bem, "🔋  Registro Batería BEM (19)")

        # ── TAB 6: PURGA ASISTIDA DE FRENOS ABS / ESP (03) ──
        tab_abs = QWidget()
        lyt_abs = QVBoxLayout(tab_abs)
        lyt_abs.setContentsMargins(20, 20, 20, 20)
        lyt_abs.setSpacing(14)

        card_abs = QFrame()
        card_abs.setObjectName("card_modo")
        ab_lyt = QVBoxLayout(card_abs)
        ab_lyt.setContentsMargins(20, 16, 20, 16)
        ab_lyt.setSpacing(12)

        lbl_abs_desc = QLabel(
            "<b>Purga Hidráulica Asistida del Sistema ABS / ESP (Módulo 03 — Bosch 8.0/8.2):</b><br>"
            "Activa la electrobomba de recirculación del bloque hidráulico para expulsar bolsas de aire retenidas en las válvulas "
            "tras cambiar el líquido de frenos o sustituir latiguillos / pinzas. Evita el pedal esponjoso."
        )
        lbl_abs_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_abs_desc.setWordWrap(True)
        ab_lyt.addWidget(lbl_abs_desc)

        self.lbl_abs_status = QLabel("Estado: Sistema listo. Conectar tubo purgador con botella a la pinza antes de activar la bomba.")
        self.lbl_abs_status.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 12.5px;")
        ab_lyt.addWidget(self.lbl_abs_status)

        fila_abs_btns = QHBoxLayout()
        fila_abs_btns.setSpacing(12)

        btn_abs_p1 = QPushButton("⚡  Paso 1: Purgar Eje Delantero (10s)")
        btn_abs_p1.setProperty("class", "btn-peligro")
        btn_abs_p1.setFixedHeight(44)
        btn_abs_p1.clicked.connect(lambda: self.worker.ejecutar("abs_purga", paso=1))
        fila_abs_btns.addWidget(btn_abs_p1)

        btn_abs_p2 = QPushButton("⚡  Paso 2: Purgar Eje Trasero (10s)")
        btn_abs_p2.setProperty("class", "btn-peligro")
        btn_abs_p2.setFixedHeight(44)
        btn_abs_p2.clicked.connect(lambda: self.worker.ejecutar("abs_purga", paso=2))
        fila_abs_btns.addWidget(btn_abs_p2)

        btn_abs_p3 = QPushButton("✓  Paso 3: Verificación Final")
        btn_abs_p3.setProperty("class", "btn-secundario")
        btn_abs_p3.setFixedHeight(44)
        btn_abs_p3.clicked.connect(lambda: self.worker.ejecutar("abs_purga", paso=3))
        fila_abs_btns.addWidget(btn_abs_p3)

        ab_lyt.addLayout(fila_abs_btns)
        lyt_abs.addWidget(card_abs)
        lyt_abs.addStretch()
        tabs_maint.addTab(tab_abs, "🩸  Purga ABS (03)")

        # ── TAB 7: CAJA AUTOMÁTICA ZF 6HP / MULTITRONIC (02) ──
        tab_caja = QWidget()
        lyt_caja = QVBoxLayout(tab_caja)
        lyt_caja.setContentsMargins(20, 20, 20, 20)
        lyt_caja.setSpacing(14)

        card_caja = QFrame()
        card_caja.setObjectName("card_modo")
        cj_lyt = QVBoxLayout(card_caja)
        cj_lyt.setContentsMargins(20, 16, 20, 16)
        cj_lyt.setSpacing(12)

        lbl_caja_desc = QLabel(
            "<b>Monitor de Temperatura ATF y Ajuste Adaptativo de Transmisión (Módulo 02 — ZF 6HP19A):</b><br>"
            "El nivel de ATF se debe medir obligatoriamente entre <b>35 °C y 45 °C</b> según el manual de taller de Audi y ZF. "
            "El reset de adaptaciones borra presiones aprendidas de embrague para eliminar tirones tras sustituir el ATF."
        )
        lbl_caja_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_caja_desc.setWordWrap(True)
        cj_lyt.addWidget(lbl_caja_desc)

        grid_atf = QGridLayout()
        grid_atf.setSpacing(10)
        grid_atf.addWidget(QLabel("Temperatura ATF en Tiempo Real:"), 0, 0)
        self.lbl_atf_temp = QLabel("--.- °C")
        self.lbl_atf_temp.setStyleSheet("font-size: 24px; font-weight: 900; color: #00E5FF; font-family: Consolas;")
        grid_atf.addWidget(self.lbl_atf_temp, 0, 1)

        grid_atf.addWidget(QLabel("Ventana de Comprobación de Nivel:"), 1, 0)
        self.lbl_atf_estado = QLabel("Pendiente de lectura")
        self.lbl_atf_estado.setStyleSheet("font-size: 13px; font-weight: 800; color: #94A3B8;")
        grid_atf.addWidget(self.lbl_atf_estado, 1, 1)

        grid_atf.addWidget(QLabel("Indicación Técnica para Taller:"), 2, 0)
        self.lbl_atf_ins = QLabel("Pulsa 'Leer Temperatura' con motor en marcha.")
        self.lbl_atf_ins.setStyleSheet("color: #CBD5E1; font-size: 12px; font-style: italic;")
        grid_atf.addWidget(self.lbl_atf_ins, 2, 1)
        cj_lyt.addLayout(grid_atf)

        fila_caja_btns = QHBoxLayout()
        fila_caja_btns.setSpacing(12)

        btn_leer_atf = QPushButton("🌡  Leer Temperatura de ATF (Grupo 004)")
        btn_leer_atf.setProperty("class", "btn-accion")
        btn_leer_atf.setFixedHeight(44)
        btn_leer_atf.clicked.connect(lambda: self.worker.ejecutar("caja_atf"))
        fila_caja_btns.addWidget(btn_leer_atf)

        btn_reset_caja = QPushButton("🔄  Reset Adaptativo Embragues (Canal 00)")
        btn_reset_caja.setProperty("class", "btn-secundario")
        btn_reset_caja.setFixedHeight(44)
        btn_reset_caja.clicked.connect(lambda: self.worker.ejecutar("caja_reset"))
        fila_caja_btns.addWidget(btn_reset_caja)

        cj_lyt.addLayout(fila_caja_btns)
        lyt_caja.addWidget(card_caja)
        lyt_caja.addStretch()
        tabs_maint.addTab(tab_caja, "⚙  Caja Automática ATF (02)")

        # ── TAB 8: SENSOR DE DIRECCIÓN G85 (03 / 16) ──
        tab_g85 = QWidget()
        lyt_g85 = QVBoxLayout(tab_g85)
        lyt_g85.setContentsMargins(20, 20, 20, 20)
        lyt_g85.setSpacing(14)

        card_g85 = QFrame()
        card_g85.setObjectName("card_modo")
        g_lyt = QVBoxLayout(card_g85)
        g_lyt.setContentsMargins(20, 16, 20, 16)
        g_lyt.setSpacing(12)

        lbl_g85_desc = QLabel(
            "<b>Calibración del Sensor de Ángulo de Dirección G85 (Módulo 03 ABS / 16 Columna):</b><br>"
            "Restablece el punto cero (0.0°) del volante para eliminar el testigo de avería del control de estabilidad ESP "
            "tras desconectar la batería, alinear la dirección o sustituir la cremallera / anillo de airbag."
        )
        lbl_g85_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_g85_desc.setWordWrap(True)
        g_lyt.addWidget(lbl_g85_desc)

        lbl_g85_req = QLabel(
            "<b>Requisitos previos:</b><br>"
            "1. Colocar las ruedas delanteras perfectamente rectas.<br>"
            "2. Volante centrado visualmente horizontal a 0.0°.<br>"
            "3. Contacto puesto o motor al ralentí."
        )
        lbl_g85_req.setStyleSheet("color: #94A3B8; font-size: 11.5px; background: #11141C; padding: 10px; border-radius: 6px;")
        g_lyt.addWidget(lbl_g85_req)

        self.lbl_g85_status = QLabel("Estado: Listo para calibración.")
        self.lbl_g85_status.setStyleSheet("color: #00FF88; font-weight: 800; font-size: 12.5px;")
        g_lyt.addWidget(self.lbl_g85_status)

        btn_g85 = QPushButton("🎯  Calibrar Sensor G85 a 0.0° (Login Oficial 40168)")
        btn_g85.setProperty("class", "btn-accion")
        btn_g85.setFixedHeight(44)
        btn_g85.clicked.connect(lambda: self.worker.ejecutar("g85_calibrar"))
        g_lyt.addWidget(btn_g85)

        lyt_g85.addWidget(card_g85)
        lyt_g85.addStretch()
        tabs_maint.addTab(tab_g85, "🎯  Sensor Dirección G85 (03)")

        # ── TAB 9: CHAPALETAS DE ADMISIÓN (01) ──
        tab_swirl = QWidget()
        lyt_swirl = QVBoxLayout(tab_swirl)
        lyt_swirl.setContentsMargins(20, 20, 20, 20)
        lyt_swirl.setSpacing(14)

        card_swirl = QFrame()
        card_swirl.setObjectName("card_modo")
        sw_lyt = QVBoxLayout(card_swirl)
        sw_lyt.setContentsMargins(20, 16, 20, 16)
        sw_lyt.setSpacing(12)

        lbl_sw_desc = QLabel(
            "<b>Ajuste Básico de Chapaletas de Admisión / Swirl Flaps (Módulo 01 — Servomotores V157 / V275):</b><br>"
            "Comprueba el fin de carrera de los colectores de admisión en motores 2.7 / 3.0 TDI V6. "
            "Realiza un ciclo de 3 aperturas y cierres completos (0% a 100%) para limpiar carbonilla y recalibrar topes mecánicos (soluciona P2015)."
        )
        lbl_sw_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_sw_desc.setWordWrap(True)
        sw_lyt.addWidget(lbl_sw_desc)

        self.lbl_swirl_status = QLabel("Estado: Servomotores en posición de reposo.")
        self.lbl_swirl_status.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 12.5px;")
        sw_lyt.addWidget(self.lbl_swirl_status)

        btn_swirl = QPushButton("🔄  Iniciar Ajuste Básico de Chapaletas (Canal 044)")
        btn_swirl.setProperty("class", "btn-accion")
        btn_swirl.setFixedHeight(44)
        btn_swirl.clicked.connect(lambda: self.worker.ejecutar("swirl_flaps"))
        sw_lyt.addWidget(btn_swirl)

        lyt_swirl.addWidget(card_swirl)
        lyt_swirl.addStretch()
        tabs_maint.addTab(tab_swirl, "🌪  Chapaletas V157 (01)")

        # ── TAB 10: MENÚ VERDE MMI (07) ──
        tab_mmi = QWidget()
        lyt_mmi = QVBoxLayout(tab_mmi)
        lyt_mmi.setContentsMargins(20, 20, 20, 20)
        lyt_mmi.setSpacing(14)

        card_mmi = QFrame()
        card_mmi.setObjectName("card_modo")
        mm_lyt = QVBoxLayout(card_mmi)
        mm_lyt.setContentsMargins(20, 16, 20, 16)
        mm_lyt.setSpacing(12)

        lbl_mmi_desc = QLabel(
            "<b>Habilitar Menú Verde Oculto de Ingeniería (Módulo 07 — MMI 2G High / MMI 3G):</b><br>"
            "Modifica el Canal de Adaptación 08 a valor 1 para desbloquear el menú de desarrollo de Audi en la pantalla central. "
            "Desde él se pueden habilitar indicadores auxiliares de batería, cronómetro de vueltas y funciones de confort."
        )
        lbl_mmi_desc.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4;")
        lbl_mmi_desc.setWordWrap(True)
        mm_lyt.addWidget(lbl_mmi_desc)

        lbl_mmi_how = QLabel(
            "<b>Cómo acceder una vez activado:</b><br>"
            "En la consola central del coche, pulsa simultáneamente y mantén presionados los botones <b>CAR + SETUP</b> durante 5 segundos."
        )
        lbl_mmi_how.setStyleSheet("color: #00FF88; font-size: 12px; background: #0E291B; padding: 10px; border-radius: 6px;")
        mm_lyt.addWidget(lbl_mmi_how)

        self.lbl_mmi_status = QLabel("Estado: Menú de ingeniería listo para ser habilitado.")
        self.lbl_mmi_status.setStyleSheet("color: #94A3B8; font-weight: 800; font-size: 12.5px;")
        mm_lyt.addWidget(self.lbl_mmi_status)

        btn_mmi = QPushButton("🟢  Activar Menú Verde Oculto en MMI")
        btn_mmi.setProperty("class", "btn-accion")
        btn_mmi.setFixedHeight(44)
        btn_mmi.clicked.connect(lambda: self.worker.ejecutar("mmi_green_menu"))
        mm_lyt.addWidget(btn_mmi)

        lyt_mmi.addWidget(card_mmi)
        lyt_mmi.addStretch()
        tabs_maint.addTab(tab_mmi, "🟢  Menú Verde MMI (07)")

        lyt.addWidget(tabs_maint, stretch=1)
        self.stack.addWidget(page)

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 4 — LONG CODING & CONFORT
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_coding(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(30, 24, 30, 16)
        lyt.setSpacing(10)

        self.lbl_coding_titulo = self._titulo("Long Coding y Funciones de Confort — Audi A6 2.7 TDI (2010)")
        lyt.addWidget(self.lbl_coding_titulo)
        self.lbl_coding_subtitulo = self._subtitulo(
            "Activa o desactiva funciones en texto claro para tu Audi A6 (modifica los bits por detrás), "
            "o usa el editor bit a bit. Se realiza backup automático antes de escribir."
        )
        lyt.addWidget(self.lbl_coding_subtitulo)

        # ── Fila 1: Control de Módulo y Lectura / Escritura ──
        fila_mod = QHBoxLayout()
        fila_mod.setSpacing(12)

        lbl_m = QLabel("MÓDULO OBJETIVO:")
        lbl_m.setStyleSheet("font-weight: 800; color: #CBD5E1; font-size: 11.5px; letter-spacing: 0.5px;")
        fila_mod.addWidget(lbl_m)

        self.combo_coding = self._combo_modulos("combo_coding")
        idx_cuadro = self.combo_coding.findText("Cuadro Instrumentos (17)")
        if idx_cuadro >= 0:
            self.combo_coding.setCurrentIndex(idx_cuadro)
        self.combo_coding.currentTextChanged.connect(self._on_modulo_coding_changed)
        self.combo_coding.setFixedWidth(260)
        fila_mod.addWidget(self.combo_coding)

        btn_leer_c = QPushButton("📖  Leer Coding Actual")
        btn_leer_c.setProperty("class", "btn-secundario")
        btn_leer_c.setFixedHeight(40)
        btn_leer_c.clicked.connect(self.leer_coding)
        fila_mod.addWidget(btn_leer_c)

        btn_escribir = QPushButton("✏  Escribir Nuevo Coding al Coche")
        btn_escribir.setProperty("class", "btn-peligro")
        btn_escribir.setFixedHeight(40)
        btn_escribir.clicked.connect(self.escribir_coding)
        fila_mod.addWidget(btn_escribir)

        fila_mod.addStretch()
        lyt.addLayout(fila_mod)

        # ── Fila 2: Acciones Rápidas & Seguridad (Needle Sweep + Backups) ──
        fila_actions = QHBoxLayout()
        fila_actions.setSpacing(10)

        self.btn_needle = QPushButton("🚀  Needle Sweep / Barrido de Agujas (1-Click)")
        self.btn_needle.setProperty("class", "btn-accion")
        self.btn_needle.setFixedHeight(38)
        self.btn_needle.clicked.connect(self.activar_needle_sweep_rapido)
        fila_actions.addWidget(self.btn_needle)

        self.btn_retrovisores = QPushButton("🪞  Plegado Retrovisores Automático (1-Click)")
        self.btn_retrovisores.setProperty("class", "btn-accion")
        self.btn_retrovisores.setFixedHeight(38)
        self.btn_retrovisores.setToolTip(
            "Codifica Módulos 46 + 42 + 52 para plegar/desplegar retrovisores automáticamente con el mando"
        )
        self.btn_retrovisores.clicked.connect(self.activar_plegado_retrovisores_rapido)
        fila_actions.addWidget(self.btn_retrovisores)

        btn_guardar_backup = QPushButton("💾  Guardar Backup Manual")
        btn_guardar_backup.setProperty("class", "btn-secundario")
        btn_guardar_backup.setFixedHeight(38)
        btn_guardar_backup.clicked.connect(self.crear_backup_manual)
        fila_actions.addWidget(btn_guardar_backup)

        btn_restaurar = QPushButton("↺  Restaurar Backup")
        btn_restaurar.setProperty("class", "btn-secundario")
        btn_restaurar.setFixedHeight(38)
        btn_restaurar.clicked.connect(self.abrir_dialogo_restaurar_backup)
        fila_actions.addWidget(btn_restaurar)

        btn_diff = QPushButton("🔍  Comparador Diff")
        btn_diff.setProperty("class", "btn-secundario")
        btn_diff.setFixedHeight(38)
        btn_diff.setToolTip("Compara diferencias byte a byte y bit a bit entre backups o contra el coche")
        btn_diff.clicked.connect(self.abrir_dialogo_diff_backups)
        fila_actions.addWidget(btn_diff)

        self.btn_gw = QPushButton("📋  Lista Gateway (19)")
        self.btn_gw.setProperty("class", "btn-secundario")
        self.btn_gw.setFixedHeight(38)
        self.btn_gw.setToolTip("Editar qué centralitas y accesorios están instalados en la pasarela Gateway J533")
        self.btn_gw.clicked.connect(self.abrir_dialogo_gateway_list)
        fila_actions.addWidget(self.btn_gw)

        fila_actions.addStretch()
        lyt.addLayout(fila_actions)

        # Fila de campos Hex
        fila_hex = QHBoxLayout()
        fila_hex.setSpacing(15)

        col_orig = QVBoxLayout()
        col_orig.setSpacing(3)
        self.lbl_coding_orig_t = QLabel("Coding Original (Leído de la centralita):")
        col_orig.addWidget(self.lbl_coding_orig_t)
        self.txt_coding_actual = QLineEdit()
        self.txt_coding_actual.setObjectName("txt_coding")
        self.txt_coding_actual.setReadOnly(True)
        self.txt_coding_actual.setPlaceholderText("Pulsa 'Leer Coding Actual'...")
        self.txt_coding_actual.setFixedHeight(36)
        col_orig.addWidget(self.txt_coding_actual)
        fila_hex.addLayout(col_orig, stretch=1)

        col_nuevo = QVBoxLayout()
        col_nuevo.setSpacing(3)
        self.lbl_coding_nuevo_t = QLabel("Nuevo Coding (Resultado en vivo):")
        col_nuevo.addWidget(self.lbl_coding_nuevo_t)
        self.txt_coding_nuevo = QLineEdit()
        self.txt_coding_nuevo.setObjectName("txt_coding")
        self.txt_coding_nuevo.setPlaceholderText("Se actualiza al activar funciones o editar bits...")
        self.txt_coding_nuevo.setFixedHeight(36)
        self.txt_coding_nuevo.textChanged.connect(self._sync_checkboxes_desde_texto)
        col_nuevo.addWidget(self.txt_coding_nuevo)
        fila_hex.addLayout(col_nuevo, stretch=1)

        lyt.addLayout(fila_hex)

        # Pestañas: 1. Funciones de Confort (Texto Claro) | 2. Editor Avanzado Bit a Bit
        self.tabs_coding = QTabWidget()

        # ── PESTAÑA 1: Funciones de Confort en Texto Claro ──
        scroll_confort = QScrollArea()
        scroll_confort.setWidgetResizable(True)
        self._confort_container = QWidget()
        self._confort_lyt = QVBoxLayout(self._confort_container)
        self._confort_lyt.setSpacing(8)
        self._confort_lyt.setContentsMargins(10, 10, 10, 10)
        scroll_confort.setWidget(self._confort_container)
        self.tabs_coding.addTab(scroll_confort, "🚗  Funciones de Confort — Audi A6 (Texto Claro)")

        # ── PESTAÑA 2: Editor Avanzado Bit a Bit (VCDS Raw) ──
        scroll_helper = QScrollArea()
        scroll_helper.setWidgetResizable(True)
        self._helper_container = QWidget()
        self._helper_container.setObjectName("coding_helper")
        self._helper_lyt = QGridLayout(self._helper_container)
        self._helper_lyt.setSpacing(4)
        self._helper_lyt.setContentsMargins(10, 10, 10, 10)
        scroll_helper.setWidget(self._helper_container)
        self.tabs_coding.addTab(scroll_helper, "🔧  Editor Avanzado Bit a Bit (VCDS Raw)")

        lyt.addWidget(self.tabs_coding, stretch=1)

        # Cargar catálogo inicial de confort
        self._cargar_catalogo_confort(self.combo_coding.currentText())

        self.stack.addWidget(page)

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 4 — ADAPTACIONES
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_adaptaciones(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(30, 30, 30, 20)
        lyt.setSpacing(12)

        lyt.addWidget(self._titulo("Adaptaciones (Función 10)"))
        lyt.addWidget(self._subtitulo(
            "Lee y modifica parámetros individuales de cada módulo sin tocar el Long Coding completo."
        ))

        fila = QHBoxLayout()
        self.combo_adapt = self._combo_modulos("combo_adapt")
        self.combo_adapt.currentTextChanged.connect(self._rebuild_adaptaciones)
        fila.addWidget(self.combo_adapt)
        btn_leer_a = QPushButton("📖  Leer Adaptaciones")
        btn_leer_a.setProperty("class", "btn-secundario")
        btn_leer_a.setFixedHeight(40)
        btn_leer_a.clicked.connect(self.leer_adaptaciones_modulo)
        fila.addWidget(btn_leer_a)
        fila.addStretch()
        lyt.addLayout(fila)

        scroll_a = QScrollArea()
        scroll_a.setWidgetResizable(True)
        self._adapt_container = QWidget()
        self._adapt_lyt = QVBoxLayout(self._adapt_container)
        self._adapt_lyt.setSpacing(6)
        self._adapt_lyt.setContentsMargins(4, 4, 4, 4)
        scroll_a.setWidget(self._adapt_container)
        lyt.addWidget(scroll_a)

        self._rebuild_adaptaciones(self.combo_adapt.currentText())
        self.stack.addWidget(page)

    def _rebuild_adaptaciones(self, modulo: str):
        """Reconstruye el listado de adaptaciones según el módulo elegido."""
        # Limpiar
        while self._adapt_lyt.count():
            item = self._adapt_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._adaptaciones_spin.clear()

        if self.es_modo_opel:
            ads = ADAPTACIONES_OPEL.get(modulo, [])
            if not ads:
                for k, v in ADAPTACIONES_OPEL.items():
                    if k.split()[0] in modulo:
                        ads = v
                        break
        elif self.es_modo_kline:
            ads = ADAPTACIONES_POLO_KLINE.get(modulo, [])
            if not ads:
                for k, v in ADAPTACIONES_POLO_KLINE.items():
                    if k.split()[0] in modulo:
                        ads = v
                        break
        else:
            ads = ADAPTACIONES_VAG.get(modulo, [])
        if not ads:
            lbl = QLabel(f"No hay adaptaciones catalogadas para {modulo}.")
            lbl.setStyleSheet("color: #94A3B8; font-style: italic; font-size: 13px;")
            self._adapt_lyt.addWidget(lbl)
            self._adapt_lyt.addStretch()
            return

        # Cabecera de columnas
        hdr = QWidget()
        hdr_lyt = QHBoxLayout(hdr)
        hdr_lyt.setContentsMargins(0, 0, 0, 0)
        for txt, width in [("Canal", 60), ("Adaptación", 270), ("Valor", 110), ("Unidad", 130), ("", 120)]:
            l = QLabel(txt)
            l.setStyleSheet("color: #E0001B; font-weight: 800; font-size: 11.5px; letter-spacing: 0.8px;")
            l.setFixedWidth(width) if width else l.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            hdr_lyt.addWidget(l)
        self._adapt_lyt.addWidget(hdr)
        self._adapt_lyt.addWidget(self._separador())

        for ad in ads:
            fila_w = QWidget()
            fila_lyt = QHBoxLayout(fila_w)
            fila_lyt.setContentsMargins(0, 4, 0, 4)
            fila_lyt.setSpacing(10)

            lbl_canal = QLabel(str(ad["canal"]))
            lbl_canal.setFixedWidth(60)
            lbl_canal.setStyleSheet("color: #CBD5E1; font-family: Consolas; font-weight: bold; font-size: 13px;")
            fila_lyt.addWidget(lbl_canal)

            lbl_nombre = QLabel(ad["nombre"])
            lbl_nombre.setFixedWidth(270)
            lbl_nombre.setStyleSheet("color: #FFFFFF; font-weight: 600; font-size: 13px;")
            lbl_nombre.setToolTip(ad["desc"])
            fila_lyt.addWidget(lbl_nombre)

            spin = QDoubleSpinBox()
            spin.setRange(ad["min"], ad["max"])
            spin.setValue(float(ad["valor"]))
            spin.setSingleStep(1.0)
            spin.setDecimals(1 if isinstance(ad["valor"], float) else 0)
            spin.setFixedWidth(110)
            fila_lyt.addWidget(spin)
            self._adaptaciones_spin[ad["nombre"]] = spin

            lbl_unidad = QLabel(ad["unidad"])
            lbl_unidad.setFixedWidth(130)
            lbl_unidad.setStyleSheet("color: #94A3B8; font-size: 12.5px; font-weight: 600;")
            fila_lyt.addWidget(lbl_unidad)

            btn_w = QPushButton("Escribir")
            btn_w.setProperty("class", "btn-secundario")
            btn_w.setFixedWidth(100)
            nombre = ad["nombre"]
            canal  = ad["canal"]
            btn_w.clicked.connect(
                lambda _, n=nombre, c=canal, s=spin: self.escribir_adaptacion(n, c, s.value())
            )
            fila_lyt.addWidget(btn_w)
            fila_lyt.addStretch()
            self._adapt_lyt.addWidget(fila_w)

        self._adapt_lyt.addStretch()

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 5 — TEST ACTUADORES
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_actuadores(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(30, 30, 30, 20)
        lyt.setSpacing(12)

        lyt.addWidget(self._titulo("Test de Actuadores"))
        lyt.addWidget(self._subtitulo(
            "Activa componentes individuales del coche para verificar su funcionamiento. "
            "Requiere conexión activa."
        ))

        fila = QHBoxLayout()
        self.combo_actu = self._combo_modulos("combo_actu")
        self.combo_actu.currentTextChanged.connect(self._rebuild_actuadores)
        fila.addWidget(self.combo_actu)
        fila.addStretch()
        lyt.addLayout(fila)

        scroll_ac = QScrollArea()
        scroll_ac.setWidgetResizable(True)
        self._actu_container = QWidget()
        self._actu_lyt = QGridLayout(self._actu_container)
        self._actu_lyt.setSpacing(10)
        self._actu_lyt.setContentsMargins(4, 4, 4, 4)
        self._actu_lyt.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_ac.setWidget(self._actu_container)
        lyt.addWidget(scroll_ac)

        self._rebuild_actuadores(self.combo_actu.currentText())
        self.stack.addWidget(page)

    def _rebuild_actuadores(self, modulo: str):
        while self._actu_lyt.count():
            item = self._actu_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.es_modo_opel:
            acts = ACTUADORES_OPEL.get(modulo, [])
            if not acts:
                for k, v in ACTUADORES_OPEL.items():
                    if k.split()[0] in modulo:
                        acts = v
                        break
        elif self.es_modo_kline:
            acts = ACTUADORES_POLO_KLINE.get(modulo, [])
            if not acts:
                for k, v in ACTUADORES_POLO_KLINE.items():
                    if k.split()[0] in modulo:
                        acts = v
                        break
        else:
            acts = ACTUADORES_VAG.get(modulo, [])
        if not acts:
            lbl = QLabel(f"No hay actuadores catalogados para {modulo}.")
            lbl.setStyleSheet("color: #94A3B8; font-style: italic; font-size: 13px;")
            self._actu_lyt.addWidget(lbl, 0, 0)
            return

        for i, act in enumerate(acts):
            row, col = divmod(i, 3)
            w = QWidget()
            w_lyt = QVBoxLayout(w)
            w_lyt.setContentsMargins(0, 0, 0, 0)
            w_lyt.setSpacing(4)

            btn = QPushButton(f"▶  {act['nombre']}")
            btn.setProperty("class", "btn-actuador")
            btn.setFixedHeight(50)
            nombre   = act["nombre"]
            canal    = act["canal"]
            duracion = act["duracion"]
            btn.clicked.connect(
                lambda _, n=nombre, c=canal, d=duracion: self.test_actuador(n, c, d)
            )
            w_lyt.addWidget(btn)

            lbl_desc = QLabel(act["desc"])
            lbl_desc.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
            lbl_desc.setWordWrap(True)
            w_lyt.addWidget(lbl_desc)

            self._actu_lyt.addWidget(w, row, col)

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 6 — HISTORIAL
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_historial(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(30, 30, 30, 20)
        lyt.setSpacing(12)

        lyt.addWidget(self._titulo("Historial de Sesiones"))

        btn_refrescar = QPushButton("🔄  Actualizar")
        btn_refrescar.setProperty("class", "btn-secundario")
        btn_refrescar.setFixedWidth(150)
        btn_refrescar.clicked.connect(self._cargar_historial)
        lyt.addWidget(btn_refrescar, alignment=Qt.AlignmentFlag.AlignLeft)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Lista de sesiones
        self.lista_sesiones = QListWidget()
        self.lista_sesiones.setFixedWidth(300)
        self.lista_sesiones.itemSelectionChanged.connect(self._sesion_seleccionada)
        splitter.addWidget(self.lista_sesiones)

        # Tabla de DTCs de la sesión
        panel_dtc = QWidget()
        p_lyt = QVBoxLayout(panel_dtc)
        p_lyt.setContentsMargins(0, 0, 0, 0)
        p_lyt.addWidget(self._section_header("Fallos de la sesión seleccionada"))
        self.tabla_hist_dtc = QTableWidget(0, 4)
        self.tabla_hist_dtc.setHorizontalHeaderLabels(["Módulo", "Código", "Descripción", "Estado"])
        self.tabla_hist_dtc.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_hist_dtc.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_hist_dtc.setAlternatingRowColors(True)
        self.tabla_hist_dtc.verticalHeader().setVisible(False)
        p_lyt.addWidget(self.tabla_hist_dtc)
        splitter.addWidget(panel_dtc)

        lyt.addWidget(splitter)
        self.stack.addWidget(page)
        self._cargar_historial()

    # ══════════════════════════════════════════════════════════════════════════
    #  PÁGINA 7 — INFORMES
    # ══════════════════════════════════════════════════════════════════════════
    def _crear_pagina_informes(self):
        page = QWidget()
        lyt = QVBoxLayout(page)
        lyt.setContentsMargins(50, 40, 50, 40)
        lyt.setSpacing(20)

        lyt.addWidget(self._titulo("Informes de Diagnóstico"))
        lyt.addWidget(self._subtitulo(
            "Genera un informe completo de la sesión activa con todos los "
            "fallos, lecturas de sensores y datos de la sesión."
        ))

        btn_gen = QPushButton("📊  Generar Informe de esta Sesión (.txt)")
        btn_gen.setProperty("class", "btn-secundario")
        btn_gen.setFixedSize(420, 48)
        btn_gen.clicked.connect(self.generar_reporte)
        lyt.addWidget(btn_gen)

        btn_html = QPushButton("🌐  Generar y Abrir Informe Oficial en HTML (Imprimible / PDF)")
        btn_html.setProperty("class", "btn-accion")
        btn_html.setFixedSize(420, 52)
        btn_html.clicked.connect(self.generar_reporte_html)
        lyt.addWidget(btn_html)

        btn_ver_txt = QPushButton("📄  Abrir Archivo de Registro Detallado (.txt)")
        btn_ver_txt.setProperty("class", "btn-secundario")
        btn_ver_txt.setFixedSize(420, 48)
        btn_ver_txt.clicked.connect(self.abrir_archivo_log)
        lyt.addWidget(btn_ver_txt)

        lyt.addStretch()
        self.stack.addWidget(page)

    # ══════════════════════════════════════════════════════════════════════════
    #  SEÑALES → SLOTS
    # ══════════════════════════════════════════════════════════════════════════
    def generar_reporte_html(self):
        sesion_id = self.worker.sesion_id or 1
        rg = ReportGenerator()
        ruta = rg.generar_reporte_html(sesion_id)
        if os.path.exists(ruta):
            self.escribir_consola(f"\n[✓ INFORME HTML] Informe oficial generado con éxito en:\n{ruta}")
            try:
                webbrowser.open(f"file:///{os.path.abspath(ruta).replace(os.sep, '/')}")
            except Exception:
                os.startfile(ruta)
        else:
            QMessageBox.warning(self, "Error al generar informe", f"No se pudo generar el informe HTML:\n{ruta}")

    # ──────────────────────────────────────────────────────────────────────────
    #  HANDLERS DE WIZARDS DE MANTENIMIENTO
    # ──────────────────────────────────────────────────────────────────────────
    def _wizard_epb_abrir(self):
        resp = QMessageBox.warning(
            self,
            "Seguridad EPB — Retracción de Pinzas Traseras",
            "ADVERTENCIA DE SEGURIDAD PARA SUSTITUCIÓN DE PASTILLAS:\n\n"
            "• El vehículo debe estar en superficie totalmente HORIZONTAL.\n"
            "• Coloca calzos de seguridad en las ruedas delanteras.\n"
            "• NO pises el pedal de freno durante la apertura de pinzas.\n"
            "• Mantén el contacto puesto con batería estable (> 12.2V).\n\n"
            "¿Deseas iniciar la retracción de los motores ahora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.lbl_epb_status.setText("Estado del EPB: Abriendo pinzas traseras... Espera unos segundos.")
            self.lbl_epb_status.setStyleSheet("color: #FFB347; font-weight: 800; font-size: 13px;")
            self.worker.ejecutar("epb_abrir")

    def _wizard_epb_cerrar(self):
        self.lbl_epb_status.setText("Estado del EPB: Cerrando pinzas y calibrando nuevo espesor...")
        self.lbl_epb_status.setStyleSheet("color: #FFB347; font-weight: 800; font-size: 13px;")
        self.worker.ejecutar("epb_cerrar")

    def _wizard_epb_test(self):
        self.lbl_epb_status.setText("Estado del EPB: Ejecutando 3 ciclos de apertura y cierre...")
        self.lbl_epb_status.setStyleSheet("color: #00E5FF; font-weight: 800; font-size: 13px;")
        self.worker.ejecutar("epb_test")

    def _wizard_dpf_regenerar(self):
        resp = QMessageBox.warning(
            self,
            "Seguridad DPF — Regeneración Forzada de Emergencia",
            "ADVERTENCIA TÉRMICA DE SEGURIDAD:\n\n"
            "• El vehículo debe encontrarse en el EXTERIOR, al aire libre.\n"
            "• NO aparcar sobre hierba seca ni cerca de materiales inflamables.\n"
            "• Temperatura de refrigerante mínima requerida: 70 °C.\n"
            "• Depósito de combustible: Al menos 1/4 (25%).\n"
            "• Capó de motor cerrado y pedales sin tocar.\n\n"
            "El régimen de motor se elevará automáticamente para alcanzar > 600 °C en el filtro.\n"
            "¿Confirmas que se cumplen todos los requisitos de seguridad?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.worker.ejecutar("dpf_regenerar")

    def _wizard_bateria_leer(self):
        self.escribir_consola("\n[ACCION] Leyendo codificación BEM actual registrada en el Gateway J533...")
        self.lbl_bem_res.setText("Leyendo batería actual en Gateway J533...")
        self.lbl_bem_res.setStyleSheet("color: #00F0FF; font-weight: bold;")
        self.worker.ejecutar("bateria_leer")

    def _wizard_bateria_codificar(self):
        txt_ah = self.combo_bem_ah.currentText().split()[0]
        marca = self.combo_bem_marca.currentText()
        serie = self.txt_bem_serie.text().strip() or "1111111111"
        self.worker.ejecutar("bateria_codificar", ah=txt_ah, marca=marca, serie=serie)

    def _recibir_wizard_datos(self, wizard: str, datos: dict):
        if wizard == "bateria_leida":
            ok = datos.get("ok", False)
            msg = datos.get("msg", "")
            info = datos.get("info", {})
            self.lbl_bem_res.setText(msg)
            self.lbl_bem_res.setStyleSheet(f"color: {'#00FF88' if ok else '#FF0026'}; font-weight: bold;")
            if ok and info.get("serial"):
                self.txt_bem_serie.setText(info["serial"])
            if ok:
                QMessageBox.information(self, "Batería Registrada en Gateway", msg)
            else:
                QMessageBox.warning(self, "Aviso BEM", msg)
            return

        if wizard == "dpf":
            if "error" in datos:
                self.lbl_dpf_eval.setText(datos["error"])
                self.lbl_dpf_eval.setStyleSheet("color: #FF0026; font-weight: bold;")
                return
            hollin = datos.get("hollin_calc_g", 0.0)
            ceniza = datos.get("ceniza_g", 0.0)
            km = datos.get("km_desde_regen", 0)
            eval_txt = datos.get("estado_filtro", "OK")
            col = datos.get("color_estado", "#00FF88")

            self.bar_dpf_hollin.setValue(int(min(45, max(0, hollin))))
            self.bar_dpf_ceniza.setValue(int(min(60, max(0, ceniza))))
            self.lbl_dpf_hollin.setText(f"{hollin:.1f} g / 45.0 g máx")
            self.lbl_dpf_ceniza.setText(f"{ceniza:.1f} g / 60.0 g vida útil")
            self.lbl_dpf_km.setText(f"{km:,} km")
            self.lbl_dpf_eval.setText(eval_txt)
            self.lbl_dpf_eval.setStyleSheet(f"color: {col}; font-weight: bold; font-size: 13px;")

        elif wizard == "inyectores":
            cilindros = datos.get("cilindros", {})
            for cyl, info in cilindros.items():
                if cyl in self.cards_cilindros:
                    card = self.cards_cilindros[cyl]
                    b300 = info.get("bar300", 0.0)
                    b600 = info.get("bar600", 0.0)
                    b1000 = info.get("bar1000", 0.0)
                    st = info.get("estado", "OK")
                    col = info.get("color", "#00FF88")

                    card["valores"].setText(f"300 bar: {b300:+.1f} ms\n600 bar: {b600:+.1f} ms\n1000 bar: {b1000:+.1f} ms")
                    card["status"].setText(f"●  {st.upper()}")
                    card["status"].setStyleSheet(f"color: {col}; font-weight: bold; font-size: 11.5px;")

        elif wizard == "caja_atf":
            if "error" in datos:
                self.lbl_atf_estado.setText(datos["error"])
                self.lbl_atf_estado.setStyleSheet("color: #FF0026; font-weight: bold;")
                return
            temp = datos.get("temperatura_c", 0.0)
            est = datos.get("estado", "OK")
            col = datos.get("color", "#00FF88")
            ins = datos.get("instruccion", "")
            self.lbl_atf_temp.setText(f"{temp:.1f} °C")
            self.lbl_atf_estado.setText(est)
            self.lbl_atf_estado.setStyleSheet(f"color: {col}; font-weight: 800; font-size: 13px;")
            self.lbl_atf_ins.setText(ins)

    def _recibir_wizard_resultado(self, accion: str, ok: bool, msg: str):
        if accion in ("epb_abrir", "epb_cerrar", "epb_test"):
            if ok:
                if accion == "epb_abrir":
                    self.lbl_epb_status.setText("Estado del EPB: PINZAS ABIERTAS (Modo Mantenimiento Activo)")
                    self.lbl_epb_status.setStyleSheet("color: #FFB347; font-weight: 800; font-size: 13px;")
                else:
                    self.lbl_epb_status.setText("Estado del EPB: Pinzas cerradas y calibradas (Listas)")
                    self.lbl_epb_status.setStyleSheet("color: #00FF88; font-weight: 800; font-size: 13px;")
                QMessageBox.information(self, "Asistente EPB", msg)
            else:
                QMessageBox.warning(self, "Error EPB", msg)

        elif accion in ("sri_aceite", "sri_completo"):
            if ok:
                QMessageBox.information(self, "Reset de Servicio SRI", msg)
            else:
                QMessageBox.warning(self, "Error SRI", msg)

        elif accion == "dpf_regen":
            if ok:
                QMessageBox.information(self, "Regeneración DPF", msg)
            else:
                QMessageBox.warning(self, "Error DPF", msg)

        elif accion == "bateria":
            self.lbl_bem_res.setText(msg)
            self.lbl_bem_res.setStyleSheet(f"color: {'#00FF88' if ok else '#FF0026'}; font-weight: bold;")
            if ok:
                QMessageBox.information(self, "Registro BEM", msg)
            else:
                QMessageBox.warning(self, "Error BEM", msg)

        elif accion == "abs_purga":
            self.lbl_abs_status.setText(msg)
            self.lbl_abs_status.setStyleSheet(f"color: {'#00FF88' if ok else '#FF0026'}; font-weight: bold;")
            if ok:
                QMessageBox.information(self, "Purga ABS", msg)
            else:
                QMessageBox.warning(self, "Error Purga ABS", msg)

        elif accion == "caja_reset":
            if ok:
                QMessageBox.information(self, "Reset Caja ZF", msg)
            else:
                QMessageBox.warning(self, "Error Transmisión", msg)

        elif accion == "g85":
            self.lbl_g85_status.setText(msg)
            self.lbl_g85_status.setStyleSheet(f"color: {'#00FF88' if ok else '#FF0026'}; font-weight: bold;")
            if ok:
                QMessageBox.information(self, "Calibración G85", msg)
            else:
                QMessageBox.warning(self, "Error G85", msg)

        elif accion == "swirl_flaps":
            self.lbl_swirl_status.setText(msg)
            self.lbl_swirl_status.setStyleSheet(f"color: {'#00FF88' if ok else '#FF0026'}; font-weight: bold;")
            if ok:
                QMessageBox.information(self, "Ajuste Chapaletas", msg)
            else:
                QMessageBox.warning(self, "Error Chapaletas", msg)

        elif accion == "mmi_green_menu":
            self.lbl_mmi_status.setText(msg)
            self.lbl_mmi_status.setStyleSheet(f"color: {'#00FF88' if ok else '#FF0026'}; font-weight: bold;")
            if ok:
                QMessageBox.information(self, "Menú Verde MMI", msg)
            else:
                QMessageBox.warning(self, "Error MMI", msg)

        elif accion == "gateway_guardar":
            if ok:
                QMessageBox.information(self, "Gateway J533", msg)
            else:
                QMessageBox.warning(self, "Error Gateway", msg)

    def abrir_dialogo_diff_backups(self):
        """Abre el comparador visual de backups de codificación (Diff Viewer)."""
        mod = self.combo_modulos.currentText()
        coding_actual = self.txt_coding_actual.text().strip()
        dlg = DialogoDiffBackups(self, modulo_filtro=mod, coding_actual=coding_actual)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.backup_seleccionado_para_restaurar:
                self.txt_coding_nuevo.setText(dlg.backup_seleccionado_para_restaurar)
                self.actualizar_bytes_desde_hex(dlg.backup_seleccionado_para_restaurar)
                self.escribir_consola("\n[CODING] Codificación transferida desde el Comparador Diff.")

    def abrir_dialogo_gateway_list(self):
        """Abre el editor visual de la Lista de Instalación del Gateway J533."""
        dlg = DialogoGatewayList(self, can_mgr=self.worker.can_mgr)
        dlg.lista_guardada_signal.connect(lambda activos: self.worker.ejecutar("gateway_guardar_lista", modulos=activos))
        dlg.exec()

    def abrir_dialogo_topologia_red(self):
        """Abre la ventana de revisión de conexión y topología de red CAN de todos los módulos."""
        can_mgr = getattr(self.worker, "can_mgr", None)
        dlg = DialogoTopologiaRed(self, can_mgr=can_mgr)
        dlg.exec()

    def abrir_archivo_log(self):
        """Abre el archivo de registro audidiag_registro_detallado.txt en el Bloc de Notas de Windows."""
        ruta = config.LOG_FILE_PATH
        if not os.path.exists(ruta):
            diag_logger.log_info("Archivo de log iniciado por el usuario.")
        try:
            os.startfile(ruta)
        except Exception as e:
            QMessageBox.information(
                self, "Registro Detallado",
                f"El archivo de registro está en:\n{ruta}\n\n(No se pudo abrir automáticamente: {e})"
            )

    def escribir_consola(self, texto: str):
        self.consola.append(texto)
        self.consola.verticalScrollBar().setValue(
            self.consola.verticalScrollBar().maximum()
        )
        for linea in str(texto).splitlines():
            if linea.strip():
                diag_logger.log("CONSOLA", linea.strip())


    def actualizar_estado(self, texto: str, color: str):
        colores = {"red": "#EF4444", "yellow": "#F59E0B", "green": "#10B981"}
        c = colores.get(color, "#38BDF8")
        self.lbl_status.setText(texto)
        self.lbl_status.setStyleSheet(f"color: {c}; font-weight: 700; font-size: 11.5px;")
        if hasattr(self, "dot_status"):
            self.dot_status.setStyleSheet(f"color: {c}; font-size: 15px; font-weight: bold;")

    def recibir_vin(self, vin: str):
        if self.es_modo_kline:
            self.lbl_vin.setText(f"{vin} (VW Polo 9N3)")
        else:
            self.lbl_vin.setText(vin)
        self.lbl_sesion_num.setText(f"# {self.worker.sesion_id}")

    def actualizar_mil(self, encendida: bool):
        self.lbl_mil.setObjectName("mil_on" if encendida else "mil_off")
        self.lbl_mil.setText("MIL\n⚠" if encendida else "MIL\n✓")
        # Forzar refresco del stylesheet para el cambio de objectName
        self.lbl_mil.setStyleSheet(self.lbl_mil.styleSheet())
        self.lbl_mil.style().unpolish(self.lbl_mil)
        self.lbl_mil.style().polish(self.lbl_mil)

    def agregar_fallos_modulo(self, modulo: str, fallos: list):
        """Agrega en tiempo real las averías de un módulo recién escaneado directamente a la tabla."""
        if not fallos:
            return

        for cod, desc, ff in fallos:
            row = self.tabla_dtc.rowCount()
            self.tabla_dtc.insertRow(row)
            self.tabla_dtc.setItem(row, 0, QTableWidgetItem(modulo))

            cod_str = str(cod)
            estado_str = "Activo"
            color_texto = "#FF4444"
            if "HISTÓRICO" in cod_str or "ESPORÁDICO" in cod_str:
                estado_str = "Histórico / Esporádico"
                color_texto = "#FFB347"
            elif "MEMORIA" in cod_str or "GUARDADO" in cod_str:
                estado_str = "En Memoria"
                color_texto = "#FFCC00"

            partes = cod_str.split()
            if partes:
                c_display = partes[1] if (len(partes) > 1 and "DTC" in partes[0].upper()) else partes[0]
            else:
                c_display = cod_str

            item_cod = QTableWidgetItem(c_display)
            item_cod.setForeground(QColor(color_texto))
            self.tabla_dtc.setItem(row, 1, item_cod)
            self.tabla_dtc.setItem(row, 2, QTableWidgetItem(desc))

            # Prioridad de avería técnica VAG
            mod_up = str(modulo).upper()
            if "01" in mod_up or "02" in mod_up or "03" in mod_up or "15" in mod_up:
                prioridad_txt = "1 — Crítica" if "Activo" in estado_str else "2 — Taller"
                color_prio = "#FF0026" if "Activo" in estado_str else "#FF9100"
            elif "17" in mod_up or "19" in mod_up or "53" in mod_up:
                prioridad_txt = "3 — Seguridad"
                color_prio = "#FFB347"
            else:
                prioridad_txt = "5 — Confort"
                color_prio = "#38BDF8"

            item_prio = QTableWidgetItem(prioridad_txt)
            item_prio.setForeground(QColor(color_prio))
            self.tabla_dtc.setItem(row, 3, item_prio)

            item_est = QTableWidgetItem(estado_str)
            item_est.setForeground(QColor(color_texto))
            self.tabla_dtc.setItem(row, 4, item_est)

            self._dtcs_datos.append((modulo, c_display, desc, ff))

        self.tabla_dtc.scrollToBottom()

    def recibir_scan(self, resumen: dict):
        """Notificación de finalización de escaneo y balance total."""
        total = self.tabla_dtc.rowCount()
        if total > 0:
            self.escribir_consola(
                f"\n[INFO] Auto-Scan finalizado: {total} avería(s) registradas en la tabla."
            )
        else:
            self.escribir_consola(
                "\n[INFO] Auto-Scan finalizado: 0 averías detectadas en los módulos consultados."
            )

    def lanzar_auditoria_km(self):
        """Lanza la herramienta forense de auditoría de kilometraje real directamente en la consola."""
        self.escribir_consola("\n[INFO] Lanzando Auditoría Forense de Kilometraje Real...")
        self.worker.ejecutar("auditar_km")

    def _mostrar_freeze_frame(self):
        """Muestra el freeze frame del fallo seleccionado en la tabla."""
        rows = self.tabla_dtc.selectedItems()
        if not rows:
            return
        row = self.tabla_dtc.currentRow()
        if row < 0 or row >= len(self._dtcs_datos):
            return

        _, cod, _, ff = self._dtcs_datos[row]

        # Limpiar panel
        while self._lyt_ff.count():
            item = self._lyt_ff.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not ff:
            lbl = QLabel(f"Sin datos de Freeze Frame registrados para {cod}.")
            lbl.setStyleSheet("color: #94A3B8; font-style: italic; font-size: 12.5px;")
            self._lyt_ff.addWidget(lbl)
            return

        lbl_cod = QLabel(f"  {cod}  ")
        lbl_cod.setStyleSheet(
            "background-color: #2A090D; color: #FFA5AF; font-weight: 800; "
            "font-family: Consolas; padding: 4px 10px; border-radius: 4px; "
            "border: 1px solid #5C1017; font-size: 13px;"
        )
        self._lyt_ff.addWidget(lbl_cod)
        self._lyt_ff.addSpacing(12)

        for param, (valor, unidad) in ff.items():
            w = QWidget()
            w_l = QVBoxLayout(w)
            w_l.setContentsMargins(0, 0, 0, 0)
            w_l.setSpacing(2)
            lbl_p = QLabel(param)
            lbl_p.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 700;")
            lbl_v = QLabel(f"{valor} {unidad}")
            lbl_v.setStyleSheet("color: #00FF88; font-weight: bold; font-size: 13.5px; font-family: Consolas;")
            w_l.addWidget(lbl_p)
            w_l.addWidget(lbl_v)
            self._lyt_ff.addWidget(w)

        self._lyt_ff.addStretch()

    def _abrir_ficha_tecnica_dtc(self):
        """Abre el diálogo modal de Ficha Técnica Guiada con localización física del componente y pasos de reparación."""
        row = self.tabla_dtc.currentRow()
        if row < 0 or row >= len(self._dtcs_datos):
            if len(self._dtcs_datos) > 0:
                row = 0
            else:
                QMessageBox.information(
                    self,
                    "Ficha Técnica DTC",
                    "No hay ningún código de avería seleccionado en la tabla.\n"
                    "Realiza primero un escaneo y selecciona un fallo para ver su ficha técnica guiada con localización exacta."
                )
                return

        modulo, cod, desc, ff = self._dtcs_datos[row]
        dlg = DialogoFichaDTC(modulo=modulo, codigo=cod, descripcion=desc, freeze_frame=ff, parent=self)
        dlg.exec()

    def _abrir_asistente_polo_kline(self):
        """Abre la ventana modal del Asistente K-Line para VW Polo 9N3."""
        dlg = DialogoPoloKLine(parent=self)
        dlg.exec()

    def recibir_sensores(self, datos: list):
        """Rellena la tabla de sensores con los datos recibidos."""
        self.tabla_sensores.setRowCount(0)

        for sensor, valor, unidad, maximo in datos:
            row = self.tabla_sensores.rowCount()
            self.tabla_sensores.insertRow(row)
            self.tabla_sensores.setItem(row, 0, QTableWidgetItem(sensor))
            item_v = QTableWidgetItem(f"{valor:.1f}")
            item_v.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_v.setForeground(QColor("#00CC88"))
            self.tabla_sensores.setItem(row, 1, item_v)
            self.tabla_sensores.setItem(row, 2, QTableWidgetItem(unidad))

            bar = QProgressBar()
            pct = int(min(100, (valor / maximo * 100))) if maximo > 0 else 0
            bar.setValue(pct)
            bar.setTextVisible(False)
            self.tabla_sensores.setCellWidget(row, 3, bar)

        self.tabla_sensores.setRowHeight
        for i in range(self.tabla_sensores.rowCount()):
            self.tabla_sensores.setRowHeight(i, 32)

        # Actualizar osciloscopio vectorial en tiempo real
        if hasattr(self, "osciloscopio"):
            for sensor, valor, _, _ in datos:
                self.osciloscopio.agregar_lectura(sensor, valor)

        # Actualizar telemetría para cronómetro de aceleración
        if hasattr(self, "cronometro"):
            vel = 0.0
            rpm = 0.0
            for sensor, valor, _, _ in datos:
                s_low = str(sensor).lower()
                if "velocidad" in s_low or "speed" in s_low:
                    vel = float(valor)
                elif "rpm" in s_low or "giro" in s_low:
                    rpm = float(valor)
            self.cronometro.alimentar_telemetria(vel, rpm)

        # CSV si está grabando
        if self._grabando_csv and self._csv_writer:
            ts = datetime.now().strftime("%H:%M:%S")
            for sensor, valor, unidad, _ in datos:
                self._csv_writer.writerow([ts, sensor, valor, unidad])

    def recibir_coding(self, valor: str):
        """Recibe coding del worker, actualiza campos, checkboxes, botones de confort y crea auto-backup."""
        self._coding_actual_leido = valor
        self.txt_coding_actual.setText(valor)
        self._rebuilding_from_worker = True
        self.txt_coding_nuevo.setText(valor)
        self._rebuilding_from_worker = False
        self._rebuild_helper_coding(valor)
        self._actualizar_estado_botones_confort()

        # Guardar automáticamente copia de seguridad original de fábrica al leer
        if valor and valor.strip():
            try:
                bm = BackupManager()
                modulo = self.combo_coding.currentText()
                vin = self.lbl_vin.text()
                if "—" in vin or not vin.strip():
                    vin = getattr(self.worker, "vin", None) or "WAUZZZ4G7BN000000"
                ruta_b = bm.guardar_backup(modulo=modulo, coche=vin, bytes_coding=valor, etiqueta="ORIGINAL_LEIDO")
                nom_f = os.path.basename(ruta_b)
                self.escribir_consola(f"\n[✓ BACKUP AUTOMÁTICO] Guardada copia de lectura original: {nom_f}")
            except Exception as e:
                self.escribir_consola(f"[WARN] No se pudo crear auto-backup de lectura: {e}")

    def recibir_adaptacion(self, nombre: str, valor: float):
        """Actualiza el SpinBox de la adaptación leída y sincroniza los botones de confort en tiempo real."""
        if nombre in self._adaptaciones_spin:
            self._adaptaciones_spin[nombre].setValue(valor)

        if self.es_modo_kline:
            if not hasattr(self, "_polo_confort_estados"):
                self._polo_confort_estados = {}
            for item, btn in self._confort_botones:
                if item.get("nombre") == nombre or item.get("id") == nombre:
                    activo = (int(valor) != 0)
                    self._polo_confort_estados[item.get("id", item["nombre"])] = activo
                    if activo:
                        btn.setText("✓ ACTIVADO")
                        btn.setProperty("class", "btn-confort-activo")
                    else:
                        btn.setText("○ DESACTIVADO")
                        btn.setProperty("class", "btn-confort-inactivo")
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)

    # ══════════════════════════════════════════════════════════════════════════
    #  LONG CODING & FUNCIONES DE CONFORT AUDI A6
    # ══════════════════════════════════════════════════════════════════════════
    def _on_modulo_coding_changed(self, nuevo_modulo: str):
        self._limpiar_helper_coding()
        self._cargar_catalogo_confort(nuevo_modulo)

    def _cargar_catalogo_confort(self, modulo: str):
        """Carga las funciones de confort en texto claro para el módulo seleccionado."""
        if not hasattr(self, "_confort_lyt"):
            return

        while self._confort_lyt.count():
            item = self._confort_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._confort_botones.clear()

        if hasattr(self, "tabs_coding"):
            if self.es_modo_kline:
                self.tabs_coding.setTabText(0, "🚗  Canales de Confort — VW Polo 9N3 (KWP1281)")
                self.tabs_coding.setTabVisible(1, False)
            elif self.es_modo_opel:
                self.tabs_coding.setTabText(0, "🚗  Funciones de Confort — Opel Corsa D")
                self.tabs_coding.setTabVisible(1, True)
                self.tabs_coding.setTabText(1, "🔧  Editor Avanzado de Variantes (GM)")
            else:
                self.tabs_coding.setTabText(0, "🚗  Funciones de Confort — Audi A6 (Texto Claro)")
                self.tabs_coding.setTabVisible(1, True)
                self.tabs_coding.setTabText(1, "🔧  Editor Avanzado Bit a Bit (VCDS Raw)")

        if self.es_modo_opel:
            funciones = CATALOGO_CONFORT_OPEL.get(modulo, [])
            if not funciones:
                for k, v in CATALOGO_CONFORT_OPEL.items():
                    if k.split()[0] in modulo:
                        funciones = v
                        break
        elif self.es_modo_kline:
            funciones = CATALOGO_CONFORT_POLO.get(modulo, [])
            if not funciones:
                for k, v in CATALOGO_CONFORT_POLO.items():
                    if k.split()[0] in modulo:
                        funciones = v
                        break
        else:
            funciones = CATALOGO_CONFORT_A6.get(modulo, [])
        if not funciones:
            lbl_vacio = QLabel(
                f"No hay funciones rápidas de confort catalogadas para {modulo}.\n"
                "Usa la pestaña 'Editor Avanzado Bit a Bit' para modificar la codificación directamente."
            )
            lbl_vacio.setStyleSheet("color: #94A3B8; font-style: italic; padding: 25px; font-size: 13px;")
            lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._confort_lyt.addWidget(lbl_vacio)
            self._confort_lyt.addStretch()
            return

        lbl_header = QLabel(f"FUNCIONES DE CONFORT  ·  {modulo.upper()} ({len(funciones)} disponibles)")
        lbl_header.setStyleSheet("color: #E0001B; font-weight: 800; font-size: 12px; letter-spacing: 1.5px; padding: 6px 0;")
        self._confort_lyt.addWidget(lbl_header)

        for item in funciones:
            card = QFrame()
            card.setObjectName("card_confort")
            card.setMinimumHeight(56)
            c_lyt = QHBoxLayout(card)
            c_lyt.setContentsMargins(16, 12, 16, 12)
            c_lyt.setSpacing(14)

            col_info = QVBoxLayout()
            col_info.setSpacing(4)

            fila_tit = QHBoxLayout()
            fila_tit.setSpacing(10)
            lbl_nom = QLabel(item["nombre"])
            lbl_nom.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 13px;")
            fila_tit.addWidget(lbl_nom)

            if "canal" in item and self.es_modo_kline:
                lbl_badge = QLabel(f"Canal {item['canal']:02d} · KWP1281")
            elif "soft_code" in item and self.es_modo_kline:
                lbl_badge = QLabel(f"Soft Coding · {item['soft_code']}")
            else:
                lbl_badge = QLabel(f"Byte {item.get('byte', 0)} · Bit {item.get('bit', 0)}")
            lbl_badge.setObjectName("badge_byte_bit")
            fila_tit.addWidget(lbl_badge)
            fila_tit.addStretch()
            col_info.addLayout(fila_tit)

            lbl_desc = QLabel(item["desc"])
            lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
            lbl_desc.setWordWrap(True)
            col_info.addWidget(lbl_desc)

            c_lyt.addLayout(col_info, stretch=1)

            btn_t = QPushButton("○ DESACTIVADO")
            btn_t.setProperty("class", "btn-confort-inactivo")
            btn_t.setFixedSize(140, 36)
            btn_t.clicked.connect(lambda _, it=item, b=btn_t: self._toggle_funcion_confort(it, b))
            c_lyt.addWidget(btn_t, alignment=Qt.AlignmentFlag.AlignVCenter)

            self._confort_botones.append((item, btn_t))
            self._confort_lyt.addWidget(card)

        self._confort_lyt.addStretch()
        self._actualizar_estado_botones_confort()

    def _actualizar_estado_botones_confort(self):
        """Actualiza el texto y color de los botones según los bits del coding actual o estado K-Line."""
        if self.es_modo_kline:
            if not hasattr(self, "_polo_confort_estados"):
                self._polo_confort_estados = {}
            for item, btn in self._confort_botones:
                item_id = item.get("id", item["nombre"])
                activo = self._polo_confort_estados.get(item_id, item.get("defecto", 0) == 1)
                if activo:
                    btn.setText("✓ ACTIVADO")
                    btn.setProperty("class", "btn-confort-activo")
                else:
                    btn.setText("○ DESACTIVADO")
                    btn.setProperty("class", "btn-confort-inactivo")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            return

        coding_actual = self.txt_coding_nuevo.text().strip() or self._coding_actual_leido
        if not coding_actual:
            for item, btn in self._confort_botones:
                btn.setText("○ DESACTIVADO")
                btn.setProperty("class", "btn-confort-inactivo")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            return

        lcm = LongCodingManager()
        for item, btn in self._confort_botones:
            try:
                activo = lcm.leer_bit(coding_actual, item["byte"], item["bit"])
                if activo:
                    btn.setText("✓ ACTIVADO")
                    btn.setProperty("class", "btn-confort-activo")
                else:
                    btn.setText("○ DESACTIVADO")
                    btn.setProperty("class", "btn-confort-inactivo")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            except Exception:
                pass

    def _toggle_funcion_confort(self, item: dict, btn: QPushButton):
        """Modifica el bit correspondiente por detrás en memoria y actualiza la GUI."""
        if self.es_modo_kline:
            if not hasattr(self, "_polo_confort_estados"):
                self._polo_confort_estados = {}
            item_id = item.get("id", item["nombre"])
            estado_actual = self._polo_confort_estados.get(item_id, item.get("defecto", 0) == 1)
            nuevo_estado = not estado_actual
            self._polo_confort_estados[item_id] = nuevo_estado

            if nuevo_estado:
                btn.setText("✓ ACTIVADO")
                btn.setProperty("class", "btn-confort-activo")
            else:
                btn.setText("○ DESACTIVADO")
                btn.setProperty("class", "btn-confort-inactivo")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

            canal = item.get("canal", 3)
            val_escrito = 1 if nuevo_estado else 0
            if hasattr(self, "txt_coding_nuevo"):
                self.txt_coding_nuevo.setText(f"Canal {canal:02d} = {val_escrito} (Polo 9N3)")
            self.escribir_consola(f"\n[CONFORT POLO] '{item['nombre']}' -> {'ACTIVADO' if nuevo_estado else 'DESACTIVADO'} (Canal {canal:02d} = {val_escrito})")
            if self.worker.conectado:
                self.worker.ejecutar(
                    "adaptacion_escribir",
                    modulo="Confort / BCM (46)",
                    nombre=item["nombre"],
                    canal=canal,
                    valor=val_escrito
                )
            return

        if not self._coding_actual_leido:
            if self.es_modo_opel:
                self._coding_actual_leido = self.txt_coding_nuevo.text().strip() or "06 05 02 00"
                self.txt_coding_actual.setText(self._coding_actual_leido)
                self.txt_coding_nuevo.setText(self._coding_actual_leido)
            else:
                self.escribir_consola(
                    "\n[AVISO] Primero pulsa '📖 Leer Coding Actual' para leer la centralita de tu Audi A6."
                )
                QMessageBox.information(
                    self, "Lectura de Centralita Necesaria",
                    "Primero debes pulsar '📖 Leer Coding Actual'.\n\n"
                    "AudiDiag Pro necesita leer la centralita de tu Audi A6 2.7 TDI para conocer "
                    "la codificación original antes de permitir activar o desactivar funciones."
                )
                return

        coding_actual = self.txt_coding_nuevo.text().strip()
        lcm = LongCodingManager()
        estado_actual = lcm.leer_bit(coding_actual, item["byte"], item["bit"])
        nuevo_estado = not estado_actual

        try:
            nuevo_hex = lcm.cambiar_bit(
                coding_actual, item["byte"], item["bit"], activar=nuevo_estado, con_espacios=True
            )
            self._rebuilding_from_worker = True
            self.txt_coding_nuevo.setText(nuevo_hex)
            self._rebuilding_from_worker = False

            # Actualizar aspecto del botón pulsado
            if nuevo_estado:
                btn.setText("✓ ACTIVADO")
                btn.setProperty("class", "btn-confort-activo")
            else:
                btn.setText("○ DESACTIVADO")
                btn.setProperty("class", "btn-confort-inactivo")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

            # Sincronizar checkboxes del editor avanzado y resto de botones
            self._sync_checkboxes_desde_texto(nuevo_hex)
            self._actualizar_estado_botones_confort()

            # Registrar en la consola con detalle técnico para el usuario
            estado_txt = "ACTIVADA" if nuevo_estado else "DESACTIVADA"
            bit_val = 1 if nuevo_estado else 0
            self.escribir_consola(
                f"\n[CONFORT AUDI A6] {item['nombre']} → {estado_txt}\n"
                f"  ▸ Bit modificado en memoria: Byte {item['byte']}, Bit {item['bit']} = {bit_val}\n"
                f"  ▸ Nuevo Coding resultante : {nuevo_hex}\n"
                f"  ▸ Para grabar definitivamente en el coche, pulsa '✏ Escribir Nuevo Coding al Coche'."
            )
        except Exception as e:
            self.escribir_consola(f"[ERROR] No se pudo modificar la función de confort: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    #  LONG CODING HELPER (BIT A BIT)
    # ══════════════════════════════════════════════════════════════════════════
    def _rebuild_helper_coding(self, hex_str: str):
        """Construye la cuadrícula de checkboxes a partir de una cadena hex."""
        while self._helper_lyt.count():
            item = self._helper_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._coding_checkboxes.clear()

        try:
            limpio = hex_str.replace(" ", "")
            if not limpio:
                return
            bytes_lista = [int(limpio[i:i+2], 16) for i in range(0, len(limpio), 2)]
        except ValueError:
            return

        for bit in range(7, -1, -1):
            lbl = QLabel(f"bit{bit}")
            lbl.setStyleSheet("color: #94A3B8; font-size: 10.5px; font-family: Consolas; font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._helper_lyt.addWidget(lbl, 0, bit + 1)

        for b_idx, byte_val in enumerate(bytes_lista):
            lbl_byte = QLabel(f"B{b_idx}  0x{byte_val:02X}")
            lbl_byte.setStyleSheet("color: #CBD5E1; font-size: 11.5px; font-family: Consolas; font-weight: bold;")
            lbl_byte.setFixedWidth(74)
            self._helper_lyt.addWidget(lbl_byte, b_idx + 1, 0)

            fila_checks = []
            for bit in range(7, -1, -1):
                cb = QCheckBox()
                cb.setChecked(bool(byte_val & (1 << bit)))
                cb.stateChanged.connect(self._update_coding_desde_helper)
                self._helper_lyt.addWidget(cb, b_idx + 1, (7 - bit) + 1, alignment=Qt.AlignmentFlag.AlignCenter)
                fila_checks.append((bit, cb))
            self._coding_checkboxes.append(fila_checks)

    def _limpiar_helper_coding(self):
        while self._helper_lyt.count():
            item = self._helper_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._coding_checkboxes.clear()
        self.txt_coding_actual.clear()
        self.txt_coding_nuevo.clear()
        self._coding_actual_leido = ""
        self._actualizar_estado_botones_confort()

    def _update_coding_desde_helper(self):
        """Recalcula el string hex desde los checkboxes y actualiza txt_coding_nuevo."""
        if not self._coding_checkboxes:
            return
        bytes_lista = []
        for fila in self._coding_checkboxes:
            val = 0
            for bit, cb in fila:
                if cb.isChecked():
                    val |= (1 << bit)
            bytes_lista.append(val)

        nuevo_hex = " ".join(f"{b:02X}" for b in bytes_lista)
        self._rebuilding_from_worker = True
        self.txt_coding_nuevo.setText(nuevo_hex)
        self._rebuilding_from_worker = False
        self._actualizar_estado_botones_confort()

    def _sync_checkboxes_desde_texto(self, texto: str):
        """Sincroniza los checkboxes cuando el usuario edita el campo de texto."""
        if getattr(self, "_rebuilding_from_worker", False):
            return
        try:
            limpio = texto.replace(" ", "")
            if not limpio or len(limpio) % 2 != 0:
                return
            bytes_lista = [int(limpio[i:i+2], 16) for i in range(0, len(limpio), 2)]
            if len(bytes_lista) != len(self._coding_checkboxes):
                return
            self._rebuilding_from_worker = True
            for b_idx, (byte_val, fila) in enumerate(zip(bytes_lista, self._coding_checkboxes)):
                for bit, cb in fila:
                    cb.setChecked(bool(byte_val & (1 << bit)))
            self._rebuilding_from_worker = False
            self._actualizar_estado_botones_confort()
        except (ValueError, Exception):
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  RESTAURACIÓN DE BACKUPS DE CODIFICACIÓN
    # ══════════════════════════════════════════════════════════════════════════
    def abrir_dialogo_restaurar_backup(self):
        """Abre una ventana modal para ver y restaurar copias de seguridad de codificación."""
        modulo_actual = self.combo_coding.currentText()
        bm = BackupManager()

        dialogo = QDialog(self)
        dialogo.setWindowTitle(f"Restaurar Copia de Seguridad — {modulo_actual}")
        dialogo.resize(840, 530)
        dialogo.setStyleSheet(self.styleSheet())

        dlg_lyt = QVBoxLayout(dialogo)
        dlg_lyt.setContentsMargins(24, 20, 24, 20)
        dlg_lyt.setSpacing(12)

        lbl_t = QLabel("Restaurar Copia de Seguridad de Codificación")
        lbl_t.setProperty("class", "titulo")
        dlg_lyt.addWidget(lbl_t)

        lbl_sub = QLabel(
            "Selecciona un backup guardado previamente para recuperar la configuración original o previa de tu vehículo. "
            "Puedes cargar el valor en el editor para revisarlo antes de escribir, o restaurarlo directamente a la centralita."
        )
        lbl_sub.setProperty("class", "subtitulo")
        lbl_sub.setWordWrap(True)
        dlg_lyt.addWidget(lbl_sub)

        # Filtro por módulo y herramientas
        fila_filtro = QHBoxLayout()
        fila_filtro.setSpacing(12)
        chk_filtrar_modulo = QCheckBox(f"Filtrar solo copias del módulo actual ({modulo_actual})")
        chk_filtrar_modulo.setChecked(True)
        fila_filtro.addWidget(chk_filtrar_modulo)

        btn_refrescar_dlg = QPushButton("🔄  Actualizar")
        btn_refrescar_dlg.setProperty("class", "btn-secundario")
        btn_refrescar_dlg.setFixedHeight(30)
        fila_filtro.addWidget(btn_refrescar_dlg)

        btn_crear_ahora = QPushButton("💾  Crear Backup Ahora")
        btn_crear_ahora.setProperty("class", "btn-secundario")
        btn_crear_ahora.setFixedHeight(30)
        fila_filtro.addWidget(btn_crear_ahora)

        fila_filtro.addStretch()
        dlg_lyt.addLayout(fila_filtro)

        # Tabla de copias de seguridad (5 columnas)
        tabla = QTableWidget(0, 5)
        tabla.setHorizontalHeaderLabels(["Fecha y Hora", "Módulo", "Tipo / Etiqueta", "Vehículo (VIN)", "Codificación (Hex)"])
        tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabla.setAlternatingRowColors(True)
        tabla.verticalHeader().setVisible(False)
        dlg_lyt.addWidget(tabla, stretch=1)

        # Cuadro de previsualización
        frame_prev = QFrame()
        frame_prev.setObjectName("card_confort")
        fp_lyt = QVBoxLayout(frame_prev)
        fp_lyt.setContentsMargins(14, 10, 14, 10)
        fp_lyt.setSpacing(4)

        lbl_prev_titulo = QLabel("DETALLE DE LA CODIFICACIÓN SELECCIONADA:")
        lbl_prev_titulo.setStyleSheet("color: #E0001B; font-weight: 800; font-size: 11.5px; letter-spacing: 1.2px;")
        fp_lyt.addWidget(lbl_prev_titulo)

        lbl_prev_hex = QLabel("Selecciona un archivo de la lista superior...")
        lbl_prev_hex.setStyleSheet("font-family: Consolas; font-size: 14px; font-weight: bold; color: #00FF88; padding: 4px 0;")
        lbl_prev_hex.setWordWrap(True)
        fp_lyt.addWidget(lbl_prev_hex)

        lbl_prev_archivo = QLabel("")
        lbl_prev_archivo.setStyleSheet("color: #94A3B8; font-size: 11.5px; font-family: Consolas;")
        fp_lyt.addWidget(lbl_prev_archivo)

        dlg_lyt.addWidget(frame_prev)

        backups_cargados = []

        def cargar_tabla():
            tabla.setRowCount(0)
            backups_cargados.clear()
            filtro_mod = modulo_actual if chk_filtrar_modulo.isChecked() else None
            lista = bm.obtener_backups_detallados(modulo=filtro_mod)

            for b in lista:
                row = tabla.rowCount()
                tabla.insertRow(row)

                hex_espacios = b.get("hex_formateado", "")

                tabla.setItem(row, 0, QTableWidgetItem(b.get("fecha_hora", "—")))
                tabla.setItem(row, 1, QTableWidgetItem(b.get("modulo", "—")))

                item_etiq = QTableWidgetItem(b.get("etiqueta", "Automático"))
                item_etiq.setForeground(QColor("#FFAA33"))
                tabla.setItem(row, 2, item_etiq)

                tabla.setItem(row, 3, QTableWidgetItem(b.get("coche", "—")))
                item_hex = QTableWidgetItem(hex_espacios)
                item_hex.setForeground(QColor("#00FF88"))
                tabla.setItem(row, 4, item_hex)

                backups_cargados.append({**b, "hex_formateado": hex_espacios})

            if backups_cargados:
                tabla.selectRow(0)
            else:
                lbl_prev_hex.setText("No hay copias de seguridad disponibles para este filtro.")
                lbl_prev_archivo.setText("Puedes pulsar '💾 Crear Backup Ahora' para guardar la codificación actual.")

        def on_seleccion():
            row = tabla.currentRow()
            if 0 <= row < len(backups_cargados):
                b = backups_cargados[row]
                lbl_prev_hex.setText(b["hex_formateado"])
                etiq = b.get("etiqueta", "Automático")
                lbl_prev_archivo.setText(f"Archivo: {b.get('fichero', '—')}  |  Tipo: {etiq}  |  VIN: {b.get('coche', '—')}")

        def crear_desde_dlg():
            self.crear_backup_manual()
            cargar_tabla()

        tabla.itemSelectionChanged.connect(on_seleccion)
        chk_filtrar_modulo.stateChanged.connect(lambda _: cargar_tabla())
        btn_refrescar_dlg.clicked.connect(lambda _: cargar_tabla())
        btn_crear_ahora.clicked.connect(crear_desde_dlg)
        cargar_tabla()

        # Botonera de acciones
        fila_btn = QHBoxLayout()
        fila_btn.setSpacing(10)

        btn_cargar = QPushButton("📥  Cargar en el Editor")
        btn_cargar.setProperty("class", "btn-secundario")
        btn_cargar.setFixedHeight(42)

        btn_restaurar_directo = QPushButton("⚡  Restaurar Directamente al Coche")
        btn_restaurar_directo.setProperty("class", "btn-peligro")
        btn_restaurar_directo.setFixedHeight(42)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setProperty("class", "btn-secundario")
        btn_cerrar.setFixedHeight(42)
        btn_cerrar.clicked.connect(dialogo.reject)

        fila_btn.addWidget(btn_cargar)
        fila_btn.addWidget(btn_restaurar_directo)
        fila_btn.addStretch()
        fila_btn.addWidget(btn_cerrar)
        dlg_lyt.addLayout(fila_btn)

        def ejecutar_cargar():
            row = tabla.currentRow()
            if row < 0 or row >= len(backups_cargados):
                QMessageBox.warning(dialogo, "Aviso", "Selecciona una copia de seguridad de la lista.")
                return
            b = backups_cargados[row]
            coding_hex = b["hex_formateado"]

            # Si el backup es de otro módulo, sincronizar el combo principal
            mod_b = b.get("modulo", "")
            if mod_b and mod_b != self.combo_coding.currentText():
                idx = self.combo_coding.findText(mod_b)
                if idx >= 0:
                    self.combo_coding.setCurrentIndex(idx)

            self._rebuilding_from_worker = True
            self.txt_coding_nuevo.setText(coding_hex)
            self._rebuilding_from_worker = False

            self._sync_checkboxes_desde_texto(coding_hex)
            self._actualizar_estado_botones_confort()

            self.escribir_consola(
                f"\n[BACKUP RESTAURADO AL EDITOR] Copia del {b.get('fecha_hora', '')}\n"
                f"  ▸ Módulo : {b.get('modulo', '')}\n"
                f"  ▸ Coding : {coding_hex}\n"
                f"  ▸ Valores cargados en el editor. Revisa los botones o pulsa '✏ Escribir' para grabar."
            )
            dialogo.accept()

        def ejecutar_restaurar():
            row = tabla.currentRow()
            if row < 0 or row >= len(backups_cargados):
                QMessageBox.warning(dialogo, "Aviso", "Selecciona una copia de seguridad de la lista.")
                return
            b = backups_cargados[row]
            coding_hex = b["hex_formateado"]
            modulo = b.get("modulo", self.combo_coding.currentText())
            fecha = b.get("fecha_hora", "")

            if QMessageBox.warning(
                dialogo, "⚠ Confirmar Restauración",
                f"¿Deseas sobreescribir la centralita {modulo} con el valor de la copia del {fecha}?\n\n"
                f"Coding a restaurar: {coding_hex}\n\n"
                "Se creará una copia de respaldo del estado actual antes de escribir.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

            dialogo.accept()

            idx = self.combo_coding.findText(modulo)
            if idx >= 0:
                self.combo_coding.setCurrentIndex(idx)

            self._rebuilding_from_worker = True
            self.txt_coding_nuevo.setText(coding_hex)
            self._rebuilding_from_worker = False
            self._sync_checkboxes_desde_texto(coding_hex)
            self._actualizar_estado_botones_confort()

            self.worker.set_accion(
                "escribir_coding",
                modulo=modulo,
                coding=coding_hex,
                coding_antiguo=self._coding_actual_leido or coding_hex
            )
            self.worker.start()

        btn_cargar.clicked.connect(ejecutar_cargar)
        btn_restaurar_directo.clicked.connect(ejecutar_restaurar)

        dialogo.exec()

    # ══════════════════════════════════════════════════════════════════════════
    #  HISTORIAL
    # ══════════════════════════════════════════════════════════════════════════
    def _cargar_historial(self):
        self.lista_sesiones.clear()
        sesiones = self._db.obtener_sesiones()
        for sid, vin, fecha in sesiones:
            item = QListWidgetItem(f"#{sid}  {vin}\n{fecha}")
            item.setData(Qt.ItemDataRole.UserRole, sid)
            self.lista_sesiones.addItem(item)

    def _sesion_seleccionada(self):
        items = self.lista_sesiones.selectedItems()
        if not items:
            return
        sesion_id = items[0].data(Qt.ItemDataRole.UserRole)
        dtcs = self._db.obtener_dtcs_sesion(sesion_id)
        self.tabla_hist_dtc.setRowCount(0)
        for dtc_id, modulo, codigo, estado, desc, ts in dtcs:
            row = self.tabla_hist_dtc.rowCount()
            self.tabla_hist_dtc.insertRow(row)
            self.tabla_hist_dtc.setItem(row, 0, QTableWidgetItem(modulo or "—"))
            item_c = QTableWidgetItem(codigo)
            item_c.setForeground(QColor("#FF6666"))
            self.tabla_hist_dtc.setItem(row, 1, item_c)
            self.tabla_hist_dtc.setItem(row, 2, QTableWidgetItem(desc or "—"))
            self.tabla_hist_dtc.setItem(row, 3, QTableWidgetItem(estado or "—"))

    # ══════════════════════════════════════════════════════════════════════════
    #  ACCIONES → WORKER
    # ══════════════════════════════════════════════════════════════════════════
    def _al_cambiar_modo_vehiculo(self, idx: int):
        if idx == 0:
            config.VEHICLE_MODE = "VAG"
            config.MODE = "real"
        elif idx == 1:
            config.VEHICLE_MODE = "VAG_KLINE"
            config.MODE = "real"
        elif idx == 2:
            config.VEHICLE_MODE = "OBD2_UNIVERSAL"
            config.MODE = "real"
        elif idx == 3:
            config.VEHICLE_MODE = "OPEL_CONFORT"
            config.MODE = "real"
        elif idx == 4:
            config.VEHICLE_MODE = "VAG"
            config.MODE = "simulado"
        elif idx == 5:
            config.VEHICLE_MODE = "VAG_KLINE"
            config.MODE = "simulado"
        elif idx == 6:
            config.VEHICLE_MODE = "OBD2_UNIVERSAL"
            config.MODE = "simulado"
        else:
            config.VEHICLE_MODE = "VAG"
            config.MODE = "real"

        if idx in (1, 5):  # Modos VW Polo 9N3 K-Line
            if hasattr(self, "btn_nav") and len(self.btn_nav) > 4:
                self.btn_nav[4].setText("🔧  Soft Coding")
            if hasattr(self, "lbl_vin"):
                self.lbl_vin.setText("6Q0959433E (VW Polo 9N3)")
            if hasattr(self, "lbl_vehiculo_desc"):
                self.lbl_vehiculo_desc.setText("Volkswagen Polo 9N3 1.9 TDI (101 CV AXR/ATD) · 2007 (PQ24)")
            if hasattr(self, "lbl_protocolo_sub"):
                self.lbl_protocolo_sub.setText("K-Line Pin 7 · KWP1281 / KWP2000")
            if hasattr(self, "lbl_red"):
                self.lbl_red.setText("K-LINE: 10.4 kbps")

            self._coding_actual_leido = "00019"
            if hasattr(self, "txt_coding_actual"):
                self.txt_coding_actual.setText(self._coding_actual_leido)
            if hasattr(self, "txt_coding_nuevo"):
                self.txt_coding_nuevo.setText(self._coding_actual_leido)

            # Aislamiento Mantenimiento Polo 9N3
            if hasattr(self, "tabs_mantenimiento"):
                for i in range(self.tabs_mantenimiento.count()):
                    self.tabs_mantenimiento.setTabVisible(i, i in (1, 5, 7))
                self.tabs_mantenimiento.setCurrentIndex(1)
            if hasattr(self, "lbl_maint_titulo"):
                self.lbl_maint_titulo.setText("Wizards de Mantenimiento y Servicio — VW Polo 9N3")
            if hasattr(self, "lbl_maint_subtitulo"):
                self.lbl_maint_subtitulo.setText(
                    "Operaciones guiadas de taller para VW Polo 9N3 (Plataforma PQ24): Reset de servicio SRI (17), "
                    "purga hidráulica asistida ABS (03) y calibración sensor de dirección G85 (03/44). "
                    "Se han filtrado automáticamente los sistemas no equipados (Caja automática, DPF, EPB, BEM, MMI)."
                )

            # Aislamiento Soft Coding Polo 9N3
            if hasattr(self, "lbl_coding_titulo"):
                self.lbl_coding_titulo.setText("Soft Coding y Confort — VW Polo 9N3 (PQ24 K-Line)")
            if hasattr(self, "lbl_coding_subtitulo"):
                self.lbl_coding_subtitulo.setText(
                    "Activa o desactiva funciones de confort adaptadas para VW Polo 9N3 (KWP1281). "
                    "En la plataforma PQ24 la configuración se realiza mediante canales de adaptación y codificación corta (Soft Coding)."
                )
            if hasattr(self, "lbl_coding_orig_t"):
                self.lbl_coding_orig_t.setText("Soft Coding Original (Leído de EEPROM):")
            if hasattr(self, "lbl_coding_nuevo_t"):
                self.lbl_coding_nuevo_t.setText("Nuevo Soft Coding / Canal (Resultado en vivo):")
            if hasattr(self, "txt_coding_actual"):
                self.txt_coding_actual.setPlaceholderText("Pulsa 'Leer Coding Actual' para leer la EEPROM...")
            if hasattr(self, "txt_coding_nuevo"):
                self.txt_coding_nuevo.setPlaceholderText("Se actualiza al seleccionar opciones de confort...")
            if hasattr(self, "btn_needle"):
                self.btn_needle.setVisible(False)
            if hasattr(self, "btn_retrovisores"):
                self.btn_retrovisores.setVisible(False)
            if hasattr(self, "btn_gw"):
                self.btn_gw.setVisible(False)
            if hasattr(self, "tabs_coding"):
                self.tabs_coding.setTabText(0, "🚗  Funciones de Confort — VW Polo 9N3 (KWP1281)")
                self.tabs_coding.setTabVisible(1, False)

            modulos_polo_dtc = [
                "Confort / BCM (46)",
                "Central Eléctrica / Luces (09)",
                "Motor (01)",
                "ABS / Frenos (03)",
                "Cuadro de Instrumentos (17)",
                "Airbag (15)",
                "Climatización (08)",
                "Radio / Sonido (56)",
                "Dirección Asistida TRW (44)",
            ]
            modulos_polo_actu = list(ACTUADORES_POLO_KLINE.keys())
            modulos_polo_adapt = list(ADAPTACIONES_POLO_KLINE.keys())

            if hasattr(self, "combo_dtc"):
                self.combo_dtc.blockSignals(True)
                self.combo_dtc.clear()
                self.combo_dtc.addItems(modulos_polo_dtc)
                self.combo_dtc.setCurrentText("Confort / BCM (46)")
                self.combo_dtc.blockSignals(False)

            if hasattr(self, "combo_coding"):
                self.combo_coding.blockSignals(True)
                self.combo_coding.clear()
                self.combo_coding.addItems([
                    "Confort / BCM (46)",
                    "Central Eléctrica / Luces (09)",
                    "Cuadro de Instrumentos (17)",
                    "Dirección Asistida TRW (44)",
                    "Motor 1.9 TDI (01)",
                    "Airbag (15)",
                    "Climatización (08)",
                    "Radio / Sonido (56)",
                ])
                self.combo_coding.setCurrentText("Confort / BCM (46)")
                self.combo_coding.blockSignals(False)
                self._cargar_catalogo_confort(self.combo_coding.currentText())

            if hasattr(self, "combo_adapt"):
                self.combo_adapt.blockSignals(True)
                self.combo_adapt.clear()
                self.combo_adapt.addItems(modulos_polo_adapt)
                self.combo_adapt.setCurrentText("Confort / BCM (46)")
                self.combo_adapt.blockSignals(False)
                self._rebuild_adaptaciones(self.combo_adapt.currentText())

            if hasattr(self, "combo_actu"):
                self.combo_actu.blockSignals(True)
                self.combo_actu.clear()
                self.combo_actu.addItems(modulos_polo_actu)
                self.combo_actu.setCurrentText("Confort / BCM (46)")
                self.combo_actu.blockSignals(False)
                self._rebuild_actuadores(self.combo_actu.currentText())

            self._actualizar_estado_botones_confort()

        elif idx in (2, 3, 6):  # Modos Opel
            if hasattr(self, "btn_nav") and len(self.btn_nav) > 4:
                self.btn_nav[4].setText("🔧  Codificación")
            if hasattr(self, "lbl_coding_orig_t"):
                self.lbl_coding_orig_t.setText("Codificación Actual (BCM / IPC):")
            if hasattr(self, "lbl_coding_nuevo_t"):
                self.lbl_coding_nuevo_t.setText("Nueva Codificación:")
            if hasattr(self, "lbl_vin"):
                self.lbl_vin.setText("W0L0SDL6874086807")
            if hasattr(self, "lbl_vehiculo_desc"):
                self.lbl_vehiculo_desc.setText("Opel Corsa D 1.3 CDTI (90 CV Z13DTH) · Confort & Motor")
            if hasattr(self, "lbl_protocolo_sub"):
                self.lbl_protocolo_sub.setText("CAN ISO 15765-4 / GMLAN")
            if hasattr(self, "lbl_red"):
                self.lbl_red.setText("BUS CAN: 500k / 95k")

            self._coding_actual_leido = "06 05 02 00"
            if hasattr(self, "txt_coding_actual"):
                self.txt_coding_actual.setText(self._coding_actual_leido)
            if hasattr(self, "txt_coding_nuevo"):
                self.txt_coding_nuevo.setText(self._coding_actual_leido)

            # Aislamiento Mantenimiento Opel Corsa
            if hasattr(self, "tabs_mantenimiento"):
                for i in range(self.tabs_mantenimiento.count()):
                    self.tabs_mantenimiento.setTabVisible(i, i == 1)
                self.tabs_mantenimiento.setCurrentIndex(1)
            if hasattr(self, "lbl_maint_titulo"):
                self.lbl_maint_titulo.setText("Wizards de Mantenimiento y Servicio — Opel Corsa D")
            if hasattr(self, "lbl_maint_subtitulo"):
                self.lbl_maint_subtitulo.setText(
                    "Operaciones guiadas de taller para Opel Corsa D: Reset de intervalos de servicio e inspección. "
                    "Se han filtrado los asistentes específicos de VAG."
                )

            # Aislamiento Long Coding Opel Corsa
            if hasattr(self, "lbl_coding_titulo"):
                self.lbl_coding_titulo.setText("Codificación y Variantes — Opel Corsa D (GMLAN / CAN)")
            if hasattr(self, "lbl_coding_subtitulo"):
                self.lbl_coding_subtitulo.setText(
                    "Configura opciones de confort y variantes para BCM e IPC en Opel Corsa D."
                )
            if hasattr(self, "btn_needle"):
                self.btn_needle.setVisible(True)
            if hasattr(self, "btn_retrovisores"):
                self.btn_retrovisores.setVisible(False)  # Solo aplica en Audi A6
            if hasattr(self, "btn_gw"):
                self.btn_gw.setVisible(False)

            if hasattr(self, "tabs_coding"):
                self.tabs_coding.setTabText(0, "🚗  Funciones de Confort — Opel Corsa D")
                self.tabs_coding.setTabVisible(1, True)

            modulos_opel_dtc = list(OPEL_MODULES_CONFIG.keys()) + ["Todos los Sistemas OBD-II"]
            modulos_opel_actu = list(ACTUADORES_OPEL.keys())
            modulos_opel_adapt = list(ADAPTACIONES_OPEL.keys())

            if hasattr(self, "combo_dtc"):
                self.combo_dtc.blockSignals(True)
                self.combo_dtc.clear()
                self.combo_dtc.addItems(modulos_opel_dtc)
                if idx == 3:
                    self.combo_dtc.setCurrentText("BCM Confort / Carrocería")
                self.combo_dtc.blockSignals(False)

            if hasattr(self, "combo_coding"):
                self.combo_coding.blockSignals(True)
                self.combo_coding.clear()
                self.combo_coding.addItems(["BCM Confort / Carrocería", "IPC Cuadro Instrumentos", "Motor / ECM"])
                if idx == 3:
                    self.combo_coding.setCurrentText("BCM Confort / Carrocería")
                self.combo_coding.blockSignals(False)
                self._cargar_catalogo_confort(self.combo_coding.currentText())

            if hasattr(self, "combo_adapt"):
                self.combo_adapt.blockSignals(True)
                self.combo_adapt.clear()
                self.combo_adapt.addItems(modulos_opel_adapt)
                if idx == 3:
                    self.combo_adapt.setCurrentText("BCM Confort / Carrocería")
                self.combo_adapt.blockSignals(False)
                self._rebuild_adaptaciones(self.combo_adapt.currentText())

            if hasattr(self, "combo_actu"):
                self.combo_actu.blockSignals(True)
                self.combo_actu.clear()
                self.combo_actu.addItems(modulos_opel_actu)
                if idx == 3:
                    self.combo_actu.setCurrentText("BCM Confort / Carrocería")
                self.combo_actu.blockSignals(False)
                self._rebuild_actuadores(self.combo_actu.currentText())

            self._actualizar_estado_botones_confort()
        else:  # Audi / VAG (0 o 4)
            config.VEHICLE_MODE = "VAG"
            if hasattr(self, "btn_nav") and len(self.btn_nav) > 4:
                self.btn_nav[4].setText("🔧  Long Coding")
            if hasattr(self, "lbl_coding_orig_t"):
                self.lbl_coding_orig_t.setText("Coding Original (Leído de la centralita):")
            if hasattr(self, "lbl_coding_nuevo_t"):
                self.lbl_coding_nuevo_t.setText("Nuevo Coding (Resultado en vivo):")
            if hasattr(self, "txt_coding_actual"):
                self.txt_coding_actual.setPlaceholderText("Pulsa 'Leer Coding Actual'...")
            if hasattr(self, "txt_coding_nuevo"):
                self.txt_coding_nuevo.setPlaceholderText("Se actualiza al activar funciones o editar bits...")
            if hasattr(self, "lbl_vin"):
                self.lbl_vin.setText("WAUZZZ4F000000000")
            if hasattr(self, "lbl_vehiculo_desc"):
                self.lbl_vehiculo_desc.setText("Audi A6 C6 2.7 TDI V6 Common Rail (190 CV) · Facelift 2010")
            if hasattr(self, "lbl_protocolo_sub"):
                self.lbl_protocolo_sub.setText("TP 2.0 CAN Nativo (KWP2000)")
            if hasattr(self, "lbl_red"):
                self.lbl_red.setText("BUS CAN: 500 kbps")

            self._coding_actual_leido = ""
            if hasattr(self, "txt_coding_actual"):
                self.txt_coding_actual.setText("")
            if hasattr(self, "txt_coding_nuevo"):
                self.txt_coding_nuevo.setText("")

            # Restaurar todos los Wizards de Mantenimiento de Audi A6
            if hasattr(self, "tabs_mantenimiento"):
                for i in range(self.tabs_mantenimiento.count()):
                    self.tabs_mantenimiento.setTabVisible(i, True)
                self.tabs_mantenimiento.setCurrentIndex(0)
            if hasattr(self, "lbl_maint_titulo"):
                self.lbl_maint_titulo.setText("Wizards de Mantenimiento y Servicio (1 Clic)")
            if hasattr(self, "lbl_maint_subtitulo"):
                self.lbl_maint_subtitulo.setText(
                    "Operaciones automatizadas y guiadas de taller para Grupo VAG / Audi A6 C6 (4F Facelift): "
                    "freno de mano eléctrico, reseteo de intervalos de servicio, monitor DPF, salud de inyectores Common Rail y registro de batería."
                )

            # Restaurar Long Coding Audi A6
            if hasattr(self, "lbl_coding_titulo"):
                self.lbl_coding_titulo.setText("Long Coding y Funciones de Confort — Audi A6 2.7 TDI (2010)")
            if hasattr(self, "lbl_coding_subtitulo"):
                self.lbl_coding_subtitulo.setText(
                    "Activa o desactiva funciones en texto claro para tu Audi A6 (modifica los bits por detrás), "
                    "o usa el editor bit a bit. Se realiza backup automático antes de escribir."
                )
            if hasattr(self, "btn_needle"):
                self.btn_needle.setVisible(True)
            if hasattr(self, "btn_retrovisores"):
                self.btn_retrovisores.setVisible(True)  # Aplica en Audi A6 con motor de plegado

            if hasattr(self, "btn_gw"):
                self.btn_gw.setVisible(True)
            if hasattr(self, "tabs_coding"):
                self.tabs_coding.setTabText(0, "🚗  Funciones de Confort — Audi A6 (Texto Claro)")
                self.tabs_coding.setTabVisible(1, True)

            modulos_vag = list(TP20_MODULE_ADDR.keys())
            modulos_vag_actu = list(ACTUADORES_VAG.keys())
            modulos_vag_adapt = list(ADAPTACIONES_VAG.keys())

            if hasattr(self, "combo_dtc"):
                self.combo_dtc.blockSignals(True)
                self.combo_dtc.clear()
                self.combo_dtc.addItems(modulos_vag)
                self.combo_dtc.setCurrentText("Cuadro Instrumentos (17)")
                self.combo_dtc.blockSignals(False)

            if hasattr(self, "combo_coding"):
                self.combo_coding.blockSignals(True)
                self.combo_coding.clear()
                self.combo_coding.addItems(modulos_vag)
                idx_c = self.combo_coding.findText("Cuadro Instrumentos (17)")
                if idx_c >= 0:
                    self.combo_coding.setCurrentIndex(idx_c)
                self.combo_coding.blockSignals(False)
                self._cargar_catalogo_confort(self.combo_coding.currentText())

            if hasattr(self, "combo_adapt"):
                self.combo_adapt.blockSignals(True)
                self.combo_adapt.clear()
                self.combo_adapt.addItems(modulos_vag_adapt)
                idx_a = self.combo_adapt.findText("Cuadro Instrumentos (17)")
                if idx_a >= 0:
                    self.combo_adapt.setCurrentIndex(idx_a)
                self.combo_adapt.blockSignals(False)
                self._rebuild_adaptaciones(self.combo_adapt.currentText())

            if hasattr(self, "combo_actu"):
                self.combo_actu.blockSignals(True)
                self.combo_actu.clear()
                self.combo_actu.addItems(modulos_vag_actu)
                idx_ac = self.combo_actu.findText("Cuadro Instrumentos (17)")
                if idx_ac >= 0:
                    self.combo_actu.setCurrentIndex(idx_ac)
                self.combo_actu.blockSignals(False)
                self._rebuild_actuadores(self.combo_actu.currentText())

            self._actualizar_estado_botones_confort()

    def iniciar_conexion(self):
        idx = self.combo_modo.currentIndex() if hasattr(self, "combo_modo") else 0
        if idx == 0:
            config.MODE = "real"
            config.VEHICLE_MODE = "VAG"
            config.SERIAL_PORT = "AUTO"
            self.escribir_consola("\n[CONEXIÓN] Modo AUDI A6 C6 (CANable 2.0 Real) activado. Buscando adaptador...")
        elif idx == 1:
            config.MODE = "real"
            config.VEHICLE_MODE = "VAG_KLINE"
            config.SERIAL_PORT = "AUTO"
            self.escribir_consola("\n[CONEXIÓN] Modo VW POLO 9N3 K-LINE (Cable FTDI Real) activado...")
            self.escribir_consola("  ▸ Protocolo: KWP1281 / K-Line Pin 7 a 10.400 baudios (Slow Init 5 Baud)")
            self.escribir_consola("  ▸ Bus objetivo: Confort 46, Motor 01, ABS 03, Cuadro 17, Airbag 15")
        elif idx == 2:
            config.MODE = "real"
            config.VEHICLE_MODE = "OBD2_UNIVERSAL"
            config.SERIAL_PORT = "AUTO"
            self.escribir_consola("\n[CONEXIÓN] Modo OPEL CORSA HSCAN (Pines 6 y 14 - 500 kbps) activado...")
            self.escribir_consola("  ▸ Protocolo: ISO 15765-4 (CAN 11-bit 500 kbps)")
            self.escribir_consola("  ▸ Bus objetivo: Motor / ECM, ABS/ESP, Dirección")
        elif idx == 3:
            config.MODE = "real"
            config.VEHICLE_MODE = "OPEL_CONFORT"
            config.SERIAL_PORT = "AUTO"
            self.escribir_consola("\n[CONEXIÓN] Modo OPEL CORSA MSCAN (Pines 3 y 11 - 95 kbps) activado...")
            self.escribir_consola("  ▸ Protocolo: GM GMLAN / ISO-TP Confort (95.238 kbps)")
            self.escribir_consola("  ▸ Bus objetivo: BCM Carrocería, Cuadro IPC, Clima, Pantalla")
        elif idx == 4:
            config.MODE = "simulado"
            config.VEHICLE_MODE = "VAG"
            self.escribir_consola("\n[CONEXIÓN] Modo SIMULADO Audi A6 C6 activado (banco de pruebas en PC).")
        elif idx == 5:
            config.MODE = "simulado"
            config.VEHICLE_MODE = "VAG_KLINE"
            self.escribir_consola("\n[CONEXIÓN] Modo SIMULADO VW Polo 9N3 K-Line activado (banco de pruebas en PC).")
            self.escribir_consola("  ▸ Emulador K-Line KWP1281: Confort (46), Motor 1.9 TDI EDC15 (01), ABS (03)")
        else:
            config.MODE = "simulado"
            config.VEHICLE_MODE = "OBD2_UNIVERSAL"
            self.escribir_consola("\n[CONEXIÓN] Modo SIMULADO Opel Corsa D activado (banco de pruebas en PC).")

        self._al_cambiar_modo_vehiculo(idx)
        self.worker.set_accion("conectar")
        self.worker.start()

    def escanear_modulo(self):
        self.tabla_dtc.setRowCount(0)
        self._dtcs_datos.clear()
        self.worker.set_accion("escanear_dtc", modulo=self.combo_dtc.currentText())
        self.worker.start()

    def auto_scan(self):
        self.tabla_dtc.setRowCount(0)
        self._dtcs_datos.clear()
        self.escribir_consola("\n[INFO] Iniciando Auto-Scan de todos los módulos...")
        self.worker.set_accion("auto_scan")
        self.worker.start()

    def borrar_fallos(self):
        modulo = self.combo_dtc.currentText()
        if QMessageBox.warning(
            self, "Confirmar Borrado",
            f"¿Borrar todos los fallos del módulo:\n{modulo}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.worker.set_accion("borrar_dtc", modulo=modulo)
            self.worker.start()

    def leer_sensores(self):
        if self.worker.isRunning():
            return
        self.worker.set_accion("leer_sensores")
        self.worker.start()

    def toggle_monitoreo_sensores(self):
        if not hasattr(self, "_timer_sensores"):
            self._timer_sensores = QTimer(self)
            self._timer_sensores.setInterval(1200)
            self._timer_sensores.timeout.connect(self.leer_sensores)

        if self._timer_sensores.isActive():
            self._timer_sensores.stop()
            self.btn_auto_sensores.setText("🔄  Monitoreo Continuo: OFF")
            self.btn_auto_sensores.setProperty("class", "btn-secundario")
            self.btn_auto_sensores.style().unpolish(self.btn_auto_sensores)
            self.btn_auto_sensores.style().polish(self.btn_auto_sensores)
            self.escribir_consola("[INFO] Monitoreo continuo detenido.")
        else:
            self._timer_sensores.start()
            self.btn_auto_sensores.setText("⏹  Monitoreo Continuo: ON")
            self.btn_auto_sensores.setProperty("class", "btn-peligro")
            self.btn_auto_sensores.style().unpolish(self.btn_auto_sensores)
            self.btn_auto_sensores.style().polish(self.btn_auto_sensores)
            self.escribir_consola("[INFO] Monitoreo continuo activado (cada 1.2s).")
            self.leer_sensores()

    def toggle_grabacion(self):
        if not self._grabando_csv:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            ruta = os.path.join(config.DATA_DIR, f"sensores_{ts}.csv")
            os.makedirs(config.DATA_DIR, exist_ok=True)
            self._csv_file = open(ruta, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(["Timestamp", "Sensor", "Valor", "Unidad"])
            self._grabando_csv = True
            self.btn_grabar.setText("⏹  Parar Grabación CSV")
            self.btn_grabar.setProperty("class", "btn-peligro")
            self.btn_grabar.style().unpolish(self.btn_grabar)
            self.btn_grabar.style().polish(self.btn_grabar)
            self.lbl_grabando.setText(f"⏺ Grabando → {ruta}")
            self.escribir_consola(f"[CSV] Grabación iniciada → {ruta}")
        else:
            self._grabando_csv = False
            if self._csv_file:
                self._csv_file.close()
                self._csv_file = None
                self._csv_writer = None
            self.btn_grabar.setText("⏺  Iniciar Grabación CSV")
            self.btn_grabar.setProperty("class", "btn-secundario")
            self.btn_grabar.style().unpolish(self.btn_grabar)
            self.btn_grabar.style().polish(self.btn_grabar)
            self.lbl_grabando.setText("")
            self.escribir_consola("[CSV] Grabación detenida.")

    def activar_needle_sweep_rapido(self):
        """Activa el test de agujas (Needle Sweep) y Lap Timer en el Cuadro J285 en 1 solo clic."""
        if QMessageBox.question(
            self, "🚀 Activar Needle Sweep + Lap Timer",
            "¿Deseas activar el test/barrido de agujas al arrancar y el cronómetro FIS en tu Audi A6 C6?\n\n"
            "El sistema realizará el protocolo quirúrgico verificado VAG:\n"
            "1. Conexión nativa TP 2.0 con el Cuadro J285 (0x07 / 0x17)\n"
            "2. Copia de seguridad obligatoria previa a disco\n"
            "3. Sesión de Taller VAG (0x89) con inyección de huella WSC oficial (DID F198)\n"
            "4. Modificación quirúrgica del Byte 1 (0x5F: +Needle Sweep +Lap Timer)\n"
            "5. Verificación inmediata byte a byte en memoria EEPROM",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.escribir_consola("\n[ACCION] Iniciando activación quirúrgica de Needle Sweep + Lap Timer...")
            self.combo_coding.setCurrentText("Cuadro Instrumentos (17)")
            self.worker.set_accion("activar_needle_sweep")
            self.worker.start()

    def activar_plegado_retrovisores_rapido(self):
        """Informa sobre el estado del plegado automático de retrovisores en el Audi A6 C6."""
        QMessageBox.information(
            self, "🪞 Plegado de Retrovisores — Audi A6 C6 (4F)",
            "INFORMACIÓN TÉCNICA VAG OFICIAL:\n\n"
            "En la plataforma Audi A6 C6 (2004–2011), las centralitas de confort (J393) y puertas "
            "(J386/J387) NO disponen en su firmware de fábrica de la rutina para plegar espejos desde "
            "el mando a distancia.\n\n"
            "• Los espejos abaten correctamente mediante el mando giratorio de la puerta.\n"
            "• Para conseguir el plegado automático al cerrar con el mando en un A6 C6, la solución "
            "estándar probada es un módulo CAN confort plug&play (~25€) intercalado en la puerta del conductor."
        )
        self.escribir_consola(
            "\n[INFO RETROVISORES] En el Audi A6 C6 el abatimiento desde mando no existe en el microcódigo "
            "de fábrica de la centralita confort. Para plegado automático con mando se requiere el módulo CAN plug&play."
        )

    def leer_coding(self):
        self.worker.set_accion("leer_coding", modulo=self.combo_coding.currentText())
        self.worker.start()

    def crear_backup_manual(self):
        """Crea una copia de seguridad manual inmediata del coding actual en pantalla."""
        coding = self.txt_coding_nuevo.text().strip() or self.txt_coding_actual.text().strip() or self._coding_actual_leido
        if not coding:
            self.escribir_consola("\n[AVISO] Primero pulsa '📖 Leer Coding Actual' para cargar la codificación de la centralita.")
            QMessageBox.warning(self, "Aviso", "Primero pulsa '📖 Leer Coding Actual' para tener un valor que respaldar.")
            return

        modulo = self.combo_coding.currentText()
        vin = self.lbl_vin.text()
        if "—" in vin or not vin.strip():
            vin = getattr(self.worker, "vin", None) or "WAUZZZ4G7BN000000"

        try:
            bm = BackupManager()
            ruta = bm.guardar_backup(modulo=modulo, coche=vin, bytes_coding=coding, etiqueta="MANUAL")
            nombre_f = os.path.basename(ruta)
            self.escribir_consola(f"\n[✓ BACKUP MANUAL CREADO] Guardado con éxito:\n  ▸ Archivo: {nombre_f}\n  ▸ Módulo:  {modulo}\n  ▸ Coding:   {coding}")
            QMessageBox.information(
                self, "Backup Guardado",
                f"Copia de seguridad guardada con éxito:\n\n"
                f"Archivo: {nombre_f}\n"
                f"Módulo:  {modulo}\n"
                f"Coding:   {coding}"
            )
        except Exception as e:
            self.escribir_consola(f"[ERROR] No se pudo guardar el backup: {e}")

    def escribir_coding(self):
        if self.es_modo_kline:
            nuevo = self.txt_coding_nuevo.text().strip()
            if not nuevo:
                self.escribir_consola("[ERROR] Campo de nuevo coding vacío.")
                return
            modulo = self.combo_coding.currentText()
            self.escribir_consola(f"\n[K-LINE CODING] Grabando Soft Coding '{nuevo}' en {modulo}...")
            self.worker.set_accion("escribir_coding", modulo=modulo, coding=nuevo, coding_antiguo=self._coding_actual_leido or "00067")
            self.worker.start()
            return

        if not self._coding_actual_leido:
            if self.es_modo_opel:
                self._coding_actual_leido = self.txt_coding_nuevo.text().strip() or "06 05 02 00"
                self.txt_coding_actual.setText(self._coding_actual_leido)
            else:
                self.escribir_consola(
                    "[ERROR] Primero debes pulsar 'Leer Coding Actual' para que el sistema tenga "
                    "una copia de respaldo obligatoria antes de escribir."
                )
                QMessageBox.warning(
                    self, "Aviso de Seguridad",
                    "Primero debes pulsar 'Leer Coding Actual'.\n\n"
                    "Por seguridad, AudiDiag Pro necesita tener la copia original del coding "
                    "para hacer un backup automático antes de realizar cualquier cambio."
                )
                return

        nuevo = self.txt_coding_nuevo.text().strip()
        if not nuevo:
            self.escribir_consola("[ERROR] Campo de nuevo coding vacío.")
            return

        orig_l = self._coding_actual_leido.replace(" ", "")
        nuevo_l = nuevo.replace(" ", "")

        if orig_l and len(nuevo_l) != len(orig_l):
            self.escribir_consola(
                f"[ERROR] Longitud incorrecta: original {len(orig_l)//2} bytes, nuevo {len(nuevo_l)//2} bytes."
            )
            return
        try:
            bytes.fromhex(nuevo_l)
        except ValueError:
            self.escribir_consola("[ERROR] El coding contiene caracteres no hexadecimales.")
            return

        modulo = self.combo_coding.currentText()
        if QMessageBox.warning(
            self, "⚠ Confirmar Escritura",
            f"Módulo: {modulo}\n\nOriginal: {self._coding_actual_leido}\nNuevo:    {nuevo}\n\n"
            "Se hará backup automático. ¿Confirmar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            self.escribir_consola("[INFO] Escritura cancelada.")
            return

        # Guardar copia de seguridad garantizada en disco antes de enviar la orden
        try:
            bm = BackupManager()
            vin = self.lbl_vin.text()
            if "—" in vin or not vin.strip():
                vin = getattr(self.worker, "vin", None) or "WAUZZZ4G7BN000000"
            ruta_prev = bm.guardar_backup(
                modulo=modulo, coche=vin, bytes_coding=self._coding_actual_leido,
                etiqueta="PREVIO_MODIFICACION"
            )
            self.escribir_consola(f"\n[SEGURIDAD] Guardado backup preventivo antes de escribir: {os.path.basename(ruta_prev)}")
        except Exception as e:
            self.escribir_consola(f"[WARN] Error al guardar backup preventivo: {e}")

        self.worker.set_accion(
            "escribir_coding", modulo=modulo,
            coding=nuevo, coding_antiguo=self._coding_actual_leido
        )
        self.worker.start()

    def leer_adaptaciones_modulo(self):
        modulo = self.combo_adapt.currentText()
        self.worker.set_accion("adaptaciones_modulo", modulo=modulo)
        self.worker.start()

    def escribir_adaptacion(self, nombre: str, canal: int, valor: float, confirmar: bool = True):
        modulo = self.combo_adapt.currentText()
        if not confirmar or QMessageBox.question(
            self, "Confirmar Adaptación",
            f"Escribir adaptación '{nombre}' = {valor} en {modulo}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.worker.set_accion("adaptacion_escribir", modulo=modulo,
                                   nombre=nombre, canal=canal, valor=valor)
            self.worker.start()

    def test_actuador(self, nombre: str, canal: str, duracion: int, confirmar: bool = True):
        modulo = self.combo_actu.currentText()
        if not confirmar or QMessageBox.question(
            self, "Confirmar Activación",
            f"Activar '{nombre}' en {modulo}?\n\nEl componente se activará ~{duracion}s.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.worker.set_accion("test_actuador", modulo=modulo,
                                   nombre=nombre, canal=canal, duracion=duracion)
            self.worker.start()

    def generar_reporte(self):
        if not self.worker.sesion_id:
            self.escribir_consola("[ERROR] No hay sesión activa. Conéctate primero.")
            return
        gen = ReportGenerator()
        ruta = gen.generar_reporte_txt(self.worker.sesion_id)
        self.escribir_consola(f"\n[✓] Informe guardado en:\n{ruta}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())
