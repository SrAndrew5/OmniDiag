# -*- coding: utf-8 -*-
"""
ui/estilos.py
Tema Visual Oficial Audi Sport / MMI Virtual Cockpit para AudiDiag Pro.
Paleta:
  - Negro Titanio / Nero: #0A0B0E / #12141A / #171922
  - Rojo Oficial Audi Sport (Tornado / Misano Red): #E0001B / #D5001C
  - Blanco Platino / Plata Aluminio: #FFFFFF / #F1F5F9 / #CBD5E1
  - Acentos de Telemetría: Verde Competición #00D26A y Azul Cockpit #00C2FF
"""

ESTILO_PRINCIPAL = """
/* ══════════════════════════════════════════════════════════════════════════════
   BASE & RESET DE PANTALLA (Audi RS Carbon Black)
══════════════════════════════════════════════════════════════════════════════ */
QWidget {
    background-color: #060709;
    color: #F1F5F9;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", Helvetica, Arial, sans-serif;
    font-size: 13.5px;
    selection-background-color: #FF0026;
    selection-color: #FFFFFF;
}

QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: transparent;
    border: none;
}

/* ══════════════════════════════════════════════════════════════════════════════
   SIDEBAR (Panel Lateral Audi RS Cockpit)
══════════════════════════════════════════════════════════════════════════════ */
#sidebar {
    background-color: #080A0E;
    border-right: 1px solid #181B24;
}

#header_brand {
    background-color: transparent;
    border-bottom: 1px solid #181B24;
}

#lbl_brand_title {
    font-size: 18px;
    font-weight: 900;
    color: #FFFFFF;
    letter-spacing: 2px;
}

#lbl_brand_sub {
    font-size: 9.5px;
    font-weight: 800;
    color: #94A3B8;
    letter-spacing: 2px;
    padding-top: 2px;
}

#sidebar QPushButton {
    background-color: transparent;
    color: #94A3B8;
    text-align: left;
    padding: 7px 14px;
    border-radius: 7px;
    margin: 2px 10px;
    border: 1px solid transparent;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.3px;
}

#sidebar QPushButton:hover {
    background-color: #12151D;
    color: #FFFFFF;
    border: 1px solid #232836;
}

#sidebar QPushButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2C080E, stop:1 #101218);
    color: #FFFFFF;
    border: 1px solid #3D1219;
    border-left: 4px solid #FF0026;
    font-weight: 800;
}

#frame_status_box {
    background-color: #0A0C11;
    border: 1px solid #1C202B;
    border-radius: 8px;
    margin: 4px 12px 12px 12px;
}

#frame_status_box QLabel {
    border: none;
    background: transparent;
}

#lbl_status {
    font-weight: 800;
    font-size: 11.5px;
    color: #CBD5E1;
    letter-spacing: 0.5px;
}

/* ══════════════════════════════════════════════════════════════════════════════
   BOTONES DE CONTROL (Audi RS Racing Styles)
══════════════════════════════════════════════════════════════════════════════ */
/* Botón Principal (Rojo Escarlata Audi RS) */
QPushButton[class="btn-accion"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF0026, stop:1 #B80018);
    color: #FFFFFF;
    border-radius: 8px;
    padding: 10px 22px;
    font-weight: 800;
    font-size: 13.5px;
    border: 1px solid #FF3352;
    letter-spacing: 0.6px;
}
QPushButton[class="btn-accion"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF2647, stop:1 #D6001E);
    border-color: #FFA3AF;
}
QPushButton[class="btn-accion"]:pressed {
    background-color: #8F0012;
}
QPushButton[class="btn-accion"]:disabled {
    background-color: #2D0C11;
    border-color: #4A141C;
    color: #8A525A;
}

/* Botón Secundario (Titanio Oscuro / Grafito RS) */
QPushButton[class="btn-secundario"] {
    background-color: #11141C;
    color: #F1F5F9;
    border-radius: 8px;
    padding: 9px 16px;
    border: 1px solid #232836;
    font-size: 13px;
    font-weight: 700;
}
QPushButton[class="btn-secundario"]:hover {
    background-color: #1C202D;
    color: #FFFFFF;
    border-color: #384055;
}
QPushButton[class="btn-secundario"]:pressed {
    background-color: #0B0D13;
}

/* Botón de Borrado / Alerta (Rojo Audi RS Oscuro) */
QPushButton[class="btn-peligro"] {
    background-color: #20080B;
    color: #FFA3AF;
    border-radius: 8px;
    padding: 9px 16px;
    border: 1px solid #FF0026;
    font-weight: 800;
    font-size: 13px;
}
QPushButton[class="btn-peligro"]:hover {
    background-color: #FF0026;
    color: #FFFFFF;
    border-color: #FF4D66;
}
QPushButton[class="btn-peligro"]:pressed {
}

/* Botón de Actuadores (Azul Virtual Cockpit) */
QPushButton[class="btn-actuador"] {
    background-color: #0E1A29;
    color: #38BDF8;
    border-radius: 8px;
    padding: 11px 16px;
    border: 1px solid #0284C7;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
}
QPushButton[class="btn-actuador"]:hover {
    background-color: #0369A1;
    color: #FFFFFF;
    border-color: #7DD3FC;
}
QPushButton[class="btn-actuador"]:pressed {
    background-color: #082F49;
}

/* Botones de Confort (Activo verde / Inactivo titanio) */
QPushButton[class="btn-confort-activo"] {
    background-color: #064E3B;
    color: #A7F3D0;
    border: 1px solid #00D26A;
    border-radius: 7px;
    padding: 8px 16px;
    font-weight: 800;
    font-size: 12px;
}
QPushButton[class="btn-confort-activo"]:hover {
    background-color: #00D26A;
    color: #000000;
    border-color: #FFFFFF;
}

QPushButton[class="btn-confort-inactivo"] {
    background-color: #1A1C24;
    color: #CBD5E1;
    border: 1px solid #2E3240;
    border-radius: 7px;
    padding: 8px 16px;
    font-weight: 700;
    font-size: 12px;
}
QPushButton[class="btn-confort-inactivo"]:hover {
    background-color: #282C3A;
    color: #FFFFFF;
    border-color: #4A5168;
}

#card_confort, #card_modo {
    background-color: #0A0C11;
    border: 1px solid #1A1D27;
    border-radius: 10px;
}
#card_confort:hover, #card_modo:hover {
    border-color: #2D3345;
    background-color: #0E1017;
}
#card_confort QLabel, #card_modo QLabel {
    border: none;
    background: transparent;
}

#card_cockpit {
    background-color: #0A0C11;
    border: 1px solid #1C202B;
    border-top: 3px solid #FF0026;
    border-radius: 10px;
}
#card_cockpit QLabel {
    border: none;
    background: transparent;
}

#badge_byte_bit {
    background-color: #24060A;
    color: #FFA3AF;
    border: 1px solid #55121B;
    border-radius: 4px;
    font-family: "Consolas", monospace;
    font-size: 11px;
    font-weight: 800;
    padding: 3px 8px;
}

/* ══════════════════════════════════════════════════════════════════════════════
   PESTAÑAS (QTabWidget)
══════════════════════════════════════════════════════════════════════════════ */
QTabWidget::pane {
    border: 1px solid #222530;
    background-color: #12141A;
    border-radius: 8px;
}

QTabBar::tab {
    background-color: #171922;
    color: #CBD5E1;
    padding: 10px 22px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 700;
    font-size: 13px;
    margin-right: 4px;
    border: 1px solid #222530;
    border-bottom: none;
}

QTabBar::tab:selected {
    background-color: #12141A;
    color: #FFFFFF;
    border-top: 3px solid #E0001B;
    border-left: 1px solid #333847;
    border-right: 1px solid #333847;
}

QTabBar::tab:hover:!selected {
    background-color: #222532;
    color: #FFFFFF;
}

/* ══════════════════════════════════════════════════════════════════════════════
   CONSOLA FIJA INFERIOR (Estilo MMI Diagnostics Shell)
══════════════════════════════════════════════════════════════════════════════ */
#frame_consola {
    background-color: #060709;
    border-top: 2px solid #E0001B;
}

#lbl_consola_titulo {
    color: #E0001B;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 2px;
    padding: 4px 8px;
}

QTextEdit {
    background-color: #060709;
    color: #00FF88;
    font-family: "Consolas", "Cascadia Code", "Fira Code", monospace;
    font-size: 12px;
    border: none;
    padding: 6px 10px;
    line-height: 1.4;
}

/* ══════════════════════════════════════════════════════════════════════════════
   TABLAS (QTableWidget)
══════════════════════════════════════════════════════════════════════════════ */
QTableWidget {
    background-color: #111319;
    color: #F1F5F9;
    gridline-color: #20232E;
    border: 1px solid #222530;
    border-radius: 8px;
    selection-background-color: #380C10;
    selection-color: #FFFFFF;
    font-size: 13.5px;
}

QTableWidget::item {
    padding: 8px 12px;
    border: none;
}

QTableWidget::item:selected {
    background-color: #4A0F15;
    color: #FFFFFF;
}

QHeaderView::section {
    background-color: #171922;
    color: #F8FAFC;
    font-weight: 800;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    padding: 9px 12px;
    border: none;
    border-bottom: 2px solid #E0001B;
    border-right: 1px solid #101217;
}

QTableWidget::item:alternate {
    background-color: #151720;
}

/* ══════════════════════════════════════════════════════════════════════════════
   PROGRESSBAR (Telemetría de Sensores Audi Virtual)
══════════════════════════════════════════════════════════════════════════════ */
QProgressBar {
    background-color: #171922;
    border: 1px solid #2E3342;
    border-radius: 6px;
    height: 14px;
    text-align: center;
    font-size: 10px;
    color: transparent;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00C2FF, stop:0.5 #3B82F6, stop:1 #E0001B);
    border-radius: 5px;
}

/* ══════════════════════════════════════════════════════════════════════════════
   DESPLEGABLES (QComboBox)
══════════════════════════════════════════════════════════════════════════════ */
#combo_modulo, QComboBox {
    background-color: #161820;
    color: #FFFFFF;
    border: 1px solid #2E3342;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13.5px;
    font-weight: 600;
    min-width: 220px;
}

QComboBox:hover {
    border-color: #E0001B;
    background-color: #1C1F2A;
}

QComboBox::drop-down {
    border: none;
    padding-right: 12px;
}

QComboBox QAbstractItemView {
    background-color: #161820;
    color: #FFFFFF;
    selection-background-color: #E0001B;
    selection-color: #FFFFFF;
    border: 1px solid #333847;
    border-radius: 6px;
    padding: 6px;
    outline: none;
}

/* ══════════════════════════════════════════════════════════════════════════════
   ENTRADAS DE TEXTO (QLineEdit)
══════════════════════════════════════════════════════════════════════════════ */
#txt_coding, QLineEdit {
    background-color: #0A0B0E;
    color: #00FF88;
    font-family: "Consolas", monospace;
    font-size: 14px;
    font-weight: bold;
    border: 1px solid #2E3342;
    border-radius: 7px;
    padding: 8px 12px;
}
#txt_coding:focus, QLineEdit:focus {
    border-color: #E0001B;
}
#txt_coding[readOnly="true"] {
    color: #8892A4;
    border-color: #1D202A;
}

/* ══════════════════════════════════════════════════════════════════════════════
   CHECKBOXES
══════════════════════════════════════════════════════════════════════════════ */
#coding_helper QCheckBox {
    spacing: 5px;
    font-size: 11px;
    color: #CBD5E1;
}

#coding_helper QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 5px;
    border: 1px solid #333847;
    background-color: #171922;
}

#coding_helper QCheckBox::indicator:checked {
    background-color: #E0001B;
    border-color: #FF4D61;
}

#coding_helper QCheckBox::indicator:hover {
    border-color: #CBD5E1;
}

/* ══════════════════════════════════════════════════════════════════════════════
   SPINBOX (Adaptaciones)
══════════════════════════════════════════════════════════════════════════════ */
QDoubleSpinBox, QSpinBox {
    background-color: #161820;
    color: #FFFFFF;
    border: 1px solid #2E3342;
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 13px;
    min-width: 90px;
}
QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #E0001B;
}

QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {
    background-color: #272B38;
    border: none;
    width: 20px;
    border-radius: 3px;
}

/* ══════════════════════════════════════════════════════════════════════════════
   MIL INDICATOR (Check Engine Glow)
══════════════════════════════════════════════════════════════════════════════ */
#mil_off {
    background-color: #0E1016;
    color: #94A3B8;
    border-radius: 34px;
    border: 2px solid #222634;
    font-size: 11.5px;
    font-weight: 800;
    qproperty-alignment: AlignCenter;
}

#mil_on {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF0026, stop:1 #B80018);
    color: #FFFFFF;
    border-radius: 34px;
    border: 2px solid #FFA3AF;
    font-size: 11.5px;
    font-weight: 900;
    qproperty-alignment: AlignCenter;
}

/* ══════════════════════════════════════════════════════════════════════════════
   PANELES & SECCIONES
══════════════════════════════════════════════════════════════════════════════ */
#panel_freeze {
    background-color: #060D0B;
    border: 1px solid #00E676;
    border-radius: 8px;
    padding: 10px 14px;
}

#section_header {
    color: #FF0026;
    font-size: 11px;
    font-weight: 900;
    letter-spacing: 1.8px;
    padding: 6px 0;
    border-bottom: 1px solid #1A1D27;
}

QLabel[class="titulo"] {
    font-size: 22px;
    font-weight: 900;
    color: #FFFFFF;
    padding-bottom: 2px;
    letter-spacing: 0.8px;
}

QLabel[class="subtitulo"] {
    font-size: 13px;
    color: #94A3B8;
}

QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #222530;
    margin: 8px 0;
}

/* ══════════════════════════════════════════════════════════════════════════════
   SCROLLBAR (Ultra Slim)
══════════════════════════════════════════════════════════════════════════════ */
QScrollBar:vertical {
    background-color: #0A0B0E;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background-color: #2E3342;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background-color: #E0001B;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #0A0B0E;
    height: 6px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background-color: #2E3342;
    border-radius: 3px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ══════════════════════════════════════════════════════════════════════════════
   LISTAS (Historial)
══════════════════════════════════════════════════════════════════════════════ */
QListWidget {
    background-color: #12141A;
    color: #F1F5F9;
    border: 1px solid #222530;
    border-radius: 8px;
    font-size: 13.5px;
    outline: none;
}
QListWidget::item {
    padding: 10px 14px;
    border-bottom: 1px solid #1E212B;
    border-radius: 6px;
    margin: 2px 4px;
}
QListWidget::item:selected {
    background-color: #380C10;
    color: #FFFFFF;
    border-left: 3px solid #E0001B;
}
QListWidget::item:hover:!selected {
    background-color: #1E212B;
}
"""
