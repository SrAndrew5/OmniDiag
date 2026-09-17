# ui/dialogo_gateway_list.py
# ══════════════════════════════════════════════════════════════════════════════
# Editor Visual de la "Lista de Instalación" del CAN Gateway J533 (Módulo 19)
# ══════════════════════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QScrollArea, QWidget, QFrame, QGridLayout, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from obd.vag_service_wizards import VAGServiceWizards


class DialogoGatewayList(QDialog):
    """
    Diálogo para editar la Lista de Instalación de la Pasarela CAN Gateway J533 (Módulo 19).
    Permite dar de alta o baja centralitas en el vehículo cuando se reequipa equipamiento.
    """
    lista_guardada_signal = pyqtSignal(list)

    def __init__(self, parent=None, can_mgr=None, modulos_iniciales=None):
        super().__init__(parent)
        self.setWindowTitle("AudiDiag Pro — Editor de Lista de Instalación (Gateway J533)")
        self.resize(920, 680)
        self.setStyleSheet("""
            QDialog {
                background-color: #0B0D13;
                color: #F8FAFC;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #CBD5E1;
            }
            QGroupBox {
                background-color: #11141C;
                border: 1px solid #282E3E;
                border-radius: 8px;
                margin-top: 14px;
                font-weight: 800;
                color: #E0001B;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 10px;
                background-color: #171A24;
                border: 1px solid #282E3E;
                border-radius: 4px;
                color: #00E5FF;
            }
            QCheckBox {
                color: #FFFFFF;
                font-size: 12px;
                padding: 4px 6px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #3E465E;
                background-color: #171A24;
            }
            QCheckBox::indicator:checked {
                background-color: #E0001B;
                border-color: #FF0026;
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

        self.can_mgr = can_mgr
        self.modulos_checkboxes = {}  # {codigo_str: (QCheckBox, item_dict)}

        self._init_ui()

    def _init_ui(self):
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(20, 20, 20, 20)
        lyt.setSpacing(14)

        # Encabezado explicativo
        f_head = QFrame()
        f_head.setStyleSheet("background-color: #11141C; border: 1px solid #1E2330; border-radius: 8px; padding: 12px;")
        h_lyt = QVBoxLayout(f_head)
        h_lyt.setContentsMargins(10, 8, 10, 8)
        h_lyt.setSpacing(4)

        lbl_tit = QLabel("📋  LISTA DE INSTALACIÓN — PASARELA CAN GATEWAY J533 (MÓDULO 19)")
        lbl_tit.setStyleSheet("font-size: 15px; font-weight: 900; color: #FFFFFF; letter-spacing: 0.5px;")
        lbl_sub = QLabel(
            "Indica qué centralitas y módulos electrónicos están físicamente montados en el vehículo. "
            "Si instalas un accesorio nuevo (retrovisores plegables, cámara de marcha atrás, enganche de remolque o Bluetooth AMI), "
            "marca su casilla correspondiente y pulsa en Guardar para que el Gateway lo comunique en los buses CAN."
        )
        lbl_sub.setStyleSheet("font-size: 12px; color: #94A3B8; line-height: 1.3;")
        lbl_sub.setWordWrap(True)
        h_lyt.addWidget(lbl_tit)
        h_lyt.addWidget(lbl_sub)
        lyt.addWidget(f_head)

        # Área con scroll para los módulos agrupados por Bus
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        c_lyt = QVBoxLayout(container)
        c_lyt.setSpacing(16)
        c_lyt.setContentsMargins(0, 0, 8, 0)

        catalogo = VAGServiceWizards.CATALOGO_GATEWAY_MODULOS
        buses = ["Tren Motriz", "Confort", "Infotainment", "Sistema"]

        for b in buses:
            items = [m for m in catalogo if m["bus"] == b]
            if not items:
                continue

            grp = QGroupBox(f"  BUS {b.upper()} ({len(items)} centralitas disponibles)  ")
            g_grid = QGridLayout(grp)
            g_grid.setContentsMargins(14, 16, 14, 14)
            g_grid.setHorizontalSpacing(16)
            g_grid.setVerticalSpacing(10)

            for idx, m in enumerate(items):
                chk = QCheckBox(f"[{m['codigo']}]  {m['nombre']}")
                chk.setChecked(m.get("default", True))
                self.modulos_checkboxes[m["codigo"]] = (chk, m)
                fila = idx // 2
                col = idx % 2
                g_grid.addWidget(chk, fila, col)

            c_lyt.addWidget(grp)

        c_lyt.addStretch()
        scroll.setWidget(container)
        lyt.addWidget(scroll)

        # Barra inferior de acciones
        f_pie = QHBoxLayout()
        f_pie.setSpacing(12)

        btn_default = QPushButton("🔄  Restablecer Configuración Base Audi A6 C6")
        btn_default.setFixedHeight(40)
        btn_default.clicked.connect(self._cargar_configuracion_base)
        f_pie.addWidget(btn_default)

        f_pie.addStretch()

        btn_guardar = QPushButton("💾  Guardar Lista en Gateway J533")
        btn_guardar.setProperty("class", "btn-accion")
        btn_guardar.setFixedHeight(40)
        btn_guardar.clicked.connect(self._confirmar_guardado)
        f_pie.addWidget(btn_guardar)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setFixedHeight(40)
        btn_cerrar.clicked.connect(self.accept)
        f_pie.addWidget(btn_cerrar)

        lyt.addLayout(f_pie)

    def _cargar_configuracion_base(self):
        """Restablece la selección por defecto de Audi A6 C6."""
        for cod, (chk, m) in self.modulos_checkboxes.items():
            chk.setChecked(m.get("default", True))
        QMessageBox.information(
            self,
            "Configuración Restablecida",
            "Se han marcado las centralitas que vienen de fábrica de serie en el Audi A6 C6 4F."
        )

    def _confirmar_guardado(self):
        """Valida y emite la lista de módulos seleccionados."""
        activos = [cod for cod, (chk, m) in self.modulos_checkboxes.items() if chk.isChecked()]
        resp = QMessageBox.question(
            self,
            "Confirmar Codificación de Gateway J533",
            f"¿Deseas grabar la nueva lista de instalación en el Gateway (Módulo 19)?\n\n"
            f"• Centralitas activas: {len(activos)}\n"
            f"• Módulos seleccionados: {', '.join(activos)}\n\n"
            "El Gateway se reiniciará brevemente para actualizar el bus CAN.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.lista_guardada_signal.emit(activos)
            self.accept()
