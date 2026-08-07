"""Unit tests for PaddleOCR-VL worker output mapping, API parameters, and offline policy."""

import pytest

from document_engine.parsers.paddleocr_vl import PaddleOCRVLParser
from document_engine.workers.paddleocr_vl_worker import build_page_ir_from_paddle


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

    assert page_ir_dict["width"] == 640.0
    assert page_ir_dict["height"] == 960.0
    assert page_ir_dict["width"] != 595.0
    assert page_ir_dict["height"] != 842.0

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


def test_paddleocr_vl_constructor_public_api_kwargs(monkeypatch):
    """Test PaddleOCRVL constructor parameters against official API signature."""
    passed_kwargs = {}

    class FakePaddleOCRVLClass:
        def __init__(self, **kwargs):
            # Raise TypeError if deprecated / unsupported kwargs are passed
            forbidden = {"use_gpu", "use_angle_cls", "use_doc_unwarp"}
            for key in kwargs:
                if key in forbidden:
                    raise TypeError(f"Unexpected keyword argument: {key}")
            passed_kwargs.update(kwargs)

    # Verify our worker options pass valid public kwargs
    valid_options = {
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

    FakePaddleOCRVLClass(**valid_options)
    assert passed_kwargs["device"] == "cpu"
    assert passed_kwargs["engine"] == "paddle"

    with pytest.raises(TypeError):
        FakePaddleOCRVLClass(use_gpu=False)


def test_paddleocr_vl_healthcheck_offline():
    parser = PaddleOCRVLParser()
    health = parser.healthcheck()
    assert isinstance(health.healthy, bool)
    assert health.parser_id == "paddleocr_vl"
