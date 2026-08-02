from __future__ import annotations

import unittest

from abrar_studio.acting import acting_pose
from abrar_studio.models import Shot


class ActingTests(unittest.TestCase):
    def test_breakdown_has_tremor_and_drop(self):
        shot = Shot(id="x", duration=2, emotion="breakdown", emotion_level=5, acting="breakdown")
        pose = acting_pose(shot, 0.7, 0.7)
        self.assertGreater(pose.dy, 4)
        self.assertNotEqual(pose.rotation, 0)

    def test_run_is_more_dynamic_than_idle(self):
        idle = Shot(id="i", duration=2, acting="idle")
        run = Shot(id="r", duration=2, acting="run")
        p_idle = acting_pose(idle, 0.4, 0.4)
        p_run = acting_pose(run, 0.4, 0.4)
        self.assertGreater(abs(p_run.dy), abs(p_idle.dy))
