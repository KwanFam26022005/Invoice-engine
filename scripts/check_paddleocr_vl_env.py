"""Inspect the installed PaddleOCR-VL API without loading model weights."""

import importlib
import importlib.util
import inspect
import json
import sys


def _version(package: str):
    try:
        module = importlib.import_module(package)
        return getattr(module, "__version__", "installed")
    except Exception:
        return None


def main() -> None:
    modules = {
        "paddle": importlib.util.find_spec("paddle") is not None,
        "paddleocr": importlib.util.find_spec("paddleocr") is not None,
        "pydantic": importlib.util.find_spec("pydantic") is not None,
    }

    api_symbols = {
        "PaddleOCRVL": False,
        "predict": False,
        "predict_iter": False,
    }
    signatures = {}
    import_error = None

    if modules["paddleocr"]:
        try:
            from paddleocr import PaddleOCRVL

            api_symbols["PaddleOCRVL"] = True
            api_symbols["predict"] = callable(getattr(PaddleOCRVL, "predict", None))
            api_symbols["predict_iter"] = callable(
                getattr(PaddleOCRVL, "predict_iter", None)
            )
            signatures["PaddleOCRVL.__init__"] = str(inspect.signature(PaddleOCRVL.__init__))
            if api_symbols["predict"]:
                signatures["PaddleOCRVL.predict"] = str(
                    inspect.signature(PaddleOCRVL.predict)
                )
            if api_symbols["predict_iter"]:
                signatures["PaddleOCRVL.predict_iter"] = str(
                    inspect.signature(PaddleOCRVL.predict_iter)
                )
        except Exception as exc:
            import_error = type(exc).__name__

    payload = {
        "modules": modules,
        "versions": {
            "python": sys.version.split()[0],
            "paddle": _version("paddle"),
            "paddleocr": _version("paddleocr"),
            "pydantic": _version("pydantic"),
        },
        "api_symbols": api_symbols,
        "signatures": signatures,
        "import_error": import_error,
        "inference_executed": False,
        "model_loaded": False,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
