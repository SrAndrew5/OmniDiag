# dtc_manager.py
"""
Gestiona lectura y borrado de fallos (DTCs), con histórico de qué se ha
borrado y cuándo, ya que el modo 04 de OBD2 borra TODOS los fallos de golpe
(no existe borrado selectivo en el estándar).
"""
import os

import json
from datetime import datetime
import config

class DTCManager:
    def __init__(self):
        if not os.path.exists(config.HISTORICO_DTCS_FOLDER):
            os.makedirs(config.HISTORICO_DTCS_FOLDER)

    def borrar_fallos(self, conexion, fallos_actuales, coche="A6"):
        """
        Borra todos los fallos del coche (modo 04), pero antes guarda
        un registro de qué fallos había justo antes de borrar.
        """
        self._guardar_historico(fallos_actuales, coche)

        conexion.enviar_comando("04")
        respuesta = conexion.leer_respuesta()

        if respuesta == "44":
            print("Fallos borrados correctamente.")
            return True
        else:
            print(f"Respuesta inesperada al borrar: {respuesta}")
            return False

    def _guardar_historico(self, fallos, coche):
        """Guarda en JSON qué fallos había antes de un borrado."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        nombre_fichero = f"{config.HISTORICO_DTCS_FOLDER}borrado_{coche}_{timestamp}.json"

        datos = {
            "coche": coche,
            "fecha_hora": timestamp,
            "fallos_antes_de_borrar": fallos,
        }

        with open(nombre_fichero, "w") as f:
            json.dump(datos, f, indent=4)

        print(f"Histórico guardado en: {nombre_fichero}")

    def listar_historico(self, coche=None):
        """Lista los históricos de borrado disponibles."""
        ficheros = [f for f in os.listdir(config.HISTORICO_DTCS_FOLDER) if f.endswith(".json")]
        if coche:
            ficheros = [f for f in ficheros if f"_{coche}_" in f]
        return sorted(ficheros, reverse=True)