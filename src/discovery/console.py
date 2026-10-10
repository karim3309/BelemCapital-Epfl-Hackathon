"""UTF-8 console: without it, the Windows console (cp1252) crashes on accents and ✓."""
import sys


def utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
