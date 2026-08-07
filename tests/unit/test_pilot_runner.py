"""Unit tests for pilot manifest execution and audit status separation."""

import yaml
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

    monkeypatch.setattr("sys.argv", ["run_pilot.py", "--manifest", str(manifest_file)])
    main()

    captured = capsys.readouterr()
    assert "manual_audit_status: NOT_AUDITED" in captured.out
