from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from abrar_studio.updater import GitHubUpdater


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class UpdaterTests(unittest.TestCase):
    def test_latest_release_detection(self):
        payload = {
            "tag_name": "v0.2.0", "body": "test",
            "assets": [
                {"name": "AbrarStudio-Setup.exe", "browser_download_url": "https://example/setup"},
                {"name": "AbrarStudio-Setup.exe.sha256", "browser_download_url": "https://example/hash"}
            ]
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            release = GitHubUpdater("owner", "repo", "0.1.0").check()
        self.assertIsNotNone(release)
        self.assertEqual(release.version, "0.2.0")

    def test_no_update_when_same_version(self):
        payload = {"tag_name": "v0.1.0", "assets": []}
        with patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            self.assertIsNone(GitHubUpdater("owner", "repo", "0.1.0").check())


if __name__ == "__main__":
    unittest.main()
