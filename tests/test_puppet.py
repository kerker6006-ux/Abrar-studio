from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from abrar_studio.paths import app_root
from abrar_studio.puppet import (
    ARTICULATED_MOTIONS,
    ArticulatedPuppetRenderer,
    RigDefinition,
    footstep_times,
    motion_state,
    normalize_motion,
)


class ArticulatedPuppetTests(unittest.TestCase):
    def rig_path(self, character_id: str) -> Path:
        return app_root() / "assets" / "characters" / character_id / "rig" / "rig.json"

    def test_bundled_rigs_load_with_complete_limb_hierarchy(self):
        required = {
            "torso", "head",
            "arm_front_upper", "arm_front_lower", "arm_back_upper", "arm_back_lower",
            "leg_front_upper", "leg_front_lower", "foot_front",
            "leg_back_upper", "leg_back_lower", "foot_back",
        }
        for character_id in ("seo_yeon", "min_jun"):
            rig = RigDefinition.load(self.rig_path(character_id))
            self.assertEqual(rig.character_id, character_id)
            self.assertTrue(required.issubset(rig.parts))
            self.assertTrue(ARTICULATED_MOTIONS.intersection(rig.motions))
            for part in rig.parts.values():
                self.assertTrue((self.rig_path(character_id).parent.parent / part.file).is_file(), part.file)

    def test_walk_and_run_states_move_opposed_limbs(self):
        walk = motion_state("walk_normal", 0.23, 0.5)
        run = motion_state("run_normal", 0.23, 0.5)
        self.assertAlmostEqual(walk.angles["leg_front_upper"], -walk.angles["leg_back_upper"], places=5)
        self.assertAlmostEqual(run.angles["arm_front_upper"], -run.angles["arm_back_upper"], places=5)
        walk_peak = max(abs(motion_state("walk_normal", x / 100, 0.5).angles["leg_front_upper"]) for x in range(100))
        run_peak = max(abs(motion_state("run_normal", x / 100, 0.5).angles["leg_front_upper"]) for x in range(100))
        walk_bob = max(abs(motion_state("walk_normal", x / 100, 0.5).root_dy) for x in range(100))
        run_bob = max(abs(motion_state("run_normal", x / 100, 0.5).root_dy) for x in range(100))
        self.assertGreater(run_peak, walk_peak)
        self.assertGreater(run_bob, walk_bob)

    def test_motion_aliases_and_footsteps(self):
        self.assertEqual(normalize_motion("walking"), "walk_normal")
        self.assertEqual(normalize_motion("run"), "run_normal")
        walk = footstep_times("walk_normal", 3.0)
        run = footstep_times("run_normal", 3.0)
        self.assertGreaterEqual(len(walk), 5)
        self.assertGreater(len(run), len(walk))
        self.assertEqual(walk, sorted(walk))

    def test_puppet_renders_transparent_distinct_motion_frames(self):
        renderer = ArticulatedPuppetRenderer()
        rig = self.rig_path("seo_yeon")
        first = renderer.render(rig, "walk_normal", 0.0, 0.15)
        second = renderer.render(rig, "walk_normal", 0.42, 0.55)
        self.assertEqual(first.mode, "RGBA")
        self.assertIsNotNone(first.getbbox())
        self.assertGreater(first.height, 500)
        self.assertNotEqual(hashlib.sha256(first.tobytes()).digest(), hashlib.sha256(second.tobytes()).digest())

    def test_facing_left_mirrors_the_articulated_rig(self):
        renderer = ArticulatedPuppetRenderer()
        rig = self.rig_path("min_jun")
        right = renderer.render(rig, "walk_confident", 0.31, 0.4, facing="right")
        left = renderer.render(rig, "walk_confident", 0.31, 0.4, facing="left")
        self.assertEqual(right.size, left.size)
        self.assertEqual(left.tobytes(), right.transpose(0).tobytes())


if __name__ == "__main__":
    unittest.main()
