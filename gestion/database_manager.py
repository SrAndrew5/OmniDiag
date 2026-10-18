import sqlite3
import os

import config
from datetime import datetime


class DatabaseManager:
    """
    Gestiona la base de datos SQLite local de AudiDiag Pro.

    Tablas:
        sesiones       — Una entrada por conexión al vehículo (VIN + fecha).
        dtcs           — Fallos detectados durante las sesiones.
        freeze_frame   — Snapshot de parámetros del coche en el momento de cada fallo.
        lecturas       — Lecturas de sensores en vivo durante las sesiones.
        diccionario_dtc — Catálogo de códigos de error con su descripción.
    """

    def __init__(self):
        self.db_path = config.DATABASE_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._migrar_db()   # ← aplica columnas nuevas a tablas existentes

    # ──────────────────────────────────────────────────────────────────────────
    #  MIGRACIÓN (compatibilidad con BDs antiguas)
    # ──────────────────────────────────────────────────────────────────────────
    def _migrar_db(self):
        """
        Añade columnas que pueden faltar en bases de datos creadas con versiones
        anteriores del esquema. SQLite no permite DROP/MODIFY, pero sí ADD COLUMN.
        Ignora silenciosamente si la columna ya existe.
        """
        migraciones = [
            "ALTER TABLE dtcs ADD COLUMN sesion_id INTEGER",
            "ALTER TABLE dtcs ADD COLUMN modulo    TEXT",
        ]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for sql in migraciones:
                try:
                    cursor.execute(sql)
                except sqlite3.OperationalError:
                    pass   # Columna ya existe → ignorar
            self._poblar_diccionario_base(cursor)
            conn.commit()


    # ──────────────────────────────────────────────────────────────────────────
    #  INICIALIZACIÓN
    # ──────────────────────────────────────────────────────────────────────────
    def _init_db(self):
        """Crea las tablas si no existen y rellena el diccionario base."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS sesiones (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    vin          TEXT    NOT NULL,
                    fecha_inicio TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dtcs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    sesion_id   INTEGER,
                    vin         TEXT    NOT NULL,
                    modulo      TEXT,
                    timestamp   TEXT    NOT NULL,
                    codigo      TEXT    NOT NULL,
                    estado      TEXT,
                    descripcion TEXT,
                    FOREIGN KEY(sesion_id) REFERENCES sesiones(id)
                );

                CREATE TABLE IF NOT EXISTS freeze_frame (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    dtc_id    INTEGER NOT NULL,
                    parametro TEXT    NOT NULL,
                    valor     REAL,
                    unidad    TEXT,
                    FOREIGN KEY(dtc_id) REFERENCES dtcs(id)
                );

                CREATE TABLE IF NOT EXISTS lecturas (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    sesion_id INTEGER,
                    timestamp TEXT    NOT NULL,
                    sensor    TEXT    NOT NULL,
                    valor     REAL,
                    unidad    TEXT,
                    FOREIGN KEY(sesion_id) REFERENCES sesiones(id)
                );

                CREATE TABLE IF NOT EXISTS diccionario_dtc (
                    codigo      TEXT PRIMARY KEY,
                    descripcion TEXT NOT NULL
                );
            """)
            conn.commit()
            self._poblar_diccionario_base(cursor)
            conn.commit()

    def _poblar_diccionario_base(self, cursor):
        """Rellena el diccionario con códigos comunes y específicos de VAG / Audi."""
        dtcs_comunes = [
            # ── Calentadores / Bujías incandescentes (Audi 2.7 / 3.0 TDI) ──
            ("P0670", "Módulo de control de bujías incandescentes (Glow Plug) - Circuito defectuoso"),
            ("P0671", "Bujía incandescente Cilindro 1 (Q10) - Circuito defectuoso / Circuito abierto"),
            ("P0672", "Bujía incandescente Cilindro 2 (Q11) - Circuito defectuoso / Circuito abierto"),
            ("P0673", "Bujía incandescente Cilindro 3 (Q12) - Circuito defectuoso / Circuito abierto"),
            ("P0674", "Bujía incandescente Cilindro 4 (Q13) - Circuito defectuoso / Circuito abierto"),
            ("P0675", "Bujía incandescente Cilindro 5 (Q14) - Circuito defectuoso / Circuito abierto"),
            ("P0676", "Bujía incandescente Cilindro 6 (Q15) - Circuito defectuoso / Circuito abierto"),
            ("0670", "Módulo de bujías incandescentes (Glow Plug) - Circuito defectuoso"),
            ("0671", "Bujía incandescente Cilindro 1 (Q10) - Circuito defectuoso / Circuito abierto"),
            ("0672", "Bujía incandescente Cilindro 2 (Q11) - Circuito defectuoso / Circuito abierto"),
            ("0673", "Bujía incandescente Cilindro 3 (Q12) - Circuito defectuoso / Circuito abierto"),
            ("0674", "Bujía incandescente Cilindro 4 (Q13) - Circuito defectuoso / Circuito abierto"),
            ("0675", "Bujía incandescente Cilindro 5 (Q14) - Circuito defectuoso / Circuito abierto"),
            ("0676", "Bujía incandescente Cilindro 6 (Q15) - Circuito defectuoso / Circuito abierto"),
            # ── EGR y Escape (Audi V6 TDI / Multimarca) ──
            ("P0400", "Sistema EGR (Recirculación de Gases de Escape) - Mal funcionamiento del flujo (Válvula anulada/desconectada)"),
            ("0400",  "Sistema EGR (Recirculación de Gases de Escape) - Mal funcionamiento del flujo (Válvula anulada/desconectada)"),
            ("P0401", "Sistema EGR (Recirculación Gases de Escape) - Flujo insuficiente"),
            ("0401", "Sistema EGR (Recirculación Gases de Escape) - Flujo insuficiente"),
            ("P0402", "Sistema EGR (Recirculación Gases de Escape) - Flujo excesivo"),
            ("0402", "Sistema EGR (Recirculación Gases de Escape) - Flujo excesivo"),
            ("P0403", "Válvula de recirculación EGR (N18) - Mal funcionamiento circuito"),
            ("0403", "Válvula de recirculación EGR (N18) - Mal funcionamiento circuito"),
            ("P0404", "Válvula EGR (N18) - Rango / Rendimiento fuera de tolerancia"),
            ("P0405", "Sensor posición de válvula EGR (G212) - Señal demasiado baja"),
            ("P0406", "Sensor posición de válvula EGR (G212) - Señal demasiado alta"),
            # ── DPF / Filtro de Partículas Diésel ──
            ("P2002", "Filtro de partículas diésel (DPF Banco 1) - Eficiencia por debajo del umbral"),
            ("P242F", "Filtro de partículas diésel (DPF) - Restricción / Acumulación de cenizas"),
            ("P2452", "Sensor de presión diferencial DPF (G450) - Fallo eléctrico en circuito"),
            ("P2453", "Sensor de presión diferencial DPF (G450) - Señal inverosímil"),
            ("P0471", "Sensor de contrapresión de escape (G450) - Rango/Rendimiento fuera de rango"),
            # ── Turbo y Admisión (V6 TDI) ──
            ("P0299", "Turbocompresor / Sobrealimentador - Presión insuficiente (Underboost)"),
            ("0299", "Turbocompresor / Sobrealimentador - Presión insuficiente (Underboost)"),
            ("P0234", "Turbocompresor / Sobrealimentador - Límite de sobrealimentación sobrepasado (Overboost)"),
            ("P0101", "Caudalímetro / Sensor MAF (G70) - Rango / Rendimiento fuera de límites"),
            ("P0102", "Caudalímetro / Sensor MAF (G70) - Señal demasiado baja"),
            ("P0103", "Caudalímetro / Sensor MAF (G70) - Señal demasiado alta"),
            ("P2008", "Válvulas chapaletas admisión colector (Banco 1) - Circuito abierto"),
            ("P2015", "Actuador chapaletas admisión (Banco 1) - Señal inverosímil / Desgaste varillaje"),
            ("P2016", "Actuador chapaletas admisión (Banco 1) - Cortocircuito a masa"),
            ("P2020", "Actuador chapaletas admisión (Banco 2) - Señal inverosímil / Desgaste varillaje"),
            ("P2112", "Actuador mariposa de admisión (V157) - Atascado cerrado"),
            ("P2100", "Motor mariposa de admisión (V157) - Circuito abierto"),
            # ── Inyección Common Rail ──
            ("P0087", "Presión de combustible en rampa Common Rail - Demasiado baja"),
            ("P0088", "Presión de combustible en rampa Common Rail - Demasiado alta"),
            ("P0201", "Inyector Cilindro 1 (N30) - Fallo circuito eléctrico"),
            ("P0202", "Inyector Cilindro 2 (N31) - Fallo circuito eléctrico"),
            ("P0203", "Inyector Cilindro 3 (N32) - Fallo circuito eléctrico"),
            ("P0204", "Inyector Cilindro 4 (N33) - Fallo circuito eléctrico"),
            ("P0205", "Inyector Cilindro 5 (N83) - Fallo circuito eléctrico"),
            ("P0206", "Inyector Cilindro 6 (N84) - Fallo circuito eléctrico"),
            # ── Sensores Motor ──
            ("P0118", "Sensor temperatura refrigerante (G62) - Señal demasiado alta"),
            ("P0116", "Sensor temperatura refrigerante (G62) - Rango / Rendimiento"),
            ("P0300", "Fallo de encendido / combustión detectado en múltiples cilindros"),
            ("P0420", "Eficiencia catalizador por debajo del umbral (Banco 1)"),
            # ── Transmisión Tiptronic (02) ──
            ("P0715", "Sensor velocidad árbol de entrada (G182) - Fallo en circuito"),
            ("P0730", "Relación de transmisión incorrecta"),
            ("P0741", "Embrague convertidor de par - Atascado abierto / Sin transferencia"),
            # ── ABS / ESP (03) ──
            ("C0031", "Sensor velocidad rueda delantera izquierda - Fallo"),
            ("C0051", "Sensor velocidad rueda trasera derecha - Señal errática"),
            ("00283", "Sensor velocidad rueda delantera izq. (G47) - Señal inverosímil / Circuito abierto"),
            ("00285", "Sensor velocidad rueda delantera der. (G45) - Señal inverosímil / Circuito abierto"),
            ("00287", "Sensor velocidad rueda trasera der. (G44) - Señal inverosímil / Circuito abierto"),
            ("00290", "Sensor velocidad rueda trasera izq. (G46) - Señal inverosímil / Circuito abierto"),
            ("01423", "Sensor aceleración transversal (G200) - Fallo eléctrico"),
            ("01435", "Sensor 1 presión de frenado (G201) - Señal inverosímil"),
            ("00778", "Sensor de ángulo de dirección (G85) - Sin ajuste básico / Señal inverosímil"),
            ("01826", "Sensor ángulo dirección (G85) - Tensión de alimentación borne 30"),
            # ── Gateway CAN (19) y Buses de Red ──
            ("U0100", "Pérdida de comunicación con ECM/PCM (Centralita Motor)"),
            ("U0101", "Pérdida de comunicación con TCM (Centralita Transmisión)"),
            ("01314", "Unidad de control del motor (J623) - Sin comunicación"),
            ("01316", "Unidad de control de frenos / ABS (J104) - Sin comunicación"),
            ("01324", "Unidad de control de tracción total quattro (J492) - Sin comunicación"),
            ("00470", "Línea de datos combinada Komfort en modo monofilar (cable cortado)"),
            ("01336", "Bus de datos confort en modo de emergencia monofilar"),
            # ── Cuadro Instrumentos (17) y Módulos Confort (46 / 09) ──
            ("00532", "Tensión de alimentación B+ - Valor por debajo del umbral"),
            ("01044", "Unidad de control mal codificada"),
            ("01330", "Unidad central de confort (J393) - Sin señal / Sin comunicación"),
            ("01331", "Unidad de control puerta conductor (J386) - Fallo en circuito"),
            ("01332", "Unidad de control puerta acompañante (J387) - Fallo en circuito"),
            ("01516", "Borne 30 izquierdo - Fallo en circuito"),
            ("01517", "Unidad de control para remolque (J345) - Sin comunicación"),
            ("B1004", "Elevalunas delantero izquierdo - Cortocircuito"),
            ("B1112", "Control espejo retrovisor - Sin comunicación"),
            ("B0001", "Airbag conductor - Circuito abierto"),
            ("B0057", "Sensor impacto lateral - Señal fuera de rango"),
            ("B1200", "Sensor temperatura interior - Circuito abierto"),
            ("B1210", "Actuador compuerta de mezcla de aire - Posición incorrecta"),
            # ── Iluminación y Faros (Central Eléctrica 09 / Confort 46) ──
            ("01496", "Lámpara de faro antiniebla izquierdo (L22) - Circuito abierto / Cortocircuito"),
            ("01497", "Lámpara de faro antiniebla derecho (L23) - Circuito abierto / Cortocircuito"),
            ("01500", "Lámpara de luz antiniebla trasera derecha (L47) - Defectuosa / Circuito abierto"),
            ("01501", "Lámpara de luz antiniebla trasera izquierda (L46) - Defectuosa / Circuito abierto"),
            ("01502", "Lámpara de luz antiniebla trasera izquierda (L46) - Señal fuera de rango"),
            ("01504", "Luz de la matrícula (X) - Circuito abierto o cortocircuito"),
            ("00984", "Lámpara para piloto trasero izquierdo (M4) - Defectuosa o circuito abierto"),
            ("00985", "Lámpara para piloto trasero derecho (M2) - Defectuosa o cortocircuito a masa"),
            ("00987", "Lámpara para luz de freno izquierda (M9) - Defectuosa"),
            ("00988", "Lámpara para luz de freno derecha (M10) - Defectuosa"),
            ("01518", "Lámpara para luz de marcha atrás izquierda (M16) - Defectuosa"),
            ("01519", "Lámpara para luz de marcha atrás derecha (M17) - Defectuosa"),
            ("00978", "Lámpara para luz de cruce izquierda (M29) - Circuito abierto"),
            ("00979", "Lámpara para luz de cruce derecha (M31) - Circuito abierto"),
            ("00982", "Lámpara para luz de posición lateral izquierda (M33) - Defectuosa"),
            ("00983", "Lámpara para luz de posición lateral derecha (M34) - Defectuosa"),
            ("02096", "Limitador de corriente para luz trasera izquierda - Cortocircuito"),
            ("02097", "Limitador de corriente para luz trasera derecha - Cortocircuito a masa"),
            ("02381", "Luz trasera / LED piloto derecho - Avería en circuito / Cortocircuito"),
            ("02382", "Luz trasera / LED piloto izquierdo - Avería en circuito / Cortocircuito"),
            ("02745", "Lámpara para luz de conducción diurna izquierda - Circuito abierto"),
            ("02746", "Lámpara para luz de conducción diurna derecha - Circuito abierto"),
            # ── Códigos VAG Decimales Frecuentes ──
            ("01650", "Bujía incandescente Cilindro 2 (Q11) - Circuito defectuoso (P0672)"),
            ("01653", "Bujía incandescente Cilindro 5 (Q14) - Circuito defectuoso (P0675)"),
            ("01651", "Bujía incandescente Cilindro 3 (Q12) - Circuito defectuoso (P0673)"),
            ("01649", "Bujía incandescente Cilindro 1 (Q10) - Circuito defectuoso (P0671)"),
            ("01025", "Sistema EGR - Flujo insuficiente detectado (P0401)"),
        ]
        catalog_file = os.path.join(os.path.dirname(self.db_path), "dtc_catalog.json")
        if os.path.exists(catalog_file):
            try:
                import json
                with open(catalog_file, "r", encoding="utf-8") as f:
                    catalogo = json.load(f)
                cursor.executemany(
                    "INSERT OR REPLACE INTO diccionario_dtc (codigo, descripcion) VALUES (?, ?)",
                    list(catalogo.items())
                )
            except Exception:
                cursor.executemany(
                    "INSERT OR REPLACE INTO diccionario_dtc (codigo, descripcion) VALUES (?, ?)",
                    dtcs_comunes
                )
        else:
            cursor.executemany(
                "INSERT OR REPLACE INTO diccionario_dtc (codigo, descripcion) VALUES (?, ?)",
                dtcs_comunes
            )
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dtc_codigo ON diccionario_dtc(codigo)")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    #  SESIONES
    # ──────────────────────────────────────────────────────────────────────────
    def nueva_sesion(self, vin: str) -> int:
        """
        Crea una nueva sesión de diagnóstico.

        Returns:
            ID de la sesión recién creada.
        """
        vin = vin or "DESCONOCIDO"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sesiones (vin, fecha_inicio) VALUES (?, ?)",
                (vin, timestamp)
            )
            conn.commit()
            return cursor.lastrowid

    def obtener_sesiones(self, vin: str = None) -> list:
        """
        Devuelve la lista de sesiones almacenadas, opcionalmente filtradas por VIN.

        Returns:
            Lista de tuplas (id, vin, fecha_inicio).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if vin:
                cursor.execute(
                    "SELECT id, vin, fecha_inicio FROM sesiones WHERE vin=? ORDER BY id DESC",
                    (vin,)
                )
            else:
                cursor.execute(
                    "SELECT id, vin, fecha_inicio FROM sesiones ORDER BY id DESC"
                )
            return cursor.fetchall()

    # ──────────────────────────────────────────────────────────────────────────
    #  DTC + FREEZE FRAME
    # ──────────────────────────────────────────────────────────────────────────
    def registrar_dtc(self, vin: str, codigo: str, estado: str,
                      descripcion: str = "", modulo: str = "",
                      sesion_id: int = None,
                      freeze_frame: dict = None) -> int:
        """
        Registra un fallo DTC y opcionalmente su Freeze Frame.

        Args:
            vin:          VIN del vehículo.
            codigo:       Código del fallo (ej. "P0171").
            estado:       "Activo", "Pendiente", "Histórico".
            descripcion:  Texto descriptivo (se busca en diccionario si está vacío).
            modulo:       Nombre del módulo de origen (ej. "Motor (01)").
            sesion_id:    ID de la sesión actual.
            freeze_frame: Dict {parametro: (valor, unidad)} con el snapshot del coche.

        Returns:
            ID del DTC insertado.
        """
        vin = vin or "DESCONOCIDO"
        if not descripcion:
            descripcion = self.traducir_dtc(codigo)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO dtcs (sesion_id, vin, modulo, timestamp, codigo, estado, descripcion)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sesion_id, vin, modulo, timestamp, codigo, estado, descripcion)
            )
            dtc_id = cursor.lastrowid

            # Guardar freeze frame si se proporcionó
            if freeze_frame and dtc_id:
                filas_ff = [
                    (dtc_id, parametro, valor, unidad)
                    for parametro, (valor, unidad) in freeze_frame.items()
                ]
                cursor.executemany(
                    "INSERT INTO freeze_frame (dtc_id, parametro, valor, unidad) VALUES (?, ?, ?, ?)",
                    filas_ff
                )

            conn.commit()
            return dtc_id

    def obtener_freeze_frame(self, dtc_id: int) -> list:
        """
        Recupera el Freeze Frame de un DTC específico.

        Returns:
            Lista de tuplas (parametro, valor, unidad).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT parametro, valor, unidad FROM freeze_frame WHERE dtc_id=?",
                (dtc_id,)
            )
            return cursor.fetchall()

    def obtener_dtcs_sesion(self, sesion_id: int) -> list:
        """
        Devuelve todos los DTCs de una sesión.

        Returns:
            Lista de tuplas (id, modulo, codigo, estado, descripcion, timestamp).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, modulo, codigo, estado, descripcion, timestamp
                   FROM dtcs WHERE sesion_id=? ORDER BY timestamp""",
                (sesion_id,)
            )
            return cursor.fetchall()

    def traducir_dtc(self, codigo: str) -> str:
        """
        Busca la descripción en castellano de un código de error.
        Maneja variaciones como '0672', 'P0672', 'DTC 0672', etc.

        Returns:
            Descripción del código o mensaje explicativo si no está en catálogo.
        """
        if not codigo:
            return "Código no especificado"

        import re
        c = str(codigo).strip().upper()

        candidatos = [c]

        # 1. Si contiene formato VAG de 5 dígitos (ej. 01496 o VAG 01496 o 1496)
        match_vag = re.findall(r'\b(0\d{4}|\d{5})\b', c)
        for m in match_vag:
            candidatos.append(m)

        # 2. Si contiene código SAE (ej. P0672, U0100, C0031, B1004)
        match_sae = re.findall(r'\b([PCBU]\d{4})\b', c)
        for m in match_sae:
            candidatos.append(m)

        # 3. Limpieza de tokens estándar
        limpio = c.replace("DTC", "").replace("VAG", "").strip()
        limpio = limpio.split("[")[0].split("(")[0].strip()
        if limpio:
            candidatos.append(limpio)
            partes = limpio.split()
            if partes:
                candidatos.append(partes[0])

        # 4. Prefijos estándar SAE (ej. 'P05D8' -> '05D8', '0672' -> 'P0672')
        for cand in list(candidatos):
            if len(cand) == 5 and cand[0] in ("P", "C", "B", "U"):
                candidatos.append(cand[1:])
            elif len(cand) == 4 and cand.isdigit():
                candidatos.append(f"0{cand}")
                candidatos.append(f"P{cand}")

        # 5. Si es un hex de 4 caracteres (ej. '05D8'), convertir a decimal VAG ('01496')
        for cand in list(candidatos):
            if len(cand) == 4 and all(ch in "0123456789ABCDEF" for ch in cand):
                try:
                    dec_val = int(cand, 16)
                    candidatos.append(f"{dec_val:05d}")
                except Exception:
                    pass

        # Eliminar duplicados manteniendo orden
        vistos = set()
        candidatos_unicos = []
        for cand in candidatos:
            if cand and cand not in vistos:
                vistos.add(cand)
                candidatos_unicos.append(cand)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for cand in candidatos_unicos:
                    cursor.execute(
                        "SELECT descripcion FROM diccionario_dtc WHERE codigo=?",
                        (cand,)
                    )
                    res = cursor.fetchone()
                    if res and res[0]:
                        return res[0]
        except Exception:
            pass

        return f"Avería {candidatos_unicos[0] if candidatos_unicos else c} — sin descripción en catálogo local."

    def buscar_descripcion(self, codigo: str) -> str:
        """Alias para traducir_dtc, garantizando total retrocompatibilidad."""
        return self.traducir_dtc(codigo)

    # ──────────────────────────────────────────────────────────────────────────
    #  LECTURAS DE SENSORES
    # ──────────────────────────────────────────────────────────────────────────
    def registrar_lectura(self, sesion_id: int, sensor: str, valor: float, unidad: str):
        """Registra una lectura de sensor asociada a una sesión activa."""
        if sesion_id is None:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO lecturas (sesion_id, timestamp, sensor, valor, unidad)
                   VALUES (?, ?, ?, ?, ?)""",
                (sesion_id, timestamp, sensor, valor, unidad)
            )
            conn.commit()

    def obtener_lecturas_sesion(self, sesion_id: int) -> list:
        """
        Devuelve todas las lecturas de sensores de una sesión.

        Returns:
            Lista de tuplas (timestamp, sensor, valor, unidad).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT timestamp, sensor, valor, unidad FROM lecturas WHERE sesion_id=? ORDER BY timestamp",
                (sesion_id,)
            )
            return cursor.fetchall()
