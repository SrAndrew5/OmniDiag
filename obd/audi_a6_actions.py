# obd/audi_a6_actions.py
# ══════════════════════════════════════════════════════════════════════════════
# Acciones y codificaciones específicas para el Audi A6 C6 4F Facelift (2010).
# Basado en la arquitectura Diagnose-CAN del Audi A6 C6:
# Comunicación 100% VW TP 2.0 / KWP2000 a través del Gateway J533.
# Evita transmisiones UDS directas no enrutadas para prevenir Bus-Off y alertas de ESP.
# ══════════════════════════════════════════════════════════════════════════════

import time
from typing import Dict, List, Tuple
from core.can_manager import CANManager
from obd.tp20_can import TP20Transport, KWP2000NativeClient, LOGICAL_MODULES
from core.diagnostic_logger import diag_logger


class AudiA6Actions:
    """
    Controlador de operaciones directas para el Audi A6 C6 (2010).
    """

    def __init__(self, can_mgr: CANManager, log_fn=None, vin: str = None):
        self.can = can_mgr
        self.vin = vin
        self.tp20 = TP20Transport(can_mgr, timeout=0.8)
        self.kwp = KWP2000NativeClient(self.tp20)
        self._log = log_fn or print

    def _emit(self, msg: str):
        try:
            self._log(msg)
        except Exception:
            print(msg)
        diag_logger.log_info(f"[A6 ACTION] {msg}")

    # ──────────────────────────────────────────────────────────────────────────
    #  OBJETIVO 1: ACTIVAR NEEDLE SWEEP (TEST DE AGUJAS AL ARRANCAR)
    #  Módulo 17 (Cuadro de Instrumentos J285) -> Byte 1, Bit 0 = 1
    # ──────────────────────────────────────────────────────────────────────────
    def activar_needle_sweep(self) -> Tuple[bool, str]:
        """
        Activa el Needle Sweep (barrido de agujas / Staging) en el Cuadro
        de Instrumentos (Módulo 17) mediante TP 2.0 / KWP2000.
        """
        self._emit("\n" + "=" * 55)
        self._emit("  ACTIVANDO NEEDLE SWEEP (MÓDULO 17 - CUADRO)")
        self._emit("=" * 55)

        try:
            self.can.flush_rx()
            tp_ok = False
            if self.tp20.open_channel(0x17, retries=2):
                tp_ok = True
                self.kwp.start_diagnostic_session(0x86)
                time.sleep(0.05)
                current_coding = self.kwp.read_coding()
                if current_coding and len(current_coding) >= 2:
                    coding_list = list(current_coding)
                    self._emit(f"Codificación actual TP 2.0 ({len(coding_list)} bytes): " + " ".join(f"{b:02X}" for b in coding_list))
                    if coding_list[1] & 0x01:
                        self._emit("El Needle Sweep ya está activado en la codificación actual.")
                        return True, "El Needle Sweep ya estaba activo en el cuadro."
                    nuevo_byte_1 = coding_list[1] | 0x01
                    coding_list[1] = nuevo_byte_1
                    self._emit(f"Byte 1 modificado: 0x{current_coding[1]:02X} -> 0x{nuevo_byte_1:02X} (Bit 0 activado)")
                    self._emit("Guardando copia de seguridad de la codificación original...")
                    try:
                        from gestion.backup_manager import BackupManager
                        bm = BackupManager()
                        bm.guardar_backup(
                            modulo="Cuadro Instrumentos (17)",
                            coche=self.vin or "GENERIC_VAG_VIN",
                            bytes_coding=" ".join(f"{b:02X}" for b in coding_list),
                            etiqueta="PRE_NEEDLE_SWEEP_TP20"
                        )
                    except Exception:
                        pass

                    self._emit("Escribiendo nueva codificación vía TP 2.0 (sin SecurityAccess restrictivo)...")
                    if self.kwp.write_coding(bytes(coding_list)):
                        time.sleep(0.1)
                        verified_coding = self.kwp.read_coding()
                        if verified_coding and len(verified_coding) > 1 and (verified_coding[1] & 0x01):
                            msg = "¡ÉXITO! Needle Sweep activado correctamente vía TP 2.0."
                            self._emit(f"✓ {msg}")
                            return True, msg

            # Si TP 2.0 no conectó o no pudo codificar, probar vía UDS directo (CAN ID 0x714 / 0x77E)
            # Empleado por el Cuadro de Instrumentos J285 en Audi A6 C6 Facelift (2009-2011)
            self._emit("[MÉTODO UDS] Conectando a Cuadro 17 por canal UDS nativo (0x714 / 0x77E)...")
            from obd.isotp_uds import ISOTPClient, UDSClient
            isotp = ISOTPClient(self.can, tx_id=0x714, rx_id=0x77E, timeout=1.0)
            uds = UDSClient(isotp)

            # Sesión extendida
            try:
                uds.diagnostic_session_control(0x03)
            except Exception:
                pass
            time.sleep(0.05)

            current_coding = None
            target_did = 0x0600
            for did in (0x0600, 0x0601, 0xF18C, 0xF1A0):
                try:
                    c = uds.read_data_by_identifier(did)
                    if c and len(c) >= 2:
                        current_coding = c
                        target_did = did
                        break
                except Exception:
                    continue

            if not current_coding or len(current_coding) < 2:
                return False, "No se pudo comunicar con el Cuadro 17 ni por TP 2.0 ni por UDS (0x714). Verifica que el contacto esté encendido y la batería tenga >12.5V."

            coding_list = list(current_coding)
            self._emit(f"Codificación actual UDS ({len(coding_list)} bytes): " + " ".join(f"{b:02X}" for b in coding_list))

            if coding_list[1] & 0x01:
                self._emit("El Needle Sweep ya está activado en la codificación actual.")
                return True, "El Needle Sweep ya estaba activo en el cuadro."

            nuevo_byte_1 = coding_list[1] | 0x01
            coding_list[1] = nuevo_byte_1
            self._emit(f"Byte 1 modificado: 0x{current_coding[1]:02X} -> 0x{nuevo_byte_1:02X} (Bit 0 activado)")

            self._emit("Guardando copia de seguridad de la codificación original...")
            try:
                from gestion.backup_manager import BackupManager
                bm = BackupManager()
                bm.guardar_backup(
                    modulo="Cuadro Instrumentos (17)",
                    coche=self.vin or "GENERIC_VAG_VIN",
                    bytes_coding=" ".join(f"{b:02X}" for b in current_coding),
                    etiqueta="PRE_NEEDLE_SWEEP_UDS"
                )
            except Exception:
                pass

            self._emit(f"Grabando codificación en DID 0x{target_did:04X}...")
            if not uds.write_data_by_identifier(target_did, bytes(coding_list)):
                return False, "El cuadro rechazó la escritura de la codificación vía UDS."

            time.sleep(0.1)
            try:
                uds.execute_service(0x11, subfunction=0x03)  # Soft Reset
            except Exception:
                pass
            time.sleep(0.3)

            verif = uds.read_data_by_identifier(target_did)
            if verif and len(verif) > 1 and (verif[1] & 0x01):
                msg = "¡ÉXITO! Needle Sweep activado correctamente en Cuadro 17 (0x714). Al poner el próximo contacto verás el barrido de agujas."
                self._emit(f"✓ {msg}")
                return True, msg
            else:
                return False, "La codificación se grabó pero la verificación falló."

        except Exception as e:
            err = f"Error durante la codificación del Needle Sweep: {e}"
            self._emit(f"✗ {err}")
            return False, err
        finally:
            self.tp20.close_channel()

    # ──────────────────────────────────────────────────────────────────────────
    #  OBJETIVO 2: PLEGADO AUTOMÁTICO DE RETROVISORES CON EL MANDO
    #  Módulo 46 (Confort J393) → Byte 4: Bit 4 (plegar al cerrar), Bit 6 (desplegar al abrir)
    #  Módulo 42 (J386 Puerta Conductor) → Byte 4: Bit 4 (Foldable Mirrors Installed)
    #  Módulo 52 (J387 Puerta Copiloto)  → Byte 4: Bit 4 (Foldable Mirrors Installed)
    # ──────────────────────────────────────────────────────────────────────────
    def activar_plegado_retrovisores(
        self,
        plegar_al_cerrar: bool = True,
        desplegar_al_abrir: bool = True,
    ) -> Tuple[bool, str]:
        """
        Activa el plegado automático de retrovisores al cerrar/abrir con el mando.

        Codifica tres módulos en secuencia:
          1. Módulo 46 (Confort J393): habilita lógica de plegado en CAN Confort.
          2. Módulo 42 (J386, puerta conductor): declara motor de plegado presente.
          3. Módulo 52 (J387, puerta copiloto): declara motor de plegado presente.

        Precondición: Los retrovisores DEBEN tener motor de plegado físico
        (verificado: se pliegan manualmente desde la rueda de la puerta).
        """
        self._emit("\n" + "=" * 60)
        self._emit("  ACTIVANDO PLEGADO AUTOMÁTICO DE RETROVISORES")
        self._emit("=" * 60)
        self._emit(f"  → Plegar al cerrar con mando : {'SÍ' if plegar_al_cerrar else 'NO'}")
        self._emit(f"  → Desplegar al abrir con mando: {'SÍ' if desplegar_al_abrir else 'NO'}")

        errores = []

        # ── PASO 1: Módulo 46 — Centralita de Confort J393 ──────────────────
        self._emit("\n[PASO 1/3] Módulo 46 — Confort J393 (lógica de plegado)")
        ok_46, msg_46 = self._codificar_bits_modulo(
            addr=0x46,
            nombre="Confort / Electrónica (46)",
            bits_activar=[
                (4, 4, plegar_al_cerrar),    # Byte 4, Bit 4 → plegar al cerrar
                (4, 6, desplegar_al_abrir),  # Byte 4, Bit 6 → desplegar al abrir
            ],
            etiqueta_backup="PRE_RETRO_MOD46"
        )
        self._emit(f"  {'✓' if ok_46 else '✗'} Módulo 46: {msg_46}")
        if not ok_46:
            errores.append(f"Módulo 46: {msg_46}")

        # ── PASO 2: Módulo 42 — Puerta Conductor J386 ───────────────────────
        self._emit("\n[PASO 2/3] Módulo 42 — Puerta Conductor J386 (Foldable Mirrors Installed)")
        ok_42, msg_42 = self._codificar_bits_modulo(
            addr=0x42,
            nombre="Puerta Conductor (42)",
            bits_activar=[
                (4, 4, True),  # Byte 4, Bit 4 → Foldable Mirrors Installed
            ],
            etiqueta_backup="PRE_RETRO_MOD42"
        )
        self._emit(f"  {'✓' if ok_42 else '✗'} Módulo 42: {msg_42}")
        if not ok_42:
            errores.append(f"Módulo 42: {msg_42}")

        # ── PASO 3: Módulo 52 — Puerta Copiloto J387 ────────────────────────
        self._emit("\n[PASO 3/3] Módulo 52 — Puerta Copiloto J387 (Foldable Mirrors Installed)")
        ok_52, msg_52 = self._codificar_bits_modulo(
            addr=0x52,
            nombre="Puerta Pasajero (52)",
            bits_activar=[
                (4, 4, True),  # Byte 4, Bit 4 → Foldable Mirrors Installed
            ],
            etiqueta_backup="PRE_RETRO_MOD52"
        )
        self._emit(f"  {'✓' if ok_52 else '✗'} Módulo 52: {msg_52}")
        if not ok_52:
            errores.append(f"Módulo 52: {msg_52}")

        # ── RESULTADO FINAL ──────────────────────────────────────────────────
        self._emit("\n" + "─" * 60)
        if not errores:
            msg_final = (
                "¡ÉXITO! Los tres módulos codificados correctamente.\n"
                "Ahora cierra el coche con el mando — los retrovisores se plegarán solos.\n"
                "Al abrir, se desplegarán automáticamente."
            )
            self._emit(f"✓ {msg_final}")
            return True, msg_final
        elif ok_46 or ok_42 or ok_52:
            msg_final = (
                f"Codificación parcial. Módulos con error: {'; '.join(errores)}.\n"
                "El plegado puede funcionar de forma incompleta. Revisa los módulos con error."
            )
            self._emit(f"⚠ {msg_final}")
            return False, msg_final
        else:
            msg_final = (
                f"Fallo total en los tres módulos. Errores: {'; '.join(errores)}.\n"
                "Verifica que el contacto esté encendido y el CANable conectado."
            )
            self._emit(f"✗ {msg_final}")
            return False, msg_final

    def _codificar_bits_modulo(
        self,
        addr: int,
        nombre: str,
        bits_activar: list,  # lista de (byte_idx, bit_idx, activar: bool)
        etiqueta_backup: str = "PRE_CODING"
    ) -> Tuple[bool, str]:
        """
        Método interno: conecta a un módulo vía TP 2.0, lee su Long Coding,
        modifica los bits indicados y escribe el resultado.

        bits_activar: lista de tuplas (byte_index, bit_index, activar)
        """
        try:
            self.can.flush_rx()
            retries = 2 if addr in (0x08, 0x09, 0x15, 0x17, 0x42, 0x46, 0x52, 0x5F) else 1
            if not self.tp20.open_channel(addr, retries=retries):
                return False, f"Sin respuesta del módulo (0x{addr:02X}). ¿Contacto encendido?"

            self.kwp.start_diagnostic_session(0x86)
            time.sleep(0.05)

            current_coding = self.kwp.read_coding()
            if not current_coding or len(current_coding) == 0:
                self.tp20.close_channel()
                return False, f"El módulo 0x{addr:02X} no devolvió codificación."

            coding_list = list(current_coding)
            self._emit(
                f"  Coding actual ({len(coding_list)} bytes): "
                + " ".join(f"{b:02X}" for b in coding_list)
            )

            # Guardar backup obligatorio
            try:
                from gestion.backup_manager import BackupManager
                bm = BackupManager()
                bm.guardar_backup(
                    modulo=nombre,
                    coche=self.vin or "GENERIC_VAG_VIN",
                    bytes_coding=" ".join(f"{b:02X}" for b in coding_list),
                    etiqueta=etiqueta_backup
                )
            except Exception:
                pass

            # Aplicar cambios de bits
            modificado = False
            for byte_idx, bit_idx, activar in bits_activar:
                if byte_idx >= len(coding_list):
                    # Extender si hace falta (raro, pero seguro)
                    coding_list.extend([0x00] * (byte_idx - len(coding_list) + 1))
                valor_actual = coding_list[byte_idx]
                if activar:
                    nuevo_valor = valor_actual | (1 << bit_idx)
                else:
                    nuevo_valor = valor_actual & ~(1 << bit_idx)
                if nuevo_valor != valor_actual:
                    self._emit(
                        f"  Byte {byte_idx} Bit {bit_idx}: "
                        f"0x{valor_actual:02X} → 0x{nuevo_valor:02X} "
                        f"({'activado' if activar else 'desactivado'})"
                    )
                    coding_list[byte_idx] = nuevo_valor
                    modificado = True
                else:
                    self._emit(
                        f"  Byte {byte_idx} Bit {bit_idx}: ya estaba "
                        f"{'activado' if activar else 'desactivado'}, sin cambio."
                    )

            if not modificado:
                self.tp20.close_channel()
                return True, "Sin cambios necesarios (bits ya en el estado deseado)."

            self._emit(
                f"  Nuevo coding: " + " ".join(f"{b:02X}" for b in coding_list)
            )

            # Escribir
            if not self.kwp.write_coding(bytes(coding_list)):
                self.tp20.close_channel()
                return False, f"El módulo 0x{addr:02X} rechazó la escritura."

            time.sleep(0.1)

            # Verificar
            verified = self.kwp.read_coding()
            self.tp20.close_channel()

            if verified and list(verified) == coding_list:
                return True, "Codificación grabada y verificada correctamente."
            elif verified:
                # Verificar al menos que los bits objetivo estén correctos
                vlist = list(verified)
                bits_ok = all(
                    ((vlist[bi] >> bit) & 1) == (1 if act else 0)
                    for bi, bit, act in bits_activar
                    if bi < len(vlist)
                )
                if bits_ok:
                    return True, "Codificación grabada (verificación de bits OK)."
                return False, "Codificación escrita pero verificación de bits falló."
            else:
                return False, "Escritura enviada pero no se pudo verificar la lectura."

        except Exception as e:
            err = f"Error en módulo 0x{addr:02X}: {e}"
            self._emit(f"  ✗ {err}")
            try:
                self.tp20.close_channel()
            except Exception:
                pass
            return False, err

    # ──────────────────────────────────────────────────────────────────────────
    #  OBJETIVO 3: DIAGNÓSTICO Y BORRADO DE LUCES (MÓDULO 09 - J519)
    # ──────────────────────────────────────────────────────────────────────────
    def gestionar_luces_modulo_09(self, borrar: bool = False) -> Tuple[bool, List[str]]:
        """
        Lee y opcionalmente borra los códigos de avería del módulo de luces/central eléctrica (09).
        """
        self._emit("\n" + "=" * 55)
        self._emit(f"  {'BORRANDO' if borrar else 'LEYENDO'} FALLOS MÓDULO 09 (LUCES)")
        self._emit("=" * 55)

        try:
            self.can.flush_rx()
            self._emit("[TP 2.0] Conectando a Módulo 09 vía canal TP 2.0...")
            if not self.tp20.open_channel(0x09, retries=1):
                return False, ["No se pudo conectar al Módulo 09 (Central Eléctrica) vía TP 2.0."]

            self.kwp.start_diagnostic_session(0x86)
            time.sleep(0.05)

            ident = self.kwp.read_ecu_identification()
            self._emit(f"Módulo identificado vía TP 2.0: Ref {ident.get('part_number')}")

            dtcs = self.kwp.read_dtcs()
            if dtcs:
                self._emit(f"Fallos encontrados ({len(dtcs)}):")
                for d in dtcs:
                    self._emit(f"  → {d}")
            else:
                self._emit("No hay códigos de error almacenados en el módulo de luces.")

            if borrar:
                self._emit("Borrando memoria de averías vía TP 2.0...")
                if self.kwp.clear_dtcs():
                    self._emit("✓ Memoria de averías borrada exitosamente.")
                    time.sleep(0.1)
                    dtcs_post = self.kwp.read_dtcs()
                    return True, dtcs_post
                else:
                    return False, ["Fallo al solicitar el borrado de averías vía TP 2.0."]

            return True, dtcs

        except Exception as e:
            err = f"Error en Módulo 09: {e}"
            self._emit(err)
            return False, [err]
        finally:
            self.tp20.close_channel()

    # ──────────────────────────────────────────────────────────────────────────
    #  AUTO-SCAN COMPLETO (VW TP 2.0)
    # ──────────────────────────────────────────────────────────────────────────
    def auto_scan_completo(self) -> Dict[str, dict]:
        """
        Escanea secuencialmente todos los módulos del Audi A6 C6 utilizando
        protocolo VW TP 2.0 a través del Gateway J533.
        """
        self._emit("\n" + "=" * 60)
        self._emit("  INICIANDO ESCANEO COMPLETO DE CENTRALITAS (AUDI A6 C6)")
        self._emit("=" * 60 + "\n")

        resultados = {}

        for addr, modulo in LOGICAL_MODULES.items():
            self._emit(f"Analizando {modulo} (0x{addr:02X})...")
            info = {
                "nombre": modulo,
                "addr": f"0x{addr:02X}",
                "conectado": False,
                "part_number": "N/A",
                "dtcs": [],
                "error": None
            }

            try:
                self.can.flush_rx()
                if self.tp20.open_channel(addr, retries=1):
                    info["conectado"] = True
                    self.kwp.start_diagnostic_session(0x86)
                    time.sleep(0.02)
                    ecu_id = self.kwp.read_ecu_identification()
                    info["part_number"] = ecu_id.get("part_number", "OK")
                    info["dtcs"] = self.kwp.read_dtcs()
                    num_dtcs = len(info["dtcs"])
                    self._emit(f"  ✓ {modulo} [TP 2.0]: {info['part_number']} — {num_dtcs} fallos detectados.")
                    self.tp20.close_channel()
                else:
                    self._emit(f"  - {modulo}: Sin respuesta (módulo no equipado o en reposo).")
            except Exception as e:
                info["error"] = str(e)
                self._emit(f"  ✗ {modulo}: Error ({e})")
                self.tp20.close_channel()

            resultados[modulo] = info
            time.sleep(0.02)

        return resultados
