"""Console UTF-8 : sans ça, la console Windows (cp1252) plante sur les accents et les ✓."""
import sys


def utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
