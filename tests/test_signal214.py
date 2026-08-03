from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from abrar_studio.signal214 import SAMPLE_KOREAN_SCRIPT, SignalScriptCompiler, SignalScriptError
from abrar_studio.signal214_renderer import Signal214Renderer, build_signal_tts_request


class Signal214Tests(unittest.TestCase):
    def test_korean_script_compiles_to_varied_vertical_episode(self):
        compiler = SignalScriptCompiler()
        episode = compiler.compile(SAMPLE_KOREAN_SCRIPT)
        report = compiler.quality(episode)
        self.assertTrue(report.passed, report.problems)
        self.assertEqual(episode.resolution, (1080, 1920))
        self.assertEqual(episode.language, "ko-KR")
        self.assertGreaterEqual(len(episode.beats), 6)
        self.assertGreaterEqual(len({beat.kind for beat in episode.beats}), 4)
        self.assertLessEqual(episode.duration, 60)

    def test_broken_or_short_scripts_are_rejected(self):
        compiler = SignalScriptCompiler()
        with self.assertRaises(SignalScriptError):
            compiler.compile("Ã¬Æ’Ë† broken")
        with self.assertRaises(SignalScriptError):
            compiler.compile("너무 짧은 이야기입니다.")

    def test_recent_near_duplicate_is_blocked(self):
        compiler = SignalScriptCompiler()
        episode = compiler.compile(SAMPLE_KOREAN_SCRIPT)
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "history.json"
            compiler.remember(episode, history)
            report = compiler.quality(episode, history)
            self.assertFalse(report.passed)
            self.assertTrue(any("비슷" in problem for problem in report.problems))

    def test_tts_request_is_korean_horror_directed(self):
        episode = SignalScriptCompiler().compile(SAMPLE_KOREAN_SCRIPT)
        request = build_signal_tts_request(episode, pro=True)
        self.assertIn(episode.script, request.prompt)
        self.assertIn("Korean", request.prompt)
        self.assertEqual(request.voice, "Gacrux")

    def test_contact_sheet_contains_every_beat(self):
        episode = SignalScriptCompiler().compile(SAMPLE_KOREAN_SCRIPT)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            backgrounds = root / "backgrounds"
            backgrounds.mkdir(parents=True)
            for name in {beat.background for beat in episode.beats}:
                Image.new("RGB", (540, 960), (20, 30, 35)).save(backgrounds / name)
            renderer = Signal214Renderer("ffmpeg", root)
            output = root / "sheet.jpg"
            renderer.contact_sheet(episode, output)
            self.assertTrue(output.exists())
            with Image.open(output) as image:
                self.assertGreater(image.width, 500)
                self.assertGreater(image.height, 500)


if __name__ == "__main__":
    unittest.main()
