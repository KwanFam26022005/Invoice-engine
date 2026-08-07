# Setup dedicated virtual environment for Docling Native and Docling OCR workers
$ErrorActionPreference = "Stop"

Write-Host "Setting up .venv-docling virtual environment..." -ForegroundColor Green

if (-not (Test-Path ".venv-docling")) {
    python -m venv .venv-docling
}

& .venv-docling\Scripts\python.exe -m pip install --upgrade pip
& .venv-docling\Scripts\python.exe -m pip install "docling>=2.0.0" easyocr torch pydantic

Write-Host "Checking Docling environment..." -ForegroundColor Green
& .venv-docling\Scripts\python.exe scripts\check_docling_env.py
