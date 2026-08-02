from __future__ import annotations

import unittest
from pathlib import Path
from abrar_studio.models import Episode, ModelError
from abrar_studio.paths import app_root


class ModelTests(unittest.TestCase):
    def test_sample_episode_loads(self):
        episode = Episode.load(app_root() / "sample_project" / "episode_001.json")
        self.assertEqual(episode.resolution, (1280, 720))
        self.assertEqual(episode.fps, 24)
        self.assertEqual(episode.shot_count, 7)
        self.assertGreater(episode.duration, 15)

    def test_rejects_invalid_emotion_level(self):
        with self.assertRaises(ModelError):
            Episode.from_dict({
                "project_id": "x", "episode_id": "e", "title": "bad",
                "scenes": [{"id": "s", "title": "x", "shots": [{"id": "a", "duration": 1, "emotion_level": 8}]}]
            })


if __name__ == "__main__":
    unittest.main()
