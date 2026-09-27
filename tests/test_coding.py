from obd.long_coding import LongCodingManager

def probar_matematicas_coding():
    print("--- PRUEBA MATEMÁTICA DE LONG CODING ---")
    coding_mgr = LongCodingManager()
    
    # Supongamos que esta es la codificación original del Módulo Confort de un Audi
    # Byte 0: 01, Byte 1: 0A, Byte 2: 3F
    coding_original = "010A3F"
    print(f"Codificación Original: {coding_original}")
    
    # 0A en binario es 0000 1010
    # Queremos activar el Bit 0 del Byte 1 (el 0A pasaría a ser 0000 1011, que es 0B)
    print("\nActivando Byte 1, Bit 0 (ej. Activar pitido cinturón)...")
    nuevo_coding = coding_mgr.cambiar_bit(coding_original, byte_index=1, bit_index=0, activar=True)
    print(f"Resultado esperado: 010B3F")
    print(f"Resultado obtenido: {nuevo_coding}")
    if nuevo_coding == "010B3F":
        print("OK - PRUEBA 1 SUPERADA")
    else:
        print("ERROR EN PRUEBA 1")
        
    # Ahora vamos a desactivar el Bit 3 del Byte 1 (el 0B es 0000 1011, quitamos bit 3 (valor 8) -> 0000 0011 -> 03)
    print("\nDesactivando Byte 1, Bit 3 (ej. Desactivar luces diurnas escandinavas)...")
    nuevo_coding_2 = coding_mgr.cambiar_bit(nuevo_coding, byte_index=1, bit_index=3, activar=False)
    print(f"Resultado esperado: 01033F")
    print(f"Resultado obtenido: {nuevo_coding_2}")
    if nuevo_coding_2 == "01033F":
        print("OK - PRUEBA 2 SUPERADA")
    else:
        print("ERROR EN PRUEBA 2")

if __name__ == "__main__":
    probar_matematicas_coding()
