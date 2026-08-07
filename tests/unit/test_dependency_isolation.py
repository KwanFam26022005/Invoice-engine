"""Unit tests for verifying optional dependency isolation in subprocesses."""

import subprocess
import sys


def test_import_document_engine_does_not_load_paddle():
    code = (
        "import sys, document_engine\n"
        "assert 'paddle' not in sys.modules, 'paddle loaded on import'\n"
        "assert 'paddleocr' not in sys.modules, 'paddleocr loaded on import'\n"
        "assert 'docling' not in sys.modules, 'docling loaded on import'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"Import isolation check failed: {result.stderr}"


def test_import_registry_does_not_load_paddle():
    code = (
        "import sys, document_engine.parsers.registry\n"
        "assert 'paddle' not in sys.modules, 'paddle loaded on registry import'\n"
        "assert 'paddleocr' not in sys.modules, 'paddleocr loaded on registry import'\n"
        "assert 'docling' not in sys.modules, 'docling loaded on registry import'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"Registry import isolation check failed: {result.stderr}"
