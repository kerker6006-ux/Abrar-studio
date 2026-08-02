from __future__ import annotations

import math
import shutil
import struct
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from abrar_studio.gemini_tts import GeminiTTSClient
from abrar_studio.models import Episode
from abrar_studio.project import StudioProject
from abrar_studio.renderer import AnimaticRenderer
from abrar_studio.validator import QualityValidator


def synthetic_voice(path: Path, seconds: float, character: str) -> None:
    rate = 24000
    path.parent.mkdir(parents=True, exist_ok=True)
    base = 188 if character == "seo_yeon" else 126
    frames = bytearray()
    for i in range(int(rate * seconds)):
        t = i / rate
        syllable = max(0.0, math.sin(math.pi * ((t * 4.0) % 1.0)))
        phrase = 0.72 + 0.28 * math.sin(2 * math.pi * 0.7 * t)
        amp = 0.18 * syllable * phrase
        value = int(32767 * amp * (math.sin(2 * math.pi * base * t) + .25 * math.sin(2 * math.pi * base * 2.01 * t)))
        frames += struct.pack("<h", max(-32767, min(32767, value)))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(frames)


def main() -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required")
    with tempfile.TemporaryDirectory(prefix="abrar-v3-motion-demo-") as td:
        project = StudioProject.create(Path(td) / "project")
        demo = Episode.load(ROOT / "templates" / "episodes" / "articulated_motion_showcase.json")
        demo.episode_id = "ABRAR_V3_MOTION_DEMO"
        demo.title = "Abrar Studio 3.0 Articulated Motion Demo"
        for scene in demo.scenes:
            for shot in scene.shots:
                speaker = shot.speaker_id
                if shot.dialogue and speaker:
                    char = project.character(speaker)
                    req = GeminiTTSClient.build_request(char, shot)
                    synthetic_voice(project.voice_cache_path(speaker, req.cache_key), max(.9, shot.duration - .25), speaker)
        report = QualityValidator(project, ffmpeg).validate(demo, require_voices=True)
        if not report.passed:
            raise RuntimeError([(r.gate, r.detail) for r in report.results if not r.passed])
        output = ROOT / "AbrarStudio_v3_Articulated_Motion_Demo_720p.mp4"
        AnimaticRenderer(project, ffmpeg, video_preset="veryfast", crf=17).render(demo, output)
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
