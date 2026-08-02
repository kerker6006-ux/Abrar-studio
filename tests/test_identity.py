from __future__ import annotations

import unittest
from abrar_studio.locks import verify_manifest
from tests.common import make_project


class IdentityTests(unittest.TestCase):
    def test_bundled_characters_are_checksum_locked(self):
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        for cid in ["seo_yeon", "min_jun"]:
            ok, errors = verify_manifest(project.character_manifest_path(cid))
            self.assertTrue(ok, errors)

    def test_tamper_is_detected(self):
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        path = project.character_manifest_path("seo_yeon").parent / "portrait.png"
        path.write_bytes(path.read_bytes() + b"tamper")
        ok, errors = verify_manifest(project.character_manifest_path("seo_yeon"))
        self.assertFalse(ok)
        self.assertTrue(any("Checksum mismatch" in x for x in errors))


if __name__ == "__main__":
    unittest.main()
