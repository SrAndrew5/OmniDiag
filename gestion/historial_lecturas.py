# historial_lecturas.py
"""
Guarda un histórico de lecturas en vivo en la base de datos SQLite.
"""
from gestion.database_manager import DatabaseManager

class HistorialLecturas:
    def __init__(self, coche):
        """
        coche: el VIN del coche. Crea una sesión en SQLite para agrupar lecturas.
        """
        self.db = DatabaseManager()
        self.sesion_id = self.db.nueva_sesion(coche)

    def registrar_lectura(self, nombre_dato, valor, unidad):
        """Añade un registro en la base de datos."""
        # Convertir a flotante si es posible, si no guardar como texto/NULL
        try:
            val_float = float(valor)
        except (ValueError, TypeError):
            val_float = None # O podrías guardar el texto si la BD lo permitiera. SQLite tipa dinámicamente, pero pasamos None por limpieza.
            
        self.db.registrar_lectura(self.sesion_id, nombre_dato, val_float, unidad)