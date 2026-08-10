from document_engine.runtime.worker_client import _last_semantic_stage


def test_last_semantic_stage_uses_only_safe_markers():
    stderr = "\n".join(
        [
            "unrelated library warning",
            "SEMANTIC_STAGE stage=preflight_ready elapsed_seconds=8.125",
            "another warning with a private-looking token that must be ignored",
            "SEMANTIC_STAGE stage=extraction_started elapsed_seconds=21.500",
        ]
    )

    stage, elapsed = _last_semantic_stage(stderr)

    assert stage == "extraction_started"
    assert elapsed == 21.5


def test_last_semantic_stage_returns_none_without_valid_marker():
    stage, elapsed = _last_semantic_stage("warning only\nSEMANTIC_STAGE malformed")

    assert stage is None
    assert elapsed is None
