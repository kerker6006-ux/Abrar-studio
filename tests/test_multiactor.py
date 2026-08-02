from __future__ import annotations

import unittest

from abrar_studio.models import Episode


class MultiActorTests(unittest.TestCase):
    def test_two_actor_shot_resolves_locked_speaker(self):
        episode = Episode.from_dict({
            "project_id": "x", "episode_id": "e", "title": "two actors",
            "scenes": [{"id": "s", "title": "scene", "shots": [{
                "id": "a", "duration": 2.0, "character_id": "seo_yeon", "dialogue": "왜요?",
                "emotion": "shock", "emotion_level": 4, "camera": "push_in",
                "actors": [
                    {"character_id": "min_jun", "position": "left", "speaking": False, "acting": "listen"},
                    {"character_id": "seo_yeon", "position": "right", "speaking": True, "expression": "shock"}
                ]
            }]}]
        })
        shot = episode.scenes[0].shots[0]
        self.assertEqual(shot.speaker_id, "seo_yeon")
        self.assertEqual(len(shot.actors), 2)
        self.assertEqual(episode.character_ids, {"seo_yeon", "min_jun"})

    def test_legacy_single_character_shot_gets_actor_cue(self):
        episode = Episode.from_dict({
            "project_id": "x", "episode_id": "e", "title": "legacy",
            "scenes": [{"id": "s", "title": "scene", "shots": [{
                "id": "a", "duration": 1.0, "character_id": "min_jun", "dialogue": "알겠어."
            }]}]
        })
        shot = episode.scenes[0].shots[0]
        self.assertEqual(len(shot.actors), 1)
        self.assertTrue(shot.actors[0].speaking)


if __name__ == "__main__":
    unittest.main()
