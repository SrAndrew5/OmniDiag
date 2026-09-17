import customtkinter as ctk
import time
import threading
from core.connection import Connection
from obd.obd_parser import OBDParser
from obd.utils import extraer_byte
from obd.dtc_manager import DTCManager
from obd.pid_discovery import detectar_pids_soportados
from obd.vin_reader import leer_vin

# Configuración básica de apariencia
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class AudiDiagApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AudiDiag Pro - Interfaz Gráfica (Prueba)")
        self.geometry("800x500")

        # Variables de estado
        self.conexion = Connection()
        self.parser = OBDParser()
        self.dtc_mgr = DTCManager()
        self.vin = None
        
        # --- Layout Principal ---
        # Configurar un grid 1x2 (Sidebar y Main Content)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="AudiDiag Pro", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 30))

        self.btn_conectar = ctk.CTkButton(self.sidebar_frame, text="1. Conectar", command=self.evento_conectar)
        self.btn_conectar.grid(row=1, column=0, padx=20, pady=10)

        self.btn_sensores = ctk.CTkButton(self.sidebar_frame, text="2. Sensores", command=self.evento_sensores)
        self.btn_sensores.grid(row=2, column=0, padx=20, pady=10)

        self.btn_dtc = ctk.CTkButton(self.sidebar_frame, text="3. Fallos (DTC)", command=self.evento_dtc)
        self.btn_dtc.grid(row=3, column=0, padx=20, pady=10)
        
        self.btn_pids = ctk.CTkButton(self.sidebar_frame, text="4. Detectar PIDs", command=self.evento_pids)
        self.btn_pids.grid(row=4, column=0, padx=20, pady=10)

        # Indicador de estado en la parte inferior del sidebar
        self.lbl_estado = ctk.CTkLabel(self.sidebar_frame, text="Desconectado", text_color="red")
        self.lbl_estado.grid(row=7, column=0, padx=20, pady=20, sticky="s")

        # --- Main Content ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.main_title = ctk.CTkLabel(self.main_frame, text="Terminal de Diagnóstico", font=ctk.CTkFont(size=18, weight="bold"))
        self.main_title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # Consola de texto para mostrar salidas
        self.textbox = ctk.CTkTextbox(self.main_frame, width=500, height=350)
        self.textbox.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.log_mensaje("Bienvenido a AudiDiag Pro.\nPor favor, conecte al vehículo para empezar.")

    def log_mensaje(self, mensaje):
        """Añade un mensaje a la consola de texto en la GUI"""
        self.textbox.insert("end", mensaje + "\n")
        self.textbox.see("end") # Scroll automático

    def evento_conectar(self):
        # Ejecutamos en un hilo separado para no congelar la interfaz
        threading.Thread(target=self._proceso_conectar).start()

    def _proceso_conectar(self):
        self.log_mensaje("\n[INFO] Conectando...")
        self.btn_conectar.configure(state="disabled")
        
        if not self.conexion.conectar():
            self.log_mensaje("[ERROR] No se pudo establecer conexión.")
            self.btn_conectar.configure(state="normal")
            return
            
        self.conexion.enviar_comando("0902")
        time.sleep(0.1)
        respuesta_vin = self.conexion.leer_respuesta()
        self.vin = leer_vin(respuesta_vin)
        
        if self.vin:
            self.log_mensaje(f"[OK] Conexión exitosa. VIN: {self.vin}")
            self.lbl_estado.configure(text=f"Conectado\n{self.vin}", text_color="green")
        else:
            self.log_mensaje("[WARN] Conectado, pero no se pudo leer el VIN.")
            self.lbl_estado.configure(text="Conectado", text_color="yellow")
            
        self.btn_conectar.configure(state="normal")

    def evento_sensores(self):
        threading.Thread(target=self._proceso_sensores).start()

    def _proceso_sensores(self):
        if not self.vin and not self.conexion.puerto:
            self.log_mensaje("[ERROR] Debes conectarte primero.")
            return

        pruebas = [
            ("0105", self.parser.parsear_temp_refrigerante, "Temp. refrigerante", "°C"),
            ("010C", self.parser.parsear_rpm, "RPM", "rpm"),
            ("010D", self.parser.parsear_velocidad, "Velocidad", "km/h")
        ]

        self.log_mensaje("\n--- LEYENDO SENSORES BÁSICOS ---")
        for comando, funcion_parser, nombre, unidad in pruebas:
            self.conexion.enviar_comando(comando)
            time.sleep(0.1)
            respuesta = self.conexion.leer_respuesta()
            
            # Lógica rápida adaptada para la GUI
            if comando == "010C": 
                byte_a = extraer_byte(respuesta, 2)
                byte_b = extraer_byte(respuesta, 3)
                if byte_a is not None and byte_b is not None:
                    res = funcion_parser(byte_a, byte_b)
                    self.log_mensaje(f"{nombre}: {res} {unidad}")
                else:
                    self.log_mensaje(f"{nombre}: Error de lectura")
            else:
                byte_a = extraer_byte(respuesta, 2)
                if byte_a is not None:
                    res = funcion_parser(byte_a)
                    self.log_mensaje(f"{nombre}: {res} {unidad}")
                else:
                    self.log_mensaje(f"{nombre}: Error de lectura")

    def evento_dtc(self):
        if not self.conexion.puerto:
            self.log_mensaje("[ERROR] Debes conectarte primero.")
            return
        
        self.log_mensaje("\n--- GESTIÓN DE DTC ---")
        # Simulación de lectura de fallos
        fallos = ["P0300", "P0171"]
        self.log_mensaje(f"Fallos detectados: {', '.join(fallos)}")
        self.log_mensaje("Limpiando fallos (simulado)...")
        self.dtc_mgr.borrar_fallos(self.conexion, fallos, coche=self.vin)
        self.log_mensaje("Comando de borrado enviado.")

    def evento_pids(self):
        threading.Thread(target=self._proceso_pids).start()

    def _proceso_pids(self):
        if not self.conexion.puerto:
            self.log_mensaje("[ERROR] Debes conectarte primero.")
            return
        
        self.log_mensaje("\n--- DETECTANDO PIDs ---")
        self.log_mensaje("Iniciando escaneo (esto puede tardar unos segundos)...")
        pids = detectar_pids_soportados(self.conexion, self.parser)
        self.log_mensaje(f"Total encontrados: {len(pids)}")
        self.log_mensaje(f"PIDs: {pids}")

if __name__ == "__main__":
    app = AudiDiagApp()
    app.mainloop()
