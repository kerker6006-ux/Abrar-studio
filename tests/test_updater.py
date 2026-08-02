from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from abrar_studio.updater import GitHubUpdater, UpdateError, _UPDATE_SCRIPT


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class UpdaterTests(unittest.TestCase):
    def test_latest_release_detection(self):
        payload = {
            "tag_name": "v0.2.0", "body": "test",
            "assets": [
                {"name": "AbrarStudio-Update.zip", "browser_download_url": "https://example/update"},
                {"name": "AbrarStudio-Update.zip.sha256", "browser_download_url": "https://example/hash"}
            ]
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            release = GitHubUpdater("owner", "repo", "0.1.0").check()
        self.assertIsNotNone(release)
        self.assertEqual(release.version, "0.2.0")
        self.assertEqual(release.package_url, "https://example/update")

    def test_no_update_when_same_version(self):
        payload = {"tag_name": "v0.1.0", "assets": []}
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            self.assertIsNone(GitHubUpdater("owner", "repo", "0.1.0").check())

    def test_update_requires_in_place_package(self):
        payload = {
            "tag_name": "v0.2.0",
            "assets": [
                {"name": "AbrarStudio-Setup.exe", "browser_download_url": "https://example/setup"},
                {"name": "AbrarStudio-Setup.exe.sha256", "browser_download_url": "https://example/hash"},
            ],
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            with self.assertRaises(UpdateError):
                GitHubUpdater("owner", "repo", "0.1.0").check()

    def test_update_package_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "update.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AbrarStudio.exe", b"application")
                archive.writestr("_internal/module.pyc", b"module")
            GitHubUpdater._validate_package(package)

    def test_update_package_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "update.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AbrarStudio.exe", b"application")
                archive.writestr("../outside.txt", b"unsafe")
            with self.assertRaises(UpdateError):
                GitHubUpdater._validate_package(package)

    def test_previous_update_result_is_consumed_once(self):
        with tempfile.TemporaryDirectory() as folder, patch("abrar_studio.updater.user_data_dir", return_value=Path(folder)):
            diagnostics = Path(folder) / "diagnostics"
            diagnostics.mkdir()
            result_path = diagnostics / "update-result.json"
            result_path.write_text(json.dumps({"status": "failed", "version": "3.0.3", "message": "test"}), encoding="utf-8")
            self.assertEqual(GitHubUpdater.consume_previous_result()["status"], "failed")
            self.assertIsNone(GitHubUpdater.consume_previous_result())

    @unittest.skipUnless(os.name == "nt", "PowerShell updater integration is Windows-only")
    def test_atomic_updater_preserves_installer_files_and_verifies_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install = root / "AbrarStudio"
            install.mkdir()
            (install / "AbrarStudio.exe").write_bytes(b"old-application")
            (install / "unins000.exe").write_bytes(b"installer-metadata")
            package = root / "update.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("AbrarStudio.exe", b"new-application")
                archive.writestr("_internal/module.pyc", b"module")
            script = root / "apply-update.ps1"
            script.write_text(_UPDATE_SCRIPT, encoding="utf-8-sig")
            result = root / "update-result.json"
            log = root / "updater.log"
            powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            completed = subprocess.run([
                str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-ProcessId", "2147483647", "-PackagePath", str(package),
                "-InstallDir", str(install), "-ExecutableName", "AbrarStudio.exe",
                "-ResultPath", str(result), "-LogPath", str(log), "-ExpectedVersion", "9.9.9", "-SkipRestart",
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((install / "AbrarStudio.exe").read_bytes(), b"new-application")
            self.assertEqual((install / "unins000.exe").read_bytes(), b"installer-metadata")
            self.assertEqual(json.loads(result.read_text(encoding="utf-8-sig"))["status"], "success")
            self.assertIn("hash verified", log.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
