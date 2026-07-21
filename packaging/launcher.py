"""PyInstaller entry point for the desktop app."""

import sys

from commission_engine.app import main

if __name__ == "__main__":
    sys.exit(main())
