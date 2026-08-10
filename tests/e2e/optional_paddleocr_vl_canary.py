"""Optional real PaddleOCR-VL visual/layout canary; not collected by default."""

import json
import os
from pathlib import Path

import fitz
import pytest

from document_engine.core.models import PDFProfileType
from document_engine.ir.models import DocumentProfile, SourceDocument
from document_engine.parsers.paddleocr_vl import PaddleOCRVLParser
from document_engine.runtime import WorkerClient


pytestmark = pytest.mark.optional_engine


def test_paddleocr_vl_real_synthetic_visual_canary(tmp_path: Path):
    if os.getenv("RUN_OPTIONAL_ENGINE_TESTS") != "1":
        pytest.skip("RUN_OPTIONAL_ENGINE_TESTS is not enabled")

    layout_dir = os.getenv("PADDLE_LAYOUT_MODEL_DIR")
    vl_rec_dir = os.getenv("PADDLE_VL_REC_MODEL_DIR")
    if not layout_dir or not vl_rec_dir:
        pytest.skip("Explicit PaddleOCR-VL local model directories are not configured")

    pdf_path = tmp_path / "synthetic_visual_invoice.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    page.insert_text((72, 72), "INVOICE")
    page.insert_text((72, 102), "Invoice No: INV-PADDLE-001")
    page.insert_text((72, 132), "Grand total: 1250000 VND")

    # A small visual table exercises layout ordering/geometry without private data.
    x0, y0, x1, y1 = 72, 180, 520, 300
    page.draw_rect(fitz.Rect(x0, y0, x1, y1))
    page.draw_line((x0, 220), (x1, 220))
    page.draw_line((x0, 260), (x1, 260))
    page.draw_line((330, y0), (330, y1))
    page.insert_text((82, 205), "Service")
    page.insert_text((350, 205), "Amount")
    page.insert_text((82, 245), "Handling")
    page.insert_text((350, 245), "1000000")
    page.insert_text((82, 285), "Tax")
    page.insert_text((350, 285), "250000")
    pdf.save(pdf_path)
    pdf.close()

    source = SourceDocument(
        document_id="doc_paddle_visual_canary",
        filename=pdf_path.name,
        path=str(pdf_path),
        sha256="synthetic-paddle-visual-canary",
        page_count=1,
    )
    profile = DocumentProfile(
        pdf_profile=PDFProfileType.NATIVE_PDF,
        has_text_layer=True,
        text_character_count=100,
    )

    parser = PaddleOCRVLParser(
        config={
            "device": os.getenv("PADDLEOCR_VL_DEVICE", "cpu"),
            "pipeline_version": "v1.6",
            "vl_rec_backend": "native",
            "layout_detection_model_dir": layout_dir,
            "vl_rec_model_dir": vl_rec_dir,
            "use_layout_detection": True,
            "use_queues": False,
        },
        worker_client=WorkerClient(default_timeout=1200.0),
    )

    health = parser.healthcheck()
    assert health.healthy, health.message

    result = parser.parse(source, profile)
    assert result.success, result.error_message
    assert result.document_ir is not None

    document_ir = result.document_ir
    assert document_ir.provenance.parser_id == "paddleocr_vl"
    assert len(document_ir.pages) == 1
    assert document_ir.pages[0].width
    assert document_ir.pages[0].height

    blocks = [block for page_ir in document_ir.pages for block in page_ir.blocks]
    tables = [table for page_ir in document_ir.pages for table in page_ir.tables]
    geometry_count = sum(block.geometry is not None for block in blocks) + sum(
        table.geometry is not None for table in tables
    )

    assert blocks, "PaddleOCR-VL returned no visual text/layout blocks"
    assert geometry_count > 0, "PaddleOCR-VL visual result did not preserve geometry"

    safe_stats = {
        "page_count": len(document_ir.pages),
        "block_count": len(blocks),
        "table_count": len(tables),
        "geometry_count": geometry_count,
        "full_text_chars": len(document_ir.full_text),
        "parser_id": document_ir.provenance.parser_id,
        "parser_version": document_ir.provenance.parser_version,
        "execution_time_seconds": document_ir.provenance.execution_time_seconds,
        "private_corpus_used": False,
    }
    print("PADDLE_VISUAL_CANARY_STATS=" + json.dumps(safe_stats, sort_keys=True))
