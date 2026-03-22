$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $projectRoot

python -m PyInstaller --noconfirm --clean NotLettersDesktop.spec
