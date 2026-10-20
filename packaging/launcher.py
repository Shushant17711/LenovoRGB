"""PyInstaller entry point. With no arguments it opens the desktop app."""

import multiprocessing
import sys

from lenovorgb.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
