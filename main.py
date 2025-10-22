#!/usr/bin/env python3
"""Punto de entrada principal para el servicio de escucha de scanner QR."""

from src.scanner_listener import ScannerListener


def main() -> None:
    """Inicializa y ejecuta el servicio de escucha del scanner."""
    listener = ScannerListener()
    listener.start()


if __name__ == "__main__":
    main()
