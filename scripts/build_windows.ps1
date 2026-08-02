$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) { return @("py", "-3.11") }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
    throw "Python 3.11+ is required."
}

function Ensure-FFmpeg {
    $found = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $toolRoot = Join-Path (Get-Location) ".build-tools\ffmpeg"
    $exe = Get-ChildItem $toolRoot -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $exe) {
        Write-Host "Downloading a private FFmpeg build..."
        $zip = Join-Path $env:TEMP "abrar-studio-ffmpeg.zip"
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Remove-Item $toolRoot -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Force $toolRoot | Out-Null
        Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $toolRoot -Force
        $exe = Get-ChildItem $toolRoot -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    }
    if (-not $exe) { throw "FFmpeg could not be installed." }
    return $exe.FullName
}

$versionMatch = Select-String -Path "abrar_studio\constants.py" -Pattern '^APP_VERSION = "([^"]+)"'
if (-not $versionMatch) { throw "Could not read APP_VERSION" }
$AppVersion = $versionMatch.Matches[0].Groups[1].Value

$python = Resolve-Python
if (-not (Test-Path ".venv-build")) {
    & $python[0] @($python[1..($python.Count-1)]) -m venv .venv-build
}
$venvPython = ".\.venv-build\Scripts\python.exe"
& $venvPython -m pip install --disable-pip-version-check --upgrade pip wheel
& $venvPython -m pip install --disable-pip-version-check -r requirements-build.txt

$ffmpegPath = Ensure-FFmpeg
$ffmpegDir = Split-Path $ffmpegPath
$env:Path = "$ffmpegDir;$env:Path"
$env:ABRAR_TEST_FFMPEG = $ffmpegPath

1..3 | ForEach-Object {
    Write-Host "Abrar Studio verification pass $_ of 3"
    & $venvPython -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Unit verification pass $_ failed" }
    & $venvPython scripts\verify_release.py
    if ($LASTEXITCODE -ne 0) { throw "Render verification pass $_ failed" }
    Copy-Item release_verification.json ("release_verification_pass_{0}.json" -f $_) -Force
}

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean --windowed `
    --name "AbrarStudio" `
    --icon "assets\app_icon.ico" `
    --add-data "assets;assets" `
    --add-data "sample_project;sample_project" `
    --add-data "templates;templates" `
    --collect-all PIL `
    app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

New-Item -ItemType Directory -Force "dist\AbrarStudio\tools" | Out-Null
Copy-Item $ffmpegPath "dist\AbrarStudio\tools\ffmpeg.exe" -Force
$ffprobe = Join-Path $ffmpegDir "ffprobe.exe"
if (Test-Path $ffprobe) { Copy-Item $ffprobe "dist\AbrarStudio\tools\ffprobe.exe" -Force }

New-Item -ItemType Directory -Force release | Out-Null
$updatePackage = "release\AbrarStudio-Update.zip"
Remove-Item $updatePackage -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "dist\AbrarStudio\*" -DestinationPath $updatePackage -CompressionLevel Optimal
$updateHash = (Get-FileHash $updatePackage -Algorithm SHA256).Hash.ToLower()
"$updateHash  AbrarStudio-Update.zip" | Set-Content -Encoding ascii "$updatePackage.sha256"

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidate = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = Get-Item $candidate }
}
if (-not $iscc) {
    Write-Warning "Inno Setup 6 not found. Portable build is ready in dist\AbrarStudio."
    exit 0
}
& $iscc.Source ("/DMyAppVersion={0}" -f $AppVersion) "installer\AbrarStudio.iss"
if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }

$setup = Get-Item "release\AbrarStudio-Setup.exe"
$hash = (Get-FileHash $setup.FullName -Algorithm SHA256).Hash.ToLower()
"$hash  AbrarStudio-Setup.exe" | Set-Content -Encoding ascii "release\AbrarStudio-Setup.exe.sha256"
Write-Host "Build complete: $($setup.FullName)"
Write-Host "In-place update complete: $updatePackage"
