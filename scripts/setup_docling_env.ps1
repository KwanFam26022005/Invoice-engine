# Setup dedicated virtual environment for Docling Native and Docling OCR workers
$ErrorActionPreference = "Stop"

$bootstrapPython = $env:DOCLING_BOOTSTRAP_PYTHON
if (-not $bootstrapPython) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) { $bootstrapPython = $pythonCommand.Source }
}
if (-not $bootstrapPython -or -not (Test-Path -LiteralPath $bootstrapPython)) {
    throw "A valid bootstrap Python is required; set DOCLING_BOOTSTRAP_PYTHON."
}

Write-Host "Setting up .venv-docling virtual environment..." -ForegroundColor Green

if (-not (Test-Path ".venv-docling")) {
    & $bootstrapPython -m venv .venv-docling
}

& .venv-docling\Scripts\python.exe -m pip install --upgrade pip
& .venv-docling\Scripts\python.exe -m pip install "docling>=2.0.0" easyocr torch pydantic

Write-Host "Checking Docling environment..." -ForegroundColor Green
& .venv-docling\Scripts\python.exe scripts\check_docling_env.py
