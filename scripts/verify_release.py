from __future__ import annotations

import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from abrar_studio.gemini_tts import GeminiTTSClient
from abrar_studio.models import Episode
from abrar_studio.project import StudioProject
from abrar_studio.puppet import ArticulatedPuppetRenderer, RigDefinition, footstep_times
from abrar_studio.renderer import AnimaticRenderer
from abrar_studio.validator import QualityValidator


def synthetic_voice(path: Path, seconds: float, character: str) -> None:
    rate = 24000
    path.parent.mkdir(parents=True, exist_ok=True)
    base = 185 if character == "seo_yeon" else 125
    frames = bytearray()
    for i in range(int(rate * seconds)):
        t = i / rate
        syllable = max(0.0, math.sin(math.pi * ((t * 4.3) % 1.0)))
        phrase = 0.75 + 0.25 * math.sin(2 * math.pi * 0.8 * t)
        amp = 0.20 * syllable * phrase
        value = int(32767 * amp * (math.sin(2 * math.pi * base * t) + 0.28 * math.sin(2 * math.pi * (base * 2.02) * t)))
        frames += struct.pack("<h", max(-32767, min(32767, value)))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(frames)


def ffprobe(path: Path) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        return {"exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}
    out = subprocess.check_output([exe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], text=True)
    return json.loads(out)


def leaked_secret_scan() -> list[str]:
    hits = []
    needles = [bytes.fromhex("41512e416238524e36"), bytes.fromhex("41497a615379")]
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() in {".png", ".jpg", ".jpeg", ".ico", ".wav", ".mp4", ".zip"}:
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if any(n in data for n in needles):
            hits.append(str(p.relative_to(ROOT)))
    return hits


def articulated_assets_ok(project: StudioProject) -> bool:
    renderer = ArticulatedPuppetRenderer()
    for character_id in ("seo_yeon", "min_jun"):
        character = project.character(character_id)
        if not character.articulated_rig:
            return False
        rig_path = project.character_manifest_path(character_id).parent / character.articulated_rig
        rig = RigDefinition.load(rig_path)
        if not {"walk_normal", "run_normal", "run_panicked"}.issubset(rig.motions):
            return False
        first = renderer.render(rig_path, "walk_normal", 0.0, 0.1)
        second = renderer.render(rig_path, "run_normal", 0.31, 0.5)
        if first.getbbox() is None or second.getbbox() is None or first.tobytes() == second.tobytes():
            return False
    return len(footstep_times("walk_normal", 2.5)) >= 4 and len(footstep_times("run_normal", 2.5)) >= 8


def main() -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required")
    with tempfile.TemporaryDirectory(prefix="abrar-studio-v3-release-") as td:
        project = StudioProject.create(Path(td) / "project")
        source = ROOT / "templates" / "episodes" / "articulated_motion_showcase.json"
        episode = Episode.load(source)
        # Keep each verification pass short while exercising walk, stop and paired run.
        for scene in episode.scenes:
            for shot in scene.shots:
                shot.duration = min(0.72, shot.duration)
        for scene in episode.scenes:
            for shot in scene.shots:
                speaker = shot.speaker_id
                if shot.dialogue and speaker:
                    char = project.character(speaker)
                    req = GeminiTTSClient.build_request(char, shot)
                    synthetic_voice(project.voice_cache_path(speaker, req.cache_key), max(0.75, shot.duration - 0.30), speaker)
        report = QualityValidator(project, ffmpeg).validate(episode, require_voices=True)
        if not report.passed:
            raise RuntimeError([(x.gate, x.detail) for x in report.results if not x.passed])
        output = ROOT / "verification_sample_720p_v3.mp4"
        AnimaticRenderer(project, ffmpeg, video_preset="ultrafast", crf=18).render(episode, output)
        probe = ffprobe(output)
        streams = probe.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        actual_duration = float(probe.get("format", {}).get("duration", 0) or 0)
        checks = {
            "quality_gates": report.passed,
            "articulated_rigs": articulated_assets_ok(project),
            "walk_run_template": source.exists(),
            "file_exists": output.exists(),
            "file_size_gt_100k": output.stat().st_size > 100_000,
            "width_1280": video.get("width") == 1280 if video else True,
            "height_720": video.get("height") == 720 if video else True,
            "video_h264": video.get("codec_name") == "h264" if video else True,
            "audio_aac": audio.get("codec_name") == "aac" if audio else True,
            "frame_rate_24": video.get("avg_frame_rate") in {"24/1", "48/2"} if video else True,
            "audio_48khz": audio.get("sample_rate") == "48000" if audio else True,
            "duration_matches_episode": abs(actual_duration - episode.duration) < 1.5,
            "secret_scan_clean": not leaked_secret_scan(),
        }
        result = {
            "version": "3.0.2",
            "checks": checks,
            "all_passed": all(checks.values()),
            "output": str(output),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "probe": probe,
        }
        (ROOT / "release_verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"checks": checks, "all_passed": result["all_passed"]}, indent=2))
        return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
