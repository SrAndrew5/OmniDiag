def extraer_byte(respuesta_texto, position=2):
    """
    Convierte una respuesta tipo '41 05 57' en el byte que necesitamos.
    Devuelve None si la respuesta está vacía o no tiene suficientes datos.
    """
    if not respuesta_texto:
        print("Aviso: respuesta vacía (el coche no contestó a tiempo).")
        return None

    partes = [int(b, 16) for b in respuesta_texto.split()]

    if position >= len(partes):
        print(f"Aviso: la respuesta no tiene suficientes datos (se esperaba posición {position}).")
        return None

    return partes[position]