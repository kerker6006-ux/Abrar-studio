from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import json


class ModelError(ValueError):
    pass


def _float(value: Any, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ModelError(f"{name} must be a number") from exc
    if minimum is not None and result < minimum:
        raise ModelError(f"{name} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ModelError(f"{name} must be at most {maximum}")
    return result


@dataclass(slots=True)
class VoiceProfile:
    profile_id: str
    character_id: str
    voice_name: str
    normal_model: str
    emotional_model: str
    language: str = "ko-KR"
    version: str = "1.0"
    locked: bool = True
    audio_profile: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoiceProfile":
        required = {"profile_id", "character_id", "voice_name", "normal_model", "emotional_model"}
        missing = required - data.keys()
        if missing:
            raise ModelError(f"Voice profile missing: {', '.join(sorted(missing))}")
        return cls(**data)


@dataclass(slots=True)
class AnimationSequence:
    """A locked loop made from complete character drawings.

    Complete frames avoid the rubber-limb artifacts produced by rotating cutout
    body parts.  The low playback rate is intentional for limited animation.
    """

    frames: list[str]
    fps: float = 8.0
    loop: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnimationSequence":
        frames = [str(item) for item in data.get("frames", []) if str(item).strip()]
        if not frames:
            raise ModelError("Animation sequence requires at least one frame")
        return cls(
            frames=frames,
            fps=_float(data.get("fps", 8.0), "animation fps", 1.0, 24.0),
            loop=bool(data.get("loop", True)),
        )


@dataclass(slots=True)
class CharacterManifest:
    character_id: str
    display_name: str
    rig_version: str
    outfit_id: str
    palette_id: str
    reference_sheet: str
    portrait: str
    full_front: str
    expressions: dict[str, str]
    voice_profile: VoiceProfile
    mouths: dict[str, str] = field(default_factory=dict)
    poses: dict[str, str] = field(default_factory=dict)
    gestures: dict[str, str] = field(default_factory=dict)
    asset_checksums: dict[str, str] = field(default_factory=dict)
    identity_locked: bool = True
    rig_type: str = "locked_pose_rig_v3"
    articulated_rig: str = ""
    animations: dict[str, AnimationSequence] = field(default_factory=dict)
    visual_tier: str = "legacy"
    mouth_anchor: list[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterManifest":
        value = dict(data)
        value["voice_profile"] = VoiceProfile.from_dict(value["voice_profile"])
        value.setdefault("poses", {})
        value.setdefault("gestures", {})
        value["animations"] = {
            str(name): AnimationSequence.from_dict(sequence)
            for name, sequence in value.get("animations", {}).items()
        }
        anchor = value.get("mouth_anchor", [])
        if anchor and (not isinstance(anchor, list) or len(anchor) != 2):
            raise ModelError("mouth_anchor must contain normalized x and y")
        value["mouth_anchor"] = [float(item) for item in anchor]
        return cls(**value)


@dataclass(slots=True)
class ActorCue:
    character_id: str
    expression: str = "neutral"
    pose: str = "portrait"
    position: str = "right"
    scale: float = 1.0
    depth: int = 0
    acting: str = "idle"
    gaze: str = "camera"
    gesture: str = "none"
    mirror: bool = False
    speaking: bool = False
    opacity: float = 1.0
    motion: str = "auto"
    motion_speed: float = 1.0
    travel_x: float = 0.0
    ground_y: float = 0.95
    facing: str = "auto"
    cycle_offset: float = 0.0
    motion_intensity: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActorCue":
        if not data.get("character_id"):
            raise ModelError("Actor cue requires character_id")
        return cls(
            character_id=str(data["character_id"]),
            expression=str(data.get("expression", "neutral")),
            pose=str(data.get("pose", "portrait")),
            position=str(data.get("position", "right")),
            scale=_float(data.get("scale", 1.0), "actor scale", 0.35, 2.0),
            depth=int(data.get("depth", 0)),
            acting=str(data.get("acting", "idle")),
            gaze=str(data.get("gaze", "camera")),
            gesture=str(data.get("gesture", "none")),
            mirror=bool(data.get("mirror", False)),
            speaking=bool(data.get("speaking", False)),
            opacity=_float(data.get("opacity", 1.0), "actor opacity", 0.0, 1.0),
            motion=str(data.get("motion", "auto")),
            motion_speed=_float(data.get("motion_speed", 1.0), "motion_speed", 0.2, 3.0),
            travel_x=_float(data.get("travel_x", 0.0), "travel_x", -1.5, 1.5),
            ground_y=_float(data.get("ground_y", 0.95), "ground_y", 0.55, 1.05),
            facing=str(data.get("facing", "auto")),
            cycle_offset=_float(data.get("cycle_offset", 0.0), "cycle_offset", -2.0, 2.0),
            motion_intensity=_float(data.get("motion_intensity", 1.0), "motion_intensity", 0.25, 1.7),
        )


@dataclass(slots=True)
class SFXCue:
    cue: str
    at: float = 0.0
    volume: float = 1.0
    pan: float = 0.0

    @classmethod
    def from_value(cls, value: str | dict[str, Any]) -> "SFXCue":
        if isinstance(value, str):
            return cls(cue=value)
        if not isinstance(value, dict) or not value.get("cue"):
            raise ModelError("SFX cue must be a filename/name or an object with cue")
        return cls(
            cue=str(value["cue"]),
            at=_float(value.get("at", 0.0), "sfx at", 0.0),
            volume=_float(value.get("volume", 1.0), "sfx volume", 0.0, 3.0),
            pan=_float(value.get("pan", 0.0), "sfx pan", -1.0, 1.0),
        )


@dataclass(slots=True)
class Shot:
    id: str
    duration: float
    character_id: str | None = None
    expression: str = "neutral"
    dialogue: str = ""
    emotion: str = "neutral"
    emotion_level: int = 1
    camera: str = "static"
    sfx: list[SFXCue] = field(default_factory=list)
    music: str | None = None
    background: str | None = None
    subtitle: bool = True
    voice_model: str = "auto"
    voice_direction: str = ""
    position: str = "right"
    acting: str = "idle"
    gaze: str = "camera"
    vfx: list[str] = field(default_factory=list)
    transition: str = "cut"
    actors: list[ActorCue] = field(default_factory=list)
    music_volume: float = 1.0
    ambience: str | None = None
    ambience_volume: float = 1.0
    subtitle_style: str = "cinematic"
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Shot":
        if not data.get("id"):
            raise ModelError("Every shot requires an id")
        duration = _float(data.get("duration", 0), f"Shot {data.get('id')} duration", 0.08, 120.0)
        level = int(data.get("emotion_level", 1))
        if not 1 <= level <= 5:
            raise ModelError(f"Shot {data.get('id')} emotion_level must be 1-5")
        actors = [ActorCue.from_dict(x) for x in data.get("actors", [])]
        character_id = data.get("character_id")
        if character_id and not actors:
            actors = [ActorCue(
                character_id=str(character_id),
                expression=str(data.get("expression", "neutral")),
                pose="full_front" if any(x in str(data.get("camera", "")).lower() for x in ("full", "walk", "run")) else "portrait",
                position=str(data.get("position", "right")),
                acting=str(data.get("acting", "idle")),
                gaze=str(data.get("gaze", "camera")),
                speaking=bool(data.get("dialogue")),
                motion=str(data.get("motion", "auto")),
                motion_speed=_float(data.get("motion_speed", 1.0), "motion_speed", 0.2, 3.0),
                travel_x=_float(data.get("travel_x", 0.0), "travel_x", -1.5, 1.5),
                facing=str(data.get("facing", "auto")),
            )]
        if data.get("dialogue") and actors and not any(a.speaking for a in actors):
            speaker = str(character_id or actors[0].character_id)
            for actor in actors:
                actor.speaking = actor.character_id == speaker
        return cls(
            id=str(data["id"]), duration=duration,
            character_id=str(character_id) if character_id else None,
            expression=str(data.get("expression", "neutral")),
            dialogue=str(data.get("dialogue", "")), emotion=str(data.get("emotion", "neutral")),
            emotion_level=level, camera=str(data.get("camera", "static")),
            sfx=[SFXCue.from_value(x) for x in data.get("sfx", [])], music=data.get("music"),
            background=data.get("background"), subtitle=bool(data.get("subtitle", True)),
            voice_model=str(data.get("voice_model", "auto")), voice_direction=str(data.get("voice_direction", "")),
            position=str(data.get("position", "right")), acting=str(data.get("acting", "idle")),
            gaze=str(data.get("gaze", "camera")), vfx=[str(x) for x in data.get("vfx", [])],
            transition=str(data.get("transition", "cut")), actors=actors,
            music_volume=_float(data.get("music_volume", 1.0), "music_volume", 0.0, 2.0),
            ambience=data.get("ambience"),
            ambience_volume=_float(data.get("ambience_volume", 1.0), "ambience_volume", 0.0, 2.0),
            subtitle_style=str(data.get("subtitle_style", "cinematic")),
            notes=str(data.get("notes", "")),
        )

    @property
    def speaker_id(self) -> str | None:
        if self.character_id:
            return self.character_id
        for actor in self.actors:
            if actor.speaking:
                return actor.character_id
        return None


@dataclass(slots=True)
class Scene:
    id: str
    title: str
    shots: list[Shot]
    location: str = ""
    dramatic_goal: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scene":
        shots = [Shot.from_dict(x) for x in data.get("shots", [])]
        if not shots:
            raise ModelError(f"Scene {data.get('id', '?')} has no shots")
        return cls(
            id=str(data.get("id", "scene")), title=str(data.get("title", "Untitled scene")), shots=shots,
            location=str(data.get("location", "")), dramatic_goal=str(data.get("dramatic_goal", "")),
        )


@dataclass(slots=True)
class Episode:
    project_id: str
    episode_id: str
    title: str
    scenes: list[Scene]
    resolution: tuple[int, int] = (1280, 720)
    fps: int = 24
    version: str = "3.0"
    language: str = "ko-KR"
    content_rating: str = "teen"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        scenes = [Scene.from_dict(x) for x in data.get("scenes", [])]
        if not scenes:
            raise ModelError("Episode requires at least one scene")
        res = data.get("resolution", [1280, 720])
        if len(res) != 2:
            raise ModelError("resolution must contain width and height")
        width, height = int(res[0]), int(res[1])
        if width < 640 or height < 360:
            raise ModelError("resolution is too small")
        fps = int(data.get("fps", 24))
        if fps not in {12, 15, 24, 25, 30}:
            raise ModelError("fps must be 12, 15, 24, 25, or 30")
        return cls(
            project_id=str(data.get("project_id", "abrar_studio")),
            episode_id=str(data.get("episode_id", "E001")),
            title=str(data.get("title", "Untitled episode")), scenes=scenes,
            resolution=(width, height), fps=fps, version=str(data.get("version", "3.0")),
            language=str(data.get("language", "ko-KR")), content_rating=str(data.get("content_rating", "teen")),
        )

    @classmethod
    def load(cls, path: Path) -> "Episode":
        with path.open("r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resolution"] = list(self.resolution)
        return data

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    @property
    def duration(self) -> float:
        return sum(shot.duration for scene in self.scenes for shot in scene.shots)

    @property
    def shot_count(self) -> int:
        return sum(len(scene.shots) for scene in self.scenes)

    @property
    def character_ids(self) -> set[str]:
        result: set[str] = set()
        for scene in self.scenes:
            for shot in scene.shots:
                if shot.speaker_id:
                    result.add(shot.speaker_id)
                result.update(actor.character_id for actor in shot.actors)
        return result
