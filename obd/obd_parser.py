# obd_parser.py

class OBDParser:
    """Interpreta tramas OBD2 genéricas (modo 01, 03, 04) según estándar SAE J1979."""

    # --- Helpers internos: fórmulas que se repiten en varios PIDs ---

    def _porcentaje_255(self, byte_a):
        """Fórmula común: A/2.55 (0-100%). Usada por carga motor, acelerador, EGR, etc."""
        return byte_a / 2.55

    def _temp_menos_40(self, byte_a):
        """Fórmula común: A - 40 (°C). Usada por refrigerante, admisión, aceite, ambiente."""
        return byte_a - 40

    def _fuel_trim(self, byte_a):
        """Fórmula común: (100/128)*A - 100 (%). Usada por fuel trims y EGR error."""
        return (100 / 128) * byte_a - 100

    # --- DTCs (modo 03) ---

    def parsear_dtc(self, byte_a, byte_b):
        primera_letra = ["P", "C", "B", "U"][(byte_a >> 6) & 0x03]
        digito1 = (byte_a >> 4) & 0x03
        digito2 = byte_a & 0x0F
        digito3 = (byte_b >> 4) & 0x0F
        digito4 = byte_b & 0x0F
        return f"{primera_letra}{digito1}{digito2:X}{digito3:X}{digito4:X}"

    def interpretar_respuesta_dtc(self, respuesta_hex):
        bytes_lista = [int(b, 16) for b in respuesta_hex.split()]
        if bytes_lista[0] != 0x43:
            return []
        datos = bytes_lista[1:]
        codigos = []
        for i in range(0, len(datos), 2):
            if i + 1 < len(datos):
                byte_a, byte_b = datos[i], datos[i + 1]
                if byte_a != 0 or byte_b != 0:
                    codigos.append(self.parsear_dtc(byte_a, byte_b))
        return codigos

    # --- PID 04-11: los que ya tenías ---

    def parsear_carga_motor(self, byte_a):
        """PID 04: Calculated engine load. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    def parsear_temp_refrigerante(self, byte_a):
        """PID 05: Engine coolant temperature. A-40 (°C)"""
        return self._temp_menos_40(byte_a)

    def parsear_fuel_trim(self, byte_a):
        """PIDs 06/07/08/09: Fuel trim corto/largo, banco 1/2. (100/128)*A-100 (%)"""
        return self._fuel_trim(byte_a)

    def parsear_presion_combustible(self, byte_a):
        """PID 0A: Fuel pressure (gauge). 3*A (kPa)"""
        return 3 * byte_a

    def parsear_presion_admision(self, byte_a):
        """PID 0B: Intake manifold absolute pressure. A directo (kPa)"""
        return byte_a

    def parsear_rpm(self, byte_a, byte_b):
        """PID 0C: Engine speed. ((A*256)+B)/4 (rpm)"""
        return ((byte_a * 256) + byte_b) / 4

    def parsear_velocidad(self, byte_a):
        """PID 0D: Vehicle speed. A directo (km/h)"""
        return byte_a

    def parsear_avance_chispa(self, byte_a):
        """PID 0E: Timing advance. A/2 - 64 (grados antes del PMS)"""
        return (byte_a / 2) - 64

    def parsear_temp_admision(self, byte_a):
        """PID 0F: Intake air temperature. A-40 (°C)"""
        return self._temp_menos_40(byte_a)

    def parsear_flujo_aire_maf(self, byte_a, byte_b):
        """PID 10: MAF air flow rate. ((A*256)+B)/100 (g/s)"""
        return ((byte_a * 256) + byte_b) / 100

    def parsear_posicion_acelerador(self, byte_a):
        """PID 11: Throttle position. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    # --- Sondas O2 (PIDs 14-1B, mismo formato para las 8) ---

    def parsear_sonda_o2_voltaje(self, byte_a, byte_b):
        """PIDs 14-1B: Voltaje sonda O2 + % fuel trim asociado."""
        voltaje = byte_a / 200
        ajuste = None if byte_b == 0xFF else self._fuel_trim(byte_b)
        return {"voltaje": voltaje, "ajuste_combustible": ajuste}

    # --- PID 1F-21 ---

    def parsear_tiempo_motor_arrancado(self, byte_a, byte_b):
        """PID 1F: Run time since engine start. (A*256)+B (segundos)"""
        return (byte_a * 256) + byte_b

    def parsear_distancia_con_mil(self, byte_a, byte_b):
        """PID 21: Distance traveled with MIL on. (A*256)+B (km)"""
        return (byte_a * 256) + byte_b

    # --- PID 22-23: presión de rail (relevante para tu diésel) ---

    def parsear_presion_rail_relativa(self, byte_a, byte_b):
        """PID 22: Fuel rail pressure relativa a vacío de admisión. 0.079*(256A+B) (kPa)"""
        return 0.079 * ((byte_a * 256) + byte_b)

    def parsear_presion_rail_combustible(self, byte_a, byte_b):
        """PID 23: Fuel rail gauge pressure (diésel/GDI). 10*((A*256)+B) (kPa) — common rail del A6."""
        return 10 * ((byte_a * 256) + byte_b)

    # --- PID 2C-2F ---

    def parsear_egr_comandada(self, byte_a):
        """PID 2C: Commanded EGR. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    def parsear_error_egr(self, byte_a):
        """PID 2D: EGR Error. (100/128)*A - 100 (%)"""
        return self._fuel_trim(byte_a)

    def parsear_purga_evap_comandada(self, byte_a):
        """PID 2E: Commanded evaporative purge. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    def parsear_nivel_combustible(self, byte_a):
        """PID 2F: Fuel Tank Level Input. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    # --- PID 30-31 ---

    def parsear_arranques_desde_borrado(self, byte_a):
        """PID 30: Warm-ups since codes cleared. A directo"""
        return byte_a

    def parsear_distancia_desde_borrado(self, byte_a, byte_b):
        """PID 31: Distance traveled since codes cleared. (A*256)+B (km)"""
        return (byte_a * 256) + byte_b

    # --- PID 33: barométrica ---

    def parsear_presion_barometrica(self, byte_a):
        """PID 33: Absolute Barometric Pressure. A directo (kPa)"""
        return byte_a

    # --- PID 3C-3F: temperatura catalizador (4 sensores, misma fórmula) ---

    def parsear_temp_catalizador(self, byte_a, byte_b):
        """PIDs 3C-3F: Catalyst Temperature. ((A*256)+B)/10 - 40 (°C)"""
        return ((byte_a * 256) + byte_b) / 10 - 40

    # --- PID 42-46 ---

    def parsear_voltaje_bateria(self, byte_a, byte_b):
        """PID 42: Control module voltage. ((A*256)+B)/1000 (V)"""
        return ((byte_a * 256) + byte_b) / 1000

    def parsear_carga_absoluta(self, byte_a, byte_b):
        """PID 43: Absolute load value. (100/255)*((A*256)+B) (%)"""
        return (100 / 255) * ((byte_a * 256) + byte_b)

    def parsear_afr_comandado(self, byte_a, byte_b):
        """PID 44: Commanded Air-Fuel Equivalence Ratio (lambda). (2/65536)*((A*256)+B)"""
        return (2 / 65536) * ((byte_a * 256) + byte_b)

    def parsear_posicion_relativa_acelerador(self, byte_a):
        """PID 45: Relative throttle position. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    def parsear_temp_ambiente(self, byte_a):
        """PID 46: Ambient air temperature. A-40 (°C)"""
        return self._temp_menos_40(byte_a)

    # --- PID 47-4B: posiciones de acelerador/pedal (misma fórmula, distinto sensor) ---

    def parsear_posicion_pedal(self, byte_a):
        """PIDs 47-4B: Throttle/pedal position B,C,D,E,F. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    # --- PID 4D-4E ---

    def parsear_tiempo_con_mil(self, byte_a, byte_b):
        """PID 4D: Time run with MIL on. (A*256)+B (minutos)"""
        return (byte_a * 256) + byte_b

    def parsear_tiempo_desde_borrado(self, byte_a, byte_b):
        """PID 4E: Time since trouble codes cleared. (A*256)+B (minutos)"""
        return (byte_a * 256) + byte_b

    # --- PID 52-54 ---

    def parsear_etanol_porcentaje(self, byte_a):
        """PID 52: Ethanol fuel %. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    def parsear_presion_evap_absoluta(self, byte_a, byte_b):
        """PID 53: Absolute Evap system Vapor Pressure. ((A*256)+B)/200 (kPa)"""
        return ((byte_a * 256) + byte_b) / 200

    # --- PID 55-58: trims secundarios O2 (misma fórmula que fuel trim) ---

    def parsear_trim_secundario_o2(self, byte_a):
        """PIDs 55-58: Secondary O2 sensor trim. (100/128)*A - 100 (%)"""
        return self._fuel_trim(byte_a)

    # --- PID 59-5E ---

    def parsear_presion_rail_absoluta(self, byte_a, byte_b):
        """PID 59: Fuel rail absolute pressure. 10*((A*256)+B) (kPa)"""
        return 10 * ((byte_a * 256) + byte_b)

    def parsear_pedal_acelerador_relativo(self, byte_a):
        """PID 5A: Relative accelerator pedal position. A/2.55 (%)"""
        return self._porcentaje_255(byte_a)

    def parsear_temp_aceite(self, byte_a):
        """PID 5C: Engine oil temperature. A-40 (°C)"""
        return self._temp_menos_40(byte_a)

    def parsear_tiempo_inyeccion(self, byte_a, byte_b):
        """PID 5D: Fuel injection timing. ((A*256)+B)/128 - 210 (grados)"""
        return ((byte_a * 256) + byte_b) / 128 - 210

    def parsear_consumo_combustible(self, byte_a, byte_b):
        """PID 5E: Engine fuel rate. ((A*256)+B)/20 (L/h)"""
        return ((byte_a * 256) + byte_b) / 20

    # --- PID 61-63: par motor ---

    def parsear_torque_demandado(self, byte_a):
        """PID 61: Driver's demand engine percent torque. A-125 (%)"""
        return byte_a - 125

    def parsear_torque_actual(self, byte_a):
        """PID 62: Actual engine percent torque. A-125 (%)"""
        return byte_a - 125

    def parsear_torque_referencia(self, byte_a, byte_b):
        """PID 63: Engine reference torque. (A*256)+B (N·m)"""
        return (byte_a * 256) + byte_b

    # --- PIDs "supported" (00, 20, 40, 60, 80): qué soporta el coche ---

    def parsear_pids_soportados(self, respuesta_4_bytes, pid_base):
        """
        Decodifica la respuesta de un PID 'supported' (00, 20, 40, 60, 80).
        respuesta_4_bytes: los 4 bytes de datos (A,B,C,D), como lista de enteros.
        pid_base: el PID que preguntaste (0x00, 0x20, 0x40...) para saber el rango.
        Devuelve la lista de PIDs (en hex, string) que el coche confirma soportar.
        """
        bits = ""
        for byte in respuesta_4_bytes:
            bits += format(byte, "08b")

        soportados = []
        for i, bit in enumerate(bits):
            if bit == "1":
                pid_numero = pid_base + i + 1
                soportados.append(f"{pid_numero:02X}")
        return soportados

        # --- PID 03: estado del sistema de combustible (enumerado) ---

    def parsear_estado_combustible(self, byte_a):
        """PID 03: Fuel system status. Valor enumerado."""
        estados = {
            0: "Motor apagado",
            1: "Lazo abierto (temperatura insuficiente)",
            2: "Lazo cerrado (usando sonda O2)",
            4: "Lazo abierto (carga motor alta o corte por deceleración)",
            8: "Lazo abierto (fallo de sistema)",
            16: "Lazo cerrado (con fallo en sonda de realimentación)",
        }
        return estados.get(byte_a, "Valor no reconocido")

    # --- PID 12: estado del aire secundario (enumerado) ---

    def parsear_aire_secundario(self, byte_a):
        """PID 12: Commanded secondary air status. Valor enumerado."""
        estados = {
            1: "Upstream",
            2: "Downstream del catalizador",
            4: "Atmósfera exterior o apagado",
            8: "Bomba activada para diagnóstico",
        }
        return estados.get(byte_a, "Valor no reconocido")

    # --- PID 1C: estándar OBD que cumple el vehículo (enumerado) ---

    def parsear_estandar_obd(self, byte_a):
        """PID 1C: OBD standards this vehicle conforms to. Valor enumerado."""
        estandares = {
            1: "OBD-II (CARB)", 2: "OBD (EPA)", 3: "OBD y OBD-II",
            4: "OBD-I", 5: "No cumple OBD", 6: "EOBD (Europa)",
            7: "EOBD y OBD-II", 8: "EOBD y OBD", 9: "EOBD, OBD y OBD-II",
            10: "JOBD (Japón)", 11: "JOBD y OBD-II", 12: "JOBD y EOBD",
        }
        return estandares.get(byte_a, f"Estándar código {byte_a} (ver tabla SAE J1979 ampliada)")

    # --- PID 51: tipo de combustible (enumerado) ---

    def parsear_tipo_combustible(self, byte_a):
        """PID 51: Fuel Type. Valor enumerado."""
        tipos = {
            0: "No disponible", 1: "Gasolina", 2: "Metanol", 3: "Etanol",
            4: "Diésel", 5: "GLP", 6: "GNC", 7: "Propano", 8: "Eléctrico",
            9: "Bifuel gasolina", 19: "Hybrido diésel",
        }
        return tipos.get(byte_a, "Tipo no reconocido/reservado")

    # --- PID 01: estado de monitores desde borrado de fallos (bit-encoded) ---

    def parsear_estado_monitores(self, byte_a, byte_b, byte_c, byte_d):
        """
        PID 01: Monitor status since DTCs cleared.
        A: bit 7 = luz MIL encendida/apagada, bits 6-0 = nº de DTCs activos.
        """
        mil_encendida = bool(byte_a & 0b10000000)
        num_dtcs = byte_a & 0b01111111
        return {
            "mil_encendida": mil_encendida,
            "numero_dtcs": num_dtcs,
        }

    # --- PID 13/1D: qué sondas O2 tiene el coche (bit-encoded) ---

    def parsear_sondas_o2_presentes(self, byte_a):
        """
        PID 13: qué sondas O2 existen (2 bancos x 4 sensores).
        Cada bit indica si esa sonda está presente.
        """
        etiquetas = ["B1S1", "B1S2", "B1S3", "B1S4", "B2S1", "B2S2", "B2S3", "B2S4"]
        presentes = []
        for i, etiqueta in enumerate(etiquetas):
            if byte_a & (1 << i):
                presentes.append(etiqueta)
        return presentes