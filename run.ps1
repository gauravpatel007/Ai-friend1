# AI Desktop Friend - PowerShell Launcher
param(
    [switch]$Force,
    [switch]$Setup,
    [switch]$TestRun
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Virtual environment python not found at: $VenvPython" -ForegroundColor Red
    Write-Host "Please ensure the virtual environment is set up at .venv" -ForegroundColor Yellow
    exit 1
}

$Arguments = @("run_desktop.py")
if ($Force) { $Arguments += "--force" }
if ($Setup) { $Arguments += "--setup" }
if ($TestRun) { $Arguments += "--test-run" }

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Launching AI Desktop Friend (PowerShell)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

& $VenvPython @Arguments
