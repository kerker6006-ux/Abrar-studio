from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from abrar_studio.audio_director import AudioDirector


class AudioDirectorTests(unittest.TestCase):
    def test_korean_scene_selects_meaningful_local_cues(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name in ("rain_ambience.wav", "tense_dark_music.wav", "phone_vibrate.wav", "door_creak.wav"):
                (root / name).write_bytes(b"audio")
            roles = {cue.role for cue in AudioDirector(root).plan("비 오는 밤 전화가 울리고 문이 열린다", 10)}
        self.assertTrue({"ambience", "music", "phone", "door"}.issubset(roles))
