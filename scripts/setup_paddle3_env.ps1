[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$VenvPath = ".venv-paddle3",
    [string]$BasePython = "python",
    [string]$PaddleVersion = "3.2.0",
    [string]$PaddleOcrSpec = "paddleocr[doc-parser]>=3,<4",
    [switch]$ForceRecreate
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $scriptDir = $PSScriptRoot
    if ([string]::IsNullOrWhiteSpace($scriptDir) -and $MyInvocation.MyCommand.Definition) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    }
    if ([string]::IsNullOrWhiteSpace($scriptDir)) {
        $scriptDir = (Get-Location).Path
    }
    $ProjectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
} else {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
}
if (-not [System.IO.Path]::IsPathRooted($VenvPath)) {
    $VenvPath = Join-Path $ProjectRoot $VenvPath
}

if ($ForceRecreate -and (Test-Path $VenvPath)) {
    Write-Host "Removing dedicated environment: $VenvPath"
    Remove-Item -Recurse -Force $VenvPath
}

if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating dedicated PaddleOCR 3.x environment: $VenvPath"
    & $BasePython -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment" }
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual-environment Python not found: $VenvPython"
}

& $VenvPython -c "import sys; assert sys.version_info[:2] >= (3, 10), sys.version"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is required" }

Write-Host "Upgrading packaging tools"
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade packaging tools" }

Write-Host "Installing PaddlePaddle CPU $PaddleVersion from the official stable index"
& $VenvPython -m pip install "paddlepaddle==$PaddleVersion" -i "https://www.paddlepaddle.org.cn/packages/stable/cpu/"
if ($LASTEXITCODE -ne 0) { throw "Failed to install PaddlePaddle" }

Write-Host "Installing PP-StructureV3 document-parser dependencies"
& $VenvPython -m pip install $PaddleOcrSpec
if ($LASTEXITCODE -ne 0) { throw "Failed to install PaddleOCR document-parser dependencies" }

Push-Location $ProjectRoot
try {
    Write-Host "Installing the project and developer test dependencies"
    & $VenvPython -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install project dependencies" }

    $ReportPath = Join-Path $VenvPath "paddle3-preflight.json"
    & $VenvPython scripts\check_paddle3_env.py --output $ReportPath --require-ready
    if ($LASTEXITCODE -ne 0) { throw "PaddleOCR 3.x preflight failed" }

    Write-Host "Dedicated environment is ready."
    Write-Host "Python: $VenvPython"
    Write-Host "Preflight report: $ReportPath"
    Write-Host "No model weights have been loaded by this setup script."
}
finally {
    Pop-Location
}
