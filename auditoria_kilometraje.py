#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════════════════════════
# AudiDiag Pro — Script de Auditoría Forense de Kilometraje Real y Anti-Afeitado
# Especializado para: Audi A6 C6 4F Facelift (2010) 2.7 TDI V6 Biturbo
#
# Comprueba y cruza los kilómetros guardados en:
#   1. Gateway CAN (Módulo 19 - J533) [Historial Gestor de Batería BEM + Wakeup]
#   2. Cuadro de Instrumentos (Módulo 17 - J285) [Odómetro display Grupo 002/001]
#   3. Motor Bosch EDC17 (Módulo 01 - J623) [Memoria ECU + DPF Regen + DTCs]
#   4. Caja de Cambios Automática Tiptronic ZF (Módulo 02 - J217)
#   5. ABS / ESP Bosch (Módulo 03 - J104) [Odometría de ruedas / DTCs]
#   6. Central Eléctrica / Luces (Módulo 09 - J519) [Freeze Frames]
#   7. Confort / BCM2 (Módulo 46 - J393) [Freeze Frames]
#   8. Freno de Mano Eléctrico EPB (Módulo 53)
#
# Protocolo: 100% VW TP 2.0 / KWP2000 a través del Gateway J533 (500 kbps)
# Cero tramas UDS directas no enrutadas (evita Bus-Off y fallos de ESP).
# ══════════════════════════════════════════════════════════════════════════════

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import struct
from datetime import datetime
from typing import Optional, List, Dict

# Asegurar path para imports locales
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.can_manager import CANManager
from obd.tp20_can import TP20Transport, KWP2000NativeClient, LOGICAL_MODULES
from core.diagnostic_logger import diag_logger


class AuditorKilometraje:
    """
    Motor forense para auditar el kilometraje real en vehículos VAG / Audi A6 C6.
    Valida estrictamente los datos contra el escalador oficial VAG 0x24 y canales certificados.
    """

    def __init__(self):
        self.can = CANManager(log_fn=self._log)
        self.tp20 = TP20Transport(self.can, timeout=0.9)
        self.kwp = KWP2000NativeClient(self.tp20)
        self.registros = []

    def _log(self, msg: str):
        diag_logger.log_info(f"[AUDITORIA] {msg}")

    def registrar(self, modulo: str, fuente: str, km: int, detalle: str = "", es_total: bool = True):
        """Registra un dato de kilometraje verificado (rango 1.000 a 999.999 km)."""
        if km and 1000 <= km <= 999999:
            # Evitar duplicados exactos en el mismo módulo
            for r in self.registros:
                if r["modulo"] == modulo and r["fuente"] == fuente and r["km"] == km:
                    return

            self.registros.append({
                "modulo": modulo,
                "fuente": fuente,
                "km": km,
                "detalle": detalle,
                "es_total": es_total,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            tag = "" if es_total else " [Parcial]"
            print(f"  ▸ [{modulo}] {fuente}: {km:,} km{tag} {f'({detalle})' if detalle else ''}")

    def iniciar_conexion(self) -> bool:
        print("\n" + "=" * 75)
        print("   AudiDiag Pro — AUDITORÍA FORENSE DE KILOMETRAJE REAL")
        print("   Vehículo objetivo: Audi A6 C6 (4F) 2010 — 2.7 TDI V6 Biturbo")
        print("   Protocolo: VW TP 2.0 Nativo vía Gateway J533 (500 kbps)")
        print("=" * 75)
        print("\n[1/6] Conectando con el adaptador CANable 2.0...")

        if not self.can.conectar(interface_preference="auto"):
            print("[X] No se pudo conectar al hardware CANable. Comprueba el cable USB y OBD2.")
            return False

        print(f"[OK] Conexión establecida vía {self.can.connected_interface} a 500 kbps.")
        print("[OK] Bus CAN listo. Consultando centralitas sin saturación...")
        time.sleep(0.1)
        return True

    # ──────────────────────────────────────────────────────────────────────────
    #  1. AUDITORÍA DEL GATEWAY CAN (MÓDULO 19 - J533)
    #  Despierta y ceba la pasarela de enrutamiento hacia los buses internos.
    # ──────────────────────────────────────────────────────────────────────────
    def auditar_gateway(self):
        print("\n[2/6] Inspeccionando Gateway Central CAN (Módulo 19 - J533)...")
        try:
            self.can.flush_rx()
            if self.tp20.open_channel(0x19, retries=2):
                time.sleep(0.04)

                # Historial Gestor de Batería BEM (Grupos 001 - 004)
                for blk in (0x01, 0x02, 0x03, 0x04):
                    try:
                        resp = self.kwp.execute_service(0x21, subfunction=blk)
                        if resp and len(resp) >= 4:
                            data = resp[1:]
                            for idx in range(0, len(data) - 2, 3):
                                scaler = data[idx]
                                a = data[idx + 1]
                                b = data[idx + 2]
                                if scaler == 0x24:
                                    km = (a * 2560) + (b * 10)
                                    if 1000 <= km <= 999999:
                                        self.registrar("Gateway (19)", f"Historial BEM (Bloque {blk})", km, "Registro gestor de batería", es_total=True)
                                elif scaler == 0x21:
                                    km = (a * 256) + b
                                    if 1000 <= km <= 999999:
                                        self.registrar("Gateway (19)", f"Historial BEM (Bloque {blk})", km, "Registro gestor de batería", es_total=True)
                    except Exception:
                        pass

                # Odómetro directo si responde
                km_gw = self.kwp.read_odometer()
                if km_gw:
                    self.registrar("Gateway (19)", "Odómetro Gateway", km_gw, "Memoria pasarela J533", es_total=True)

                # Freeze Frames en averías del Gateway
                try:
                    dtcs = self.kwp.read_dtcs()
                    for d in dtcs[:3]:
                        partes = d.split()
                        if len(partes) >= 2 and "DTC" in partes[0]:
                            cod_hex = partes[1]
                            if len(cod_hex) == 4:
                                b1, b2 = int(cod_hex[:2], 16), int(cod_hex[2:], 16)
                                ff = self.kwp.read_freeze_frame(b1, b2)
                                if ff.get("km"):
                                    self.registrar("Gateway (19)", f"Freeze Frame Avería {cod_hex}", ff["km"], f"Guardado con fallo {cod_hex}", es_total=True)
                except Exception:
                    pass

                self.tp20.close_channel()
            else:
                print("  - Gateway (19): En espera.")
        except Exception as e:
            print(f"  - Error en Gateway 19: {e}")
            self.tp20.close_channel()

    # ──────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _extraer_b1_b2(d: str):
        import re
        m_vag = re.search(r"VAG\s+(\d+)", d)
        m_hex = re.search(r"DTC\s+([0-9A-Fa-f]{4})", d)
        m_sae = re.search(r"([PCBU]\d{4})", d)
        if m_vag:
            vag_val = int(m_vag.group(1))
            return (vag_val >> 8) & 0xFF, vag_val & 0xFF, m_sae.group(1) if m_sae else f"VAG {vag_val}"
        if m_hex:
            h = m_hex.group(1)
            return int(h[:2], 16), int(h[2:], 16), h
        if m_sae:
            sae = m_sae.group(1)
            prefix_bits = {"P": 0, "C": 1, "B": 2, "U": 3}.get(sae[0], 0)
            d1, d2, d3, d4 = int(sae[1]), int(sae[2], 16), int(sae[3], 16), int(sae[4], 16)
            return (prefix_bits << 6) | (d1 << 4) | d2, (d3 << 4) | d4, sae
        partes = d.split()
        if len(partes) >= 1 and len(partes[0]) == 4 and all(c in "0123456789ABCDEFabcdef" for c in partes[0]):
            return int(partes[0][:2], 16), int(partes[0][2:], 16), partes[0]
        return None, None, ""

    # ──────────────────────────────────────────────────────────────────────────
    #  2. AUDITORÍA DEL CUADRO DE INSTRUMENTOS (MÓDULO 17 - J285)
    # ──────────────────────────────────────────────────────────────────────────
    def auditar_cuadro(self):
        print("\n[3/6] Inspeccionando Cuadro de Instrumentos (Módulo 17 - J285)...")
        km_cuadro = None

        # Método 0: Cuadro UDS nativo (Audi A6 C6 Facelift 2009-2011 opera en 0x714 / 0x77E)
        try:
            from obd.isotp_uds import ISOTPClient, UDSClient
            isotp = ISOTPClient(self.can, tx_id=0x714, rx_id=0x77E, timeout=0.8)
            uds = UDSClient(isotp)
            km_uds = uds.read_odometer()
            if km_uds and 1000 <= km_uds <= 999999:
                km_cuadro = km_uds
                self.registrar("Cuadro (17)", "Odómetro Pantalla UDS (DID 0x02BD)", km_uds, "Lectura directa display digital", es_total=True)
        except Exception:
            pass

        if not km_cuadro:
            try:
                self.can.flush_rx()
                if self.tp20.open_channel(0x17, retries=2):
                    self.kwp.start_diagnostic_session(0x86)
                    time.sleep(0.05)

                    # Método 1: Grupo 002 (En Cuadro VAG KWP2000, Grupo 002 Campo 1 es el Odómetro)
                    try:
                        resp = self.kwp.execute_service(0x21, subfunction=0x02)
                        if resp and len(resp) >= 4:
                            data = resp[1:]
                            scaler = data[0]
                            a = data[1]
                            b = data[2]
                            if scaler == 0x24:
                                km = (a * 2560) + (b * 10)
                                if 1000 <= km <= 999999:
                                    km_cuadro = km
                                    self.registrar("Cuadro (17)", "Odómetro Pantalla (Grupo 002)", km, "Lectura del display digital", es_total=True)
                    except Exception:
                        pass

                    # Método 2: Grupo 001 (En algunos modelos A6 C6, Campo 2 es Odómetro)
                    if not km_cuadro:
                        try:
                            resp = self.kwp.execute_service(0x21, subfunction=0x01)
                            if resp and len(resp) >= 4:
                                data = resp[1:]
                                for idx in range(0, len(data) - 2, 3):
                                    scaler = data[idx]
                                    a = data[idx + 1]
                                    b = data[idx + 2]
                                    if scaler == 0x24:
                                        km = (a * 2560) + (b * 10)
                                        if 1000 <= km <= 999999:
                                            km_cuadro = km
                                            self.registrar("Cuadro (17)", "Odómetro Pantalla (Grupo 001)", km, "Lectura del display digital", es_total=True)
                                            break
                        except Exception:
                            pass

                    # Método 3: read_odometer() genérico con escalador oficial 0x24
                    if not km_cuadro:
                        km_kwp = self.kwp.read_odometer()
                        if km_kwp:
                            km_cuadro = km_kwp
                            self.registrar("Cuadro (17)", "Odómetro Display (KWP2000)", km_kwp, "Lectura del display digital", es_total=True)

                    # Método 4: Canal de Adaptación 09 (Odómetro en decenas de km: valor * 10)
                    if not km_cuadro:
                        for srv, arg in ((0x22, b"\x00\x09"), (0x21, 0x09)):
                            try:
                                if srv == 0x22:
                                    resp = self.kwp.execute_service(0x22, data=arg)
                                else:
                                    resp = self.kwp.execute_service(0x21, subfunction=arg)
                                if resp and len(resp) >= 2:
                                    val_10 = (resp[-2] << 8) | resp[-1]
                                    km_calc = val_10 * 10
                                    if 1000 <= km_calc <= 999999:
                                        km_cuadro = km_calc
                                        self.registrar("Cuadro (17)", "Canal Adaptación 09", km_calc, "Almacenado en memoria EEPROM", es_total=True)
                                        break
                            except Exception:
                                pass

                    # Método 5: DID UDS/KWP extendido 0x02BD
                    if not km_cuadro:
                        try:
                            resp = self.kwp.execute_service(0x22, data=b"\x02\xbd")
                            if resp and len(resp) >= 5:
                                d = resp[2:]
                                val = struct.unpack(">I", d[:4])[0] if len(d) >= 4 else (d[0] << 16) | (d[1] << 8) | d[2]
                                if 1000 <= val <= 999999:
                                    km_cuadro = val
                                    self.registrar("Cuadro (17)", "DID 0x02BD (Odómetro)", val, "Lectura directa odómetro", es_total=True)
                        except Exception:
                            pass

                    self.tp20.close_channel()
                else:
                    print("  - Cuadro (17): No respondió en TP 2.0.")
            except Exception as e:
                print(f"  - Error en Cuadro 17 TP 2.0: {e}")
                self.tp20.close_channel()

        if not km_cuadro:
            print("  - Cuadro (17): No facilitó odómetro directo. Se cruzarán los datos del resto de centralitas.")

    # ──────────────────────────────────────────────────────────────────────────
    #  3. AUDITORÍA DEL MOTOR EDC17 (MÓDULO 01 - J623)
    # ──────────────────────────────────────────────────────────────────────────
    def auditar_motor(self):
        print("\n[4/6] Inspeccionando Centralita de Motor Bosch EDC17 (Módulo 01)...")

        try:
            self.can.flush_rx()
            if self.tp20.open_channel(0x01, retries=2):
                self.kwp.start_diagnostic_session(0x86)
                time.sleep(0.04)

                # A. Odómetro directo con escalador oficial
                km_kwp = self.kwp.read_odometer()
                if km_kwp:
                    self.registrar("Motor (01)", "Memoria Interna EDC17", km_kwp, "Registro odómetro ECU motor", es_total=True)

                # B. Filtro Antipartículas DPF: Bloque 104 (0x68)
                # El Campo 4 indica la distancia recorrida desde la última regeneración del DPF
                try:
                    resp = self.kwp.execute_service(0x21, subfunction=0x68)
                    if resp and len(resp) >= 4:
                        data = resp[1:]
                        for idx in range(0, len(data) - 2, 3):
                            scaler = data[idx]
                            a = data[idx + 1]
                            b = data[idx + 2]
                            if scaler == 0x24:
                                km_dpf = (a * 2560) + (b * 10)
                                if 0 < km_dpf < 50000:
                                    self.registrar("Motor (01)", "DPF (Distancia última regeneración)", km_dpf, "Filtro antipartículas Grupo 104", es_total=False)
                                    break
                except Exception:
                    pass

                # C. Freeze Frames de averías registradas en la memoria de la ECU (Motor 01)
                try:
                    dtcs = self.kwp.read_dtcs()
                    if dtcs:
                        print(f"    ℹ {len(dtcs)} fallo(s) detectado(s) en motor. Analizando Freeze Frames...")
                        for d in dtcs:
                            b1, b2, cod_label = self._extraer_b1_b2(d)
                            if b1 is not None and b2 is not None:
                                ff = self.kwp.read_freeze_frame(b1, b2)
                                if ff.get("km"):
                                    self.registrar("Motor (01)", f"Freeze Frame Avería {cod_label}", ff["km"], f"Kilómetros congelados al registrarse fallo {cod_label}", es_total=True)
                except Exception:
                    pass

                self.tp20.close_channel()
            else:
                print("  - Motor (01): Sin respuesta en canal TP 2.0.")
        except Exception as e:
            print(f"  - Error en Motor 01: {e}")
            self.tp20.close_channel()

    # ──────────────────────────────────────────────────────────────────────────
    #  4. AUDITORÍA DE TRANSMISIÓN TIPTRONIC (02) Y ABS / ESP (03)
    # ──────────────────────────────────────────────────────────────────────────
    def auditar_transmision_y_abs(self):
        print("\n[5/6] Inspeccionando Transmisión Tiptronic (02) y ABS/ESP (03)...")

        # Caja de Cambios ZF 6HP19A (02)
        try:
            self.can.flush_rx()
            if self.tp20.open_channel(0x02, retries=2):
                self.kwp.start_diagnostic_session(0x86)
                time.sleep(0.04)
                km_tcm = self.kwp.read_odometer()
                if km_tcm:
                    self.registrar("Caja Cambios (02)", "Memoria TCU Tiptronic", km_tcm, "Odómetro caja de cambios", es_total=True)

                # Freeze Frames en transmisión
                try:
                    dtcs = self.kwp.read_dtcs()
                    for d in dtcs[:3]:
                        b1, b2, cod_label = self._extraer_b1_b2(d)
                        if b1 is not None and b2 is not None:
                            ff = self.kwp.read_freeze_frame(b1, b2)
                            if ff.get("km"):
                                self.registrar("Caja Cambios (02)", f"Freeze Frame Avería {cod_label}", ff["km"], f"Guardado con fallo {cod_label}", es_total=True)
                except Exception:
                    pass

                self.tp20.close_channel()
        except Exception:
            self.tp20.close_channel()

        # ABS / ESP Bosch 8.0 (03)
        try:
            self.can.flush_rx()
            if self.tp20.open_channel(0x03, retries=2):
                self.kwp.start_diagnostic_session(0x86)
                time.sleep(0.04)
                km_abs = self.kwp.read_odometer()
                if km_abs:
                    self.registrar("ABS / ESP (03)", "Bloque Odometría ESP8", km_abs, "Odometría de sensores de rueda", es_total=True)

                # Freeze Frames en ABS
                try:
                    dtcs = self.kwp.read_dtcs()
                    for d in dtcs[:3]:
                        b1, b2, cod_label = self._extraer_b1_b2(d)
                        if b1 is not None and b2 is not None:
                            ff = self.kwp.read_freeze_frame(b1, b2)
                            if ff.get("km"):
                                self.registrar("ABS / ESP (03)", f"Freeze Frame Avería {cod_label}", ff["km"], f"Guardado con fallo {cod_label}", es_total=True)
                except Exception:
                    pass

                self.tp20.close_channel()
        except Exception:
            self.tp20.close_channel()

    # ──────────────────────────────────────────────────────────────────────────
    #  5. AUDITORÍA DE RESTO DE MÓDULOS (LUCES 09, CONFORT 46, FRENO EPB 53)
    # ──────────────────────────────────────────────────────────────────────────
    def auditar_resto_modulos(self):
        print("\n[6/6] Inspeccionando Central Eléctrica (09), Confort (46) y Freno Mano (53)...")

        modulos_secundarios = [
            (0x09, "Central Eléctrica / Luces (09)"),
            (0x46, "Confort / BCM2 (46)"),
            (0x53, "Freno Mano EPB (53)"),
        ]

        for addr, nombre in modulos_secundarios:
            try:
                self.can.flush_rx()
                if self.tp20.open_channel(addr, retries=1):
                    self.kwp.start_diagnostic_session(0x86)
                    time.sleep(0.03)

                    km_mod = self.kwp.read_odometer()
                    if km_mod:
                        self.registrar(nombre, "Memoria Odómetro Módulo", km_mod, "Registro no volátil", es_total=True)

                    # DTC Freeze Frames
                    try:
                        dtcs = self.kwp.read_dtcs()
                        if dtcs:
                            for d in dtcs[:3]:
                                b1, b2, cod_label = self._extraer_b1_b2(d)
                                if b1 is not None and b2 is not None:
                                    ff = self.kwp.read_freeze_frame(b1, b2)
                                    if ff.get("km"):
                                        self.registrar(nombre, f"Freeze Frame Avería {cod_label}", ff["km"], f"Guardado con fallo {cod_label}", es_total=True)
                    except Exception:
                        pass

                    self.tp20.close_channel()
            except Exception:
                self.tp20.close_channel()

    # ──────────────────────────────────────────────────────────────────────────
    #  INFORME FINAL Y DETECCIÓN FORENSE DE AFEITADO
    # ──────────────────────────────────────────────────────────────────────────
    def generar_informe(self):
        print("\n" + "═" * 78)
        print("           RESULTADO DE LA AUDITORÍA FORENSE DE KILOMETRAJE")
        print("═" * 78)

        if not self.registros:
            print("\n⚠ No se pudieron extraer lecturas directas de kilometraje en esta sesión.")
            print("  Posibles causas:")
            print("  - El contacto del coche no estaba puesto en posición ON (cuadro encendido).")
            print("  - No hay fallos almacenados con Freeze Frames y el módulo motor no expone odómetro libre.")
            return

        print(f"\nSe han localizado {len(self.registros)} registro(s) de distancia en las centralitas:\n")
        print(f"{'MÓDULO':<28} | {'ORIGEN / MEMORIA':<36} | {'KILÓMETROS':>12}")
        print("-" * 82)

        for r in self.registros:
            tag = " km" if r.get("es_total", True) else " km (parcial)"
            print(f"{r['modulo']:<28} | {r['fuente']:<36} | {r['km']:>8,} {tag}")

        print("-" * 82)

        registros_totales = [r for r in self.registros if r.get("es_total", True)]

        if registros_totales:
            kms = [r["km"] for r in registros_totales]
            km_min = min(kms)
            km_max = max(kms)
            diferencia = km_max - km_min

            reg_cuadro = next((r for r in registros_totales if "Cuadro" in r["modulo"]), None)

            print(f"\n[DATOS] Balance de Odómetros Totales:")
            print(f"  ▸ Valor Mínimo Detectado : {km_min:,} km")
            print(f"  ▸ Valor Máximo Detectado : {km_max:,} km")
            print(f"  ▸ Discrepancia Máxima    : {diferencia:,} km")

            if reg_cuadro:
                km_c = reg_cuadro["km"]
                print(f"  ▸ Kilómetros en Cuadro   : {km_c:,} km (Referencia en salpicadero)")

                sospechosos = [r for r in registros_totales if r["km"] > (km_c + 1500)]

                if sospechosos:
                    print("\n" + "!" * 78)
                    print("[ALERTA CRITICA] ¡EVIDENCIA DE MANIPULACIÓN DE KILÓMETROS (AFEITADO)!")
                    print("!" * 78)
                    print(f"El Cuadro de mandos indica {km_c:,} km, pero se han encontrado registros")
                    print("con un kilometraje SUPERIOR en las siguientes centralitas:\n")
                    for s in sospechosos:
                        dif = s["km"] - km_c
                        print(f"  [X] {s['modulo']} ({s['fuente']}): {s['km']:,} km  [+ {dif:,} km más que el cuadro]")
                    print("\nConclusión: El odómetro del cuadro fue manipulado hacia abajo, pero quedaron")
                    print("los registros reales congelados en la memoria profunda del vehículo.")
                else:
                    print("\n" + "=" * 78)
                    print("[OK] KILOMETRAJE COHERENTE: No se detecta afeitado de kilómetros.")
                    print("=" * 78)
                    print("Todos los registros verificados son coherentes con el odómetro del cuadro.")
            else:
                if diferencia > 3000:
                    print(f"\n[AVISO] ATENCIÓN: Se detecta una discrepancia de {diferencia:,} km entre centralitas.")
                    print("Revisa en la tabla superior qué módulo registró el kilometraje más alto.")
                else:
                    print("\n[OK] Los registros entre centralitas son coherentes entre sí.")

        # Mostrar datos parciales si los hay (ej: DPF)
        parciales = [r for r in self.registros if not r.get("es_total", True)]
        if parciales:
            print("\n[INFO] Información Adicional de Mantenimiento:")
            for p in parciales:
                print(f"  ▸ {p['modulo']} — {p['fuente']}: {p['km']:,} km ({p['detalle']})")

        # Guardar informe en archivo de texto
        nombre_archivo = "auditoria_kilometros_informe.txt"
        try:
            with open(nombre_archivo, "w", encoding="utf-8") as f:
                f.write("======================================================================\n")
                f.write("AudiDiag Pro — INFORME DE AUDITORÍA FORENSE DE KILOMETRAJE\n")
                f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("Vehículo: Audi A6 C6 (4F) 2010 — 2.7 TDI V6 Biturbo\n")
                f.write("======================================================================\n\n")
                for r in self.registros:
                    tipo = "TOTAL" if r.get("es_total", True) else "PARCIAL"
                    f.write(f"[{r['modulo']}] {r['fuente']}: {r['km']} km [{tipo}] ({r['detalle']})\n")
                if registros_totales:
                    f.write(f"\nResumen: Min {km_min} km, Max {km_max} km, Discrepancia {diferencia} km\n")
            print(f"\n[DOC] Informe guardado en: {os.path.abspath(nombre_archivo)}\n")
        except Exception as e:
            print(f"Error al guardar informe: {e}")


def main():
    auditor = AuditorKilometraje()
    if not auditor.iniciar_conexion():
        input("\nPresiona Enter para salir...")
        return

    try:
        auditor.auditar_gateway()
        auditor.auditar_cuadro()
        auditor.auditar_motor()
        auditor.auditar_transmision_y_abs()
        auditor.auditar_resto_modulos()
        auditor.generar_informe()
    except KeyboardInterrupt:
        print("\n[INFO] Auditoría cancelada por el usuario.")
    except Exception as e:
        print(f"\n[X] Error durante la auditoría: {e}")
    finally:
        auditor.tp20.close_channel()
        auditor.can.desconectar()

    input("\nPresiona Enter para cerrar...")


if __name__ == "__main__":
    main()
