$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$python = if (Test-Path ".venv-build\Scripts\python.exe") { ".venv-build\Scripts\python.exe" } elseif (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "py" }
$tools = Join-Path (Get-Location) "tools"
if (Test-Path $tools) { $env:Path = "$tools;$env:Path" }
1..3 | ForEach-Object {
    Write-Host "Verification pass $_ of 3"
    if ($python -eq "py") { & py -3 -m pytest -q }
    else { & $python -m pytest -q }
    if ($LASTEXITCODE -ne 0) { throw "Unit verification pass $_ failed" }
    if ($python -eq "py") { & py -3 scripts\verify_release.py }
    else { & $python scripts\verify_release.py }
    if ($LASTEXITCODE -ne 0) { throw "720p render verification pass $_ failed" }
    Copy-Item release_verification.json ("release_verification_pass_{0}.json" -f $_) -Force
}
if ($python -eq "py") { & py -3 run_diagnostics.py }
else { & $python run_diagnostics.py }
if ($LASTEXITCODE -ne 0) { throw "Diagnostics failed" }
