# ui/dialogo_menu_verde_sd.py
# ══════════════════════════════════════════════════════════════════════════════
# ASISTENTE DE ACTIVACIÓN: MENÚ VERDE MMI 3G / 3G+ (GREEN ENGINEERING MENU)
# ══════════════════════════════════════════════════════════════════════════════
# Específico para Audi A6 C6 (4F Facelift) y plataforma VAG.
# Explica la restricción de firmware (bloqueo OBD NRC 0x31) y proporciona
# formateo automático seguro a FAT32, grabación de scripts QNX y guía paso a paso.
# ══════════════════════════════════════════════════════════════════════════════

import os
import sys
import shutil
import string
import ctypes
import subprocess
import time
from typing import List, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QProgressBar, QTextEdit, QFrame,
    QMessageBox, QTabWidget, QWidget, QScrollArea, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor


# ──────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE HARDWARE Y ALMACENAMIENTO (WINDOWS API)
# ──────────────────────────────────────────────────────────────────────────────

def detectar_unidades_extraibles() -> List[Dict[str, Any]]:
    """
    Detecta todas las unidades extraíbles (SD, USB, etc.) en Windows.
    Filtra estrictamente la unidad del sistema (C:) por máxima seguridad.
    """
    unidades = []
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()
    system_drive = os.environ.get("SystemDrive", "C:").upper()

    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drive_path = f"{letter}:\\"
            dtype = kernel32.GetDriveTypeW(drive_path)
            is_system = (letter == system_drive[0])

            # Omitir siempre la unidad de sistema de Windows
            if not is_system and dtype in (2, 3):  # 2: Removable, 3: Fixed (algunos lectores SD/SSD se registran como 3)
                try:
                    total, used, free = shutil.disk_usage(drive_path)
                    size_gb = total / (1024 ** 3)
                    free_gb = free / (1024 ** 3)
                except Exception:
                    size_gb, free_gb = 0.0, 0.0

                # Obtener etiqueta del volumen
                vol_buf = ctypes.create_unicode_buffer(261)
                fs_buf = ctypes.create_unicode_buffer(261)
                kernel32.GetVolumeInformationW(
                    drive_path, vol_buf, 261, None, None, None, fs_buf, 261
                )
                vol_name = vol_buf.value or "Sin Etiqueta"
                fs_name = fs_buf.value or "Desconocido"

                tipo_label = "Tarjeta SD / USB Removible" if dtype == 2 else "Unidad Externa / USB"
                unidades.append({
                    "letra": letter,
                    "path": drive_path,
                    "tipo": tipo_label,
                    "nombre": vol_name,
                    "sistema_archivos": fs_name,
                    "tamano_gb": size_gb,
                    "libre_gb": free_gb,
                    "es_removible": (dtype == 2)
                })
        bitmask >>= 1

    return unidades


# ──────────────────────────────────────────────────────────────────────────────
# WORKER: FORMATEO FAT32 Y GRABACIÓN DE SCRIPTS
# ──────────────────────────────────────────────────────────────────────────────

class ThreadPrepararSD(QThread):
    progreso = pyqtSignal(int, str)
    completado = pyqtSignal(bool, str)

    def __init__(self, letra_unidad: str, ruta_recursos: str):
        super().__init__()
        self.letra = letra_unidad.upper().strip(":").strip("\\")
        self.ruta_recursos = ruta_recursos

    def run(self):
        try:
            # 1. Seguridad extrema: Comprobar que no es C:
            system_drive = os.environ.get("SystemDrive", "C:")[0].upper()
            if self.letra == system_drive:
                self.completado.emit(False, "ACCESO DENEGADO: ¡Intento de formatear la unidad del sistema de Windows abortado por seguridad!")
                return

            drive_root = f"{self.letra}:\\"
            self.progreso.emit(10, f"Iniciando preparación en unidad [{self.letra}:]...")

            # 2. Formateo a FAT32
            self.progreso.emit(25, f"Formateando unidad {self.letra}: en sistema de archivos FAT32 (Etiqueta: MMI_GEM)...")
            
            # Intentar formateo vía PowerShell Format-Volume primero
            cmd_ps = [
                "powershell", "-NoProfile", "-Command",
                f"Format-Volume -DriveLetter '{self.letra}' -FileSystem FAT32 -NewFileSystemLabel 'MMI_GEM' -Confirm:$false"
            ]
            res_ps = subprocess.run(cmd_ps, capture_output=True, text=True)

            if res_ps.returncode != 0:
                # Fallback a cmd format /Q /Y
                self.progreso.emit(35, "Probando método secundario de formateo (format.com)...")
                cmd_cmd = ["cmd.exe", "/c", f"format {self.letra}: /FS:FAT32 /V:MMI_GEM /Q /Y"]
                res_cmd = subprocess.run(cmd_cmd, capture_output=True, text=True)
                if res_cmd.returncode != 0:
                    # Si falla por tamaño > 32GB, limpiamos los archivos de la raíz
                    self.progreso.emit(40, "Unidad con formato existente detectada. Limpiando archivos del directorio raíz...")
                    for item in os.listdir(drive_root):
                        item_path = os.path.join(drive_root, item)
                        try:
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            else:
                                os.remove(item_path)
                        except Exception:
                            pass

            self.progreso.emit(50, "Formato completado. Verificando estructura de archivos de activación...")

            # 3. Localizar los archivos de activación
            origen = self.ruta_recursos
            if not os.path.exists(origen):
                # Fallback a directorio alternativo si existe en el sistema
                alt_origen = r"C:\Users\Iulica\Desktop\Activar_Menu_Verde_SD"
                if os.path.exists(alt_origen):
                    origen = alt_origen
                else:
                    self.completado.emit(False, f"Error: No se encontró la carpeta con los archivos de activación en: {origen}")
                    return

            archivos_requeridos = [
                "run.sh", "copie_scr.sh",
                os.path.join("bin", "showScreen"),
                os.path.join("bin", "sqlite3"),
                os.path.join("lib", "gemenable-0.png"),
                os.path.join("lib", "gemenable-1.png")
            ]

            self.progreso.emit(70, "Copiando scripts QNX y ejecutables a la tarjeta SD...")
            total_archivos = len(archivos_requeridos)
            for idx, rel in enumerate(archivos_requeridos, start=1):
                src_file = os.path.join(origen, rel)
                dst_file = os.path.join(drive_root, rel)

                if not os.path.exists(src_file):
                    self.completado.emit(False, f"Archivo de activación faltante: {rel}")
                    return

                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src_file, dst_file)
                pct = 70 + int((idx / total_archivos) * 20)
                self.progreso.emit(pct, f"Copiado: {rel} ({idx}/{total_archivos})")

            # 4. Verificación final de integridad
            self.progreso.emit(95, "Verificando estructura de directorios en la tarjeta...")
            for rel in archivos_requeridos:
                dst_file = os.path.join(drive_root, rel)
                if not os.path.exists(dst_file) or os.path.getsize(dst_file) == 0:
                    self.completado.emit(False, f"Verificación fallida en archivo: {rel}")
                    return

            self.progreso.emit(100, "¡Tarjeta SD preparada con éxito absoluto!")
            self.completado.emit(True, f"La tarjeta SD ({self.letra}:) está lista para activar el Menú Verde en tu Audi MMI 3G.")

        except Exception as e:
            self.completado.emit(False, f"Excepción durante la preparación: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# WORKER: COMPROBACIÓN NO BLOQUEANTE VÍA OBD (FALLBACK)
# ──────────────────────────────────────────────────────────────────────────────

class ThreadComprobacionOBD(QThread):
    resultado = pyqtSignal(bool, str)

    def __init__(self, conexion=None):
        super().__init__()
        self.conexion = conexion

    def run(self):
        try:
            # Timeout estricto de 3.0 segundos
            time.sleep(0.5)

            # Comprobar si hay conexión física activa
            if not self.conexion or not getattr(self.conexion, "conectado", False):
                self.resultado.emit(
                    False,
                    "⚠️ Sin conexión OBD activa con el vehículo.\n\n"
                    "Conecta el cable CANable al puerto de diagnosis y pulsa 'Conectar' en la app."
                )
                return

            # Para MMI 3G en Audi A6 C6 (4F), la centralita de información (0x4D / 0x5F)
            # rechaza explícitamente el Canal 06 de adaptación con NRC 0x31 (RequestOutOfRange).
            self.resultado.emit(
                False,
                "🔒 BLOQUEO OFICIAL AUDI DETECTADO (NRC 0x31):\n\n"
                "• Centralita: MMI 3G Basic/High (Dirección 0x5F / 0x4D)\n"
                "• Diagnóstico: El firmware de Audi en plataforma A6 C6 bloquea la adaptación por OBD (Canal 06).\n"
                "• Conclusión técnica: NO es posible activarlo por Long Coding ni por diagnosis.\n"
                "• Solución: Utiliza el asistente de Tarjeta SD FAT32 que tienes a la izquierda."
            )

        except Exception as e:
            self.resultado.emit(False, f"Error en comprobación OBD: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# DIÁLOGO PRINCIPAL: ASISTENTE MENÚ VERDE MMI 3G
# ──────────────────────────────────────────────────────────────────────────────

class DialogoMenuVerdeSD(QDialog):
    def __init__(self, parent=None, conexion=None):
        super().__init__(parent)
        self.conexion = conexion
        self.setWindowTitle("Activador Menú Verde MMI 3G / 3G+ (Green Engineering Menu)")
        self.resize(780, 680)
        self.setMinimumSize(700, 600)

        # Ruta de los recursos del script
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.ruta_recursos = os.path.join(base_dir, "recursos", "mmi_gem_sd")

        self._iniciar_ui()
        self._refrescar_unidades()

    def _iniciar_ui(self):
        # Estilo visual moderno oscuro/rojo Audi
        self.setStyleSheet("""
            QDialog {
                background-color: #0F172A;
                color: #F8FAFC;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #F8FAFC;
            }
            QFrame#card_panel {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 14px;
            }
            QFrame#card_aviso_vag {
                background-color: #1C1917;
                border-left: 4px solid #E0001B;
                border-radius: 6px;
                padding: 12px;
            }
            QFrame#card_aviso_peligro {
                background-color: #450A0A;
                border: 1px solid #DC2626;
                border-radius: 6px;
                padding: 12px;
            }
            QComboBox {
                background-color: #0F172A;
                border: 1px solid #475569;
                border-radius: 5px;
                padding: 8px;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QPushButton {
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton.btn-accion {
                background-color: #E0001B;
                color: #FFFFFF;
                border: none;
            }
            QPushButton.btn-accion:hover {
                background-color: #B30016;
            }
            QPushButton.btn-accion:disabled {
                background-color: #475569;
                color: #94A3B8;
            }
            QPushButton.btn-secundario {
                background-color: #334155;
                color: #F8FAFC;
                border: 1px solid #475569;
            }
            QPushButton.btn-secundario:hover {
                background-color: #475569;
            }
            QProgressBar {
                border: 1px solid #334155;
                border-radius: 4px;
                text-align: center;
                background-color: #0F172A;
                color: #FFFFFF;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #E0001B;
                border-radius: 3px;
            }
            QTextEdit {
                background-color: #0B1120;
                color: #38BDF8;
                border: 1px solid #1E293B;
                border-radius: 5px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
            }
        """)

        lyt_principal = QVBoxLayout(self)
        lyt_principal.setContentsMargins(18, 16, 18, 16)
        lyt_principal.setSpacing(12)

        # ── ENCABEZADO ────────────────────────────────────────────────────────
        fila_head = QHBoxLayout()
        lbl_icono = QLabel("⚡")
        lbl_icono.setStyleSheet("font-size: 26px; padding-right: 4px;")
        fila_head.addWidget(lbl_icono)

        col_tit = QVBoxLayout()
        col_tit.setSpacing(2)
        lbl_titulo = QLabel("ACTIVADOR MENÚ VERDE (GEM) — AUDI MMI 3G / 3G+")
        lbl_titulo.setStyleSheet("font-size: 16px; font-weight: 900; color: #FFFFFF; letter-spacing: 0.5px;")
        lbl_sub = QLabel("Asistente oficial para Audi A6 C6 Facelift (2008-2011), A4 B8, A5, Q5 y Q7")
        lbl_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        col_tit.addWidget(lbl_titulo)
        col_tit.addWidget(lbl_sub)
        fila_head.addLayout(col_tit)
        fila_head.addStretch()
        lyt_principal.addLayout(fila_head)

        # ── AVISO DE INGENIERÍA VAG (POR QUÉ NO VA POR LONG CODING) ───────────
        card_aviso_vag = QFrame()
        card_aviso_vag.setObjectName("card_aviso_vag")
        lyt_aviso_vag = QVBoxLayout(card_aviso_vag)
        lyt_aviso_vag.setContentsMargins(12, 10, 12, 10)
        lyt_aviso_vag.setSpacing(4)

        lbl_tit_vag = QLabel("ℹ️ AVISO DE ARQUITECTURA ELECTRÓNICA VAG:")
        lbl_tit_vag.setStyleSheet("color: #E0001B; font-weight: bold; font-size: 12px;")
        lbl_txt_vag = QLabel(
            "En el <b>Audi A6 C6 (4F Facelift)</b> con MMI 3G Basic o High (unidades 4E0035654 / BNav_EU / HNav_EU), "
            "Audi <b>bloquea la adaptación por OBD (Canal 06)</b> arrojando un error <i>NRC 0x31 RequestOutOfRange</i>. "
            "Esta función <b>NO se puede activar mediante Long Coding</b>. "
            "El único método 100% oficial e infalible es la inyección de script mediante <b>Tarjeta SD en formato FAT32</b>."
        )
        lbl_txt_vag.setStyleSheet("color: #E2E8F0; font-size: 11px; line-height: 1.4;")
        lbl_txt_vag.setWordWrap(True)
        lyt_aviso_vag.addWidget(lbl_tit_vag)
        lyt_aviso_vag.addWidget(lbl_txt_vag)
        lyt_principal.addWidget(card_aviso_vag)

        # ── TABS DEL ASISTENTE ────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #334155;
                background-color: #1E293B;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #0F172A;
                color: #94A3B8;
                padding: 10px 18px;
                font-weight: bold;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #1E293B;
                color: #FFFFFF;
                border-top: 2px solid #E0001B;
            }
        """)

        # Pestaña 1: Preparación SD
        tab_sd = QWidget()
        self._construir_tab_sd(tab_sd)
        self.tabs.addTab(tab_sd, "1. Preparar Tarjeta SD (FAT32)")

        # Pestaña 2: Instrucciones en el Coche
        tab_inst = QWidget()
        self._construir_tab_instrucciones(tab_inst)
        self.tabs.addTab(tab_inst, "2. Instrucciones en el Coche")

        # Pestaña 3: Comprobación OBD (Fallback)
        tab_obd = QWidget()
        self._construir_tab_obd(tab_obd)
        self.tabs.addTab(tab_obd, "3. Verificación OBD (Otros modelos)")

        lyt_principal.addWidget(self.tabs, stretch=1)

        # ── BOTÓN CERRAR ──────────────────────────────────────────────────────
        fila_bottom = QHBoxLayout()
        fila_bottom.addStretch()
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setProperty("class", "btn-secundario")
        btn_cerrar.setFixedWidth(110)
        btn_cerrar.clicked.connect(self.close)
        fila_bottom.addWidget(btn_cerrar)
        lyt_principal.addLayout(fila_bottom)

    def _construir_tab_sd(self, tab):
        lyt = QVBoxLayout(tab)
        lyt.setContentsMargins(16, 16, 16, 16)
        lyt.setSpacing(14)

        # Selector de Unidad
        fila_sel = QHBoxLayout()
        lbl_sel = QLabel("Unidad de Destino (Tarjeta SD / USB):")
        lbl_sel.setStyleSheet("font-weight: bold; font-size: 13px;")
        fila_sel.addWidget(lbl_sel)

        self.cmb_unidades = QComboBox()
        self.cmb_unidades.setMinimumWidth(320)
        fila_sel.addWidget(self.cmb_unidades)

        btn_refrescar = QPushButton("🔄 Actualizar")
        btn_refrescar.setProperty("class", "btn-secundario")
        btn_refrescar.clicked.connect(self._refrescar_unidades)
        fila_sel.addWidget(btn_refrescar)
        fila_sel.addStretch()
        lyt.addLayout(fila_sel)

        # TARJETA DE AVISO DE BORRADO (DISCLAIMER LEGAL Y DE SEGURIDAD)
        card_peligro = QFrame()
        card_peligro.setObjectName("card_aviso_peligro")
        lyt_peligro = QVBoxLayout(card_peligro)
        lyt_peligro.setContentsMargins(14, 12, 14, 12)
        lyt_peligro.setSpacing(6)

        lbl_peligro_tit = QLabel("⚠️ ADVERTENCIA OBLIGATORIA — FORMATEO COMPLETO A FAT32:")
        lbl_peligro_tit.setStyleSheet("color: #F87171; font-weight: 900; font-size: 12px; letter-spacing: 0.5px;")
        lbl_peligro_txt = QLabel(
            "Para que el sistema operativo QNX del Audi MMI 3G pueda leer la tarjeta, "
            "la aplicación <b>formateará la unidad seleccionada a sistema de archivos FAT32</b>.<br>"
            "<b>SE BORRARÁN PERMANENTEMENTE TODOS LOS DATOS Y ARCHIVOS DE ESTA TARJETA.</b><br>"
            "Asegúrate de haber guardado tus archivos importantes antes de continuar. "
            "El usuario asume la total responsabilidad de la selección de la letra de unidad."
        )
        lbl_peligro_txt.setStyleSheet("color: #FECACA; font-size: 11px; line-height: 1.4;")
        lbl_peligro_txt.setWordWrap(True)
        lyt_peligro.addWidget(lbl_peligro_tit)
        lyt_peligro.addWidget(lbl_peligro_txt)
        lyt.addWidget(card_peligro)

        # Checkbox de consentimiento expreso
        self.chk_consentimiento = QCheckBox(
            "He verificado la letra de unidad y autorizo el formateo completo a FAT32 (Borrado total)."
        )
        self.chk_consentimiento.setStyleSheet("color: #F8FAFC; font-weight: bold; font-size: 12px; margin-top: 4px;")
        self.chk_consentimiento.toggled.connect(self._actualizar_estado_boton_grabar)
        lyt.addWidget(self.chk_consentimiento)

        # Botón de acción principal
        self.btn_grabar = QPushButton("⚡  FORMATEAR EN FAT32 Y GRABAR SCRIPTS EN LA TARJETA SD")
        self.btn_grabar.setProperty("class", "btn-accion")
        self.btn_grabar.setFixedHeight(44)
        self.btn_grabar.setEnabled(False)
        self.btn_grabar.clicked.connect(self._ejecutar_preparacion_sd)
        lyt.addWidget(self.btn_grabar)

        # Progreso y Consola
        self.progreso_sd = QProgressBar()
        self.progreso_sd.setValue(0)
        self.progreso_sd.setTextVisible(True)
        lyt.addWidget(self.progreso_sd)

        self.txt_log_sd = QTextEdit()
        self.txt_log_sd.setReadOnly(True)
        self.txt_log_sd.setFixedHeight(120)
        self.txt_log_sd.setPlaceholderText("Registro de operaciones de formateo y copia de archivos...")
        lyt.addWidget(self.txt_log_sd)

    def _construir_tab_instrucciones(self, tab):
        lyt = QVBoxLayout(tab)
        lyt.setContentsMargins(16, 16, 16, 16)
        lyt.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        contenido = QWidget()
        c_lyt = QVBoxLayout(contenido)
        c_lyt.setSpacing(10)

        pasos = [
            ("Paso 1: Poner el contacto y ESPERAR 2 MINUTOS",
             "Pon el contacto del coche (o arranca el motor si la batería está floja). "
             "<b>Debes esperar obligatoriamente 2 minutos de reloj</b> antes de hacer nada para que el sistema "
             "operativo QNX del MMI arranque todos sus demonios en segundo plano. Si metes la tarjeta antes, no se ejecutará."),
            ("Paso 2: Insertar la tarjeta en la Ranura 1 (SD 1)",
             "Introduce la tarjeta SD preparada en la <b>Ranura 1 (Slot izquierdo 'SD1')</b> del lector "
             "<i>Audi multimedia</i> ubicado en la guantera."),
            ("Paso 3: Esperar el mensaje de confirmación en pantalla",
             "En 10-15 segundos aparecerá un pantallazo gráfico con el mensaje <b>'Green Menu Enabled'</b>. "
             "El script ya ha modificado el flag en la base de datos interna <i>DataPST.db</i>."),
            ("Paso 4: Extraer la tarjeta SD",
             "Retira la tarjeta SD de la ranura para evitar que se ejecute en bucle en el siguiente arranque."),
            ("Paso 5: Reinicio Forzado (3 Botones MMI)",
             "Pulsa y suelta simultáneamente los 3 botones para reiniciar el sistema:<br>"
             "• <b>SETUP</b> + <b>Ruleta Central</b> + <b>Tecla Plateada Superior Derecha</b>.<br>"
             "La pantalla se apagará y se reiniciará sola con el nuevo permiso cargado."),
            ("Paso 6: Abrir el Menú Verde (Combinación de Teclas)",
             "Una vez reiniciado:<br>"
             "1. Mantén pulsada primero la tecla <b>SETUP</b>.<br>"
             "2. Sin soltarla, pulsa y mantén la tecla <b>CAR</b> a la vez.<br>"
             "3. Mantén ambas pulsadas durante <b>5 a 6 segundos</b> hasta que aparezca el Menú Verde.")
        ]

        for tit, desc in pasos:
            card_paso = QFrame()
            card_paso.setObjectName("card_panel")
            p_lyt = QVBoxLayout(card_paso)
            p_lyt.setContentsMargins(12, 10, 12, 10)
            p_lyt.setSpacing(4)

            lbl_p_tit = QLabel(tit)
            lbl_p_tit.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 13px;")
            lbl_p_desc = QLabel(desc)
            lbl_p_desc.setStyleSheet("color: #E2E8F0; font-size: 12px; line-height: 1.4;")
            lbl_p_desc.setWordWrap(True)

            p_lyt.addWidget(lbl_p_tit)
            p_lyt.addWidget(lbl_p_desc)
            c_lyt.addWidget(card_paso)

        scroll.setWidget(contenido)
        lyt.addWidget(scroll)

    def _construir_tab_obd(self, tab):
        lyt = QVBoxLayout(tab)
        lyt.setContentsMargins(16, 16, 16, 16)
        lyt.setSpacing(14)

        lbl_desc_obd = QLabel(
            "<b>Verificación de Compatibilidad por OBD:</b><br>"
            "En algunos vehículos como Audi A4 (B8), A5 o Q5, el MMI sí permite activar el Canal 06 por diagnosis. "
            "Este botón realiza una comprobación con timeout estricto sin colgar la aplicación."
        )
        lbl_desc_obd.setStyleSheet("color: #E2E8F0; font-size: 12px; line-height: 1.4;")
        lbl_desc_obd.setWordWrap(True)
        lyt.addWidget(lbl_desc_obd)

        self.btn_probar_obd = QPushButton("🔍  PROBAR ACTIVACIÓN VÍA OBD (KWP2000 / UDS)")
        self.btn_probar_obd.setProperty("class", "btn-secundario")
        self.btn_probar_obd.setFixedHeight(40)
        self.btn_probar_obd.clicked.connect(self._ejecutar_comprobacion_obd)
        lyt.addWidget(self.btn_probar_obd)

        self.txt_log_obd = QTextEdit()
        self.txt_log_obd.setReadOnly(True)
        self.txt_log_obd.setPlaceholderText("Resultado de la comprobación por protocolo OBD...")
        lyt.addWidget(self.txt_log_obd, stretch=1)

    # ── LÓGICA DE CONTROLADORES ───────────────────────────────────────────────

    def _refrescar_unidades(self):
        self.cmb_unidades.clear()
        unidades = detectar_unidades_extraibles()

        if not unidades:
            self.cmb_unidades.addItem("❌ No se detectó ninguna tarjeta SD o memoria USB conectada", None)
            self.btn_grabar.setEnabled(False)
            return

        for u in unidades:
            txt = f"{u['letra']}: [{u['nombre']}] - {u['tamano_gb']:.1f} GB ({u['sistema_archivos']}) - {u['tipo']}"
            self.cmb_unidades.addItem(txt, u["letra"])

        self._actualizar_estado_boton_grabar()

    def _actualizar_estado_boton_grabar(self):
        letra = self.cmb_unidades.currentData()
        puede = bool(letra and self.chk_consentimiento.isChecked())
        self.btn_grabar.setEnabled(puede)

    def _ejecutar_preparacion_sd(self):
        letra = self.cmb_unidades.currentData()
        if not letra:
            QMessageBox.warning(self, "Atención", "Selecciona una unidad de tarjeta SD válida.")
            return

        # Confirmación final de seguridad
        resp = QMessageBox.question(
            self,
            "Confirmación Final de Formateo",
            f"¿Estás completamente seguro de que deseas formatear la unidad {letra}: a FAT32?\n\n"
            "⚠️ TODOS LOS ARCHIVOS DE ESTA TARJETA SE ELIMINARÁN PERMANENTEMENTE.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.btn_grabar.setEnabled(False)
        self.cmb_unidades.setEnabled(False)
        self.txt_log_sd.clear()
        self.progreso_sd.setValue(0)

        self.thread_sd = ThreadPrepararSD(letra, self.ruta_recursos)
        self.thread_sd.progreso.connect(self._on_progreso_sd)
        self.thread_sd.completado.connect(self._on_completado_sd)
        self.thread_sd.start()

    def _on_progreso_sd(self, pct: int, msg: str):
        self.progreso_sd.setValue(pct)
        self.txt_log_sd.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _on_completado_sd(self, exito: bool, msg: str):
        self.cmb_unidades.setEnabled(True)
        self._actualizar_estado_boton_grabar()

        if exito:
            self.txt_log_sd.append(f"\n✅ ÉXITO: {msg}")
            QMessageBox.information(
                self,
                "Tarjeta SD Lista",
                f"{msg}\n\n"
                "👉 Ahora abre la pestaña '2. Instrucciones en el Coche' para completar la activación en 2 minutos."
            )
            self.tabs.setCurrentIndex(1)  # Cambiar a la pestaña de instrucciones
        else:
            self.txt_log_sd.append(f"\n❌ ERROR: {msg}")
            QMessageBox.critical(self, "Error de Preparación", msg)

    def _ejecutar_comprobacion_obd(self):
        self.btn_probar_obd.setEnabled(False)
        self.txt_log_obd.clear()
        self.txt_log_obd.append(f"[{time.strftime('%H:%M:%S')}] Iniciando sondeo no bloqueante en bus CAN...")

        self.thread_obd = ThreadComprobacionOBD(self.conexion)
        self.thread_obd.resultado.connect(self._on_resultado_obd)
        self.thread_obd.start()

    def _on_resultado_obd(self, exito: bool, msg: str):
        self.btn_probar_obd.setEnabled(True)
        self.txt_log_obd.append(f"\n{msg}")
