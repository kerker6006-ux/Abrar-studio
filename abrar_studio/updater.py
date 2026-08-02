from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from packaging.version import Version, InvalidVersion


class UpdateError(RuntimeError):
    pass


@dataclass(slots=True)
class ReleaseInfo:
    version: str
    installer_url: str
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
        installer = assets.get("AbrarStudio-Setup.exe")
        checksum = assets.get("AbrarStudio-Setup.exe.sha256")
        if not installer or not checksum:
            raise UpdateError("Latest release is missing the installer or SHA-256 file")
        return ReleaseInfo(tag, installer, checksum, str(data.get("body", "")))

    def download_and_launch(self, release: ReleaseInfo) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="abrar_studio-update-"))
        installer = folder / "AbrarStudio-Setup.exe"
        checksum_file = folder / "AbrarStudio-Setup.exe.sha256"
        self._download(release.installer_url, installer)
        self._download(release.checksum_url, checksum_file)
        expected = checksum_file.read_text(encoding="utf-8").strip().split()[0].lower()
        actual = hashlib.sha256(installer.read_bytes()).hexdigest()
        if actual != expected:
            raise UpdateError("Update checksum validation failed")
        subprocess.Popen([str(installer), "/SILENT", "/CLOSEAPPLICATIONS"])
        return installer

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
