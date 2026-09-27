# -*- coding: utf-8 -*-
"""
main.py — Lanzador oficial de OmniDiag / AudiDiag Pro.
Permite iniciar la suite completa desde la raíz con 'python main.py'.
"""
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from audi_diag_pro import MainWindow


def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
