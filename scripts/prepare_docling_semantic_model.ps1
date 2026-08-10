param(
    [string]$OutputDir = "workspace/model_cache/docling_semantic",
    [string]$ModelRepo = "numind/NuExtract-2.0-2B"
)

$ErrorActionPreference = "Stop"

$python = Join-Path (Get-Location) ".venv-docling-semantic\Scripts\python.exe"
$doclingTools = Join-Path (Get-Location) ".venv-docling-semantic\Scripts\docling-tools.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Docling semantic environment is missing. Run scripts/setup_docling_semantic_env.ps1 first."
}
if (-not (Test-Path -LiteralPath $doclingTools)) {
    throw "docling-tools.exe is missing from .venv-docling-semantic."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$resolvedOutput = (Resolve-Path -LiteralPath $OutputDir).Path

Write-Host "Preparing local Docling semantic model assets..." -ForegroundColor Green
Write-Host "Model repo: $ModelRepo"
Write-Host "Output: $resolvedOutput"
Write-Host "This is an explicit ONLINE preparation step. Runtime remains offline." -ForegroundColor Yellow

& $doclingTools models download-hf-repo $ModelRepo -o $resolvedOutput
if ($LASTEXITCODE -ne 0) {
    throw "Docling semantic model download failed with exit code $LASTEXITCODE."
}

$env:DOCLING_SEMANTIC_ARTIFACTS_PATH = $resolvedOutput
& $python scripts\check_docling_semantic_model_cache.py
if ($LASTEXITCODE -ne 0) {
    throw "Downloaded model assets did not pass the local readiness check."
}

Write-Host "Model assets are ready for this PowerShell session." -ForegroundColor Green
Write-Host "DOCLING_SEMANTIC_ARTIFACTS_PATH=$resolvedOutput"
Write-Host "For a new shell, set the environment variable again before running the canary." -ForegroundColor Yellow
