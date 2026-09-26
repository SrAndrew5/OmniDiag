# -*- coding: utf-8 -*-
"""
ui/dialogo_polo_kline.py
══════════════════════════════════════════════════════════════════════════════
Asistente Gráfico Oficial VAG K-Line (VW Polo 9N3 / Plataforma PQ24).
Permite:
  1. Conexión directa K-Line por puerto serie FTDI (Pin 7) o Modo Simulado.
  2. Gestión 1-Clic de Canales de Confort del Polo:
     - Canal 04: Auto-Unlock al extraer llave.
     - Canal 06: Silenciar pitido/bocinazo de cierre con mando.
     - Canal 07: Desactivar apertura selectiva (1 toque abre todo).
     - Canal 03: Auto-Lock antiasalto a 15 km/h.
  3. Diagnóstico completo de averías en Motor 1.9 TDI (01) y Confort (46).
══════════════════════════════════════════════════════════════════════════════
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QWidget, QScrollArea, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from obd.vag_kline import VAGKLineClient, POLO_9N3_CONFORT_CHANNELS
from ui.dialogo_ficha_dtc import DialogoFichaDTC


class DialogoPoloKLine(QDialog):
    """
    Ventana interactiva de configuración y diagnóstico para VW Polo 9N3 vía K-Line.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cliente = VAGKLineClient(port_name="MOCK")
        self.setWindowTitle("🚗 Asistente VAG K-Line — VW Polo 9N3 (PQ24)")
        self.setMinimumSize(780, 640)
        self.resize(820, 680)
        self._init_ui()
        self._cargar_puertos()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0A0F1D;
                color: #F8FAFC;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QFrame.card {
                background-color: #131E32;
                border: 1px solid #1E2E4A;
                border-radius: 8px;
                padding: 12px;
            }
            QComboBox {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
            }
            QPushButton.btn-primary {
                background-color: #0284C7;
                color: white;
                border: none;
            }
            QPushButton.btn-primary:hover {
                background-color: #0369A1;
            }
            QPushButton.btn-success {
                background-color: #10B981;
                color: white;
                border: none;
            }
            QPushButton.btn-success:hover {
                background-color: #059669;
            }
            QTableWidget {
                background-color: #0F172A;
                border: 1px solid #1E293B;
                gridline-color: #1E293B;
                color: #F8FAFC;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #1E293B;
                color: #94A3B8;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
        """)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(20, 20, 20, 20)
        lyt.setSpacing(14)

        # ── Cabecera ──
        header = QHBoxLayout()
        tit_box = QVBoxLayout()
        tit = QLabel("Asistente K-Line: VW Polo (2007) 1.9 TDI")
        tit.setStyleSheet("font-size: 18px; font-weight: bold; color: #38BDF8;")
        sub = QLabel("Conexión directa por Pin 7 K-Line (FTDI FT232RL) — Módulos 46 (Confort) y 01 (Motor)")
        sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        tit_box.addWidget(tit)
        tit_box.addWidget(sub)
        header.addLayout(tit_box)
        header.addStretch()

        # Selector de Puerto
        port_box = QHBoxLayout()
        port_lbl = QLabel("Puerto Serie:")
        port_lbl.setStyleSheet("color: #CBD5E1; font-weight: bold;")
        self.combo_puerto = QComboBox()
        self.btn_conectar = QPushButton("🔌 Conectar K-Line")
        self.btn_conectar.setProperty("class", "btn-primary")
        self.btn_conectar.clicked.connect(self._toggle_conexion)
        port_box.addWidget(port_lbl)
        port_box.addWidget(self.combo_puerto)
        port_box.addWidget(self.btn_conectar)
        header.addLayout(port_box)

        lyt.addLayout(header)

        # ── Estado de Conexión ──
        self.card_info = QFrame()
        self.card_info.setProperty("class", "card")
        info_lyt = QHBoxLayout(self.card_info)
        self.lbl_estado_ecu = QLabel("⚪ Estado: No conectado. Selecciona el puerto COM o Modo Simulado.")
        self.lbl_estado_ecu.setStyleSheet("font-size: 12px; color: #94A3B8; font-weight: 500;")
        info_lyt.addWidget(self.lbl_estado_ecu)
        lyt.addWidget(self.card_info)

        # ── Pestaña de Canales de Confort del Polo (El pedido del padre) ──
        card_confort = QFrame()
        card_confort.setProperty("class", "card")
        c_lyt = QVBoxLayout(card_confort)
        c_tit = QLabel("🛠️ Configuración de Confort del Polo (Módulo 46)")
        c_tit.setStyleSheet("font-size: 14px; font-weight: bold; color: #F8FAFC;")
        c_lyt.addWidget(c_tit)

        # Grid de Canales
        self.filas_canales = {}
        for canal, info in POLO_9N3_CONFORT_CHANNELS.items():
            f_box = QHBoxLayout()
            c_desc = QVBoxLayout()
            c_nom = QLabel(f"Canal {canal:02d} — {info['nombre']}")
            c_nom.setStyleSheet("font-weight: bold; color: #E2E8F0; font-size: 13px;")
            c_sub = QLabel(info['desc'])
            c_sub.setStyleSheet("color: #64748B; font-size: 11px;")
            c_desc.addWidget(c_nom)
            c_desc.addWidget(c_sub)

            lbl_val = QLabel("Valor: --")
            lbl_val.setStyleSheet("font-weight: bold; color: #F59E0B; min-width: 140px;")
            self.filas_canales[canal] = lbl_val

            btn_accion = QPushButton()
            if canal == 6:
                btn_accion.setText("🔇 Silenciar Pitido")
                btn_accion.setProperty("class", "btn-success")
                btn_accion.clicked.connect(lambda _, c=canal: self._cambiar_canal(c, 0))
            elif canal == 4:
                btn_accion.setText("🔓 Activar Auto-Unlock")
                btn_accion.setProperty("class", "btn-success")
                btn_accion.clicked.connect(lambda _, c=canal: self._cambiar_canal(c, 1))
            elif canal == 7:
                btn_accion.setText("🔑 1 Toque Abre Todo")
                btn_accion.setProperty("class", "btn-primary")
                btn_accion.clicked.connect(lambda _, c=canal: self._cambiar_canal(c, 0))
            elif canal == 3:
                btn_accion.setText("🔒 Conmutar Antiasalto")
                btn_accion.clicked.connect(lambda _, c=canal: self._toggle_canal(c))

            f_box.addLayout(c_desc, stretch=3)
            f_box.addWidget(lbl_val, stretch=2)
            f_box.addWidget(btn_accion, stretch=1)
            c_lyt.addLayout(f_box)

        lyt.addWidget(card_confort)

        # ── Diagnóstico y Averías K-Line ──
        card_dtc = QFrame()
        card_dtc.setProperty("class", "card")
        d_lyt = QVBoxLayout(card_dtc)
        d_hdr = QHBoxLayout()
        d_tit = QLabel("🔍 Memoria de Averías K-Line")
        d_tit.setStyleSheet("font-size: 14px; font-weight: bold; color: #F8FAFC;")
        d_hdr.addWidget(d_tit)
        d_hdr.addStretch()

        self.btn_scan_motor = QPushButton("🔎 Escanear Motor (01)")
        self.btn_scan_motor.clicked.connect(lambda: self._escanear_modulo(0x01))
        self.btn_scan_confort = QPushButton("🔎 Escanear Confort (46)")
        self.btn_scan_confort.clicked.connect(lambda: self._escanear_modulo(0x46))
        self.btn_borrar = QPushButton("🗑️ Borrar Averías")
        self.btn_borrar.clicked.connect(self._borrar_averias)

        d_hdr.addWidget(self.btn_scan_motor)
        d_hdr.addWidget(self.btn_scan_confort)
        d_hdr.addWidget(self.btn_borrar)
        d_lyt.addLayout(d_hdr)

        self.tabla_dtc = QTableWidget(0, 3)
        self.tabla_dtc.setHorizontalHeaderLabels(["Código", "Descripción Oficial VAG", "Estado"])
        self.tabla_dtc.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla_dtc.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla_dtc.cellDoubleClicked.connect(self._on_dtc_doble_clic)
        d_lyt.addWidget(self.tabla_dtc)

        lbl_ayuda = QLabel("💡 Haz doble clic en cualquier fallo para ver su ubicación física y guía técnica de reparación.")
        lbl_ayuda.setStyleSheet("font-size: 11px; color: #64748B; font-style: italic;")
        d_lyt.addWidget(lbl_ayuda)

        lyt.addWidget(card_dtc)

    def _cargar_puertos(self):
        puertos = VAGKLineClient.listar_puertos_com()
        self.combo_puerto.clear()
        for p in puertos:
            self.combo_puerto.addItem(p)
        if "MOCK" not in puertos:
            self.combo_puerto.addItem("MOCK")

    def _toggle_conexion(self):
        if not self.cliente.conectado:
            puerto = self.combo_puerto.currentText()
            self.cliente = VAGKLineClient(port_name=puerto)
            if self.cliente.conectar(0x46):
                ident = self.cliente.leer_identificacion()
                ref = ident.get("referencia", "OK")
                comp = ident.get("componente", "OK")
                self.lbl_estado_ecu.setText(f"🟢 CONECTADO vía K-Line (Pin 7) | ECU: {ref} — {comp}")
                self.lbl_estado_ecu.setStyleSheet("font-size: 12px; color: #4ADE80; font-weight: bold;")
                self.btn_conectar.setText("🔴 Desconectar")
                self._actualizar_canales_ui()
                self._escanear_modulo(0x46)
            else:
                QMessageBox.critical(self, "Error de Conexión", f"No se pudo conectar al puerto {puerto} a 10.400 baudios.")
        else:
            self.cliente.desconectar()
            self.lbl_estado_ecu.setText("⚪ Estado: Desconectado.")
            self.lbl_estado_ecu.setStyleSheet("font-size: 12px; color: #94A3B8; font-weight: 500;")
            self.btn_conectar.setText("🔌 Conectar K-Line")

    def _actualizar_canales_ui(self):
        if not self.cliente.conectado:
            return
        for canal, lbl in self.filas_canales.items():
            val = self.cliente.leer_canal_adaptacion(canal)
            if val is not None:
                opc_str = POLO_9N3_CONFORT_CHANNELS[canal]["opciones"].get(val, f"Valor {val}")
                lbl.setText(f"Valor: {val} ({opc_str})")
                if canal == 6:
                    lbl.setStyleSheet("font-weight: bold; color: #10B981;" if val == 0 else "font-weight: bold; color: #F43F5E;")
                elif canal == 4:
                    lbl.setStyleSheet("font-weight: bold; color: #10B981;" if val == 1 else "font-weight: bold; color: #F59E0B;")
                else:
                    lbl.setStyleSheet("font-weight: bold; color: #38BDF8;")

    def _cambiar_canal(self, canal: int, nuevo_valor: int):
        if not self.cliente.conectado:
            QMessageBox.warning(self, "Aviso", "Primero conecta con la centralita K-Line.")
            return
        ok = self.cliente.guardar_canal_adaptacion(canal, nuevo_valor)
        if ok:
            info = POLO_9N3_CONFORT_CHANNELS[canal]
            opc = info["opciones"].get(nuevo_valor, str(nuevo_valor))
            QMessageBox.information(self, "Canal Guardado", f"Canal {canal:02d} ({info['nombre']}) modificado con éxito:\n\nNuevo Estado: {opc}")
            self._actualizar_canales_ui()
        else:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el valor en el Canal {canal:02d}.")

    def _toggle_canal(self, canal: int):
        val_actual = self.cliente.leer_canal_adaptacion(canal) or 0
        nuevo = 0 if val_actual == 1 else 1
        self._cambiar_canal(canal, nuevo)

    def _escanear_modulo(self, addr: int):
        if not self.cliente.conectado:
            QMessageBox.warning(self, "Aviso", "Primero conecta con el cable K-Line.")
            return
        self.cliente.conectar(addr)
        fallos = self.cliente.leer_dtcs()
        self.tabla_dtc.setRowCount(0)
        for f in fallos:
            row = self.tabla_dtc.rowCount()
            self.tabla_dtc.insertRow(row)
            self.tabla_dtc.setItem(row, 0, QTableWidgetItem(f["codigo"]))
            self.tabla_dtc.setItem(row, 1, QTableWidgetItem(f["desc"]))
            self.tabla_dtc.setItem(row, 2, QTableWidgetItem(f["estado"]))

    def _borrar_averias(self):
        if not self.cliente.conectado:
            return
        if QMessageBox.question(self, "Confirmar Borrado", "¿Deseas borrar la memoria de averías del módulo actual?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.cliente.borrar_dtcs()
            self.tabla_dtc.setRowCount(0)
            QMessageBox.information(self, "Averías Borradas", "Memoria de averías borrada con éxito.")

    def _on_dtc_doble_clic(self, row, col):
        cod_item = self.tabla_dtc.item(row, 0)
        desc_item = self.tabla_dtc.item(row, 1)
        if cod_item and desc_item:
            dlg = DialogoFichaDTC("VAG K-Line", cod_item.text(), desc_item.text(), parent=self)
            dlg.exec()