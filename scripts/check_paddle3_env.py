"""Check that the active Python environment can host PP-StructureV3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from document_benchmark.smoke.preflight import inspect_paddle3_environment


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a PaddleOCR 3.x environment")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    report = inspect_paddle3_environment()
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    if args.require_ready and not report["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
