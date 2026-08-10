"""Unit tests for Phase 9 corpus CLI tools."""

import json
import os
from pathlib import Path
import subprocess
import sys
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(script_name: str, cmd_args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    script_path = REPO_ROOT / "scripts" / script_name
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    return subprocess.run(
        [sys.executable, str(script_path)] + cmd_args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def test_register_phase9_document_cli(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    pdf1 = ws / "doc1.pdf"
    pdf1.write_bytes(b"%PDF-1.4 test document content 1")
    reg_file = ws / "corpus_registry.yaml"

    # Register candidate 1
    res = run_cli(
        "register_phase9_document.py",
        [
            "--source",
            "workspace/doc1.pdf",
            "--alias",
            "alias_001",
            "--family",
            "sales_invoice",
            "--cohort",
            "current_pilot",
            "--layout-group",
            "sales_layout_a",
            "--registry",
            str(reg_file),
        ],
        cwd=tmp_path,
    )
    assert res.returncode == 0
    assert "REGISTERED_CANDIDATE: alias=alias_001" in res.stdout

    # Test duplicate SHA256 rejection under different alias
    pdf2 = ws / "doc2.pdf"
    pdf2.write_bytes(b"%PDF-1.4 test document content 1")  # identical content
    res_dup = run_cli(
        "register_phase9_document.py",
        [
            "--source",
            "workspace/doc2.pdf",
            "--alias",
            "alias_002",
            "--family",
            "sales_invoice",
            "--cohort",
            "current_pilot",
            "--layout-group",
            "sales_layout_a",
            "--registry",
            str(reg_file),
        ],
        cwd=tmp_path,
    )
    assert res_dup.returncode != 0
    assert "ERROR: Exact duplicate document already registered" in res_dup.stdout


def test_register_holdout_prior_tuning_rejection(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    pdf = ws / "tuned.pdf"
    pdf.write_bytes(b"%PDF-1.4 tuned content")
    reg_file = ws / "corpus_registry.yaml"

    res = run_cli(
        "register_phase9_document.py",
        [
            "--source",
            "workspace/tuned.pdf",
            "--alias",
            "holdout_001",
            "--family",
            "sales_invoice",
            "--cohort",
            "holdout_same_family",
            "--layout-group",
            "sales_b",
            "--used-for-prior-tuning",
            "true",
            "--registry",
            str(reg_file),
        ],
        cwd=tmp_path,
    )
    assert res.returncode != 0
    assert "ERROR: Document used for prior tuning cannot be registered" in res.stdout


def test_create_phase9_audit_skeleton_cli(tmp_path: Path) -> None:
    audit_file = tmp_path / "workspace" / "sales_001.audit.json"
    res = run_cli(
        "create_phase9_audit_skeleton.py",
        [
            "--alias",
            "sales_001",
            "--family",
            "sales_invoice",
            "--output",
            str(audit_file),
        ],
        cwd=tmp_path,
    )
    assert res.returncode == 0
    assert audit_file.exists()

    data = json.loads(audit_file.read_text(encoding="utf-8"))
    assert data["document_id"] == "sales_001"
    assert data["family"] == "sales_invoice"

    fields = data["fields"]
    assert "common.document_number" in fields
    assert fields["common.document_number"]["status"] == "NOT_AUDITED"
    assert fields["common.document_number"]["expected"] is None


def test_check_phase9_corpus_readiness_cli(tmp_path: Path) -> None:
    reg_file = tmp_path / "workspace" / "corpus_registry.yaml"
    reg_file.parent.mkdir(parents=True, exist_ok=True)
    reg_file.write_text("registry_version: '1.0'\ncandidates: []\n", encoding="utf-8")

    res = run_cli(
        "check_phase9_corpus_readiness.py",
        [
            "--registry",
            str(reg_file),
        ],
        cwd=tmp_path,
    )
    assert res.returncode == 0
    assert "registered_documents: 0" in res.stdout
    assert "VERDICT: PHASE_9F_CORPUS_PREPARATION_REQUIRED" in res.stdout


def test_build_phase9_manifest_cli_insufficient(tmp_path: Path) -> None:
    reg_file = tmp_path / "workspace" / "corpus_registry.yaml"
    reg_file.parent.mkdir(parents=True, exist_ok=True)
    reg_file.write_text("registry_version: '1.0'\ncandidates: []\n", encoding="utf-8")

    manifest_file = tmp_path / "workspace" / "phase9_manifest.yaml"
    res = run_cli(
        "build_phase9_manifest.py",
        [
            "--registry",
            str(reg_file),
            "--output",
            str(manifest_file),
        ],
        cwd=tmp_path,
    )
    assert res.returncode != 0
    assert "PHASE_9F_CORPUS_PREPARATION_REQUIRED" in res.stdout
    assert not manifest_file.exists()


def test_build_phase9_manifest_cli_success(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    candidates = []
    # Create 12 valid documents across 4 layout groups and 3 cohorts
    cohorts = ["current_pilot", "holdout_same_family", "unknown_family"]
    families = [
        "sales_invoice",
        "utility_consumption_invoice",
        "tax_withholding_certificate",
        "receipt",
    ]
    layouts = ["layout_a", "layout_b", "layout_c", "layout_d"]

    for i in range(12):
        alias = f"doc_{i+1:03d}"
        pdf_path = ws / f"{alias}.pdf"
        pdf_path.write_bytes(f"%PDF-1.4 content {i}".encode())
        audit_path = ws / f"{alias}.audit.json"
        audit_path.write_text(
            json.dumps({"fields": {"common.doc_num": {"status": "CONFIRMED", "expected": f"VAL{i}"}}}),
            encoding="utf-8",
        )

        cohort = cohorts[i % len(cohorts)]
        family = families[i % len(families)]
        layout = layouts[i % len(layouts)]

        candidates.append(
            {
                "alias": alias,
                "source_ref": f"workspace/{alias}.pdf",
                "audit_ref": f"workspace/{alias}.audit.json",
                "family": family,
                "cohort": cohort,
                "layout_group": layout,
                "sha256": f"hash_{i:04d}",
                "used_for_prior_tuning": False,
                "audit_confirmed_field_count": 1,
            }
        )

    reg_file = ws / "corpus_registry.yaml"
    reg_file.write_text(
        yaml.safe_dump({"registry_version": "1.0", "candidates": candidates}),
        encoding="utf-8",
    )

    manifest_file = ws / "phase9_manifest.yaml"
    res = run_cli(
        "build_phase9_manifest.py",
        [
            "--registry",
            str(reg_file),
            "--output",
            str(manifest_file),
        ],
        cwd=tmp_path,
    )
    assert res.returncode == 0
    assert "PHASE_9F_MANIFEST_CREATED" in res.stdout
    assert manifest_file.exists()

    manifest_content = yaml.safe_load(manifest_file.read_text(encoding="utf-8"))
    assert len(manifest_content["documents"]) == 12
