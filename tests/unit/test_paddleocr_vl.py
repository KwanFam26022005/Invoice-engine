"""Unit tests for PaddleOCR-VL mapping, current API options, local cache policy, and healthcheck."""

import sys
from unittest.mock import MagicMock

from document_engine.ir.models import BlockIR
from document_engine.parsers.paddleocr_vl import PaddleOCRVLParser
from document_engine.workers.paddleocr_vl_worker import (
    _safe_error,
    build_page_ir_from_paddle,
    check_model_cache_status,
    create_paddleocr_vl_pipeline,
    has_model_artifacts,
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
    assert blocks[0]["block_type"] == "title"
    assert blocks[0]["reading_order"] == 0
    assert blocks[0]["geometry"] == {
        "bbox": [10.0, 20.0, 300.0, 50.0],
        "coordinate_system": "image_pixels_topleft",
        "page_width": 640.0,
        "page_height": 960.0,
    }

    typed_block = BlockIR.model_validate(blocks[0])
    assert typed_block.block_type == "title"
    assert typed_block.geometry is not None
    assert typed_block.geometry.bbox == [10.0, 20.0, 300.0, 50.0]

    assert "placeholder" not in page_ir_dict["text_content"].lower()
    assert "fallback page" not in page_ir_dict["text_content"].lower()


def test_paddleocr_vl_table_and_cell_geometry_mapping():
    fake_res = FakePaddleResultItem(
        {
            "res": {
                "width": 800,
                "height": 1000,
                "parsing_res_list": [
                    {
                        "block_id": "table-1",
                        "block_label": "table",
                        "block_content": "Item | Qty",
                        "block_order": 2,
                        "block_bbox": [100, 200, 700, 500],
                        "table_cells": [
                            {
                                "row_index": 0,
                                "col_index": 0,
                                "text": "Item",
                                "bbox": [100, 200, 400, 250],
                            },
                            {
                                "row_index": 0,
                                "col_index": 1,
                                "text": "Qty",
                                "bbox": [400, 200, 700, 250],
                            },
                        ],
                    }
                ],
            }
        }
    )

    page = build_page_ir_from_paddle(fake_res, page_num=1, doc_id="doc_table")
    assert len(page["tables"]) == 1
    table = page["tables"][0]
    assert table["geometry"]["bbox"] == [100.0, 200.0, 700.0, 500.0]
    assert table["cells"][0]["geometry"]["bbox"] == [100.0, 200.0, 400.0, 250.0]


def test_paddleocr_vl_generator_predict_contract():
    """A generator result can be consumed into deterministic PageIR dictionaries."""

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
    """Use current PaddleOCRVL names and reject deprecated/legacy kwargs."""
    captured_kwargs = {}

    class MockPaddleOCRVL:
        def __init__(self, **kwargs):
            forbidden = {"use_gpu", "use_angle_cls", "use_doc_unwarp", "engine"}
            for key in kwargs:
                if key in forbidden:
                    raise TypeError(f"Unexpected keyword argument: {key}")
            captured_kwargs.update(kwargs)

    mock_paddleocr_mod = MagicMock()
    mock_paddleocr_mod.PaddleOCRVL = MockPaddleOCRVL
    monkeypatch.setitem(sys.modules, "paddleocr", mock_paddleocr_mod)

    options = {
        "pipeline_version": "v1.6",
        "device": "cpu",
        "vl_rec_backend": "native",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_layout_detection": True,
        "use_chart_recognition": False,
        "use_seal_recognition": False,
        "use_ocr_for_image_block": False,
        "use_queues": False,
    }

    pipeline = create_paddleocr_vl_pipeline(options)
    assert isinstance(pipeline, MockPaddleOCRVL)
    assert captured_kwargs["pipeline_version"] == "v1.6"
    assert captured_kwargs["device"] == "cpu"
    assert captured_kwargs["vl_rec_backend"] == "native"
    assert captured_kwargs["use_layout_detection"] is True
    assert captured_kwargs["use_queues"] is False

    assert "engine" not in captured_kwargs
    assert "use_gpu" not in captured_kwargs
    assert "use_angle_cls" not in captured_kwargs
    assert "use_doc_unwarp" not in captured_kwargs


def test_check_model_cache_status_explicit_valid_local_dirs(tmp_path):
    layout_dir = tmp_path / "layout_model"
    vl_rec_dir = tmp_path / "vl_rec_model"
    layout_dir.mkdir()
    vl_rec_dir.mkdir()

    (layout_dir / "model.pdiparams").write_text("dummy", encoding="utf-8")
    (vl_rec_dir / "model.pdiparams").write_text("dummy", encoding="utf-8")

    options = {
        "layout_detection_model_dir": str(layout_dir),
        "vl_rec_model_dir": str(vl_rec_dir),
    }

    status, ready = check_model_cache_status(options)
    assert status == "READY_LOCAL_MODEL_DIRS"
    assert ready is True


def test_check_model_cache_status_recognizes_nested_weight_artifact(tmp_path):
    layout_dir = tmp_path / "layout"
    vl_dir = tmp_path / "vl"
    (layout_dir / "weights").mkdir(parents=True)
    (vl_dir / "weights").mkdir(parents=True)
    (layout_dir / "weights" / "model.pdiparams").write_text("w", encoding="utf-8")
    (vl_dir / "weights" / "model.safetensors").write_text("w", encoding="utf-8")
    status, ready = check_model_cache_status(
        {
            "layout_detection_model_dir": str(layout_dir),
            "vl_rec_model_dir": str(vl_dir),
        }
    )
    assert status == "READY_LOCAL_MODEL_DIRS"
    assert ready is True


def test_check_model_cache_status_missing_one_model_dir(tmp_path):
    layout_dir = tmp_path / "layout_model"
    layout_dir.mkdir()
    (layout_dir / "model.pdiparams").write_text("dummy", encoding="utf-8")

    status, ready = check_model_cache_status(
        {"layout_detection_model_dir": str(layout_dir)}
    )
    assert status == "LOCAL_MODEL_DIRS_INVALID"
    assert ready is False


def test_check_model_cache_status_partial_default_cache(monkeypatch, tmp_path):
    fake_home = tmp_path / "user_home"
    paddle_cache = fake_home / ".paddleocr"
    paddle_cache.mkdir(parents=True)
    (paddle_cache / "model.pdiparams").write_text("dummy", encoding="utf-8")

    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    status, ready = check_model_cache_status({})
    assert status == "MODEL_CACHE_PARTIALLY_VERIFIED"
    assert ready is False


def test_healthcheck_request_carries_local_visual_options():
    captured_request = []

    class MockWorkerClient:
        def execute_worker(self, request):
            captured_request.append(request)
            return MagicMock(
                success=True,
                health_data={
                    "python_executable": "python.exe",
                    "paddle_installed": True,
                },
            )

    parser = PaddleOCRVLParser(worker_client=MockWorkerClient())
    health = parser.healthcheck()

    assert health.healthy is True
    assert len(captured_request) == 1
    assert captured_request[0].operation == "healthcheck"
    assert captured_request[0].options["pipeline_version"] == "v1.6"
    assert captured_request[0].options["device"] == "cpu"
    assert captured_request[0].options["vl_rec_backend"] == "native"
    assert captured_request[0].options["use_queues"] is False


def test_parser_resolves_model_dirs_from_environment(monkeypatch, tmp_path):
    layout_dir = tmp_path / "layout"
    vl_dir = tmp_path / "vl"
    layout_dir.mkdir()
    vl_dir.mkdir()
    monkeypatch.setenv("PADDLE_LAYOUT_MODEL_DIR", str(layout_dir))
    monkeypatch.setenv("PADDLE_VL_REC_MODEL_DIR", str(vl_dir))

    parser = PaddleOCRVLParser(worker_client=MagicMock())
    assert parser.spec.config["layout_detection_model_dir"] == str(layout_dir)
    assert parser.spec.config["vl_rec_model_dir"] == str(vl_dir)


def test_has_model_artifacts_empty_dir(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert has_model_artifacts(empty_dir) is False


def test_has_model_artifacts_readme_only(tmp_path):
    model_dir = tmp_path / "readme_only"
    model_dir.mkdir()
    (model_dir / "README.md").write_text("Just a readme", encoding="utf-8")
    assert has_model_artifacts(model_dir) is False


def test_has_model_artifacts_config_only_is_false(tmp_path):
    config_dir = tmp_path / "config_only"
    config_dir.mkdir()
    (config_dir / "config.json").write_text("{}", encoding="utf-8")
    (config_dir / "inference.yml").write_text("mode: test", encoding="utf-8")
    assert has_model_artifacts(config_dir) is False


def test_has_model_artifacts_with_weight_file(tmp_path):
    model_dir = tmp_path / "with_weight"
    model_dir.mkdir()
    (model_dir / "model.pdiparams").write_text("weight", encoding="utf-8")
    assert has_model_artifacts(model_dir) is True


def test_has_model_artifacts_with_config_and_weight(tmp_path):
    model_dir = tmp_path / "full_model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_text("weight", encoding="utf-8")
    assert has_model_artifacts(model_dir) is True


def test_has_model_artifacts_nonexistent_path(tmp_path):
    assert has_model_artifacts(tmp_path / "does_not_exist") is False


def test_check_model_cache_status_empty_dirs(tmp_path):
    layout_dir = tmp_path / "layout"
    vl_dir = tmp_path / "vl"
    layout_dir.mkdir()
    vl_dir.mkdir()

    status, ready = check_model_cache_status(
        {
            "layout_detection_model_dir": str(layout_dir),
            "vl_rec_model_dir": str(vl_dir),
        }
    )
    assert status == "LOCAL_MODEL_DIRS_PARTIALLY_VERIFIED"
    assert ready is False


def test_check_model_cache_status_readme_only_dirs(tmp_path):
    layout_dir = tmp_path / "layout"
    vl_dir = tmp_path / "vl"
    layout_dir.mkdir()
    vl_dir.mkdir()
    (layout_dir / "README.md").write_text("readme", encoding="utf-8")
    (vl_dir / "README.md").write_text("readme", encoding="utf-8")

    status, ready = check_model_cache_status(
        {
            "layout_detection_model_dir": str(layout_dir),
            "vl_rec_model_dir": str(vl_dir),
        }
    )
    assert status == "LOCAL_MODEL_DIRS_PARTIALLY_VERIFIED"
    assert ready is False


def test_check_model_cache_status_plausible_artifacts(tmp_path):
    layout_dir = tmp_path / "layout"
    vl_dir = tmp_path / "vl"
    layout_dir.mkdir()
    vl_dir.mkdir()
    (layout_dir / "model.pdiparams").write_text("w", encoding="utf-8")
    (layout_dir / "config.yaml").write_text("cfg", encoding="utf-8")
    (vl_dir / "model.safetensors").write_text("w", encoding="utf-8")
    (vl_dir / "config.json").write_text("{}", encoding="utf-8")

    status, ready = check_model_cache_status(
        {
            "layout_detection_model_dir": str(layout_dir),
            "vl_rec_model_dir": str(vl_dir),
        }
    )
    assert status == "READY_LOCAL_MODEL_DIRS"
    assert ready is True


def test_check_model_cache_status_one_valid_one_empty(tmp_path):
    layout_dir = tmp_path / "layout"
    vl_dir = tmp_path / "vl"
    layout_dir.mkdir()
    vl_dir.mkdir()
    (layout_dir / "model.pdiparams").write_text("w", encoding="utf-8")

    status, ready = check_model_cache_status(
        {
            "layout_detection_model_dir": str(layout_dir),
            "vl_rec_model_dir": str(vl_dir),
        }
    )
    assert status == "LOCAL_MODEL_DIRS_PARTIALLY_VERIFIED"
    assert ready is False


def test_paddleocr_vl_none_block_order_regression():
    fake_res = FakePaddleResultItem(
        {
            "res": {
                "width": 600.0,
                "height": 800.0,
                "parsing_res_list": [
                    {
                        "block_id": 1,
                        "block_label": "text",
                        "block_content": "Synthetic A",
                        "block_order": None,
                        "block_bbox": [10, 20, 100, 40],
                    },
                    {
                        "block_id": 2,
                        "block_label": "text",
                        "block_content": "Synthetic B",
                        "block_order": 5,
                        "block_bbox": [10, 50, 100, 70],
                    },
                ],
            }
        }
    )

    page = build_page_ir_from_paddle(fake_res, page_num=1, doc_id="doc_none_order")
    blocks = page["blocks"]
    assert len(blocks) == 2
    assert blocks[0]["text"] == "Synthetic A"
    assert blocks[0]["reading_order"] == 0
    assert blocks[0]["block_id"] == "1"
    assert blocks[1]["text"] == "Synthetic B"
    assert blocks[1]["reading_order"] == 5
    assert blocks[1]["block_id"] == "2"


class FakeArray:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


def test_paddleocr_vl_numpy_like_bbox_regression():
    fake_res = FakePaddleResultItem(
        {
            "res": {
                "width": 800.0,
                "height": 1000.0,
                "parsing_res_list": [
                    {
                        "block_id": "b1",
                        "block_label": "text",
                        "block_content": "Numpy Bbox Text",
                        "block_order": 0,
                        "block_bbox": FakeArray([10, 20, 300, 50]),
                    },
                    {
                        "block_id": "b2",
                        "block_label": "text",
                        "block_content": "Quad Bbox Text",
                        "block_order": 1,
                        "block_bbox": [
                            [10, 20],
                            [300, 20],
                            [300, 50],
                            [10, 50],
                        ],
                    },
                ],
            }
        }
    )

    page = build_page_ir_from_paddle(fake_res, page_num=1, doc_id="doc_numpy")
    blocks = page["blocks"]
    assert blocks[0]["geometry"]["bbox"] == [10.0, 20.0, 300.0, 50.0]
    assert blocks[0]["geometry"]["coordinate_system"] == "image_pixels_topleft"
    assert blocks[1]["geometry"]["bbox"] == [10.0, 20.0, 300.0, 50.0]


def test_paddleocr_vl_none_table_cell_and_block_id_regression():
    fake_res = FakePaddleResultItem(
        {
            "res": {
                "width": 800.0,
                "height": 1000.0,
                "parsing_res_list": [
                    {
                        "block_id": None,
                        "block_label": "table",
                        "block_content": "Cell A | Cell B",
                        "block_order": None,
                        "block_bbox": [100, 200, 700, 500],
                        "table_cells": [
                            {
                                "row_index": None,
                                "col_index": None,
                                "text": "Cell A",
                                "bbox": [100, 200, 400, 250],
                            },
                            {
                                "row_index": "invalid",
                                "col_index": -1,
                                "text": "Cell B",
                                "bbox": [400, 200, 700, 250],
                            },
                        ],
                    }
                ],
            }
        }
    )

    page = build_page_ir_from_paddle(fake_res, page_num=1, doc_id="doc_none_cell")
    assert len(page["blocks"]) == 1
    assert page["blocks"][0]["block_id"] == "doc_none_cell_p0001_b00000"
    assert page["blocks"][0]["block_id"] != "None"

    assert len(page["tables"]) == 1
    cells = page["tables"][0]["cells"]
    assert len(cells) == 2
    assert cells[0]["row_index"] == 0
    assert cells[0]["col_index"] == 0
    assert cells[1]["row_index"] == 1
    assert cells[1]["col_index"] == 0


def test_paddleocr_vl_privacy_safe_stage_diagnostic():
    err = _safe_error(
        req_id="req_test",
        parser_id="paddleocr_vl",
        versions={"paddleocr": "3.7.0"},
        code="PADDLEOCR_VL_TYPEERROR",
        message="PaddleOCR-VL worker failed during ir_mapping: TypeError",
        stage="ir_mapping",
    )

    assert err["error_type"] == "PADDLEOCR_VL_TYPEERROR"
    assert err["error_message"] == "PaddleOCR-VL worker failed during ir_mapping: TypeError"
    assert "error_stage" in err
    assert err["error_stage"] == "ir_mapping"
    assert "invoice" not in err["error_message"].lower()
    assert "secret" not in err["error_message"].lower()
