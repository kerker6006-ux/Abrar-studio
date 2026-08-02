from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from abrar_studio.gemini_tts import GeminiTTSClient, TTSGenerationError, TTSRequest, _extract_audio_base64, _score_wav
from abrar_studio.constants import GEMINI_FLASH_TTS, GEMINI_PRO_TTS
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
        self.assertEqual(nr.model, "gemini-3.1-flash-tts-preview")
        self.assertEqual(er.model, "gemini-2.5-pro-preview-tts")
        self.assertEqual(nr.model, GEMINI_FLASH_TTS)
        self.assertEqual(er.model, GEMINI_PRO_TTS)
        self.assertNotEqual(nr.cache_key, er.cache_key)
        self.assertIn("Synthesize speech audio only", er.prompt)
        self.assertIn("natural contemporary Korean", er.prompt)

    def test_audio_response_parser(self):
        encoded = base64.b64encode(b"pcm").decode("ascii")
        self.assertEqual(_extract_audio_base64({"output_audio": {"data": encoded}}), encoded)

    def test_audio_response_parser_supports_steps_schema(self):
        encoded = base64.b64encode(b"new-schema-pcm").decode("ascii")
        response = {
            "steps": [
                {
                    "type": "model_output",
                    "content": [
                        {"type": "audio", "data": encoded, "mime_type": "audio/l16"},
                    ],
                },
            ],
        }
        self.assertEqual(_extract_audio_base64(response), encoded)

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

    def test_all_take_failures_keep_the_provider_reason(self):
        request = TTSRequest(model="test-model", voice="Leda", prompt="test", cache_key="test")
        with tempfile.TemporaryDirectory() as td:
            client = GeminiTTSClient("test-key")
            with patch.object(client, "generate", side_effect=TTSGenerationError("HTTP 429: quota exhausted")), patch("abrar_studio.gemini_tts.time.sleep"):
                with self.assertRaisesRegex(TTSGenerationError, "HTTP 429: quota exhausted"):
                    client.generate_best(request, Path(td) / "voice.wav", takes=2)


if __name__ == "__main__":
    unittest.main()
