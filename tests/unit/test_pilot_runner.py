"""Unit tests for pilot manifest execution and audit status separation."""

import yaml
import json
from scripts.run_pilot import main


def test_pilot_manual_audit_defaults_to_not_audited(tmp_path, monkeypatch, capsys):
    manifest_file = tmp_path / "pilot_manifest.yaml"
    manifest_data = {
        "documents": [
            {
                "id": "test_doc_001",
                "path": str(tmp_path / "nonexistent.pdf"),
                "expected_family": "sales_invoice",
            }
        ]
    }
    manifest_file.write_text(yaml.dump(manifest_data), encoding="utf-8")

    output_dir = tmp_path / "reports"
    monkeypatch.setattr(
        "sys.argv",
        ["run_pilot.py", "--manifest", str(manifest_file), "--output-dir", str(output_dir)],
    )
    main()

    captured = capsys.readouterr()
    assert "Starting Private Real-Document Pilot V2" in captured.out
    assert output_dir.exists()
    assert "nonexistent.pdf" not in captured.out


def test_pilot_error_report_excludes_path_filename_and_exception(tmp_path, monkeypatch):
    manifest_file = tmp_path / "pilot_manifest.yaml"
    private_filename = "private_supplier_invoice.pdf"
    manifest_file.write_text(
        yaml.dump({"documents": [{"id": "safe-doc", "path": str(tmp_path / private_filename)}]}),
        encoding="utf-8",
    )
    (tmp_path / private_filename).touch()
    output_dir = tmp_path / "reports"

    class ExplodingPipeline:
        def process_file(self, *_args, **_kwargs):
            raise RuntimeError("private raw exception contents")

    monkeypatch.setattr("scripts.run_pilot.DocumentPipeline", ExplodingPipeline)
    monkeypatch.setattr(
        "sys.argv",
        ["run_pilot.py", "--manifest", str(manifest_file), "--output-dir", str(output_dir)],
    )
    main()

    report = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
    serialized = json.dumps(report)
    assert private_filename not in serialized
    assert str(tmp_path) not in serialized
    assert "private raw exception contents" not in serialized
    assert report["document_reports"] == [
        {
            "document_id": "safe-doc",
            "status": "ERROR",
            "error_type": "RuntimeError",
            "safe_error_code": "PIPELINE_PROCESSING_ERROR",
            "manual_audit_status": "NOT_AUDITED",
        }
    ]

