# scratch/test_cuadro_uds_full.py
# ══════════════════════════════════════════════════════════════════════════════
# Test de diagnóstico UDS completo para Cuadro de Instrumentos (J285)
# Audi A6 C6 Facelift (2010)
#
# Secuencia oficial UDS:
#   1. Despertar funcional (0x7DF -> 0x10 0x01)
#   2. Sesión extendida específica Cuadro (0x714 -> 0x10 0x03)
#   3. TesterPresent (0x714 -> 0x3E 0x80)
#   4. Petición de Identificación / Referencia (0x714 -> 0x22 0xF1 0x91 / 0xF1 0x87)
#   5. Gestión automática de tramas multi-paquete ISO-TP (Flow Control 0x30)
# ══════════════════════════════════════════════════════════════════════════════

import os
import sys
import time

# Configuración DLL libusb para Windows
dll_dir = r"C:\Users\Iulica\Desktop\AudiDiagProjectGemini"
if os.path.exists(dll_dir):
    os.environ["PATH"] = dll_dir + ";" + os.environ["PATH"]
    try:
        os.add_dll_directory(dll_dir)
    except Exception:
        pass

from core.can_manager import CANManager

def ejecutar_test_cuadro_uds():
    print("=" * 65)
    print("  TEST UDS COMPLETO: CUADRO DE INSTRUMENTOS (J285)")
    print("  IDs: Petición 0x714 / 0x7DF  -->  Respuesta esperada 0x77E")
    print("=" * 65)

    can_mgr = CANManager()
    if not can_mgr.conectar():
        print("\n[!] No se pudo conectar con el adaptador CANable.")
        print("    Asegúrate de que está enchufado al USB y el contacto del coche puesto.")
        return

    try:
        can_mgr.flush_rx()
        time.sleep(0.05)

        # ──────────────────────────────────────────────────────────────────────
        # PASO 1: Despertar funcional global (0x7DF)
        # ──────────────────────────────────────────────────────────────────────
        print("\n[PASO 1] Enviando despertar funcional global a 0x7DF (Session 0x01)...")
        wake_msg = [0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]
        can_mgr.send_frame(0x7DF, bytes(wake_msg))
        
        # Escuchar respuestas de centralitas despiertas durante 200 ms
        t_end = time.perf_counter() + 0.2
        respuestas_paso1 = []
        while time.perf_counter() < t_end:
            rx = can_mgr.recv_frame(timeout=0.03)
            if rx and (0x700 <= rx.arbitration_id <= 0x7FF):
                respuestas_paso1.append((rx.arbitration_id, rx.data.hex()))
                print(f"  << Respuesta global detectada: ID 0x{rx.arbitration_id:03X} -> {rx.data.hex()}")

        if not respuestas_paso1:
            print("  (Sin respuestas inmediatas a broadcast 0x7DF, continuando a petición directa...)")

        time.sleep(0.05)

        # ──────────────────────────────────────────────────────────────────────
        # PASO 2: Probar Sesión UDS en los dos pares posibles:
        #   A) Estándar VAG Dashboard UDS: TX 0x714 / RX 0x77E
        #   B) Mapeo directo por dirección 0x17 (como Airbag 0x715): TX 0x717 / RX 0x781
        # ──────────────────────────────────────────────────────────────────────
        candidatos_cuadro = [
            (0x714, 0x77E, "Estándar VAG LL_DashBoardUDS (0x714 -> 0x77E)"),
            (0x717, 0x781, "Mapeo directo Módulo 0x17 (0x717 -> 0x781)")
        ]

        tx_activo = None
        rx_activo = None

        for tx_id, rx_id, desc in candidatos_cuadro:
            print(f"\n[PASO 2] Probando {desc}...")
            for sub_sesion in (0x03, 0x01):
                sess_frame = bytes([0x02, 0x10, sub_sesion, 0x00, 0x00, 0x00, 0x00, 0x00])
                can_mgr.send_frame(tx_id, sess_frame)
                print(f"  >> TX [0x{tx_id:03X}]: {sess_frame.hex()} (Sesión 0x{sub_sesion:02X})")

                t_end = time.perf_counter() + 0.3
                while time.perf_counter() < t_end:
                    rx = can_mgr.recv_frame(timeout=0.05, expected_id=rx_id)
                    if rx:
                        print(f"  << ¡RESPUESTA RECIBIDA EN 0x{rx_id:03X}!: {rx.data.hex()}")
                        if len(rx.data) >= 3 and rx.data[1] == 0x50:
                            print(f"  ✓ ¡ÉXITO TOTAL! Cuadro aceptó la sesión diagnóstica 0x{sub_sesion:02X} en 0x{tx_id:03X}")
                            tx_activo = tx_id
                            rx_activo = rx_id
                            break
                        elif len(rx.data) >= 4 and rx.data[1] == 0x7F:
                            print(f"  - Cuadro respondió negativo (NRC 0x{rx.data[3]:02X}) a sesión 0x{sub_sesion:02X}")
                            tx_activo = tx_id
                            rx_activo = rx_id
                if tx_activo:
                    break
                time.sleep(0.04)
            if tx_activo:
                break

        if not tx_activo:
            tx_activo = 0x714
            rx_activo = 0x77E
            print("\n  (Probando lectura directa sobre 0x714 / 0x77E y 0x717 / 0x781 por si responde sin sesión...)")

        # ──────────────────────────────────────────────────────────────────────
        # PASO 3: TesterPresent para fijar el canal
        # ──────────────────────────────────────────────────────────────────────
        print(f"\n[PASO 3] Enviando TesterPresent (0x3E 0x80) a 0x{tx_activo:03X}...")
        tp_frame = bytes([0x02, 0x3E, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00])
        can_mgr.send_frame(tx_activo, tp_frame)
        time.sleep(0.03)

        # ──────────────────────────────────────────────────────────────────────
        # PASO 4: Pedir Referencia e Identificación (DIDs F191, F187, F190, 0600)
        # ──────────────────────────────────────────────────────────────────────
        dids_a_probar = [
            (0xF191, "Referencia Hardware (ECU HW Number)"),
            (0xF187, "Referencia Recambio (Spare Part Number)"),
            (0xF190, "Número de Bastidor (VIN)"),
            (0x0600, "Codificación Larga (Long Coding)"),
        ]

        # Si ninguno respondió sesión previa, probamos peticiones sobre ambos IDs
        pares_a_leer = [(tx_activo, rx_activo)] if tx_activo != 0x714 else [(0x714, 0x77E), (0x717, 0x781)]

        for tx_id_req, rx_id_exp in pares_a_leer:
            print(f"\n--- Probando lectura de datos en TX 0x{tx_id_req:03X} -> RX 0x{rx_id_exp:03X} ---")
            for did, nombre in dids_a_probar:
                did_h = (did >> 8) & 0xFF
                did_l = did & 0xFF
                req_frame = bytes([0x03, 0x22, did_h, did_l, 0x00, 0x00, 0x00, 0x00])
                print(f"\n[PASO 4] Solicitando {nombre} (DID 0x{did:04X}) a 0x{tx_id_req:03X}...")
                can_mgr.send_frame(tx_id_req, req_frame)
            print(f"  >> TX [0x714]: {req_frame.hex()}")

            # Recibir y gestionar Flow Control si es First Frame (0x10)
            t_end = time.perf_counter() + 0.5
            buffer_resp = bytearray()
            recibiendo_multitrama = False
            total_bytes = 0

            while time.perf_counter() < t_end:
                rx = can_mgr.recv_frame(timeout=0.08, expected_id=0x77E)
                if not rx:
                    continue

                d = rx.data
                print(f"  << RX [0x77E]: {d.hex()}")

                # Single Frame UDS (0x0x)
                if (d[0] & 0xF0) == 0x00:
                    length = d[0] & 0x0F
                    payload = d[1:1 + length]
                    buffer_resp.extend(payload)
                    break

                # First Frame ISO-TP (0x10)
                elif (d[0] & 0xF0) == 0x10:
                    total_bytes = ((d[0] & 0x0F) << 8) | d[1]
                    buffer_resp.extend(d[2:])
                    recibiendo_multitrama = True
                    # Enviar Flow Control inmediatamente para pedir el resto
                    fc_frame = bytes([0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    can_mgr.send_frame(0x714, fc_frame)
                    print(f"  >> TX Flow Control [0x714]: {fc_frame.hex()}")
                    t_end = time.perf_counter() + 0.5

                # Consecutive Frame ISO-TP (0x2x)
                elif (d[0] & 0xF0) == 0x20 and recibiendo_multitrama:
                    buffer_resp.extend(d[1:])
                    if len(buffer_resp) >= total_bytes:
                        break

            if buffer_resp:
                print(f"  ✓ Datos completos recibidos de 0x{did:04X}: {buffer_resp.hex()}")
                # Decodificar texto ASCII si aplica
                ascii_text = "".join(chr(b) if 32 <= b <= 126 else "." for b in buffer_resp)
                print(f"    Texto ASCII decodificado: '{ascii_text}'")
            else:
                print(f"  - Sin respuesta para DID 0x{did:04X}")

            time.sleep(0.05)

        print("\n" + "=" * 65)
        print("  FIN DEL TEST UDS. Revisa las respuestas capturadas arriba.")
        print("=" * 65)

    except Exception as e:
        print(f"\n[!] Error durante la ejecución del test: {e}")
    finally:
        can_mgr.desconectar()

if __name__ == "__main__":
    ejecutar_test_cuadro_uds()
