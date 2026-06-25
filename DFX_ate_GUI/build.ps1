# Build DFX_Tester with PyInstaller.
#
# Usage (from repo root):
#     .\build.ps1
#
# Produces:
#     dist\DFX_Tester\DFX_Tester.exe   — launcher
#     dist\DFX_Tester\*.dll, *.pyd ... — runtime
#     build\                           — PyInstaller intermediates (safe to delete)
#
# Ship the WHOLE dist\DFX_Tester folder (zip it). The user runs
# DFX_Tester.exe inside the folder; on first launch the app creates a
# sibling 'data\' directory for the SQLite DB, PDF results, encrypted
# logs, and the app.lock single-instance file.
#
# Why onedir (folder) and not onefile (single .exe)? Antivirus engines
# (notably Avast/AVG IDP.HELU.*) heuristically flag PyInstaller onefile
# binaries because they self-extract to %TEMP% on every launch. Onedir
# avoids that pattern and ships unflagged on stock Windows 10/11.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Get-PythonExe {
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }
    $venvPython2 = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPython2) { return $venvPython2 }
    return "python"
}

$py = Get-PythonExe
Write-Host "Using Python: $py"

# Make sure runtime deps and PyInstaller are present.
& $py -m pip install --disable-pip-version-check --quiet -r requirements.txt
& $py -m pip install --disable-pip-version-check --quiet "pyinstaller>=6.5"

# Clean previous build artifacts so stale data files don't sneak in.
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }

# Build using the spec (do NOT pass --onefile/--windowed etc. — those
# come from the spec).
& $py -m PyInstaller --noconfirm --clean DFX_Tester.spec

$bundle = Join-Path $PSScriptRoot "dist\DFX_Tester"
$exe    = Join-Path $bundle "DFX_Tester.exe"
if (-not (Test-Path $exe)) {
    throw "Build finished but $exe was not produced. Check the PyInstaller output above."
}

$bundleSizeMB = [math]::Round(((Get-ChildItem -Recurse $bundle | Measure-Object Length -Sum).Sum) / 1MB, 1)
Write-Host ""
Write-Host "Done. Bundle folder: $bundle  ($bundleSizeMB MB total)"
Write-Host "Launcher: $exe"
Write-Host ""
Write-Host "To share with the boss: zip the dist\DFX_Tester folder, send the zip, unzip on the demo machine, double-click DFX_Tester.exe."
Write-Host "On first launch the app creates a sibling 'data\' folder for the database and reports."
