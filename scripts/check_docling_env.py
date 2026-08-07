"""Check script for Docling environment status and model cache readiness."""

import importlib.util
from pathlib import Path
import sys


def check_docling_env():
    print("--- Docling Environment Status ---")
    print(f"Python interpreter: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    has_docling = importlib.util.find_spec("docling") is not None
    has_easyocr = importlib.util.find_spec("easyocr") is not None

    print(f"docling installed: {has_docling}")
    print(f"easyocr installed: {has_easyocr}")

    if has_docling:
        import docling

        print(f"docling version: {getattr(docling, '__version__', 'installed')}")

    if has_easyocr:
        import easyocr

        print(f"easyocr version: {getattr(easyocr, '__version__', 'installed')}")

    user_home = Path.home()
    easyocr_cache = user_home / ".EasyOCR"
    easyocr_models_exist = (
        easyocr_cache.exists()
        and any(easyocr_cache.rglob("*.pth"))
    )
    print(f"EasyOCR model cache present: {easyocr_models_exist} ({easyocr_cache})")

    docling_cache = user_home / ".cache" / "docling"
    docling_models_exist = (
        docling_cache.exists()
        and any(docling_cache.rglob("*"))
    )
    print(f"Docling layout model cache present: {docling_models_exist} ({docling_cache})")
    print("---------------------------------")


if __name__ == "__main__":
    check_docling_env()
