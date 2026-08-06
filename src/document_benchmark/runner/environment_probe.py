"""Environment and hardware detection probe."""

import platform
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

import psutil


def get_git_commit() -> str | None:
    """Retrieve git commit hash if running in git repo."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def get_gpu_info() -> dict[str, Any]:
    """Detect GPU hardware and CUDA driver info using nvidia-ml-py if available."""
    gpu_data: dict[str, Any] = {
        "gpu_available": False,
        "gpu_name": None,
        "vram_total_mb": None,
        "cuda_version": None,
        "driver_version": None,
    }

    try:
        import pynvml

        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count > 0:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            driver = pynvml.nvmlSystemGetDriverVersion()
            if isinstance(driver, bytes):
                driver = driver.decode("utf-8")

            cuda_v = None
            try:
                cuda_raw = pynvml.nvmlSystemGetCudaDriverVersion()
                cuda_v = f"{cuda_raw // 1000}.{(cuda_raw % 1000) // 10}"
            except Exception:
                pass

            gpu_data.update(
                {
                    "gpu_available": True,
                    "gpu_name": name,
                    "vram_total_mb": round(mem.total / (1024 * 1024), 2),
                    "cuda_version": cuda_v,
                    "driver_version": driver,
                }
            )
        pynvml.nvmlShutdown()
    except Exception:
        # Fallback to nvidia-smi command line check
        try:
            res = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=gpu_name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                line = res.stdout.strip().split("\n")[0]
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpu_data.update(
                        {
                            "gpu_available": True,
                            "gpu_name": parts[0],
                            "vram_total_mb": float(parts[1]),
                            "driver_version": parts[2],
                        }
                    )
        except Exception:
            pass

    return gpu_data


def probe_environment() -> dict[str, Any]:
    """Collect complete environment probe metadata."""
    gpu_info = get_gpu_info()

    # Collect key python package versions
    key_packages = [
        "pydantic",
        "duckdb",
        "openpyxl",
        "psutil",
        "pyyaml",
        "pypdf",
        "docling",
        "paddlepaddle",
        "paddleocr",
        "ollama",
        "torch",
        "transformers",
        "streamlit",
    ]
    pkg_versions: dict[str, str | None] = {}
    for pkg in key_packages:
        try:
            mod = __import__(pkg)
            pkg_versions[pkg] = getattr(mod, "__version__", "installed")
        except Exception:
            pkg_versions[pkg] = None

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "os_family": platform.system(),
        "python_version": sys.version,
        "cpu_model": platform.processor() or "Generic CPU",
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "ram_total_mb": round(psutil.virtual_memory().total / (1024 * 1024), 2),
        "gpu": gpu_info["gpu_name"],
        "gpu_available": gpu_info["gpu_available"],
        "vram_total_mb": gpu_info["vram_total_mb"],
        "cuda_version": gpu_info["cuda_version"],
        "driver_version": gpu_info["driver_version"],
        "package_versions": pkg_versions,
        "git_commit": get_git_commit(),
    }
