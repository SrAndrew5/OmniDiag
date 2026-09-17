# ui/dialogo_diff_backups.py
# ══════════════════════════════════════════════════════════════════════════════
# Comparador Visual de Backups de Codificación (Diff Viewer Byte a Byte / Bit a Bit)
# ══════════════════════════════════════════════════════════════════════════════

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QMessageBox,
    QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from gestion.backup_manager import BackupManager


class DialogoDiffBackups(QDialog):
    """
    Diálogo interactivo para inspeccionar y comparar dos copias de seguridad de Long Coding,
    o comparar un backup guardado contra la codificación actualmente leída del vehículo.
    """

    def __init__(self, parent=None, modulo_filtro: str = None, coding_actual: str = ""):
        super().__init__(parent)
        self.setWindowTitle("AudiDiag Pro — Comparador Visual de Backups (Diff Viewer)")
        self.resize(950, 620)
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0D13;
                color: #F8FAFC;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #CBD5E1;
            }
            QComboBox {
                background-color: #171A24;
                border: 1px solid #282E3E;
                border-radius: 6px;
                padding: 6px 12px;
                color: #FFFFFF;
                font-size: 12px;
                font-family: Consolas, monospace;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #171A24;
                color: #FFFFFF;
                selection-background-color: #E0001B;
                selection-color: #FFFFFF;
            }
            QTableWidget {
                background-color: #11141C;
                border: 1px solid #282E3E;
                gridline-color: #1E2330;
                border-radius: 8px;
                color: #FFFFFF;
                font-family: Consolas, monospace;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QHeaderView::section {
                background-color: #171A24;
                color: #E0001B;
                font-weight: 800;
                font-size: 11px;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #E0001B;
            }
            QPushButton {
                background-color: #171A24;
                border: 1px solid #282E3E;
                border-radius: 6px;
                padding: 8px 16px;
                color: #FFFFFF;
                font-weight: bold;
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
        """)

        self.bm = BackupManager()
        self.modulo_filtro = modulo_filtro
        self.coding_actual = coding_actual
        self.backup_seleccionado_para_restaurar = None

        self._init_ui()
        self._cargar_backups()
        self.ejecutar_comparacion()

    def _init_ui(self):
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(20, 20, 20, 20)
        lyt.setSpacing(14)

        # Cabecera
        f_head = QFrame()
        f_head.setStyleSheet("background-color: #11141C; border: 1px solid #1E2330; border-radius: 8px; padding: 12px;")
        h_lyt = QVBoxLayout(f_head)
        h_lyt.setContentsMargins(10, 8, 10, 8)
        h_lyt.setSpacing(4)

        lbl_tit = QLabel("🔍  COMPARADOR DE CODIFICACIONES & CONTROL DE VERSIONES")
        lbl_tit.setStyleSheet("font-size: 15px; font-weight: 900; color: #FFFFFF; letter-spacing: 0.5px;")
        lbl_sub = QLabel(
            "Compara cualquier copia de seguridad anterior con el estado actual del coche o con otro backup. "
            "Detecta automáticamente qué bytes y qué bits individuales han sido modificados."
        )
        lbl_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        lbl_sub.setWordWrap(True)
        h_lyt.addWidget(lbl_tit)
        h_lyt.addWidget(lbl_sub)
        lyt.addWidget(f_head)

        # Selectores de comparación (A vs B)
        f_sel = QFrame()
        f_sel.setStyleSheet("background-color: #171A24; border: 1px solid #282E3E; border-radius: 8px; padding: 10px;")
        s_lyt = QHBoxLayout(f_sel)
        s_lyt.setSpacing(14)

        # Lado A (Referencia / Anterior)
        v_a = QVBoxLayout()
        v_a.setSpacing(4)
        lbl_a = QLabel("Versión A (Referencia / Anterior):")
        lbl_a.setStyleSheet("font-weight: 800; color: #00E5FF; font-size: 11.5px;")
        self.combo_a = QComboBox()
        self.combo_a.currentIndexChanged.connect(self.ejecutar_comparacion)
        v_a.addWidget(lbl_a)
        v_a.addWidget(self.combo_a)
        s_lyt.addLayout(v_a, stretch=1)

        lbl_vs = QLabel("VS")
        lbl_vs.setStyleSheet("font-size: 16px; font-weight: 900; color: #E0001B; padding: 10px;")
        s_lyt.addWidget(lbl_vs, alignment=Qt.AlignmentFlag.AlignCenter)

        # Lado B (Nueva / Objetivo)
        v_b = QVBoxLayout()
        v_b.setSpacing(4)
        lbl_b = QLabel("Versión B (Comparar contra):")
        lbl_b.setStyleSheet("font-weight: 800; color: #00FF88; font-size: 11.5px;")
        self.combo_b = QComboBox()
        self.combo_b.currentIndexChanged.connect(self.ejecutar_comparacion)
        v_b.addWidget(lbl_b)
        v_b.addWidget(self.combo_b)
        s_lyt.addLayout(v_b, stretch=1)

        lyt.addWidget(f_sel)

        # Barra de Resumen / Estado
        self.lbl_resumen = QLabel("Analizando diferencias...")
        self.lbl_resumen.setStyleSheet("font-size: 13px; font-weight: 800; padding: 4px 8px; border-radius: 4px;")
        lyt.addWidget(self.lbl_resumen)

        # Tabla de diferencias
        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels([
            "Byte #", "Versión A (Hex / Bin)", "Versión B (Hex / Bin)", "Bits Modificados", "Diagnóstico"
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lyt.addWidget(self.tabla)

        # Botones de pie
        f_pie = QHBoxLayout()
        f_pie.setSpacing(12)

        self.btn_restaurar = QPushButton("⚡  Transferir Codificación de Versión A al Editor")
        self.btn_restaurar.setProperty("class", "btn-accion")
        self.btn_restaurar.setFixedHeight(38)
        self.btn_restaurar.clicked.connect(self._aplicar_restauracion)
        f_pie.addWidget(self.btn_restaurar)

        f_pie.addStretch()

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setFixedHeight(38)
        btn_cerrar.clicked.connect(self.accept)
        f_pie.addWidget(btn_cerrar)

        lyt.addLayout(f_pie)

    def _cargar_backups(self):
        """Carga la lista de backups en los selectores."""
        backups = self.bm.obtener_backups_detallados(modulo=self.modulo_filtro)

        self.combo_a.clear()
        self.combo_b.clear()

        # En B agregamos siempre la opción de "Codificación en Vivo del Vehículo" si existe
        if self.coding_actual:
            self.combo_b.addItem("⚡ ESTADO ACTUAL EN VIVO (Coche)", userData={"tipo": "vivo", "coding": self.coding_actual})

        for b in backups:
            fecha = b.get("fecha_hora", "")
            tag = b.get("etiqueta", "Backup")
            mod = b.get("modulo", "")
            nombre = f"[{fecha}] {tag} — {mod}"
            self.combo_a.addItem(nombre, userData=b)
            self.combo_b.addItem(nombre, userData=b)

        # Por defecto seleccionar A = el backup más reciente o el segundo, B = actual o el primero
        if self.combo_a.count() > 1:
            self.combo_a.setCurrentIndex(1)
        if self.combo_b.count() > 0:
            self.combo_b.setCurrentIndex(0)

    def ejecutar_comparacion(self):
        """Calcula las diferencias entre A y B y rellena la tabla."""
        item_a = self.combo_a.currentData()
        item_b = self.combo_b.currentData()

        if not item_a or not item_b:
            self.lbl_resumen.setText("Selecciona dos elementos para comparar.")
            self.lbl_resumen.setStyleSheet("color: #94A3B8;")
            self.tabla.setRowCount(0)
            return

        coding_a = item_a.get("bytes_coding", "") if isinstance(item_a, dict) else ""
        if isinstance(item_b, dict) and item_b.get("tipo") == "vivo":
            coding_b = item_b.get("coding", "")
        elif isinstance(item_b, dict):
            coding_b = item_b.get("bytes_coding", "")
        else:
            coding_b = ""

        diff_res = self.bm.comparar_codificaciones(coding_a, coding_b, modulo=self.modulo_filtro or "")

        diferencias = diff_res.get("diferencias", [])
        total_diff = len(diferencias)

        if total_diff == 0:
            self.lbl_resumen.setText("✓ Las dos codificaciones son 100% IDÉNTICAS. No hay diferencias.")
            self.lbl_resumen.setStyleSheet("color: #00FF88; background-color: #0E291B; font-size: 13px; font-weight: bold;")
        else:
            self.lbl_resumen.setText(f"⚠ SE HAN DETECTADO {total_diff} BYTE(S) MODIFICADO(S) ENTRE AMBAS VERSIONES")
            self.lbl_resumen.setStyleSheet("color: #FFB347; background-color: #291C0E; font-size: 13px; font-weight: bold;")

        self.tabla.setRowCount(len(diferencias))
        for row, d in enumerate(diferencias):
            # Byte
            item_byte = QTableWidgetItem(f"Byte {d['byte_index']:02d}")
            item_byte.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_byte.setForeground(QColor("#00E5FF"))
            self.tabla.setItem(row, 0, item_byte)

            # Hex/Bin A
            txt_a = f"{d['hex_a']}  ({d['bin_a']})"
            item_a = QTableWidgetItem(txt_a)
            item_a.setForeground(QColor("#CBD5E1"))
            self.tabla.setItem(row, 1, item_a)

            # Hex/Bin B
            txt_b = f"{d['hex_b']}  ({d['bin_b']})"
            item_b = QTableWidgetItem(txt_b)
            item_b.setForeground(QColor("#FF4D6D"))
            item_b.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            self.tabla.setItem(row, 2, item_b)

            # Bits cambiados
            bits_txt = ", ".join(f"Bit {b['bit']}: {b['antes']}->{b['despues']}" for b in d.get("bits_cambiados", []))
            item_bits = QTableWidgetItem(bits_txt or "Tamaño dispar")
            item_bits.setForeground(QColor("#FFB347"))
            self.tabla.setItem(row, 3, item_bits)

            # Diagnóstico
            desc_items = [b["cambio"] for b in d.get("bits_cambiados", [])]
            item_diag = QTableWidgetItem(" | ".join(desc_items) or d.get("descripcion", ""))
            item_diag.setForeground(QColor("#FFFFFF"))
            self.tabla.setItem(row, 4, item_diag)

    def _aplicar_restauracion(self):
        """Marca el backup A para ser cargado en el editor principal."""
        item_a = self.combo_a.currentData()
        if not item_a:
            return
        coding_a = item_a.get("bytes_coding", "")
        self.backup_seleccionado_para_restaurar = coding_a
        QMessageBox.information(
            self,
            "Codificación Seleccionada",
            f"Se ha preparado la codificación de la Versión A:\n\n{coding_a}\n\n"
            "Se transferirá al editor Long Coding de la pantalla principal."
        )
        self.accept()
