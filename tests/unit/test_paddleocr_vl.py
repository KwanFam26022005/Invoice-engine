"""Unit tests for PaddleOCR-VL adapter and offline policy."""

import os
from document_engine.parsers.paddleocr_vl import PaddleOCRVLParser


def test_paddleocr_vl_healthcheck_offline():
    parser = PaddleOCRVLParser()
    health = parser.healthcheck()
    assert isinstance(health.healthy, bool)
    assert health.parser_id == "paddleocr_vl"
