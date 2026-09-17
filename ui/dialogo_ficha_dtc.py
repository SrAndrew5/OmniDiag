# ui/dialogo_ficha_dtc.py
# ══════════════════════════════════════════════════════════════════════════════
# Diálogo de Ficha Técnica Guiada y Localización de Averías VAG (Smart DTC Guider).
# Muestra ubicación física exacta, componente oficial (N, G, V, F, J),
# causas típicas en Audi A6 C6 y protocolo de reparación paso a paso.
# ══════════════════════════════════════════════════════════════════════════════

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from obd.vag_dtc_smart_guide import obtener_ficha_dtc


class DialogoFichaDTC(QDialog):
    """
    Ventana modal de Ficha Técnica Guiada para el DTC seleccionado.
    """
    def __init__(self, modulo: str, codigo: str, descripcion: str = "", freeze_frame: dict = None, parent=None):
        super().__init__(parent)
        self.modulo = modulo
        self.codigo = codigo
        self.descripcion = descripcion
        self.freeze_frame = freeze_frame or {}
        
        self.ficha = obtener_ficha_dtc(codigo, descripcion)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle(f"📋 Ficha Técnica y Localización — {self.codigo}")
        self.setMinimumSize(680, 560)
        self.resize(720, 600)
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
                padding: 14px;
            }
            QPushButton {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
            }
            QPushButton.btn-primary {
                background-color: #E0001B;
                color: white;
                border: none;
            }
            QPushButton.btn-primary:hover {
                background-color: #FF1A35;
            }
        """)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(24, 20, 24, 20)
        lyt.setSpacing(14)

        # ── Cabecera Principal ──
        header = QFrame()
        header.setProperty("class", "card")
        h_lyt = QVBoxLayout(header)
        h_lyt.setContentsMargins(16, 12, 16, 12)
        h_lyt.setSpacing(6)

        fila_top = QHBoxLayout()
        lbl_badge_mod = QLabel(f"  {self.modulo}  ")
        lbl_badge_mod.setStyleSheet("background-color: #1E2E4A; color: #38BDF8; font-weight: bold; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
        fila_top.addWidget(lbl_badge_mod)

        lbl_badge_cod = QLabel(f"  {self.codigo}  ")
        lbl_badge_cod.setStyleSheet("background-color: #3B0D14; color: #FFA5AF; font-weight: 800; border-radius: 4px; padding: 3px 8px; font-family: Consolas; font-size: 13px; border: 1px solid #E0001B;")
        fila_top.addWidget(lbl_badge_cod)
        fila_top.addStretch()
        h_lyt.addLayout(fila_top)

        lbl_comp = QLabel(self.ficha.get("componente", self.descripcion or "Componente VAG"))
        lbl_comp.setStyleSheet("font-size: 15px; font-weight: 800; color: #FFFFFF; margin-top: 4px;")
        lbl_comp.setWordWrap(True)
        h_lyt.addWidget(lbl_comp)

        if self.descripcion and self.descripcion != self.ficha.get("componente"):
            lbl_desc = QLabel(self.descripcion)
            lbl_desc.setStyleSheet("font-size: 12px; color: #94A3B8; font-style: italic;")
            lbl_desc.setWordWrap(True)
            h_lyt.addWidget(lbl_desc)

        lyt.addWidget(header)

        # ── Área de contenido desplazable ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        scroll_widget = QWidget()
        s_lyt = QVBoxLayout(scroll_widget)
        s_lyt.setContentsMargins(0, 0, 0, 0)
        s_lyt.setSpacing(12)

        # Card 1: Ubicación Física
        card_ubic = QFrame()
        card_ubic.setProperty("class", "card")
        u_lyt = QVBoxLayout(card_ubic)
        lbl_u_tit = QLabel("📍  UBICACIÓN FÍSICA EN EL VEHÍCULO")
        lbl_u_tit.setStyleSheet("color: #38BDF8; font-weight: 800; font-size: 11.5px; letter-spacing: 1px;")
        u_lyt.addWidget(lbl_u_tit)

        lbl_u_txt = QLabel(self.ficha.get("ubicacion", "Consultar el esquema de cableado del vehículo."))
        lbl_u_txt.setStyleSheet("color: #F8FAFC; font-size: 13px; line-height: 1.4; margin-top: 4px;")
        lbl_u_txt.setWordWrap(True)
        u_lyt.addWidget(lbl_u_txt)
        s_lyt.addWidget(card_ubic)

        # Card 2: Causas Frecuentes
        card_causas = QFrame()
        card_causas.setProperty("class", "card")
        c_lyt = QVBoxLayout(card_causas)
        lbl_c_tit = QLabel("⚠️  CAUSAS FRECUENTES Y PUNTOS DÉBILES (AUDI A6 C6)")
        lbl_c_tit.setStyleSheet("color: #FFAA33; font-weight: 800; font-size: 11.5px; letter-spacing: 1px;")
        c_lyt.addWidget(lbl_c_tit)

        lbl_c_txt = QLabel(self.ficha.get("causas_tipicas", "Fallo intermitente en circuito o terminales con holgura."))
        lbl_c_txt.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.4; margin-top: 4px;")
        lbl_c_txt.setWordWrap(True)
        c_lyt.addWidget(lbl_c_txt)
        s_lyt.addWidget(card_causas)

        # Card 3: Comprobación y Solución
        card_sol = QFrame()
        card_sol.setProperty("class", "card")
        sol_lyt = QVBoxLayout(card_sol)
        lbl_s_tit = QLabel("🔧  PROTOCOLO DE COMPROBACIÓN Y REPARACIÓN")
        lbl_s_tit.setStyleSheet("color: #00FF88; font-weight: 800; font-size: 11.5px; letter-spacing: 1px;")
        sol_lyt.addWidget(lbl_s_tit)

        lbl_s_txt = QLabel(self.ficha.get("comprobacion", "Verificar continuidad de cableado y alimentar según esquema."))
        lbl_s_txt.setStyleSheet("color: #F1F5F9; font-size: 12.5px; line-height: 1.5; margin-top: 4px;")
        lbl_s_txt.setWordWrap(True)
        sol_lyt.addWidget(lbl_s_txt)
        s_lyt.addWidget(card_sol)

        # Freeze Frame si existe
        if self.freeze_frame:
            card_ff = QFrame()
            card_ff.setProperty("class", "card")
            ff_lyt = QVBoxLayout(card_ff)
            lbl_ff_tit = QLabel("❄  CONDICIONES EN EL MOMENTO DEL FALLO (FREEZE FRAME)")
            lbl_ff_tit.setStyleSheet("color: #A78BFA; font-weight: 800; font-size: 11.5px; letter-spacing: 1px;")
            ff_lyt.addWidget(lbl_ff_tit)

            ff_str_list = [f"• {k}: {v[0]} {v[1]}" if isinstance(v, (list, tuple)) else f"• {k}: {v}" for k, v in self.freeze_frame.items()]
            lbl_ff_txt = QLabel("\n".join(ff_str_list))
            lbl_ff_txt.setStyleSheet("color: #E2E8F0; font-family: Consolas; font-size: 12px; margin-top: 4px;")
            ff_lyt.addWidget(lbl_ff_txt)
            s_lyt.addWidget(card_ff)

        s_lyt.addStretch()
        scroll.setWidget(scroll_widget)
        lyt.addWidget(scroll)

        # ── Botonera Inferior ──
        fila_btn = QHBoxLayout()
        btn_copiar = QPushButton("📋  Copiar Ficha")
        btn_copiar.clicked.connect(self._copiar_portapapeles)
        fila_btn.addWidget(btn_copiar)

        fila_btn.addStretch()

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setProperty("class", "btn-primary")
        btn_cerrar.setFixedWidth(110)
        btn_cerrar.clicked.connect(self.accept)
        fila_btn.addWidget(btn_cerrar)

        lyt.addLayout(fila_btn)

    def _copiar_portapapeles(self):
        texto = (
            f"DIAGNÓSTICO VAG — {self.modulo}\n"
            f"Código: {self.codigo}\n"
            f"Componente: {self.ficha.get('componente', self.descripcion)}\n\n"
            f"[UBICACIÓN FÍSICA]:\n{self.ficha.get('ubicacion')}\n\n"
            f"[CAUSAS TÍPICAS]:\n{self.ficha.get('causas_tipicas')}\n\n"
            f"[SOLUCIÓN RECOMENDADA]:\n{self.ficha.get('comprobacion')}\n"
        )
        QApplication.clipboard().setText(texto)
