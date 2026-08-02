from __future__ import annotations

import base64
import unittest
from abrar_studio.gemini_tts import GeminiTTSClient, _extract_audio_base64, _score_wav
from abrar_studio.models import Shot
from tests.common import make_project


class TTSTests(unittest.TestCase):
    def test_locked_voice_and_model_selection(self):
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        char = project.character("seo_yeon")
        neutral = Shot(id="n", duration=2, character_id="seo_yeon", dialogue="안녕하세요", emotion="neutral")
        emotional = Shot(id="e", duration=2, character_id="seo_yeon", dialogue="왜 그랬어?", emotion="crying", emotion_level=5)
        nr = GeminiTTSClient.build_request(char, neutral)
        er = GeminiTTSClient.build_request(char, emotional)
        self.assertEqual(nr.voice, "Leda")
        self.assertEqual(er.voice, "Leda")
        self.assertIn("flash", nr.model)
        self.assertIn("pro", er.model)
        self.assertNotEqual(nr.cache_key, er.cache_key)
        self.assertIn("natural contemporary Korean", er.prompt)

    def test_audio_response_parser(self):
        encoded = base64.b64encode(b"pcm").decode("ascii")
        self.assertEqual(_extract_audio_base64({"output_audio": {"data": encoded}}), encoded)

    def test_wav_quality_scoring_rejects_silence(self):
        import tempfile, wave, math, struct
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            silent = Path(td) / "silent.wav"
            voice = Path(td) / "voice.wav"
            with wave.open(str(silent), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(b"\0\0" * 24000)
            frames = b"".join(struct.pack("<h", int(7000 * math.sin(2*math.pi*180*i/24000))) for i in range(24000))
            with wave.open(str(voice), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(frames)
            self.assertGreater(_score_wav(voice)["score"], _score_wav(silent)["score"])


if __name__ == "__main__":
    unittest.main()
