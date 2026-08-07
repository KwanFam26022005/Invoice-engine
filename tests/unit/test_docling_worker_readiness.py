"""Regression tests for Docling worker offline EasyOCR readiness."""

import sys
import types

from document_engine.workers.docling_worker import easyocr_offline_runtime_ready


def test_easyocr_offline_ready_uses_download_disabled_reader(monkeypatch):
    calls = []

    class Reader:
        def __init__(self, languages, download_enabled, verbose):
            calls.append((languages, download_enabled, verbose))

    monkeypatch.setitem(sys.modules, "easyocr", types.SimpleNamespace(Reader=Reader))

    ready, error = easyocr_offline_runtime_ready(["vi", "en"])

    assert ready is True
    assert error is None
    assert calls == [(["vi", "en"], False, False)]


def test_easyocr_incomplete_cache_is_not_offline_ready(monkeypatch):
    class Reader:
        def __init__(self, *_args, **_kwargs):
            raise FileNotFoundError("required recognizer model is absent")

    monkeypatch.setitem(sys.modules, "easyocr", types.SimpleNamespace(Reader=Reader))

    ready, error = easyocr_offline_runtime_ready(["vi", "en"])

    assert ready is False
    assert error == "FileNotFoundError"
