from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from abrar_studio.updater import GitHubUpdater, UpdateError


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


if __name__ == "__main__":
    unittest.main()
