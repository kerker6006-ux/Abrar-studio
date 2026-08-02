from __future__ import annotations

import shutil
import unittest
import wave
from abrar_studio.gemini_tts import GeminiTTSClient
from abrar_studio.validator import QualityValidator
from tests.common import make_project


class ValidatorTests(unittest.TestCase):
    def test_preflight_passes_sample(self):
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        episode = project.load_episode()
        report = QualityValidator(project, shutil.which("ffmpeg") or "ffmpeg").validate(episode, require_voices=False)
        self.assertTrue(report.passed, [(x.gate, x.detail) for x in report.results if not x.passed])


    def test_changed_character_voice_is_blocked(self):
        import json
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        manifest_path = project.character_manifest_path("seo_yeon")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["voice_profile"]["voice_name"] = "Kore"
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        episode = project.load_episode()
        report = QualityValidator(project, shutil.which("ffmpeg") or "ffmpeg").validate(episode, require_voices=False)
        voice_gate = next(item for item in report.results if item.gate == "Voice identity and cache")
        self.assertFalse(voice_gate.passed)
        self.assertIn("must remain Leda", voice_gate.detail)

    def test_walk_requires_complete_reference_frames(self):
        import json
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        manifest_path = project.character_manifest_path("min_jun")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["animations"] = {}
        data["visual_tier"] = "legacy"
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        report = QualityValidator(project, shutil.which("ffmpeg") or "ffmpeg").validate(project.load_episode(), require_voices=False)
        gate = next(item for item in report.results if item.gate == "Reference artwork and complete-frame motion")
        self.assertFalse(gate.passed)
        self.assertIn("complete-frame", gate.detail)

    def test_final_passes_with_valid_cached_wavs(self):
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        episode = project.load_episode()
        for scene in episode.scenes:
            for shot in scene.shots:
                speaker = shot.speaker_id
                if not shot.dialogue or not speaker:
                    continue
                char = project.character(speaker)
                request = GeminiTTSClient.build_request(char, shot)
                path = project.voice_cache_path(speaker, request.cache_key)
                path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(path), "wb") as wf:
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(b"\0\0" * 2400)
        report = QualityValidator(project, shutil.which("ffmpeg") or "ffmpeg").validate(episode, require_voices=True)
        self.assertTrue(report.passed, [(x.gate, x.detail) for x in report.results if not x.passed])


if __name__ == "__main__":
    unittest.main()
