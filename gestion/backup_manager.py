import os

import json
import re
from datetime import datetime
import config


import unicodedata

def _sanitizar_nombre(texto: str) -> str:
    """
    Elimina o reemplaza caracteres inválidos en nombres de fichero de Windows.
    Caracteres prohibidos: \\ / : * ? " < > |
    También elimina tildes/acentos y recorta espacios y puntos al final.
    """
    if not texto:
        return "modulo"
    # Quitar acentos (ej. Electrónica -> Electronica)
    texto_sin_acentos = unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII')
    limpio = re.sub(r'[\\/:*?"<>|]', '_', texto_sin_acentos)
    limpio = re.sub(r'[_\s]+', '_', limpio).strip('_').strip()
    return limpio or "modulo"


class BackupManager:
    """Gestiona el guardado y restaurado de backups de coding de módulos."""

    def __init__(self):
        os.makedirs(config.BACKUP_FOLDER, exist_ok=True)

    def guardar_backup(self, modulo: str, coche: str, bytes_coding, etiqueta: str = None) -> str:
        """
        Guarda un backup del coding de un módulo en formato JSON.

        Args:
            modulo:       Nombre del módulo (ej. 'Confort / Electrónica (46)').
            coche:        VIN del vehículo.
            bytes_coding: Valor de coding (string hex o lista de bytes).
            etiqueta:     Etiqueta opcional descriptiva ('ORIGINAL', 'MANUAL', etc.).

        Returns:
            Ruta absoluta del fichero guardado.
        """
        os.makedirs(config.BACKUP_FOLDER, exist_ok=True)

        modulo_safe = _sanitizar_nombre(modulo)
        coche_safe  = _sanitizar_nombre(coche) if coche else "DESCONOCIDO"
        timestamp   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        tag_prefix  = f"{_sanitizar_nombre(etiqueta)}_" if etiqueta else ""

        nombre_fichero = f"backup_{tag_prefix}{modulo_safe}_{coche_safe}_{timestamp}.json"
        ruta_completa  = os.path.join(config.BACKUP_FOLDER, nombre_fichero)

        # Si bytes_coding es una lista, convertirla también a formato legible
        datos = {
            "modulo":       modulo,
            "coche":        coche or "DESCONOCIDO",
            "fecha_hora":   timestamp,
            "etiqueta":     etiqueta or "Copia Automática",
            "bytes_coding": bytes_coding,
        }

        with open(ruta_completa, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)

        return ruta_completa

    def listar_backups(self, modulo: str = None, coche: str = None) -> list[str]:
        """Lista los backups disponibles en disco, opcionalmente filtrados."""
        if not os.path.exists(config.BACKUP_FOLDER):
            return []

        ficheros = [f for f in os.listdir(config.BACKUP_FOLDER) if f.endswith(".json")]

        if modulo:
            modulo_safe = _sanitizar_nombre(modulo)
            patrones = [modulo_safe.lower()]
            if "confort" in modulo.lower() or "46" in modulo or "bcm" in modulo.lower():
                patrones.extend(["bcm", "confort", "46"])
            elif "motor" in modulo.lower() or "01" in modulo or "ecu" in modulo.lower():
                patrones.extend(["motor", "ecu", "01"])
            elif "cuadro" in modulo.lower() or "17" in modulo:
                patrones.extend(["cuadro", "17", "instrument"])

            ficheros = [
                f for f in ficheros
                if any(p in f.lower() for p in patrones)
            ]

        if coche:
            coche_safe = _sanitizar_nombre(coche).lower()
            ficheros = [f for f in ficheros if coche_safe in f.lower()]

        # Ordenar por fecha real del archivo (el más reciente primero)
        def get_mtime(fname):
            full_p = os.path.join(config.BACKUP_FOLDER, fname)
            return os.path.getmtime(full_p) if os.path.exists(full_p) else 0

        return sorted(ficheros, key=get_mtime, reverse=True)

    def cargar_backup(self, nombre_fichero: str) -> dict | None:
        """Carga un backup concreto y devuelve sus datos como dict."""
        ruta_completa = os.path.join(config.BACKUP_FOLDER, nombre_fichero)
        if not os.path.exists(ruta_completa):
            return None

        try:
            with open(ruta_completa, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def obtener_backups_detallados(self, modulo: str = None, coche: str = None) -> list[dict]:
        """
        Devuelve la lista de backups cargados con toda su información útil para la interfaz.
        Ordenados del más reciente al más antiguo.
        """
        ficheros = self.listar_backups(modulo=modulo, coche=coche)
        resultado = []
        for f in ficheros:
            datos = self.cargar_backup(f)
            if not datos:
                continue

            datos["fichero"] = f

            # Normalizar siempre bytes_coding a una cadena hex limpia y con espacios
            raw_coding = datos.get("bytes_coding")
            if isinstance(raw_coding, list):
                hex_limpio = " ".join(f"{b:02X}" for b in raw_coding)
            elif isinstance(raw_coding, str):
                c = raw_coding.replace(" ", "").strip()
                if len(c) % 2 == 0 and len(c) >= 2:
                    hex_limpio = " ".join(c[i:i+2] for i in range(0, len(c), 2))
                else:
                    hex_limpio = raw_coding
            else:
                hex_limpio = str(raw_coding or "")

            datos["hex_formateado"] = hex_limpio
            resultado.append(datos)

        return resultado

    def comparar_codificaciones(self, coding_a, coding_b, modulo: str = "") -> dict:
        """
        Compara dos codificaciones (hexadecimales o listas de bytes) byte a byte y bit a bit.
        Devuelve un análisis detallado de diferencias.
        """
        def _a_bytes(c):
            if isinstance(c, list):
                return bytes(c)
            if isinstance(c, (bytes, bytearray)):
                return bytes(c)
            if isinstance(c, str):
                limpio = c.replace(" ", "").replace("-", "").strip()
                if len(limpio) % 2 != 0:
                    limpio = "0" + limpio
                try:
                    return bytes.fromhex(limpio)
                except Exception:
                    return b""
            return b""

        bytes_a = _a_bytes(coding_a)
        bytes_b = _a_bytes(coding_b)

        max_len = max(len(bytes_a), len(bytes_b))
        diferencias = []

        for i in range(max_len):
            val_a = bytes_a[i] if i < len(bytes_a) else None
            val_b = bytes_b[i] if i < len(bytes_b) else None

            if val_a != val_b:
                bits_diff = []
                if val_a is not None and val_b is not None:
                    for bit in range(8):
                        bit_a = (val_a >> bit) & 1
                        bit_b = (val_b >> bit) & 1
                        if bit_a != bit_b:
                            bits_diff.append({
                                "bit": bit,
                                "antes": bit_a,
                                "despues": bit_b,
                                "cambio": "ACTIVADO (0 -> 1)" if bit_b == 1 else "DESACTIVADO (1 -> 0)"
                            })

                diferencias.append({
                    "byte_index": i,
                    "hex_a": f"{val_a:02X}" if val_a is not None else "--",
                    "hex_b": f"{val_b:02X}" if val_b is not None else "--",
                    "bin_a": f"{val_a:08b}" if val_a is not None else "--------",
                    "bin_b": f"{val_b:08b}" if val_b is not None else "--------",
                    "bits_cambiados": bits_diff,
                    "descripcion": f"Byte {i:02d}: Modificación de {val_a:02X} a {val_b:02X}" if (val_a is not None and val_b is not None) else f"Byte {i:02d}: Tamaño dispar"
                })

        return {
            "coinciden": len(diferencias) == 0,
            "modulo": modulo,
            "len_a": len(bytes_a),
            "len_b": len(bytes_b),
            "hex_a": " ".join(f"{b:02X}" for b in bytes_a),
            "hex_b": " ".join(f"{b:02X}" for b in bytes_b),
            "total_diferencias": len(diferencias),
            "diferencias": diferencias
        }

    def comparar_backups_por_nombre(self, fichero_a: str, fichero_b: str) -> dict:
        """Carga dos ficheros de backup por nombre y realiza una comparación de diferencias."""
        datos_a = self.cargar_backup(fichero_a)
        datos_b = self.cargar_backup(fichero_b)

        if not datos_a or not datos_b:
            return {"error": "Uno o ambos archivos de backup no se pudieron leer."}

        res = self.comparar_codificaciones(
            datos_a.get("bytes_coding", ""),
            datos_b.get("bytes_coding", ""),
            modulo=datos_a.get("modulo", "")
        )
        res["meta_a"] = {
            "fichero": fichero_a,
            "etiqueta": datos_a.get("etiqueta", ""),
            "fecha": datos_a.get("fecha_hora", ""),
            "modulo": datos_a.get("modulo", "")
        }
        res["meta_b"] = {
            "fichero": fichero_b,
            "etiqueta": datos_b.get("etiqueta", ""),
            "fecha": datos_b.get("fecha_hora", ""),
            "modulo": datos_b.get("modulo", "")
        }
        return res