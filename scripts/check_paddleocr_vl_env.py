"""Check script for PaddleOCR-VL environment status and model artifact readiness."""

import importlib.util
from pathlib import Path
import sys


def check_paddle_env():
    print("--- PaddleOCR-VL Environment Status ---")
    print(f"Python interpreter: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    has_paddle = importlib.util.find_spec("paddle") is not None
    has_paddleocr = importlib.util.find_spec("paddleocr") is not None

    print(f"paddlepaddle installed: {has_paddle}")
    print(f"paddleocr installed: {has_paddleocr}")

    if has_paddle:
        import paddle

        print(f"paddle version: {getattr(paddle, '__version__', 'installed')}")

    if has_paddleocr:
        import paddleocr

        print(f"paddleocr version: {getattr(paddleocr, '__version__', 'installed')}")

    user_home = Path.home()
    paddle_cache = user_home / ".paddleocr"
    has_pdiparams = paddle_cache.exists() and any(paddle_cache.rglob("*.pdiparams"))
    print(f"Paddle model artifacts present (.pdiparams): {has_pdiparams} ({paddle_cache})")
    print("--------------------------------------")


if __name__ == "__main__":
    check_paddle_env()
