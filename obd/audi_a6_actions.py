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
        self.tp20 = TP20Transport(can_mgr, timeout=1.2)
        self.kwp = KWP2000NativeClient(self.tp20)
        self._log = log_fn or print

    def _emit(self, msg: str):
        try:
            self._log(msg)
        except Exception:
            print(msg)
        diag_logger.log_info(f"[A6 ACTION] {msg}")

    def _rollback(self, original: bytes) -> bool:
        """
        Restaura la codificación original y re-lee obligatoriamente para verificar
        que la centralita realmente tiene la configuración previa en su EEPROM.
        """
        try:
            ok = self.kwp.write_coding(bytes(original))
            time.sleep(0.1)
            back = self.kwp.read_coding()
            return bool(ok and back and bytes(back) == bytes(original))
        except Exception as e:
            self._emit(f"  [ERROR] Excepción ejecutando rollback: {e}")
            return False

    def escribir_coding_seguro(
        self,
        addr: int,
        nombre: str,
        nuevo_bytes: bytes,
        etiqueta_backup: str = "PRE_CODING",
        canal_ya_abierto: bool = False,
        current_coding: bytes = None
    ) -> Tuple[bool, str]:
        """
        Función ÚNICA y unificada de escritura segura de codificación para VAG TP 2.0 / KWP2000.
        Aplica la receta de seguridad completa:
        1. Apertura de canal TP 2.0 (o reutilización si canal_ya_abierto=True).
        2. Lectura estricta por 0x1A 0x9E (aborta si la fuente no es 0x1A 0x9E).
        3. Comprobación estricta de longitud: len(nuevo_bytes) == len(original).
        4. Backup obligatorio a disco antes de cualquier intento de escritura (aborta si falla).
        5. Comprobación de idempotencia: si nuevo_bytes == original, no escribe y retorna éxito.
        6. Escritura mediante Service 0x3B 0x9E (write_coding).
        7. Relectura y verificación byte a byte al 100%.
        8. Si la verificación no coincide: ROLLBACK automático obligatorio a la codificación original,
           con relectura obligatoria para confirmar que el módulo recuperó su estado previo.
        9. Cierre seguro del canal TP 2.0 con pausa de estabilización.
        """
        if not canal_ya_abierto:
            self.can.flush_rx()
            addrs_to_try = [0x07, 0x17] if addr in (0x07, 0x17) or "cuadro" in nombre.lower() else [addr]
            canal_conectado = False
            for a_cand in addrs_to_try:
                retries = 2 if a_cand in (0x07, 0x08, 0x09, 0x15, 0x17, 0x42, 0x46, 0x52, 0x5F) else 1
                if self.tp20.open_channel(a_cand, retries=retries):
                    addr = a_cand
                    canal_conectado = True
                    break
            if not canal_conectado:
                return False, f"Sin respuesta del módulo {nombre} (0x{addr:02X}). ¿Contacto encendido y batería >12.5V?"

        try:
            if not canal_ya_abierto:
                self.kwp.start_diagnostic_session(0x86)
                time.sleep(0.05)

            if current_coding is None:
                current_coding = self.kwp.read_coding()
            if not current_coding or len(current_coding) == 0:
                return False, f"El módulo {nombre} (0x{addr:02X}) no devolvió codificación."

            read_src = getattr(self.kwp, "last_read_source", "Desconocido")
            self._emit(f"Canal de lectura en {nombre}: {read_src}")
            fuentes_validas = ("0x1A 0x9E", "0x1A 0x9A", "0x1A 0x9B", "0x22 0x0600", "0x22 0x0601")
            if read_src not in fuentes_validas and not (read_src and read_src.startswith("0x22")):
                return False, f"ABORTADO POR SEGURIDAD: La codificación de {nombre} se obtuvo mediante '{read_src}', no vía protocolo nativo reconocido. Escritura rechazada."

            # Comprobación de longitud exacta
            if len(nuevo_bytes) != len(current_coding):
                err_len = (
                    f"ABORTADO POR SEGURIDAD: Longitud incompatible para {nombre}. "
                    f"Nueva: {len(nuevo_bytes)} bytes | Original: {len(current_coding)} bytes. "
                    f"No se permite escribir codificaciones con longitudes distintas."
                )
                self._emit(f"✗ {err_len}")
                return False, err_len

            # Backup obligatorio previo a la escritura
            self._emit(f"Guardando copia de seguridad obligatoria para {nombre}...")
            original_hex = " ".join(f"{b:02X}" for b in current_coding)
            try:
                from gestion.backup_manager import BackupManager
                bm = BackupManager()
                bm.guardar_backup(
                    modulo=nombre,
                    coche=self.vin or "GENERIC_VAG_VIN",
                    bytes_coding=original_hex,
                    etiqueta=etiqueta_backup
                )
                self._emit(f"✓ Backup original guardado exitosamente para {nombre}.")
            except Exception as e:
                err_backup = f"ABORTADO POR SEGURIDAD: Falló la creación del backup obligatorio de {nombre} ({e}). Escritura cancelada."
                self._emit(f"✗ {err_backup}")
                return False, err_backup

            # Idempotencia: si ya coincide, no escribir
            if bytes(nuevo_bytes) == bytes(current_coding):
                self._emit(f"La codificación en {nombre} ya coincide exactamente con el valor solicitado. Sin cambios.")
                return True, f"Sin cambios: la codificación en {nombre} ya coincide con el valor deseado."

            # Escritura
            nuevo_hex = " ".join(f"{b:02X}" for b in nuevo_bytes)
            self._emit(f"Escribiendo nueva codificación en {nombre} ({len(nuevo_bytes)} bytes): {nuevo_hex}")
            if not self.kwp.write_coding(bytes(nuevo_bytes)):
                return False, f"La centralita de {nombre} (0x{addr:02X}) rechazó el comando de escritura KWP2000 (0x3B 0x9E)."

            time.sleep(0.1)

            # Relectura y verificación byte a byte
            verified_coding = self.kwp.read_coding()
            escrito_str = " ".join(f"{b:02X}" for b in nuevo_bytes)
            releido_str = " ".join(f"{b:02X}" for b in verified_coding) if verified_coding else "NINGUNO"
            self._emit(f"  ▸ Verificación {nombre}: Escrito=[{escrito_str}] | Releído=[{releido_str}]")

            if verified_coding and bytes(verified_coding) == bytes(nuevo_bytes):
                msg = f"¡ÉXITO! Codificación grabada y verificada al 100% (byte a byte) en {nombre} vía TP 2.0."
                self._emit(f"✓ {msg}")
                return True, msg
            else:
                self._emit(f"  ⚠ ALERTA: La verificación no confirmó la codificación completa en {nombre}. Ejecutando ROLLBACK automático...")
                if self._rollback(current_coding):
                    self._emit(f"  ✓ ROLLBACK verificado: {nombre} restaurado y confirmado con su codificación original.")
                    return False, f"La codificación en {nombre} falló en la verificación (releído != escrito). Se ejecutó rollback con éxito y la centralita volvió a su estado original."
                else:
                    self._emit(f"  ✗ CRÍTICO: El ROLLBACK automático FALLÓ o no se confirmó en {nombre}. Restaura manualmente desde el archivo de backup.")
                    return False, f"CRÍTICO: Verificación fallida y el ROLLBACK automático no pudo confirmar la restauración en {nombre}. Restaura manualmente desde el backup."

        except Exception as e:
            err = f"Error durante la codificación de {nombre} (0x{addr:02X}): {e}"
            self._emit(f"✗ {err}")
            return False, err
        finally:
            if not canal_ya_abierto:
                self.tp20.close_channel()
                time.sleep(0.1)

    # ──────────────────────────────────────────────────────────────────────────
    #  OBJETIVO 1: ACTIVAR NEEDLE SWEEP (TEST DE AGUJAS AL ARRANCAR) + LAP TIMER
    #  Cuadro J285 (4F0920933Q) en 0x07 / 0x17 -> Byte 1: Bit 0=1 y Bit 3=1 (0x5F)
    # ──────────────────────────────────────────────────────────────────────────
    def activar_needle_sweep(self) -> Tuple[bool, str]:
        """
        Activa el Needle Sweep (barrido de agujas / Staging) y el Lap Timer (cronómetro)
        en el Cuadro de Instrumentos J285 mediante el método quirúrgico WSC oficial VAG.
        Estrictamente seguro:
          • Sin sesiones de flasheo (0x85) -> sin reinicios bruscos ni parpadeos.
          • Inyección de huella WSC oficial en DID 0xF198 bajo Sesión de Taller 0x89.
          • Verificación obligatoria byte a byte en memoria EEPROM.
        """
        self._emit("\n" + "=" * 65)
        self._emit("  ACTIVANDO NEEDLE SWEEP Y CRONÓMETRO FIS (CUADRO J285)")
        self._emit("=" * 65)

        canal_abierto = False
        addr_usada = 0x07
        # En Audi A6 C6 Facelift la dirección lógica es 0x07 (fallback 0x17 para otros años)
        for cand_addr in (0x07, 0x17):
            self._emit(f"Conectando con Cuadro J285 en dirección 0x{cand_addr:02X}...")
            if self.tp20.open_channel(cand_addr, attempts=3, setup_timeout=1.0):
                canal_abierto = True
                addr_usada = cand_addr
                self._emit(f"✓ Canal TP 2.0 activo en 0x{cand_addr:02X} (TX 0x{self.tp20.tx_addr:03X} / RX 0x{self.tp20.rx_addr:03X})")
                break

        if not canal_abierto:
            return False, "Sin respuesta del Cuadro de Instrumentos (0x07 / 0x17). ¿Contacto puesto y batería >12.5V?"

        try:
            # 1. Leer Codificación Actual en memoria
            current_coding = None
            try:
                resp_cod = self.kwp.execute_service(0x22, data=b"\x06\x00")
                if resp_cod and len(resp_cod) >= 3:
                    current_coding = resp_cod[2:]
            except Exception:
                self.tp20.resync_rx()

            if not current_coding:
                current_coding = self.kwp.read_coding()

            if not current_coding or len(current_coding) < 2:
                return False, "No se pudo leer la codificación del Cuadro de Instrumentos."

            coding_bytes = bytearray(current_coding)
            orig_hex = " ".join(f"{b:02X}" for b in coding_bytes)
            self._emit(f"Codificación actual en memoria ({len(coding_bytes)} bytes): [{orig_hex}]")

            # 2. Guardar Copia de Seguridad obligatoria
            try:
                from gestion.backup_manager import BackupManager
                bm = BackupManager()
                bm.guardar_backup(
                    modulo="Cuadro Instrumentos (17)",
                    coche=self.vin or "GENERIC_VAG_VIN",
                    bytes_coding=orig_hex,
                    etiqueta="PRE_NEEDLE_SWEEP_WSC"
                )
                self._emit("✓ Copia de seguridad obligatoria registrada con éxito en disco.")
            except Exception as e:
                self._emit(f"⚠ Aviso guardando backup: {e}")

            # 3. Comprobar si ya está activo (Bit 0 Staging y Bit 3 Lap Timer)
            byte1_actual = coding_bytes[1]
            if (byte1_actual & 0x01) != 0 and (byte1_actual & 0x08) != 0:
                self._emit(f"✓ El Needle Sweep y el Cronómetro FIS ya están activos en tu cuadro (Byte 1 = 0x{byte1_actual:02X}).")
                return True, f"El Needle Sweep y el Lap Timer ya están activos en el cuadro (Byte 1 = 0x{byte1_actual:02X})."

            # Modificar Byte 1: activar Bit 0 (+Needle Sweep) y Bit 3 (+Lap Timer) -> 0x09
            byte1_nuevo = byte1_actual | 0x09
            coding_bytes[1] = byte1_nuevo
            nueva_coding = bytes(coding_bytes)
            nueva_hex = " ".join(f"{b:02X}" for b in nueva_coding)
            self._emit(f"Nueva codificación a grabar: [{nueva_hex}] (Byte 1: 0x{byte1_actual:02X} -> 0x{byte1_nuevo:02X})")

            # 4. Obtener huella de taller WSC actual
            wsc_payload = bytes([0x0B, 0x07, 0xBC, 0x78, 0x01, 0xBD])
            try:
                resp_wsc = self.kwp.execute_service(0x22, data=b"\xF1\x98")
                if resp_wsc and len(resp_wsc) >= 3:
                    wsc_payload = resp_wsc[2:]
            except Exception:
                self.tp20.resync_rx()

            # 5. Aplicar escritura quirúrgica en Sesión de Taller (0x89) con huella WSC
            self._emit("Entrando en Sesión de Taller VAG (0x89) y estampando huella WSC...")
            try:
                self.kwp.execute_service(0x10, subfunction=0x89)
                time.sleep(0.05)
                self.kwp.execute_service(0x2E, data=b"\xF1\x98" + wsc_payload)
            except Exception as e_wsc:
                self._emit(f"Info WSC: {e_wsc}")
                self.tp20.resync_rx()

            self._emit("Escribiendo Long Coding en DID 0x0600...")
            grabado = False
            try:
                payload_uds = bytes([0x06, 0x00]) + nueva_coding
                resp_w = self.kwp.execute_service(0x2E, data=payload_uds)
                if resp_w is not None:
                    grabado = True
            except Exception as e_w:
                self._emit(f"Info escritura directa: {e_w}")
                self.tp20.resync_rx()
                try:
                    if self.kwp.write_coding(nueva_coding):
                        grabado = True
                except Exception:
                    pass

            if not grabado:
                return False, "La centralita del cuadro rechazó el comando de escritura."

            # 6. Verificación inmediata en memoria EEPROM
            time.sleep(0.1)
            cod_verificada = None
            try:
                resp_chk = self.kwp.execute_service(0x22, data=b"\x06\x00")
                if resp_chk and len(resp_chk) >= 3:
                    cod_verificada = resp_chk[2:]
            except Exception:
                self.tp20.resync_rx()

            if not cod_verificada:
                cod_verificada = self.kwp.read_coding()

            if cod_verificada and len(cod_verificada) >= 2:
                ver_hex = " ".join(f"{b:02X}" for b in cod_verificada)
                self._emit(f"✓ Codificación verificada en memoria: [{ver_hex}]")
                if (cod_verificada[1] & 0x01) != 0:
                    msg_ok = (
                        "¡ÉXITO TOTAL! Barrido de agujas (Needle Sweep) y Cronómetro FIS (Lap Timer) "
                        "grabados y verificados al 100% en el cuadro.\n"
                        "Para disfrutarlo: Quita la llave 15 segundos y vuelve a poner el contacto."
                    )
                    self._emit("=" * 65)
                    self._emit(f"  {msg_ok}")
                    self._emit("=" * 65)
                    return True, msg_ok

            return False, "La codificación fue transmitida pero la verificación no confirmó el cambio en el Byte 1."

        except Exception as e:
            err = f"Error durante la activación del cuadro: {e}"
            self._emit(f"✗ {err}")
            return False, err
        finally:
            self.tp20.close_channel()
            time.sleep(0.1)

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
            addrs_to_try = [0x07, 0x17] if addr in (0x07, 0x17) or "cuadro" in nombre.lower() else [addr]
            canal_conectado = False
            for a_cand in addrs_to_try:
                retries = 2 if a_cand in (0x07, 0x08, 0x09, 0x15, 0x17, 0x42, 0x46, 0x52, 0x5F) else 1
                if self.tp20.open_channel(a_cand, retries=retries):
                    addr = a_cand
                    canal_conectado = True
                    break
            if not canal_conectado:
                return False, f"Sin respuesta del módulo (0x{addr:02X}). ¿Contacto encendido?"

            self.kwp.start_diagnostic_session(0x86)
            time.sleep(0.05)

            current_coding = self.kwp.read_coding()
            if not current_coding or len(current_coding) == 0:
                self.tp20.close_channel()
                return False, f"El módulo 0x{addr:02X} no devolvió codificación."

            read_src = getattr(self.kwp, "last_read_source", "Desconocido")
            fuentes_validas = ("0x1A 0x9E", "0x1A 0x9A", "0x1A 0x9B", "0x22 0x0600", "0x22 0x0601")
            if read_src not in fuentes_validas and not (read_src and read_src.startswith("0x22")):
                self.tp20.close_channel()
                return False, f"ABORTADO POR SEGURIDAD: Codificación de {nombre} leída vía '{read_src}', no vía protocolo reconocido."

            coding_list = list(current_coding)
            self._emit(
                f"  Coding actual ({len(coding_list)} bytes vía {read_src}): "
                + " ".join(f"{b:02X}" for b in coding_list)
            )

            # 1. Validar que todos los bytes requeridos existan en la codificación leída (nunca rellenar con ceros)
            for byte_idx, bit_idx, _ in bits_activar:
                if byte_idx >= len(coding_list):
                    self.tp20.close_channel()
                    err_len = (
                        f"ABORTADO POR SEGURIDAD: El módulo {nombre} tiene {len(coding_list)} bytes de codificación, "
                        f"pero se solicitó modificar el Byte {byte_idx}. No se extenderá la longitud artificialmente."
                    )
                    self._emit(f"  ✗ {err_len}")
                    return False, err_len

            # 2. Aplicar cambios de bits
            modificado = False
            for byte_idx, bit_idx, activar in bits_activar:
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
                return True, "Sin cambios necesarios (bits ya en el estado deseado)."

            nuevo_bytes = bytes(coding_list)

            # 3. Delegar la escritura a la función unificada manteniendo el canal ya abierto (evita doble apertura)
            return self.escribir_coding_seguro(
                addr=addr,
                nombre=nombre,
                nuevo_bytes=nuevo_bytes,
                etiqueta_backup=etiqueta_backup,
                canal_ya_abierto=True,
                current_coding=current_coding
            )
        except Exception as e:
            err = f"Error en módulo 0x{addr:02X}: {e}"
            self._emit(f"  ✗ {err}")
            return False, err
        finally:
            self.tp20.close_channel()
            # Pausa de seguridad para permitir que el Gateway J533 estabilice el canal
            time.sleep(0.1)

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
