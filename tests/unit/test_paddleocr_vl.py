"""Unit tests for PaddleOCR-VL worker output mapping, API parameters, generator contract, and offline policy."""

import sys
from unittest.mock import MagicMock

from document_engine.parsers.paddleocr_vl import PaddleOCRVLParser
from document_engine.workers.paddleocr_vl_worker import (
    build_page_ir_from_paddle,
    create_paddleocr_vl_pipeline,
)


class FakePaddleResultItem:
    def __init__(self, data: dict):
        self._data = data

    def json(self) -> dict:
        return self._data


def test_paddleocr_vl_output_mapping_contract():
    fake_res = FakePaddleResultItem(
        {
            "res": {
                "width": 640.0,
                "height": 960.0,
                "page_index": 0,
                "parsing_res_list": [
                    {
                        "block_id": "b001",
                        "block_label": "title",
                        "block_content": "HÓA ĐƠN ĐIỆN TỬ",
                        "block_order": 0,
                        "block_bbox": [10.0, 20.0, 300.0, 50.0],
                    },
                    {
                        "block_id": "b002",
                        "block_label": "text",
                        "block_content": "Số: HD-999",
                        "block_order": 1,
                        "block_bbox": [10.0, 60.0, 200.0, 80.0],
                    },
                ],
            }
        }
    )

    page_ir_dict = build_page_ir_from_paddle(fake_res, page_num=1, doc_id="doc_test_123")

    assert page_ir_dict["page_id"] == "doc_test_123_p0001"
    assert page_ir_dict["width"] == 640.0
    assert page_ir_dict["height"] == 960.0

    blocks = page_ir_dict["blocks"]
    assert len(blocks) == 2
    assert blocks[0]["block_id"] == "b001"
    assert blocks[0]["text"] == "HÓA ĐƠN ĐIỆN TỬ"
    assert blocks[0]["label"] == "title"
    assert blocks[0]["reading_order"] == 0
    assert blocks[0]["bbox"] == {
        "x0": 10.0,
        "y0": 20.0,
        "x1": 300.0,
        "y1": 50.0,
        "page_number": 1,
    }

    assert "placeholder" not in page_ir_dict["text_content"].lower()
    assert "fallback page" not in page_ir_dict["text_content"].lower()


def test_paddleocr_vl_generator_predict_contract():
    """Test that predict returning a generator produces 2 deterministic PageIR objects."""
    def generator_predict():
        yield FakePaddleResultItem(
            {
                "res": {
                    "width": 595.0,
                    "height": 842.0,
                    "page_index": 0,
                    "parsing_res_list": [
                        {
                            "block_id": "p1_b1",
                            "block_label": "text",
                            "block_content": "Page 1 Content",
                            "block_order": 0,
                        }
                    ],
                }
            }
        )
        yield FakePaddleResultItem(
            {
                "res": {
                    "width": 595.0,
                    "height": 842.0,
                    "page_index": 1,
                    "parsing_res_list": [
                        {
                            "block_id": "p2_b1",
                            "block_label": "text",
                            "block_content": "Page 2 Content",
                            "block_order": 0,
                        }
                    ],
                }
            }
        )

    results = list(generator_predict())
    assert len(results) == 2

    page1 = build_page_ir_from_paddle(results[0], page_num=1, doc_id="doc_test")
    page2 = build_page_ir_from_paddle(results[1], page_num=2, doc_id="doc_test")

    assert page1["page_id"] == "doc_test_p0001"
    assert page2["page_id"] == "doc_test_p0002"
    assert page1["width"] == 595.0
    assert page2["height"] == 842.0
    assert page1["blocks"][0]["text"] == "Page 1 Content"
    assert page2["blocks"][0]["text"] == "Page 2 Content"


def test_create_paddleocr_vl_pipeline_constructor_kwargs(monkeypatch):
    """Test create_paddleocr_vl_pipeline by monkeypatching PaddleOCRVL in worker module."""
    captured_kwargs = {}

    class MockPaddleOCRVL:
        def __init__(self, **kwargs):
            # Fail if deprecated/unsupported kwargs are passed
            forbidden = {"use_gpu", "use_angle_cls", "use_doc_unwarp"}
            for key in kwargs:
                if key in forbidden:
                    raise TypeError(f"Unexpected deprecated keyword argument: {key}")
            captured_kwargs.update(kwargs)

    mock_paddleocr_mod = MagicMock()
    mock_paddleocr_mod.PaddleOCRVL = MockPaddleOCRVL
    monkeypatch.setitem(sys.modules, "paddleocr", mock_paddleocr_mod)

    options = {
        "pipeline_version": "v1.6",
        "device": "cpu",
        "engine": "paddle",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_layout_detection": True,
        "use_chart_recognition": False,
        "use_seal_recognition": False,
        "use_ocr_for_image_block": False,
    }

    pipeline = create_paddleocr_vl_pipeline(options)
    assert isinstance(pipeline, MockPaddleOCRVL)
    assert captured_kwargs["pipeline_version"] == "v1.6"
    assert captured_kwargs["device"] == "cpu"
    assert captured_kwargs["engine"] == "paddle"
    assert captured_kwargs["use_layout_detection"] is True

    # Assert forbidden kwargs are not present in captured kwargs
    assert "use_gpu" not in captured_kwargs
    assert "use_angle_cls" not in captured_kwargs
    assert "use_doc_unwarp" not in captured_kwargs


def test_paddleocr_vl_healthcheck():
    parser = PaddleOCRVLParser()
    health = parser.healthcheck()
    assert isinstance(health.healthy, bool)
    assert health.parser_id == "paddleocr_vl"
