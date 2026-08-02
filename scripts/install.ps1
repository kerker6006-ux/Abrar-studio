$ErrorActionPreference = "Stop"
$Source = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\AbrarStudio"
$LogDir = Join-Path $env:LOCALAPPDATA "AbrarStudio\InstallLogs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Log = Join-Path $LogDir ("install-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
Start-Transcript -Path $Log -Force | Out-Null

function Find-Python {
    $candidates = @(
        @{ Cmd = "py"; Args = @("-3.11") },
        @{ Cmd = "python"; Args = @() },
        @{ Cmd = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"; Args = @() }
    )
    foreach ($item in $candidates) {
        try {
            if ($item.Cmd -eq "py") {
                & $item.Cmd @($item.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ Cmd = $item.Cmd; Args = $item.Args } }
            } elseif (Test-Path $item.Cmd) {
                & $item.Cmd -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ Cmd = $item.Cmd; Args = $item.Args } }
            } elseif (Get-Command $item.Cmd -ErrorAction SilentlyContinue) {
                & $item.Cmd -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @{ Cmd = $item.Cmd; Args = $item.Args } }
            }
        } catch {}
    }
    return $null
}

Write-Host "[1/7] Checking Python 3.11+..."
$Python = Find-Python
if (-not $Python) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw "Python 3.11+ is required and winget is unavailable. Install 64-bit Python 3.11, then run this installer again." }
    Write-Host "Installing Python 3.11 for the current user..."
    & $winget.Source install --id Python.Python.3.11 --exact --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python installation failed with exit code $LASTEXITCODE" }
    $env:Path = "$env:LOCALAPPDATA\Programs\Python\Python311;$env:LOCALAPPDATA\Programs\Python\Python311\Scripts;$env:Path"
    $Python = Find-Python
    if (-not $Python) { throw "Python was installed but could not be located. Restart Windows and run the installer again." }
}

Write-Host "[2/7] Copying application files..."
if (Test-Path $InstallDir) {
    Remove-Item -Recurse -Force $InstallDir
}
New-Item -ItemType Directory -Force $InstallDir | Out-Null
$exclude = @(".venv", ".venv-build", "build", "dist", "__pycache__")
Get-ChildItem -Force $Source | Where-Object { $exclude -notcontains $_.Name } | ForEach-Object {
    Copy-Item $_.FullName -Destination $InstallDir -Recurse -Force
}

Write-Host "[3/7] Preparing local Python environment..."
$venv = Join-Path $InstallDir ".venv"
if ($Python.Cmd -eq "py") {
    & $Python.Cmd @($Python.Args) -m venv $venv
} else {
    & $Python.Cmd -m venv $venv
}
$VenvPython = Join-Path $venv "Scripts\python.exe"
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip wheel
& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt")

Write-Host "[4/7] Installing private FFmpeg runtime..."
$Tools = Join-Path $InstallDir "tools"
New-Item -ItemType Directory -Force $Tools | Out-Null
$Ffmpeg = Join-Path $Tools "ffmpeg.exe"
$Ffprobe = Join-Path $Tools "ffprobe.exe"
if (-not (Test-Path $Ffmpeg)) {
    $zip = Join-Path $env:TEMP "abrar_studio-ffmpeg.zip"
    $extract = Join-Path $env:TEMP "abrar_studio-ffmpeg"
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $extract -Force
    $foundFfmpeg = Get-ChildItem $extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
    $foundFfprobe = Get-ChildItem $extract -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
    if (-not $foundFfmpeg) { throw "Downloaded FFmpeg archive did not contain ffmpeg.exe" }
    Copy-Item $foundFfmpeg.FullName $Ffmpeg -Force
    if ($foundFfprobe) { Copy-Item $foundFfprobe.FullName $Ffprobe -Force }
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue
}

$env:Path = "$Tools;$env:Path"
Write-Host "[5/7] Running three complete verification passes..."
Push-Location $InstallDir
try {
    $env:ABRAR_TEST_FFMPEG = $Ffmpeg
    1..3 | ForEach-Object {
        Write-Host "Verification pass $_ of 3"
        & $VenvPython -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Unit verification pass $_ failed" }
        & $VenvPython scripts\verify_release.py
        if ($LASTEXITCODE -ne 0) { throw "720p render verification pass $_ failed" }
        Copy-Item release_verification.json ("release_verification_pass_{0}.json" -f $_) -Force
    }
    & $VenvPython run_diagnostics.py
    if ($LASTEXITCODE -ne 0) { throw "System diagnostics failed" }
} finally {
    Pop-Location
}

Write-Host "[6/7] Creating shortcuts..."
$RunBat = Join-Path $InstallDir "RUN_ABRAR_STUDIO.bat"
@"
@echo off
cd /d `"$InstallDir`"
start `"Abrar Studio`" `"$VenvPython`" `"$InstallDir\app.py`"
"@ | Set-Content -Path $RunBat -Encoding ASCII
$Shell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
$Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
foreach ($link in @((Join-Path $Desktop "Abrar Studio.lnk"), (Join-Path $Programs "Abrar Studio.lnk"))) {
    $shortcut = $Shell.CreateShortcut($link)
    $shortcut.TargetPath = $RunBat
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.IconLocation = Join-Path $InstallDir "assets\app_icon.ico"
    $shortcut.Save()
}

Write-Host "[7/7] Launching Abrar Studio..."
Start-Process $RunBat
Write-Host "Installed to: $InstallDir"
Write-Host "Verification log: $Log"
Stop-Transcript | Out-Null
