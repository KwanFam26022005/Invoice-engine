"""Launcher script for running the single-document comparison Streamlit UI."""

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Run single-document engine comparison Streamlit UI")
    parser.add_argument(
        "--campaign-dir",
        type=str,
        default=r"D:\Documents-engine\runs\smoke\smoke_scan_baseline_001",
        help="Path to campaign directory",
    )
    parser.add_argument(
        "--dataset-root",
        type=str,
        default=r"D:\Documents-engine\datasets",
        help="Path to dataset root directory",
    )
    args = parser.parse_args()

    app_path = Path(__file__).resolve().parent.parent / "src" / "document_benchmark" / "ui" / "comparison_app.py"

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--",
        "--campaign-dir",
        args.campaign_dir,
        "--dataset-root",
        args.dataset_root,
    ]

    print(f"Launching Streamlit UI: {' '.join(cmd)}")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
