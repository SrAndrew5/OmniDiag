# ui/osciloscopio.py
# ══════════════════════════════════════════════════════════════════════════════
# Widget de osciloscopio vectorial de alto rendimiento para AudiDiag Pro.
# Renderizado fluido a 60 FPS con PyQt6.QtGui.QPainter (sin dependencias pesadas).
# ══════════════════════════════════════════════════════════════════════════════

import time
from collections import deque
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QFrame
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QLinearGradient


class OsciloscopioWidget(QWidget):
    """
    Osciloscopio gráfico en tiempo real con trazado multicanal,
    rejilla calibrada y amortiguación visual con estilo deportivo Audi RS.
    """

    CANALES_CONFIG = {
        "RPM": {
            "color": QColor("#00E5FF"),      # Cian brillante
            "unidad": "RPM",
            "min": 0.0,
            "max": 5000.0,
            "nombre": "Régimen Motor (RPM)",
        },
        "Turbo / Boost": {
            "color": QColor("#00FF88"),      # Verde neón
            "unidad": "mbar",
            "min": 900.0,
            "max": 2600.0,
            "nombre": "Presión Turbo (mbar)",
        },
        "Presión Rail": {
            "color": QColor("#FF9100"),      # Naranja vivo
            "unidad": "bar",
            "min": 200.0,
            "max": 1800.0,
            "nombre": "Rampa Common Rail (bar)",
        },
        "Temperatura": {
            "color": QColor("#FF1744"),      # Rojo RS
            "unidad": "°C",
            "min": 20.0,
            "max": 120.0,
            "nombre": "Temp. Refrigerante (°C)",
        },
        "Caudal MAF": {
            "color": QColor("#D500F9"),      # Magenta
            "unidad": "mg/str",
            "min": 150.0,
            "max": 750.0,
            "nombre": "Caudalímetro MAF (mg/str)",
        },
    }

    def __init__(self, max_puntos: int = 150, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(280)
        self.max_puntos = max_puntos
        self.pausado = False

        # Buffers de datos por canal (FIFO)
        self.datos = {canal: deque(maxlen=max_puntos) for canal in self.CANALES_CONFIG}
        self.activos = {canal: True for canal in self.CANALES_CONFIG}
        self.ultimos_valores = {canal: 0.0 for canal in self.CANALES_CONFIG}

        # Inicializar con puntos en cero para trazado continuo
        for canal in self.CANALES_CONFIG:
            for _ in range(max_puntos):
                self.datos[canal].append(0.0)

    def agregar_lectura(self, sensor: str, valor: float):
        """Mapea el nombre del sensor reportado por el OBD al canal del osciloscopio."""
        if self.pausado:
            return

        s_upper = sensor.upper()
        canal_dest = None

        if "RPM" in s_upper or "REVOLUCIONES" in s_upper:
            canal_dest = "RPM"
        elif "TURBO" in s_upper or "SOBREALIMENTACIÓN" in s_upper or "MAP" in s_upper or "COLECTOR" in s_upper:
            canal_dest = "Turbo / Boost"
        elif "RAIL" in s_upper or "RAMPA" in s_upper or "COMBUSTIBLE" in s_upper:
            canal_dest = "Presión Rail"
        elif "REFRIGERANTE" in s_upper or "AGUA" in s_upper or "MOTOR TEMP" in s_upper or "G62" in s_upper:
            canal_dest = "Temperatura"
        elif "MAF" in s_upper or "MASA" in s_upper or "CAUDAL" in s_upper or "G70" in s_upper:
            canal_dest = "Caudal MAF"

        if canal_dest:
            self.datos[canal_dest].append(float(valor))
            self.ultimos_valores[canal_dest] = float(valor)
            self.update()

    def toggle_canal(self, canal: str, activo: bool):
        if canal in self.activos:
            self.activos[canal] = activo
            self.update()

    def limpiar(self):
        for canal in self.CANALES_CONFIG:
            self.datos[canal].clear()
            for _ in range(self.max_puntos):
                self.datos[canal].append(0.0)
            self.ultimos_valores[canal] = 0.0
        self.update()

    def toggle_pausa(self) -> bool:
        self.pausado = not self.pausado
        return self.pausado

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin_x = 20
        margin_y = 35
        graph_w = w - (margin_x * 2)
        graph_h = h - (margin_y * 2)

        if graph_w <= 0 or graph_h <= 0:
            return

        # 1. Fondo oscuro estilo cockpit de carreras
        bg_rect = QRectF(margin_x, margin_y, graph_w, graph_h)
        painter.fillRect(bg_rect, QColor("#0B0E14"))

        # Borde exterior de la rejilla
        pen_border = QPen(QColor("#1E2536"), 1.5)
        painter.setPen(pen_border)
        painter.drawRect(bg_rect)

        # 2. Rejilla horizontal graduada (5 líneas)
        pen_grid = QPen(QColor("#151B28"), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        font_grid = QFont("Consolas", 8)
        painter.setFont(font_grid)

        for i in range(1, 5):
            y_grid = margin_y + (graph_h * i / 5.0)
            painter.drawLine(QPointF(margin_x, y_grid), QPointF(margin_x + graph_w, y_grid))

        # Rejilla vertical (marcas de tiempo)
        for i in range(1, 8):
            x_grid = margin_x + (graph_w * i / 8.0)
            painter.drawLine(QPointF(x_grid, margin_y), QPointF(x_grid, margin_y + graph_h))

        # 3. Dibujar curvas para cada canal activo
        step_x = graph_w / max(1, self.max_puntos - 1)

        for canal, cfg in self.CANALES_CONFIG.items():
            if not self.activos.get(canal, True):
                continue

            color = cfg["color"]
            min_val = cfg["min"]
            max_val = cfg["max"]
            rango = max(1.0, max_val - min_val)

            buf = self.datos[canal]
            puntos = []

            for idx, val in enumerate(buf):
                # Normalizar en el rango del canal (0.0 a 1.0)
                norm = max(0.0, min(1.0, (val - min_val) / rango))
                px = margin_x + (idx * step_x)
                py = margin_y + graph_h - (norm * graph_h)
                puntos.append(QPointF(px, py))

            if len(puntos) >= 2:
                # Dibujar curva con trazo grueso
                pen_line = QPen(color, 2.2)
                pen_line.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen_line.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen_line)
                painter.drawPolyline(QPolygonF(puntos))

                # Dibujar punto brillante en la última lectura
                last_pt = puntos[-1]
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
                painter.drawEllipse(last_pt, 4.0, 4.0)

        # 4. Cabecera con valores en tiempo real (HUD superior)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        cur_x = margin_x + 10

        for canal, cfg in self.CANALES_CONFIG.items():
            if not self.activos.get(canal, True):
                continue
            color = cfg["color"]
            val = self.ultimos_valores[canal]
            unit = cfg["unidad"]
            txt = f"{canal}: {val:.1f} {unit}"

            # Cuadrito de color
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(cur_x, margin_y - 20, 8, 8), 2, 2)

            # Texto
            painter.setPen(QColor("#E2E8F0"))
            painter.drawText(QPointF(cur_x + 14, margin_y - 12), txt)
            cur_x += painter.fontMetrics().horizontalAdvance(txt) + 26
