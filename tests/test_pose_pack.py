from __future__ import annotations

import unittest

from abrar_studio.locks import verify_manifest
from tests.common import make_project


class PosePackTests(unittest.TestCase):
    def test_main_characters_have_complete_locked_pose_pack(self):
        temp, project = make_project(); self.addCleanup(temp.cleanup)
        for character_id in ["seo_yeon", "min_jun"]:
            character = project.character(character_id)
            self.assertGreaterEqual(len(character.poses), 4)
            self.assertGreaterEqual(len(character.gestures), 8)
            self.assertGreaterEqual(len(character.mouths), 5)
            ok, errors = verify_manifest(project.character_manifest_path(character_id))
            self.assertTrue(ok, errors)


if __name__ == "__main__":
    unittest.main()
