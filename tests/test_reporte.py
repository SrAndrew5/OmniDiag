import time
from gestion.database_manager import DatabaseManager
from gestion.report_generator import ReportGenerator

def simular_sesion_y_reporte():
    print("Iniciando simulación de diagnóstico...")
    db = DatabaseManager()
    
    # 1. Crear una nueva sesión para un coche inventado
    vin_simulado = "WAUZZZ4F0AN123456" # VIN típico de Audi A6 C6
    sesion_id = db.nueva_sesion(vin_simulado)
    print(f"Sesión creada con ID: {sesion_id} para VIN: {vin_simulado}")
    
    # 2. Registrar algunas lecturas de sensores (como si estuviéramos leyendo PIDs)
    print("Registrando sensores...")
    db.registrar_lectura(sesion_id, "RPM", 850.5, "rpm")
    db.registrar_lectura(sesion_id, "Temp. Refrigerante", 90.0, "°C")
    db.registrar_lectura(sesion_id, "Velocidad", 0.0, "km/h")
    
    # 3. Registrar fallos de prueba
    # Usamos códigos que hemos puesto en nuestro diccionario base
    print("Registrando fallos (DTCs)...")
    # P0171 está en el diccionario, la descripción se cogerá sola
    db.registrar_dtc(vin_simulado, "P0171", "Activo", "") 
    # Un fallo VAG específico
    db.registrar_dtc(vin_simulado, "01044", "Histórico", "")
    # Un fallo que NO está en el diccionario para ver qué pasa
    db.registrar_dtc(vin_simulado, "P9999", "Pendiente", "")
    
    print("Datos guardados en SQLite.")
    
    # 4. Generar el reporte
    print("Generando reporte TXT...")
    generador = ReportGenerator()
    ruta_reporte = generador.generar_reporte_txt(sesion_id)
    
    return ruta_reporte

if __name__ == "__main__":
    ruta = simular_sesion_y_reporte()
    print("\nSimulación completada. Revisa el archivo generado.")
