from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from abrar_studio.alignment import alignment_at, build_alignment, load_alignment


class AlignmentTests(unittest.TestCase):
    def test_audio_derived_korean_alignment_is_cached(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wav_path = root / "line.wav"
            rate = 24000
            frames = bytearray()
            for index in range(rate * 2):
                t = index / rate
                if t < 0.25 or t > 1.75:
                    value = 0
                else:
                    value = int(5000 * math.sin(2 * math.pi * 180 * t))
                frames += struct.pack("<h", value)
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate); wf.writeframes(frames)
            output = root / "line.align.json"
            segments = build_alignment("아 우 이.", wav_path, output)
            self.assertTrue(output.exists())
            self.assertEqual(load_alignment(output), segments)
            self.assertEqual(segments[0].viseme, "closed")
            shapes = {segment.viseme for segment in segments}
            self.assertTrue({"wide", "round", "narrow"}.issubset(shapes))
            self.assertEqual(alignment_at(segments, 0.05, 0.8), "closed")


if __name__ == "__main__":
    unittest.main()
