# Setup dedicated virtual environment for Docling semantic extraction canary
$ErrorActionPreference = "Stop"

$bootstrapPython = $env:DOCLING_BOOTSTRAP_PYTHON
if (-not $bootstrapPython) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) { $bootstrapPython = $pythonCommand.Source }
}
if (-not $bootstrapPython -or -not (Test-Path -LiteralPath $bootstrapPython)) {
    throw "A valid bootstrap Python is required; set DOCLING_BOOTSTRAP_PYTHON."
}

if (-not (Test-Path ".venv-docling-semantic")) {
    & $bootstrapPython -m venv .venv-docling-semantic
}

& .venv-docling-semantic\Scripts\python.exe -m pip install --upgrade pip
& .venv-docling-semantic\Scripts\python.exe -m pip install "docling[vlm]>=2.0.0,<3.0.0" "pydantic>=2.0.0"
& .venv-docling-semantic\Scripts\python.exe scripts\check_docling_semantic_env.py

Write-Host "Docling semantic environment installed. Model assets are NOT downloaded by this script." -ForegroundColor Green
Write-Host "Configure DOCLING_SEMANTIC_ARTIFACTS_PATH only after explicit model preparation." -ForegroundColor Yellow
