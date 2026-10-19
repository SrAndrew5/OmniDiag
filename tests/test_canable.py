# test_canable.py — Utilidad de prueba para CANable en el Audi A6 C6
# ══════════════════════════════════════════════════════════════════════════════
# Ejecución: python test_canable.py
# ══════════════════════════════════════════════════════════════════════════════

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.can_manager import CANManager
from obd.audi_a6_actions import AudiA6Actions
from obd.tp20_can import LOGICAL_MODULES


def main():
    print("=" * 65)
    print("  AudiDiag Pro — Sistema Nativo CANable (python-can)")
    print("  Vehiculo: Audi A6 C6 4F (2010) 2.7 TDI V6")
    print("  VIN: WAUZZZ4F000000000")
    print("=" * 65)
    print()

    can_mgr = CANManager()

    print("[*] Conectando con el adaptador CANable...")
    if not can_mgr.conectar():
        print()
        print("[!] No se detecto adaptador fisico CANable conectado.")
        resp = input("    Deseas iniciar en modo SIMULADOR para probar el menu? (s/n): ")
        if resp.lower().startswith("s"):
            can_mgr.conectar(interface_preference="virtual")
        else:
            print("[*] Saliendo. Conecta el CANable y vuelve a ejecutar.")
            return

    actions = AudiA6Actions(can_mgr)

    while True:
        print()
        print("-" * 50)
        print("  MENU PRINCIPAL")
        print("-" * 50)
        print("  [1] Activar Needle Sweep (Barrido de agujas en Cuadro 17)")
        print("  [2] Diagnosticar y Borrar Fallos de Luces (Modulo 09)")
        print("  [3] Auto-Scan completo de todas las centralitas")
        print("  [4] Monitor de trafico CAN en vivo (Sniffer)")
        print("  [5] Desconectar y Salir")
        print("-" * 50)

        opcion = input("Selecciona una opcion [1-5]: ").strip()

        if opcion == "1":
            print("\n[*] Ejecutando activacion de Needle Sweep...")
            ok, msg = actions.activar_needle_sweep()
            print(f"\nResultado: {'[OK]' if ok else '[FALLO]'} {msg}")

        elif opcion == "2":
            print("\n--- Modulo 09 (Luces y Central Electrica) ---")
            print("  a) Solo leer fallos")
            print("  b) Leer y BORRAR fallos")
            sub = input("Opcion [a/b]: ").strip().lower()
            borrar = sub == "b"
            ok, dtcs = actions.gestionar_luces_modulo_09(borrar=borrar)
            if ok:
                if borrar:
                    print("\n[OK] Memoria de averias borrada.")
                else:
                    print(f"\n[OK] Lectura completada. Codigos: {len(dtcs)}")
            else:
                print(f"\n[FALLO] No se pudo completar la operacion: {dtcs}")

        elif opcion == "3":
            print("\n[*] Iniciando Auto-Scan de centralitas...")
            resultados = actions.auto_scan_completo()
            print("\n" + "=" * 60)
            print("  RESUMEN DE AUTO-SCAN")
            print("=" * 60)
            for nombre, info in resultados.items():
                estado = "ACTIVO" if info["conectado"] else "SIN RESPUESTA"
                num_dtcs = len(info["dtcs"])
                print(f"  {info['addr']} {nombre:<30} [{estado}] Ref: {info['part_number']} | Fallos: {num_dtcs}")

        elif opcion == "4":
            print("\n[*] Sniffer CAN iniciado (Presiona Ctrl+C para detener)...")
            try:
                while True:
                    msg = can_mgr.recv_frame(timeout=1.0)
                    if msg:
                        data_hex = " ".join(f"{b:02X}" for b in msg.data)
                        print(f"  ID: 0x{msg.arbitration_id:03X}  DLC: {len(msg.data)}  DATOS: {data_hex}")
            except KeyboardInterrupt:
                print("\n[*] Sniffer detenido.")

        elif opcion == "5":
            print("\n[*] Desconectando bus CAN...")
            can_mgr.desconectar()
            print("[*] Finalizado. Hasta pronto.")
            break
        else:
            print("[!] Opcion no valida.")


if __name__ == "__main__":
    main()
