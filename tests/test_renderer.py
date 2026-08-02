from __future__ import annotations

import shutil
import subprocess
import unittest
import wave
from pathlib import Path

from abrar_studio.gemini_tts import GeminiTTSClient
from abrar_studio.models import Episode
from abrar_studio.renderer import AnimaticRenderer
from tests.common import make_project


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
class RendererTests(unittest.TestCase):
    def test_short_720p_render(self):
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        data = {
            "project_id": "abrar_studio", "episode_id": "TEST", "title": "test",
            "resolution": [1280, 720], "fps": 24,
            "scenes": [{"id": "s", "title": "test", "shots": [{
                "id": "sh", "duration": 0.6, "character_id": "seo_yeon",
                "expression": "shock", "dialogue": "왜?", "emotion": "shock",
                "emotion_level": 4, "camera": "push_in", "sfx": ["impact"], "music": "mystery"
            }]}]
        }
        episode = Episode.from_dict(data)
        shot = episode.scenes[0].shots[0]
        char = project.character("seo_yeon")
        req = GeminiTTSClient.build_request(char, shot)
        wav = project.voice_cache_path("seo_yeon", req.cache_key)
        wav.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(wav), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(24000); wf.writeframes(b"\0\0" * 4800)
        out = project.render_dir / "test.mp4"
        AnimaticRenderer(project, shutil.which("ffmpeg") or "ffmpeg").render(episode, out)
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 1000)
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            value = subprocess.check_output([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(out)], text=True).strip()
            self.assertEqual(value, "1280x720")
            frame_rate = subprocess.check_output([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "default=nw=1:nk=1", str(out)], text=True).strip()
            self.assertEqual(frame_rate, "24/1")
            audio_codec = subprocess.check_output([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(out)], text=True).strip()
            self.assertEqual(audio_codec, "aac")
            sample_rate = subprocess.check_output([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate", "-of", "default=nw=1:nk=1", str(out)], text=True).strip()
            self.assertEqual(sample_rate, "48000")
            duration = float(subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(out)], text=True).strip())
            self.assertGreater(duration, 0.5)
            self.assertLess(duration, 1.2)

    def test_complete_frame_walk_renders_at_720p(self):
        temp, project = make_project()
        self.addCleanup(temp.cleanup)
        episode = Episode.from_dict({
            "project_id": "abrar_studio", "episode_id": "WALK", "title": "walk",
            "resolution": [1280, 720], "fps": 24,
            "scenes": [{"id": "s", "title": "walk", "shots": [{
                "id": "walk", "duration": 0.8, "background": "school_hallway_webtoon",
                "camera": "pan_right", "music": "mystery",
                "actors": [{
                    "character_id": "min_jun", "pose": "full_side", "position": "left",
                    "acting": "walk", "motion": "walk", "travel_x": 0.18,
                    "ground_y": 0.96, "facing": "right"
                }]
            }]}]
        })
        out = project.render_dir / "walk.mp4"
        AnimaticRenderer(project, shutil.which("ffmpeg") or "ffmpeg").render(episode, out)
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
