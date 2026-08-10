"""Unit tests for Phase 9 corpus CLI tools, candidate selection, and contract hardening."""

import hashlib
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


def test_register_phase9_document_cli_privacy_safe_errors(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    pdf1 = ws / "doc1.pdf"
    pdf1.write_bytes(b"%PDF-1.4 test document content 1")
    reg_file = ws / "corpus_registry.yaml"

    # Test invalid family enum
    res_fam = run_cli(
        "register_phase9_document.py",
        [
            "--source",
            "workspace/doc1.pdf",
            "--alias",
            "alias_001",
            "--family",
            "invalid_family_xyz",
            "--cohort",
            "current_pilot",
            "--layout-group",
            "sales_layout_a",
            "--registry",
            str(reg_file),
        ],
        cwd=tmp_path,
    )
    assert res_fam.returncode != 0
    assert "ERROR: INVALID_FAMILY_TYPE" in res_fam.stdout
    assert "invalid_family_xyz" not in res_fam.stdout  # O. Privacy-safe error

    # Test non-workspace path rejection
    res_path = run_cli(
        "register_phase9_document.py",
        [
            "--source",
            "private/doc1.pdf",
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
    assert res_path.returncode != 0
    assert "ERROR: INVALID_WORKSPACE_PATH" in res_path.stdout
    assert "private/doc1.pdf" not in res_path.stdout  # O. Privacy-safe error

    # Test cohort-family mismatch
    res_mismatch = run_cli(
        "register_phase9_document.py",
        [
            "--source",
            "workspace/doc1.pdf",
            "--alias",
            "alias_001",
            "--family",
            "sales_invoice",
            "--cohort",
            "unknown_family",  # sales_invoice is a mature family, cannot be unknown_family!
            "--layout-group",
            "sales_layout_a",
            "--registry",
            str(reg_file),
        ],
        cwd=tmp_path,
    )
    assert res_mismatch.returncode != 0
    assert "ERROR: COHORT_FAMILY_MISMATCH" in res_mismatch.stdout


def test_register_phase9_document_cli_duplicate_and_tuning(tmp_path: Path) -> None:
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

    # Duplicate SHA rejection
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
    assert "ERROR: DUPLICATE_DOCUMENT_REJECTED" in res_dup.stdout

    # Prior tuning holdout rejection
    res_tune = run_cli(
        "register_phase9_document.py",
        [
            "--source",
            "workspace/doc1.pdf",
            "--alias",
            "alias_holdout",
            "--family",
            "sales_invoice",
            "--cohort",
            "holdout_same_family",
            "--layout-group",
            "sales_layout_a",
            "--used-for-prior-tuning",
            "true",
            "--registry",
            str(reg_file),
        ],
        cwd=tmp_path,
    )
    assert res_tune.returncode != 0
    assert "ERROR: HOLDOUT_TUNING_REJECTED" in res_tune.stdout


def test_create_phase9_audit_skeleton_cli_schema_derived(tmp_path: Path) -> None:
    # D, E, N. Skeleton fields derived from schema_registry.py
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
    # Schema-derived canonical paths for sales_invoice
    assert "common.document_number" in fields
    assert "common.issue_date" in fields
    assert "common.seller.name" in fields
    assert "common.grand_total" in fields

    for f_entry in fields.values():
        assert f_entry["expected"] is None
        assert f_entry["status"] == "NOT_AUDITED"
        assert f_entry["notes"] is None


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
    assert "documents_without_confirmed_fields: 0" in res.stdout
    assert "cohort_family_mismatch_count: 0" in res.stdout
    assert "VERDICT: PHASE_9F_CORPUS_PREPARATION_REQUIRED" in res.stdout


def test_build_phase9_manifest_cli_excludes_not_audited_candidate(tmp_path: Path) -> None:
    # L & M. Manifest builder excludes NOT_AUDITED candidates and uses shared evaluation-ready selector
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    candidates = []
    cohorts = ["current_pilot", "holdout_same_family", "unknown_family"]
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
        family = "sales_invoice" if cohort == "holdout_same_family" else ("receipt" if cohort == "unknown_family" else "tax_withholding_certificate")
        sha = hashlib.sha256(f"seed_{i}".encode()).hexdigest()

        candidates.append(
            {
                "alias": alias,
                "source_ref": f"workspace/{alias}.pdf",
                "audit_ref": f"workspace/{alias}.audit.json",
                "family": family,
                "cohort": cohort,
                "layout_group": layouts[i % len(layouts)],
                "sha256": sha,
                "used_for_prior_tuning": False,
                "audit_confirmed_field_count": 1,
            }
        )

    # Add 13th candidate with NOT_AUDITED only audit skeleton
    alias_13 = "doc_013_skeleton"
    pdf_13 = ws / f"{alias_13}.pdf"
    pdf_13.write_bytes(b"%PDF-1.4 skeleton content")
    audit_13 = ws / f"{alias_13}.audit.json"
    audit_13.write_text(
        json.dumps({"fields": {"common.doc_num": {"status": "NOT_AUDITED", "expected": None}}}),
        encoding="utf-8",
    )
    sha_13 = hashlib.sha256(b"seed_13_skeleton").hexdigest()
    candidates.append(
        {
            "alias": alias_13,
            "source_ref": f"workspace/{alias_13}.pdf",
            "audit_ref": f"workspace/{alias_13}.audit.json",
            "family": "sales_invoice",
            "cohort": "current_pilot",
            "layout_group": "layout_a",
            "sha256": sha_13,
            "used_for_prior_tuning": False,
            "audit_confirmed_field_count": 0,
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
    # M. Exactly 12 selected documents in manifest (doc_013_skeleton excluded!)
    assert len(manifest_content["documents"]) == 12
    manifest_aliases = [d["alias"] for d in manifest_content["documents"]]
    assert alias_13 not in manifest_aliases
