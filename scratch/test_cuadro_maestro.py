# scratch/test_cuadro_maestro.py
# ══════════════════════════════════════════════════════════════════════════════
# TEST MAESTRO DEFINITIVO PARA CUADRO DE INSTRUMENTOS (J285)
# Audi A6 C6 Facelift (2010) — 2.7 TDI V6 (WAUZZZ4F2AN066325)
#
# Ejecuta en un solo viaje al coche todas las variantes de acceso por software:
#   FASE 1: Protocolo UDS Moderno (Doble puerta: 0x714/0x77E y 0x717/0x781)
#   FASE 2: Protocolo VW TP 2.0 Clásico (4 Application Types + Timeouts lentos de pasarela)
# ══════════════════════════════════════════════════════════════════════════════

import os
import sys
import time
import struct

# Forzar UTF-8 en Windows stdout
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Configuración DLL libusb para Windows
dll_dir = r"C:\Users\Iulica\Desktop\AudiDiagProjectGemini"
if os.path.exists(dll_dir):
    os.environ["PATH"] = dll_dir + ";" + os.environ["PATH"]
    try:
        os.add_dll_directory(dll_dir)
    except Exception:
        pass

from core.can_manager import CANManager

def test_maestro_cuadro():
    print("=" * 70)
    print("   TEST MAESTRO: ACCESO AL CUADRO DE INSTRUMENTOS (AUDI A6 C6)")
    print("   Probando Fase 1 (UDS Moderno) y Fase 2 (TP 2.0 Clásico)")
    print("=" * 70)

    can_mgr = CANManager()
    if not can_mgr.conectar():
        print("\n[!] No se pudo conectar con el adaptador CANable.")
        print("    Asegúrate de que está enchufado al USB y el contacto del coche puesto.")
        return

    exito = False
    modo_ganador = ""

    try:
        can_mgr.flush_rx()
        time.sleep(0.05)

        # ══════════════════════════════════════════════════════════════════════
        #  FASE 1: PROTOCOLO UDS (ISO 14229 / ISO 15765-2)
        # ══════════════════════════════════════════════════════════════════════
        print("\n" + "─" * 70)
        print("  [FASE 1] PROBANDO PROTOCOLO UDS MODERNO")
        print("─" * 70)

        # 1.1 Despertar funcional global (0x7DF)
        print("  1. Despertar funcional en broadcast 0x7DF...")
        can_mgr.send_frame(0x7DF, bytes([0x02, 0x10, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]))
        time.sleep(0.08)

        # 1.2 Probar las dos posibles parejas de IDs UDS
        candidatos_uds = [
            (0x714, 0x77E, "Estándar VAG LL_DashBoardUDS (TX: 0x714 / RX: 0x77E)"),
            (0x717, 0x781, "Mapeo directo Módulo 17 (TX: 0x717 / RX: 0x781)"),
        ]

        for tx_id, rx_id, desc in candidatos_uds:
            print(f"\n  Probando {desc}:")
            for sub_s in (0x03, 0x01):
                sess_pkt = bytes([0x02, 0x10, sub_s, 0x00, 0x00, 0x00, 0x00, 0x00])
                can_mgr.send_frame(tx_id, sess_pkt)
                print(f"    >> TX [0x{tx_id:03X}]: {sess_pkt.hex()} (Sesión 0x{sub_s:02X})")

                t_fin = time.perf_counter() + 0.35
                while time.perf_counter() < t_fin:
                    rx = can_mgr.recv_frame(timeout=0.06, expected_id=rx_id)
                    if rx:
                        print(f"    << ¡RESPUESTA EN 0x{rx_id:03X}!: {rx.data.hex()}")
                        if len(rx.data) >= 3 and rx.data[1] == 0x50:
                            print(f"    ✓ ¡BINGO UDS! Cuadro aceptó la sesión diagnóstica 0x{sub_s:02X}")
                            exito = True
                            modo_ganador = f"UDS nativo en TX 0x{tx_id:03X} / RX 0x{rx_id:03X}"
                            
                            # Pedir referencia
                            time.sleep(0.03)
                            can_mgr.send_frame(tx_id, bytes([0x02, 0x3E, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00]))
                            time.sleep(0.02)
                            can_mgr.send_frame(tx_id, bytes([0x03, 0x22, 0xF1, 0x91, 0x00, 0x00, 0x00, 0x00]))
                            t_dat = time.perf_counter() + 0.5
                            while time.perf_counter() < t_dat:
                                r_dat = can_mgr.recv_frame(timeout=0.08, expected_id=rx_id)
                                if r_dat:
                                    print(f"    << Referencia recibida: {r_dat.data.hex()}")
                                    break
                            break
                        elif len(rx.data) >= 4 and rx.data[1] == 0x7F:
                            print(f"    - Cuadro contestó negativo NRC 0x{rx.data[3]:02X}")
                if exito:
                    break

            if exito:
                break

        # ══════════════════════════════════════════════════════════════════════
        #  FASE 2: PROTOCOLO VW TP 2.0 / KWP2000 CLÁSICO (SI UDS NO RESPONDE)
        # ══════════════════════════════════════════════════════════════════════
        if not exito:
            print("\n" + "─" * 70)
            print("  [FASE 2] UDS en reposo. PROBANDO VW TP 2.0 CLÁSICO AFINADO")
            print("─" * 70)

            # Probar diferentes variantes de Channel Setup a 0x200
            variantes_tp20 = [
                ("Estándar Diagnóstico (App 0x01)", bytes([0x17, 0xC0, 0x00, 0x10, 0x00, 0x03, 0x01])),
                ("Instrumentación Interna (App 0x02)", bytes([0x17, 0xC0, 0x00, 0x10, 0x00, 0x03, 0x02])),
                ("Bus Kombi Alternativo (App 0x03)", bytes([0x17, 0xC0, 0x00, 0x10, 0x00, 0x03, 0x03])),
                ("Rango Dinámico Invertido (0x0340)", bytes([0x17, 0xC0, 0x00, 0x03, 0x40, 0x07, 0x01])),
            ]

            for desc, payload in variantes_tp20:
                print(f"\n  Probando {desc}...")
                can_mgr.flush_rx()
                can_mgr.send_frame(0x200, payload)
                print(f"    >> TX [0x200]: {payload.hex()}")

                # Timeout generoso de 1.2 segundos para permitir conversión 500k -> 100k
                t_fin = time.perf_counter() + 1.2
                while time.perf_counter() < t_fin:
                    rx = can_mgr.recv_frame(timeout=0.08, expected_id=0x217)
                    if rx and len(rx.data) >= 7:
                        print(f"    << ¡RESPUESTA EN 0x217!: {rx.data.hex()}")
                        status = rx.data[1]
                        if status == 0xD0:
                            print(f"    ✓ ¡BINGO TP 2.0! Gateway abrió canal hacia Cuadro 17")
                            exito = True
                            modo_ganador = f"TP 2.0 con {desc}"
                            break
                        else:
                            print(f"    - Código de rechazo: 0x{status:02X}")
                if exito:
                    break
                time.sleep(0.1)

        # ══════════════════════════════════════════════════════════════════════
        #  RESUMEN FINAL
        # ══════════════════════════════════════════════════════════════════════
        print("\n" + "=" * 70)
        if exito:
            print(f"  ¡¡RESULTADO POSITIVO!!")
            print(f"  Modo que abrió el Cuadro: {modo_ganador}")
            print("  Ya podemos aplicar la codificación de Needle Sweep directamente.")
        else:
            print("  RESULTADO: El Cuadro no respondió a UDS (0x714/0x717) ni a TP 2.0 (0x217).")
            print("  Confirmado que la pasarela J533 aísla totalmente el bus CAN-Kombi.")
        print("=" * 70)

    except Exception as e:
        print(f"\n[!] Error imprevisto: {e}")
    finally:
        can_mgr.desconectar()

if __name__ == "__main__":
    test_maestro_cuadro()
