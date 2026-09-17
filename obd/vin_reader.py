import re


def leer_vin(respuesta_texto: str) -> str | None:
    """
    Decodifica la respuesta del PID 0902 (VIN) al string del VIN completo.
    Soporta múltiples formatos de tramas CAN del ELM327:
    - Multi-trama con numeración CAN (0: 49 02 01 57..., 1: 5A..., 2: ...)
    - Cabeceras CAN activas (7E8 10 14 49 02 01 ...)
    - Formato estándar de línea única (49 02 01 57 41 55 ...)
    - Formato sin espacios

    Returns:
        String del VIN (ej. 17 caracteres como 'WAUZZZ4F7BN000000'), o None si no es válido.
    """
    if not respuesta_texto or not isinstance(respuesta_texto, str):
        return None

    # 1. Si la respuesta contiene directamente un VIN en texto ASCII visible
    patron_vin = r"[A-HJ-NPR-Z0-9]{17}"
    coincidencia_directa = re.search(patron_vin, respuesta_texto.upper())
    if coincidencia_directa:
        # Asegurarse de que no sea solo una cadena de ceros
        vin_candidato = coincidencia_directa.group(0)
        if not vin_candidato.startswith("0000"):
            return vin_candidato

    # 2. Limpiar la respuesta línea por línea
    lineas = respuesta_texto.strip().splitlines()
    tokens_hex = []

    for linea in lineas:
        l = linea.strip()
        if not l or any(kw in l.upper() for kw in ["SEARCHING", "BUS INIT", "STOPPED", "ERROR"]):
            continue

        # Quitar prefijos de tramas CAN como "0:", "1:", "2:", "014"
        l = re.sub(r"^[0-9A-Fa-f]:\s*", "", l)
        l = re.sub(r"^7E[8-9A-Fa-f]\s*", "", l)
        if len(l) <= 3 and l.isalnum():  # Ej. "014" (longitud de trama ISO-TP)
            continue

        # Extraer todos los bytes hexadecimales de 2 dígitos
        palabras = l.split()
        for p in palabras:
            p_limpio = p.strip().strip(":").strip()
            if len(p_limpio) == 2:
                try:
                    int(p_limpio, 16)
                    tokens_hex.append(p_limpio.upper())
                except ValueError:
                    pass
            elif len(p_limpio) > 2 and len(p_limpio) % 2 == 0:
                # Si vienen bytes pegados, ej. 4902015741
                for i in range(0, len(p_limpio), 2):
                    par = p_limpio[i:i+2]
                    try:
                        int(par, 16)
                        tokens_hex.append(par.upper())
                    except ValueError:
                        pass

    if not tokens_hex:
        return None

    # 3. Buscar la cabecera OBD Mode 09 PID 02: "49", "02"
    cadena_hex = " ".join(tokens_hex)
    bytes_datos = []

    if "49 02 01" in cadena_hex:
        idx = cadena_hex.find("49 02 01")
        subcadena = cadena_hex[idx + len("49 02 01"):].strip()
        bytes_datos = subcadena.split()
    elif "49 02" in cadena_hex:
        idx = cadena_hex.find("49 02")
        subcadena = cadena_hex[idx + len("49 02"):].strip()
        bytes_datos = subcadena.split()
        # Si el primer byte es el contador de paquete (ej. 01), saltarlo
        if bytes_datos and bytes_datos[0] in ["01", "00"]:
            bytes_datos = bytes_datos[1:]
    else:
        # Usar todos los tokens hex directamente
        bytes_datos = tokens_hex

    # 4. Convertir los bytes a caracteres ASCII imprimibles
    caracteres = []
    for b in bytes_datos:
        try:
            val = int(b, 16)
            if 0x20 <= val <= 0x7E:  # Caracteres ASCII imprimibles
                caracteres.append(chr(val))
        except ValueError:
            pass

    texto_ascii = "".join(caracteres).strip()

    # 5. Extraer el VIN de 17 caracteres de la cadena decodificada
    m = re.search(patron_vin, texto_ascii.upper())
    if m:
        return m.group(0)

    # 6. Si no encontramos 17 exactos pero hay al menos 7 alfanuméricos
    limpio_alnum = "".join(c for c in texto_ascii if c.isalnum())
    if len(limpio_alnum) >= 7:
        return limpio_alnum[:17]

    return None