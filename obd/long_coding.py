class LongCodingManager:
    """
    Motor lógico para manipular los Bytes y Bits de la codificación de una ECU
    de forma segura y matemáticamente exacta.
    """

    @staticmethod
    def hex_to_bytes(cadena_hex: str) -> list[int]:
        """
        Convierte un string de codificación ('01 0A 3F' o '010A3F') a una lista de enteros ([1, 10, 63]).
        Se eliminan los espacios si los hubiera.
        """
        if not cadena_hex or not isinstance(cadena_hex, str):
            return []
        cadena_limpia = cadena_hex.replace(" ", "").strip()
        if len(cadena_limpia) % 2 != 0:
            raise ValueError("La cadena hexadecimal debe tener longitud par.")
        return [int(cadena_limpia[i:i+2], 16) for i in range(0, len(cadena_limpia), 2)]

    @staticmethod
    def bytes_to_hex(lista_bytes: list[int], separador: str = " ") -> str:
        """
        Convierte una lista de enteros ([1, 10, 63]) a string Hex ('01 0A 3F').
        """
        return separador.join([f"{b:02X}" for b in lista_bytes])

    def cambiar_bit(self, cadena_hex: str, byte_index: int, bit_index: int,
                    activar: bool = True, con_espacios: bool = True) -> str:
        """
        Toma una cadena de codificación, va al Byte indicado, y activa (1) o desactiva (0) 
        el Bit indicado, sin afectar al resto.
        - byte_index: 0-indexed (El primer par de letras es el Byte 0)
        - bit_index: 0-indexed (0 a 7, siendo 0 el bit menos significativo - derecha)
        - activar: True (pone a 1), False (pone a 0)
        - con_espacios: si True devuelve 'FF D0 00', si False 'FFD000'
        """
        if bit_index < 0 or bit_index > 7:
            raise ValueError("El índice del Bit debe estar entre 0 y 7.")

        bytes_lista = self.hex_to_bytes(cadena_hex)
        if byte_index < 0 or byte_index >= len(bytes_lista):
            raise IndexError(f"El índice de Byte {byte_index} está fuera de rango ({len(bytes_lista)} bytes disponibles).")

        valor_actual = bytes_lista[byte_index]

        if activar:
            nuevo_valor = valor_actual | (1 << bit_index)
        else:
            nuevo_valor = valor_actual & ~(1 << bit_index)

        bytes_lista[byte_index] = nuevo_valor
        return self.bytes_to_hex(bytes_lista, separador=" " if con_espacios else "")

    def leer_bit(self, cadena_hex: str, byte_index: int, bit_index: int) -> bool:
        """
        Devuelve True si el bit está activo (1), False si está inactivo (0).
        Retorna False si el índice de byte está fuera de rango o el string es inválido.
        """
        try:
            bytes_lista = self.hex_to_bytes(cadena_hex)
            if byte_index < 0 or byte_index >= len(bytes_lista):
                return False
            if bit_index < 0 or bit_index > 7:
                return False
            valor = bytes_lista[byte_index]
            return (valor & (1 << bit_index)) != 0
        except Exception:
            return False
