# Setup dedicated virtual environment for PaddleOCR-VL fallback worker
$ErrorActionPreference = "Stop"

Write-Host "Setting up .venv-paddlevl virtual environment..." -ForegroundColor Green

if (-not (Test-Path ".venv-paddlevl")) {
    python -m venv .venv-paddlevl
}

& .venv-paddlevl\Scripts\python.exe -m pip install --upgrade pip
& .venv-paddlevl\Scripts\python.exe -m pip install "paddlepaddle>=3.2.1" "paddleocr[doc-parser]>=3.7.0" pydantic

Write-Host "Checking PaddleOCR-VL environment..." -ForegroundColor Green
& .venv-paddlevl\Scripts\python.exe scripts\check_paddleocr_vl_env.py
