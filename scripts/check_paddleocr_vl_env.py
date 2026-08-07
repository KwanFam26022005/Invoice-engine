"""Check script for PaddleOCR-VL environment status without downloading models."""

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
    print(f"Paddle model cache present: {paddle_cache.exists()} ({paddle_cache})")
    print("--------------------------------------")

if __name__ == "__main__":
    check_paddle_env()
