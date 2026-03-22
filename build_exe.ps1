$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$iconPath = Join-Path $projectRoot "Logo\logo (1).ico"

if (-not (Test-Path $iconPath)) {
    throw "Icon file not found: $iconPath"
}

Set-Location $projectRoot

python -m PyInstaller --noconfirm --clean --windowed --name NotLettersDesktop --icon "$iconPath" --add-data "Logo;Logo" main.py
