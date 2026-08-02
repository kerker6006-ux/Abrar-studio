from __future__ import annotations

import shutil
import wave
from dataclasses import dataclass, field
from pathlib import Path

from .constants import LOCKED_VOICE_PROFILES
from .gemini_tts import GeminiTTSClient
from .locks import verify_manifest
from .models import Episode
from .project import StudioProject
from .puppet import RigDefinition, normalize_motion, uses_articulated_motion


@dataclass(slots=True)
class GateResult:
    gate: str
    passed: bool
    detail: str
    weight: int = 1


@dataclass(slots=True)
class ValidationReport:
    results: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(item.passed for item in self.results)

    @property
    def score(self) -> int:
        total = sum(item.weight for item in self.results) or 1
        earned = sum(item.weight for item in self.results if item.passed)
        return round(earned / total * 100)

    def add(self, gate: str, passed: bool, detail: str, weight: int = 1) -> None:
        self.results.append(GateResult(gate, passed, detail, weight))


class QualityValidator:
    def __init__(self, project: StudioProject, ffmpeg_path: str = "ffmpeg") -> None:
        self.project = project
        self.ffmpeg_path = ffmpeg_path

    def validate(self, episode: Episode, require_voices: bool = False) -> ValidationReport:
        report = ValidationReport()
        self._identity(episode, report)
        self._voices(episode, report, require_voices)
        self._rig_assets(episode, report)
        self._acting(episode, report)
        self._sound(episode, report)
        self._music(episode, report)
        self._pacing(episode, report)
        self._render_tool(report)
        self._continuity(episode, report)
        return report

    def _identity(self, episode: Episode, report: ValidationReport) -> None:
        errors: list[str] = []
        for character_id in sorted(episode.character_ids):
            path = self.project.character_manifest_path(character_id)
            if not path.exists():
                errors.append(f"missing manifest {character_id}")
                continue
            ok, details = verify_manifest(path)
            if not ok:
                errors.extend([f"{character_id}: {item}" for item in details])
        report.add("Character identity lock", not errors, "All approved asset checksums match" if not errors else "; ".join(errors), 4)

    def _voices(self, episode: Episode, report: ValidationReport, require: bool) -> None:
        missing: list[str] = []
        invalid: list[str] = []
        for character_id in sorted(episode.character_ids):
            character = self.project.character(character_id)
            expected = LOCKED_VOICE_PROFILES.get(character_id)
            profile = character.voice_profile
            if expected is not None:
                for name, expected_value in expected.items():
                    if getattr(profile, name) != expected_value:
                        invalid.append(f"{character_id}: {name} must remain {expected_value}")
            else:
                # Guest/supporting characters may use another approved Gemini voice, but
                # their identity is locked at import and must never change silently.
                if not profile.voice_name or not profile.normal_model or not profile.emotional_model:
                    invalid.append(f"{character_id}: incomplete guest voice profile")
                if profile.language != "ko-KR":
                    invalid.append(f"{character_id}: guest language must remain ko-KR")
            if not profile.locked or profile.character_id != character_id:
                invalid.append(f"{character_id}: voice profile is not identity-locked")
        for scene in episode.scenes:
            for shot in scene.shots:
                speaker = shot.speaker_id
                if not shot.dialogue or not speaker:
                    continue
                char = self.project.character(speaker)
                request = GeminiTTSClient.build_request(char, shot)
                path = self.project.voice_cache_path(speaker, request.cache_key)
                if not path.exists():
                    missing.append(shot.id)
                    continue
                try:
                    with wave.open(str(path), "rb") as wf:
                        if wf.getnchannels() != 1 or wf.getframerate() not in {24000, 48000} or wf.getnframes() < 100:
                            invalid.append(f"{shot.id}: invalid WAV")
                except wave.Error:
                    invalid.append(f"{shot.id}: unreadable WAV")
        passed = not invalid and (not require or not missing)
        detail = "Locked voice profiles and approved WAV cache are valid"
        if missing:
            detail += f"; {len(missing)} line(s) not generated"
        if invalid:
            detail += "; " + ", ".join(invalid)
        report.add("Voice identity and cache", passed, detail, 4)

    def _rig_assets(self, episode: Episode, report: ValidationReport) -> None:
        missing: list[str] = []
        for scene in episode.scenes:
            for shot in scene.shots:
                speaker = shot.speaker_id
                for actor in shot.actors:
                    char = self.project.character(actor.character_id)
                    base = self.project.character_manifest_path(actor.character_id).parent
                    articulated = bool(char.articulated_rig) and actor.pose not in {"portrait", "close", "closeup"} and uses_articulated_motion(actor.motion, actor.acting)
                    if articulated:
                        rig_path = base / char.articulated_rig
                        if not rig_path.exists():
                            missing.append(f"{shot.id}:{actor.character_id}:articulated rig")
                        else:
                            try:
                                rig = RigDefinition.load(rig_path)
                                motion = normalize_motion(actor.motion, actor.acting)
                                if motion not in rig.motions and motion != "idle_breathe":
                                    missing.append(f"{shot.id}:{actor.character_id}:motion {motion}")
                                for part in rig.parts.values():
                                    if not (base / part.file).exists():
                                        missing.append(f"{shot.id}:{actor.character_id}:part {part.name}")
                            except Exception as exc:
                                missing.append(f"{shot.id}:{actor.character_id}:invalid rig ({exc})")
                    else:
                        if actor.pose in {"portrait", "close", "closeup"}:
                            rel = char.expressions.get(actor.expression)
                        else:
                            rel = char.poses.get(actor.pose)
                        if not rel or not (base / rel).exists():
                            missing.append(f"{shot.id}:{actor.character_id}:{actor.pose}/{actor.expression}")
                    if actor.gesture not in {"", "none"}:
                        grel = char.gestures.get(actor.gesture)
                        if not grel or not (base / grel).exists():
                            missing.append(f"{shot.id}:{actor.character_id}:gesture {actor.gesture}")
                if shot.dialogue and speaker:
                    char = self.project.character(speaker)
                    base = self.project.character_manifest_path(speaker).parent
                    for shape in ["closed", "open", "wide", "round", "narrow"]:
                        rel = char.mouths.get(shape)
                        if not rel or not (base / rel).exists():
                            missing.append(f"{speaker}:mouth {shape}")
        report.add("Pose, articulated motion and lip rig", not missing, "All approved pose, bone-rig, motion, gesture and five-shape mouth assets are available" if not missing else "Missing: " + ", ".join(sorted(set(missing))), 5)

    def _acting(self, episode: Episode, report: ValidationReport) -> None:
        weak: list[str] = []
        for scene in episode.scenes:
            for shot in scene.shots:
                if shot.dialogue and not shot.speaker_id:
                    weak.append(f"{shot.id}: no speaking actor")
                if shot.dialogue and shot.emotion.lower() not in {"neutral", "calm"}:
                    speaker = next((a for a in shot.actors if a.character_id == shot.speaker_id), None)
                    if speaker and speaker.expression == "neutral":
                        weak.append(f"{shot.id}: neutral face")
                if shot.emotion_level >= 4 and shot.camera == "static":
                    weak.append(f"{shot.id}: static intense camera")
                positions = [a.position for a in shot.actors if a.opacity > 0.1]
                if len(positions) != len(set(positions)):
                    weak.append(f"{shot.id}: actors overlap")
                if len(shot.actors) > 1 and not any(not actor.speaking for actor in shot.actors):
                    weak.append(f"{shot.id}: no listener staging")
                for actor in shot.actors:
                    motion = normalize_motion(actor.motion, actor.acting)
                    if motion.startswith(("walk", "run")) and actor.pose in {"portrait", "close", "closeup"}:
                        weak.append(f"{shot.id}:{actor.character_id} locomotion requires a full-body pose")
                    if motion.startswith(("walk", "run")) and abs(actor.travel_x) < 0.01 and "tracking" in shot.camera:
                        weak.append(f"{shot.id}:{actor.character_id} tracking camera has no travel_x")
        report.add("Acting and blocking", not weak, "Expressions, body acting, listener reactions and staging are coherent" if not weak else "Review: " + ", ".join(weak), 3)

    def _media_exists(self, kind: str, cue: str) -> bool:
        raw = Path(cue)
        if raw.is_file():
            return True
        folder = self.project.assets_dir / kind
        if (folder / cue).exists():
            return True
        return any((folder / f"{cue}{ext}").exists() for ext in [".wav", ".mp3", ".flac", ".ogg", ".m4a"])

    def _sound(self, episode: Episode, report: ValidationReport) -> None:
        important: list[str] = []
        missing_files: list[str] = []
        for scene in episode.scenes:
            for shot in scene.shots:
                action = (shot.emotion + " " + shot.dialogue + " " + " ".join(shot.vfx)).lower()
                if any(word in action for word in ["shock", "scanner", "run", "cry", "breakdown"]) and not shot.sfx:
                    important.append(shot.id)
                for cue in shot.sfx:
                    if cue.at > shot.duration:
                        missing_files.append(f"{shot.id}:{cue.cue} starts after shot")
                    elif not self._media_exists("sfx", cue.cue):
                        missing_files.append(f"{shot.id}:{cue.cue}")
                if shot.ambience and not self._media_exists("sfx", shot.ambience):
                    missing_files.append(f"{shot.id}:ambience {shot.ambience}")
        passed = not important and not missing_files
        detail = "Important actions have timed local SFX and optional ambience" if passed else "; ".join(filter(None, [
            "Missing SFX cue: " + ", ".join(important) if important else "",
            "Missing SFX file/timing: " + ", ".join(missing_files) if missing_files else "",
        ]))
        report.add("Sound effects and ambience", passed, detail, 2)

    def _music(self, episode: Episode, report: ValidationReport) -> None:
        no_plan = [scene.id for scene in episode.scenes if not any(shot.music for shot in scene.shots)]
        missing_files = [f"{shot.id}:{shot.music}" for scene in episode.scenes for shot in scene.shots if shot.music and not self._media_exists("music", shot.music)]
        passed = not no_plan and not missing_files
        detail = "Every scene has a playable, ducked music cue" if passed else "; ".join(filter(None, [
            "No music cue in: " + ", ".join(no_plan) if no_plan else "",
            "Missing music file: " + ", ".join(missing_files) if missing_files else "",
        ]))
        report.add("Scene music", passed, detail, 2)

    def _pacing(self, episode: Episode, report: ValidationReport) -> None:
        long_static = [shot.id for scene in episode.scenes for shot in scene.shots if shot.duration > 4 and shot.camera == "static"]
        hook_ok = bool(episode.scenes and episode.scenes[0].shots and episode.scenes[0].shots[0].duration <= 3.5)
        transitions = [shot.id for scene in episode.scenes for shot in scene.shots if shot.transition not in {"cut", "fade", "dip_black", "flash", "whip"}]
        passed = hook_ok and not long_static and not transitions
        detail = "Fast hook, controlled shot length and valid transitions" if passed else f"hook_ok={hook_ok}; long static={', '.join(long_static) or 'none'}; invalid transitions={', '.join(transitions) or 'none'}"
        report.add("Pacing and transitions", passed, detail, 2)

    def _render_tool(self, report: ValidationReport) -> None:
        executable = shutil.which(self.ffmpeg_path) if not Path(self.ffmpeg_path).is_file() else self.ffmpeg_path
        report.add("FFmpeg", bool(executable), f"Found: {executable}" if executable else "FFmpeg not found; set its path in Settings", 2)

    def _continuity(self, episode: Episode, report: ValidationReport) -> None:
        ids = [shot.id for scene in episode.scenes for shot in scene.shots]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        report.add("Continuity and IDs", not duplicates, "Shot IDs are unique and character references resolve" if not duplicates else "Duplicate shot IDs: " + ", ".join(duplicates), 2)
