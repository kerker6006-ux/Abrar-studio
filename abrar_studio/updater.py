from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from packaging.version import Version, InvalidVersion

from .paths import app_root, user_data_dir


UPDATE_PACKAGE_NAME = "AbrarStudio-Update.zip"
UPDATE_CHECKSUM_NAME = f"{UPDATE_PACKAGE_NAME}.sha256"
UPDATE_EXECUTABLE_NAME = "AbrarStudio.exe"
UPDATE_RESULT_NAME = "update-result.json"
UPDATE_LOG_NAME = "updater.log"


class UpdateError(RuntimeError):
    pass


@dataclass(slots=True)
class ReleaseInfo:
    version: str
    package_url: str
    checksum_url: str
    notes: str = ""


class GitHubUpdater:
    def __init__(self, owner: str, repo: str, current_version: str, timeout: int = 20) -> None:
        self.owner = owner.strip()
        self.repo = repo.strip()
        self.current_version = current_version
        self.timeout = timeout

    def check(self) -> ReleaseInfo | None:
        if not self.owner or not self.repo:
            raise UpdateError("Update repository is not configured")
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/releases/latest"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "AbrarStudio"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise UpdateError(f"Could not check updates: {exc}") from exc
        tag = str(data.get("tag_name", "")).lstrip("v")
        try:
            if Version(tag) <= Version(self.current_version):
                return None
        except InvalidVersion as exc:
            raise UpdateError(f"Invalid release version: {tag}") from exc
        assets = {item.get("name"): item.get("browser_download_url") for item in data.get("assets", []) if isinstance(item, dict)}
        package = assets.get(UPDATE_PACKAGE_NAME)
        checksum = assets.get(UPDATE_CHECKSUM_NAME)
        if not package or not checksum:
            raise UpdateError("Latest release is missing the in-place update package or SHA-256 file")
        return ReleaseInfo(tag, package, checksum, str(data.get("body", "")))

    def download_and_launch(self, release: ReleaseInfo) -> Path:
        if os.name != "nt" or not getattr(sys, "frozen", False):
            raise UpdateError("Automatic in-place updates are available in the installed Windows app")

        folder = Path(tempfile.mkdtemp(prefix="abrar_studio-update-"))
        package = folder / UPDATE_PACKAGE_NAME
        checksum_file = folder / UPDATE_CHECKSUM_NAME
        self._download(release.package_url, package)
        self._download(release.checksum_url, checksum_file)
        checksum_parts = checksum_file.read_text(encoding="utf-8").strip().split()
        expected = checksum_parts[0].lower() if checksum_parts else ""
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise UpdateError("Update checksum file is invalid")
        actual = hashlib.sha256(package.read_bytes()).hexdigest()
        if actual != expected:
            raise UpdateError("Update checksum validation failed")
        self._validate_package(package)

        install_dir = app_root().resolve()
        installed_executable = install_dir / UPDATE_EXECUTABLE_NAME
        if not installed_executable.exists():
            raise UpdateError("Installed application executable was not found")

        script = folder / "apply-update.ps1"
        script.write_text(_UPDATE_SCRIPT, encoding="utf-8-sig")
        diagnostics = user_data_dir() / "diagnostics"
        diagnostics.mkdir(parents=True, exist_ok=True)
        result_path = diagnostics / UPDATE_RESULT_NAME
        log_path = diagnostics / UPDATE_LOG_NAME
        result_path.unlink(missing_ok=True)
        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if not powershell.exists():
            raise UpdateError("Windows PowerShell was not found")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            [
                str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-ProcessId", str(os.getpid()), "-PackagePath", str(package),
                "-InstallDir", str(install_dir), "-ExecutableName", UPDATE_EXECUTABLE_NAME,
                "-ResultPath", str(result_path), "-LogPath", str(log_path),
                "-ExpectedVersion", release.version,
            ],
            close_fds=True,
            creationflags=creation_flags,
        )
        return package

    @staticmethod
    def consume_previous_result() -> dict[str, str] | None:
        path = user_data_dir() / "diagnostics" / UPDATE_RESULT_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            path.unlink(missing_ok=True)
            return {str(key): str(value) for key, value in data.items()}
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _validate_package(package: Path) -> None:
        try:
            with zipfile.ZipFile(package) as archive:
                files = {item.filename.replace("\\", "/") for item in archive.infolist() if not item.is_dir()}
                for name in files:
                    path = Path(name)
                    if path.is_absolute() or path.drive or ".." in path.parts:
                        raise UpdateError("Update package contains an unsafe path")
                if UPDATE_EXECUTABLE_NAME not in files:
                    raise UpdateError("Update package does not contain AbrarStudio.exe")
                bad_file = archive.testzip()
                if bad_file:
                    raise UpdateError(f"Update package is corrupt: {bad_file}")
        except zipfile.BadZipFile as exc:
            raise UpdateError("Update package is not a valid ZIP archive") from exc

    def _download(self, url: str, target: Path) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "AbrarStudio"})
        try:
            with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as fh:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
        except urllib.error.URLError as exc:
            raise UpdateError(f"Update download failed: {exc}") from exc


_UPDATE_SCRIPT = r'''param(
    [Parameter(Mandatory=$true)][int]$ProcessId,
    [Parameter(Mandatory=$true)][string]$PackagePath,
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$ExecutableName,
    [Parameter(Mandatory=$true)][string]$ResultPath,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [Parameter(Mandatory=$true)][string]$ExpectedVersion,
    [switch]$SkipRestart
)
$ErrorActionPreference = "Stop"
$installPath = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$parent = Split-Path -Parent $installPath
$leaf = Split-Path -Leaf $installPath
$suffix = [guid]::NewGuid().ToString("N")
$payload = Join-Path $parent ("." + $leaf + "-payload-" + $suffix)
$stage = Join-Path $parent ("." + $leaf + "-stage-" + $suffix)
$backup = Join-Path $parent ("." + $leaf + "-backup-" + $suffix)
$oldMoved = $false

function Write-UpdateLog([string]$Message) {
    $folder = Split-Path -Parent $LogPath
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value ((Get-Date).ToString("o") + " " + $Message)
}

function Write-UpdateResult([string]$Status, [string]$Message) {
    $folder = Split-Path -Parent $ResultPath
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    [ordered]@{ status = $Status; version = $ExpectedVersion; message = $Message; timestamp = (Get-Date).ToString("o") } |
        ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}

try {
    Write-UpdateLog "Starting update to $ExpectedVersion from package $PackagePath"
    $deadline = (Get-Date).AddSeconds(120)
    while (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        if ((Get-Date) -ge $deadline) { throw "Abrar Studio did not close within 120 seconds" }
        Start-Sleep -Milliseconds 500
    }

    New-Item -ItemType Directory -Path $payload -Force | Out-Null
    Expand-Archive -LiteralPath $PackagePath -DestinationPath $payload -Force
    $payloadExe = Join-Path $payload $ExecutableName
    if (-not (Test-Path -LiteralPath $payloadExe -PathType Leaf)) {
        throw "The staged update does not contain $ExecutableName"
    }

    # Clone the installation first so installer metadata and any future local files survive.
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    if (Test-Path -LiteralPath $installPath -PathType Container) {
        Get-ChildItem -LiteralPath $installPath -Force | Copy-Item -Destination $stage -Recurse -Force -ErrorAction Stop
    }
    Get-ChildItem -LiteralPath $payload -Force | Copy-Item -Destination $stage -Recurse -Force -ErrorAction Stop
    $stagedExe = Join-Path $stage $ExecutableName
    if (-not (Test-Path -LiteralPath $stagedExe -PathType Leaf)) {
        throw "The staged update does not contain $ExecutableName"
    }

    $expectedHash = (Get-FileHash -LiteralPath $stagedExe -Algorithm SHA256).Hash
    Move-Item -LiteralPath $installPath -Destination $backup -Force -ErrorAction Stop
    $oldMoved = $true
    try {
        Move-Item -LiteralPath $stage -Destination $installPath -Force -ErrorAction Stop
    }
    catch {
        Move-Item -LiteralPath $backup -Destination $installPath -Force -ErrorAction SilentlyContinue
        $oldMoved = $false
        throw
    }

    $installedExe = Join-Path $installPath $ExecutableName
    $installedHash = (Get-FileHash -LiteralPath $installedExe -Algorithm SHA256).Hash
    if ($installedHash -ne $expectedHash) { throw "Installed executable verification failed" }
    Write-UpdateLog "Update to $ExpectedVersion installed and hash verified"
    Write-UpdateResult "success" "Abrar Studio $ExpectedVersion installed successfully"
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    $oldMoved = $false
    if (-not $SkipRestart) { Start-Process -FilePath $installedExe }
}
catch {
    $failure = $_.Exception.Message
    Write-UpdateLog ("FAILED: " + $failure)
    if ($oldMoved -and (Test-Path -LiteralPath $backup)) {
        Remove-Item -LiteralPath $installPath -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $backup -Destination $installPath -Force -ErrorAction SilentlyContinue
        $oldMoved = $false
    }
    Write-UpdateResult "failed" $failure
    if ($SkipRestart) {
        [Console]::Error.WriteLine("Updater integration failure: " + $failure)
        exit 1
    }
}
finally {
    Remove-Item -LiteralPath $payload -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
'''
