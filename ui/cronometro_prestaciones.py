# ui/cronometro_prestaciones.py
# ══════════════════════════════════════════════════════════════════════════════
# Cronómetro de Prestaciones en Tiempo Real (Banco Virtual / 0-100 km/h CAN)
# ══════════════════════════════════════════════════════════════════════════════

import time
import os
import csv
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor


class CronometroPrestacionesWidget(QWidget):
    """
    Widget de telemetría deportiva y banco virtual de aceleración.
    Lee la velocidad y RPM transmitidas por el bus CAN en tiempo real,
    activándose automáticamente cuando el vehículo acelera desde parado.
    """

    ESTADO_IDLE = "IDLE"
    ESTADO_ARMED = "ARMED"
    ESTADO_RUNNING = "RUNNING"
    ESTADO_FINISHED = "FINISHED"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.estado = self.ESTADO_IDLE
        self.tiempo_inicio = None
        self.tiempo_transcurrido = 0.0

        # Tiempos de paso registrados
        self.t_0_60 = None
        self.t_0_100 = None
        self.t_80_120_inicio = None
        self.t_80_120 = None
        self.rpm_max = 0
        self.g_max = 0.0

        self.velocidad_anterior = 0.0
        self.tiempo_velocidad_anterior = None
        self.distancia_m = 0.0

        self._timer_ui = QTimer(self)
        self._timer_ui.setInterval(25)  # 40 Hz de refresco de pantalla
        self._timer_ui.timeout.connect(self._actualizar_cronometro_ui)

        self._init_ui()

    def _init_ui(self):
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(14, 14, 14, 14)
        lyt.setSpacing(12)

        # ── 1. CABECERA HUD CON DISPLAY DIGITAL ──
        f_hud = QFrame()
        f_hud.setStyleSheet("""
            background-color: #0E1118;
            border: 2px solid #282E3E;
            border-radius: 12px;
            padding: 12px;
        """)
        h_lyt = QVBoxLayout(f_hud)
        h_lyt.setContentsMargins(16, 12, 16, 12)
        h_lyt.setSpacing(8)

        fila_top = QHBoxLayout()
        lbl_hud_tit = QLabel("🏁  TELEMETRÍA DE ACELERACIÓN & BANCO VIRTUAL CAN")
        lbl_hud_tit.setStyleSheet("font-size: 14px; font-weight: 900; color: #FFFFFF; letter-spacing: 0.8px;")
        fila_top.addWidget(lbl_hud_tit)
        fila_top.addStretch()

        self.lbl_semaforo = QLabel("●  SISTEMA EN ESPERA")
        self.lbl_semaforo.setStyleSheet("font-size: 13px; font-weight: 800; color: #94A3B8; background: #171A24; padding: 4px 12px; border-radius: 6px;")
        fila_top.addWidget(self.lbl_semaforo)
        h_lyt.addLayout(fila_top)

        # Panel de marcadores digitales (Speed, Time, G-Force, RPM)
        fila_displays = QHBoxLayout()
        fila_displays.setSpacing(16)

        # Display 1: Velocidad
        d_vel = self._crear_bloque_display("VELOCIDAD CAN", "0", "km/h", "#00E5FF")
        self.lbl_display_vel = d_vel.findChild(QLabel, "val")
        fila_displays.addWidget(d_vel, stretch=2)

        # Display 2: Cronómetro Principal
        d_time = self._crear_bloque_display("TIEMPO TOTAL", "0.00", "segundos", "#FF0026")
        self.lbl_display_time = d_time.findChild(QLabel, "val")
        fila_displays.addWidget(d_time, stretch=2)

        # Display 3: Fuerza G Longitudinal
        d_g = self._crear_bloque_display("ACEL. LONGITUDINAL", "0.00", "G", "#00FF88")
        self.lbl_display_g = d_g.findChild(QLabel, "val")
        fila_displays.addWidget(d_g, stretch=1)

        # Display 4: RPM Máximas
        d_rpm = self._crear_bloque_display("RÉGIMEN MOTOR", "0", "RPM", "#FFB347")
        self.lbl_display_rpm = d_rpm.findChild(QLabel, "val")
        fila_displays.addWidget(d_rpm, stretch=1)

        h_lyt.addLayout(fila_displays)
        lyt.addWidget(f_hud)

        # ── 2. TARJETAS DE HITOS (0-60, 0-100, 80-120, 400M) ──
        f_milestones = QHBoxLayout()
        f_milestones.setSpacing(10)

        self.card_0_60 = self._crear_tarjeta_hito("0 - 60 km/h", "-- s", "#00E5FF")
        self.card_0_100 = self._crear_tarjeta_hito("0 - 100 km/h", "-- s", "#E0001B")
        self.card_80_120 = self._crear_tarjeta_hito("80 - 120 km/h", "-- s", "#FFB347")
        self.card_400m = self._crear_tarjeta_hito("1/4 Milla (400 m)", "-- s", "#9D4EDD")

        f_milestones.addWidget(self.card_0_60)
        f_milestones.addWidget(self.card_0_100)
        f_milestones.addWidget(self.card_80_120)
        f_milestones.addWidget(self.card_400m)
        lyt.addLayout(f_milestones)

        # ── 3. BOTONERA DE CONTROL ──
        fila_ctrl = QHBoxLayout()
        fila_ctrl.setSpacing(12)

        self.btn_armar = QPushButton("🚀  Armar Lanzada (0-100 km/h)")
        self.btn_armar.setProperty("class", "btn-accion")
        self.btn_armar.setFixedHeight(42)
        self.btn_armar.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E0001B, stop:1 #B00015);
            font-size: 13px; font-weight: 900; color: #FFFFFF; border-radius: 6px; padding: 0 20px;
        """)
        self.btn_armar.clicked.connect(self.armar_lanzada)
        fila_ctrl.addWidget(self.btn_armar)

        btn_reset = QPushButton("🔄  Reiniciar")
        btn_reset.setFixedHeight(42)
        btn_reset.clicked.connect(self.reiniciar_prueba)
        fila_ctrl.addWidget(btn_reset)

        fila_ctrl.addStretch()

        btn_exportar = QPushButton("💾  Exportar Historial (CSV)")
        btn_exportar.setFixedHeight(42)
        btn_exportar.clicked.connect(self._exportar_csv)
        fila_ctrl.addWidget(btn_exportar)

        lyt.addLayout(fila_ctrl)

        # ── 4. TABLA HISTÓRICA DE LANZADAS ──
        self.tabla_historial = QTableWidget(0, 7)
        self.tabla_historial.setHorizontalHeaderLabels([
            "Fecha / Hora", "0-60 km/h", "0-100 km/h", "80-120 km/h", "1/4 Milla", "RPM Máx", "G Máx"
        ])
        self.tabla_historial.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            self.tabla_historial.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_historial.verticalHeader().setVisible(False)
        self.tabla_historial.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla_historial.setStyleSheet("""
            QTableWidget {
                background-color: #11141C;
                border: 1px solid #282E3E;
                gridline-color: #1E2330;
                border-radius: 8px;
                color: #FFFFFF;
                font-family: Consolas, monospace;
            }
            QHeaderView::section {
                background-color: #171A24;
                color: #E0001B;
                font-weight: 800;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #E0001B;
            }
        """)
        lyt.addWidget(self.tabla_historial)

    def _crear_bloque_display(self, titulo: str, valor: str, unidad: str, color_hex: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet("background-color: #141722; border: 1px solid #242A3A; border-radius: 8px;")
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(2)

        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet("font-size: 10px; font-weight: 800; color: #94A3B8; letter-spacing: 0.5px;")
        v.addWidget(lbl_t)

        lbl_v = QLabel(valor)
        lbl_v.setObjectName("val")
        lbl_v.setStyleSheet(f"font-size: 32px; font-weight: 900; color: {color_hex}; font-family: Consolas, monospace;")
        v.addWidget(lbl_v)

        lbl_u = QLabel(unidad)
        lbl_u.setStyleSheet("font-size: 10px; font-weight: 700; color: #CBD5E1;")
        v.addWidget(lbl_u)
        return f

    def _crear_tarjeta_hito(self, titulo: str, valor: str, color_hex: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"background-color: #141722; border: 1px solid {color_hex}44; border-radius: 8px; padding: 6px;")
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(2)

        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet(f"font-size: 11px; font-weight: 800; color: {color_hex};")
        v.addWidget(lbl_t)

        lbl_v = QLabel(valor)
        lbl_v.setObjectName("val_hito")
        lbl_v.setStyleSheet("font-size: 20px; font-weight: 900; color: #FFFFFF; font-family: Consolas, monospace;")
        v.addWidget(lbl_v)
        return f

    # ══════════════════════════════════════════════════════════════════════════
    #  LÓGICA DEL CRONÓMETRO Y TELEMETRÍA CAN
    # ══════════════════════════════════════════════════════════════════════════
    def armar_lanzada(self):
        """Pone el sistema en modo armado esperando que el coche esté a 0 km/h."""
        self.reiniciar_prueba(limpiar_hitos=True)
        self.estado = self.ESTADO_ARMED
        self.lbl_semaforo.setText("🟡  ARMADO — DETÉN EL COCHE POR COMPLETO (0 km/h)")
        self.lbl_semaforo.setStyleSheet("font-size: 13px; font-weight: 800; color: #FFB347; background: #291C0E; padding: 4px 12px; border-radius: 6px;")

    def reiniciar_prueba(self, limpiar_hitos: bool = False):
        """Reinicia el cronómetro."""
        self.estado = self.ESTADO_IDLE
        self._timer_ui.stop()
        self.tiempo_inicio = None
        self.tiempo_transcurrido = 0.0
        self.lbl_display_time.setText("0.00")
        self.lbl_semaforo.setText("●  SISTEMA EN ESPERA")
        self.lbl_semaforo.setStyleSheet("font-size: 13px; font-weight: 800; color: #94A3B8; background: #171A24; padding: 4px 12px; border-radius: 6px;")

        if limpiar_hitos:
            self.t_0_60 = None
            self.t_0_100 = None
            self.t_80_120_inicio = None
            self.t_80_120 = None
            self.rpm_max = 0
            self.g_max = 0.0
            self.distancia_m = 0.0
            self.card_0_60.findChild(QLabel, "val_hito").setText("-- s")
            self.card_0_100.findChild(QLabel, "val_hito").setText("-- s")
            self.card_80_120.findChild(QLabel, "val_hito").setText("-- s")
            self.card_400m.findChild(QLabel, "val_hito").setText("-- s")

    def alimentar_telemetria(self, velocidad_kmh: float, rpm: float):
        """
        Método llamado por el worker en cada paquete de sensores recibido del CAN Bus.
        """
        ahora = time.time()
        self.lbl_display_vel.setText(f"{velocidad_kmh:.0f}")
        self.lbl_display_rpm.setText(f"{rpm:.0f}")

        if rpm > self.rpm_max:
            self.rpm_max = int(rpm)

        # Cálculo de Aceleración G
        if self.tiempo_velocidad_anterior is not None and ahora > self.tiempo_velocidad_anterior:
            dt = ahora - self.tiempo_velocidad_anterior
            dv_ms = (velocidad_kmh - self.velocidad_anterior) / 3.6
            if dt > 0.01:
                acel_ms2 = dv_ms / dt
                g = acel_ms2 / 9.80665
                if 0 <= g <= 2.5:  # Filtro de ruido
                    self.lbl_display_g.setText(f"{g:.2f}")
                    if g > self.g_max:
                        self.g_max = g

        self.velocidad_anterior = velocidad_kmh
        self.tiempo_velocidad_anterior = ahora

        # ── MÁQUINA DE ESTADOS ──
        if self.estado == self.ESTADO_ARMED:
            if velocidad_kmh <= 1.0:
                self.lbl_semaforo.setText("🟢  ¡LISTO! ACELERA A FONDO CUANDO QUIERAS")
                self.lbl_semaforo.setStyleSheet("font-size: 13px; font-weight: 800; color: #00FF88; background: #0E291B; padding: 4px 12px; border-radius: 6px;")
            elif velocidad_kmh > 2.0:
                # ¡Arranca la lanzada automáticamente!
                self.estado = self.ESTADO_RUNNING
                self.tiempo_inicio = ahora
                self._timer_ui.start()
                self.lbl_semaforo.setText("⚡  ¡LANZADA EN CURSO! ACELERANDO...")
                self.lbl_semaforo.setStyleSheet("font-size: 13px; font-weight: 900; color: #00E5FF; background: #0B2533; padding: 4px 12px; border-radius: 6px;")

        elif self.estado == self.ESTADO_RUNNING:
            if self.tiempo_inicio is None:
                return
            t_actual = ahora - self.tiempo_inicio

            # Integración de distancia recorrida
            dt = 0.05
            v_ms = velocidad_kmh / 3.6
            self.distancia_m += v_ms * dt

            # 1. Registro 0 - 60 km/h
            if velocidad_kmh >= 60.0 and self.t_0_60 is None:
                self.t_0_60 = t_actual
                self.card_0_60.findChild(QLabel, "val_hito").setText(f"{self.t_0_60:.2f} s")

            # 2. Registro 0 - 100 km/h
            if velocidad_kmh >= 100.0 and self.t_0_100 is None:
                self.t_0_100 = t_actual
                self.card_0_100.findChild(QLabel, "val_hito").setText(f"{self.t_0_100:.2f} s")

            # 3. Registro 80 - 120 km/h
            if velocidad_kmh >= 80.0 and self.t_80_120_inicio is None:
                self.t_80_120_inicio = ahora
            if velocidad_kmh >= 120.0 and self.t_80_120 is None and self.t_80_120_inicio is not None:
                self.t_80_120 = ahora - self.t_80_120_inicio
                self.card_80_120.findChild(QLabel, "val_hito").setText(f"{self.t_80_120:.2f} s")

            # 4. Registro 1/4 Milla (402 metros)
            if self.distancia_m >= 402.0 and not hasattr(self, "_t_400m_done"):
                self._t_400m_done = True
                self.card_400m.findChild(QLabel, "val_hito").setText(f"{t_actual:.2f} s ({velocidad_kmh:.0f} km/h)")

            # Finalización si se alcanza 105 km/h o pasan 25 segundos
            if (self.t_0_100 is not None and velocidad_kmh > 102.0) or t_actual > 25.0:
                self.finalizar_prueba()

    def _actualizar_cronometro_ui(self):
        if self.estado == self.ESTADO_RUNNING and self.tiempo_inicio:
            t = time.time() - self.tiempo_inicio
            self.lbl_display_time.setText(f"{t:.2f}")

    def finalizar_prueba(self):
        """Termina la lanzada y guarda los datos en el historial."""
        self.estado = self.ESTADO_FINISHED
        self._timer_ui.stop()

        self.lbl_semaforo.setText("✓  PRUEBA COMPLETADA")
        self.lbl_semaforo.setStyleSheet("font-size: 13px; font-weight: 800; color: #00FF88; background: #0E291B; padding: 4px 12px; border-radius: 6px;")

        # Añadir al historial
        row = self.tabla_historial.rowCount()
        self.tabla_historial.insertRow(row)

        fecha_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        v_0_60 = f"{self.t_0_60:.2f} s" if self.t_0_60 else "--"
        v_0_100 = f"{self.t_0_100:.2f} s" if self.t_0_100 else "--"
        v_80_120 = f"{self.t_80_120:.2f} s" if self.t_80_120 else "--"
        v_400m = getattr(self, "card_400m").findChild(QLabel, "val_hito").text()

        self.tabla_historial.setItem(row, 0, QTableWidgetItem(fecha_str))
        self.tabla_historial.setItem(row, 1, QTableWidgetItem(v_0_60))
        item_100 = QTableWidgetItem(v_0_100)
        item_100.setForeground(QColor("#FF4D6D"))
        item_100.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.tabla_historial.setItem(row, 2, item_100)
        self.tabla_historial.setItem(row, 3, QTableWidgetItem(v_80_120))
        self.tabla_historial.setItem(row, 4, QTableWidgetItem(v_400m))
        self.tabla_historial.setItem(row, 5, QTableWidgetItem(f"{self.rpm_max} RPM"))
        self.tabla_historial.setItem(row, 6, QTableWidgetItem(f"{self.g_max:.2f} G"))

    def _exportar_csv(self):
        """Exporta las mediciones de aceleración a un fichero CSV."""
        if self.tabla_historial.rowCount() == 0:
            QMessageBox.warning(self, "Sin datos", "No hay registros de aceleración en el historial para exportar.")
            return

        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar Registros de Aceleración", "lanzadas_audi_a6.csv", "CSV (*.csv)")
        if not ruta:
            return

        try:
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Fecha_Hora", "0_60_kmh_s", "0_100_kmh_s", "80_120_kmh_s", "Cuarto_Milla", "RPM_Max", "G_Max"])
                for r in range(self.tabla_historial.rowCount()):
                    fila = [self.tabla_historial.item(r, c).text() if self.tabla_historial.item(r, c) else "" for c in range(7)]
                    writer.writerow(fila)
            QMessageBox.information(self, "Exportación Exitosa", f"Datos exportados a:\n{ruta}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el archivo:\n{e}")
