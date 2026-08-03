"""Validated manifests for the one-prompt drama production pipeline."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class ProductionPlanError(ValueError):
    pass


SUPPORTED_TTS_VOICES = frozenset({
    "Achernar", "Achird", "Algenib", "Algieba", "Alnilam", "Aoede", "Autonoe",
    "Callirrhoe", "Charon", "Despina", "Enceladus", "Erinome", "Fenrir", "Gacrux",
    "Iapetus", "Kore", "Laomedeia", "Leda", "Orus", "Puck", "Pulcherrima",
    "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar", "Sulafat", "Umbriel",
    "Vindemiatrix", "Zephyr", "Zubenelgenubi",
})


def normalized_voice(value: object, gender: str) -> str:
    """Return only a Gemini prebuilt voice name, never model-written prose."""
    requested = str(value or "").strip()
    if requested in SUPPORTED_TTS_VOICES:
        return requested
    gender_key = gender.casefold()
    if any(token in gender_key for token in ("female", "woman", "girl", "여", "여자")):
        return "Kore"
    if any(token in gender_key for token in ("male", "man", "boy", "남", "남자")):
        return "Orus"
    return "Kore"


def safe_id(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized[:40] or fallback


@dataclass(frozen=True, slots=True)
class CharacterPlan:
    id: str
    name: str
    role: str
    age: str
    gender: str
    appearance: str
    outfit: str
    voice: str = "Kore"

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int) -> "CharacterPlan":
        name = str(data.get("name") or f"Character {index + 1}").strip()
        gender = str(data.get("gender") or "unspecified").strip()
        return cls(
            id=safe_id(str(data.get("id") or name), f"character_{index + 1}"),
            name=name,
            role=str(data.get("role") or "supporting character").strip(),
            age=str(data.get("age") or "adult").strip(),
            gender=gender,
            appearance=str(data.get("appearance") or "distinct Korean drama character").strip(),
            outfit=str(data.get("outfit") or "story-appropriate modern outfit").strip(),
            voice=normalized_voice(data.get("voice"), gender),
        )


@dataclass(frozen=True, slots=True)
class ActorPlan:
    character_id: str
    position: str = "center"
    state: str = "neutral"
    motion: str = "idle"
    facing: str = "camera"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActorPlan":
        return cls(
            character_id=safe_id(str(data.get("character_id") or ""), "missing"),
            position=str(data.get("position") or "center").lower(),
            state=str(data.get("state") or "neutral").lower(),
            motion=str(data.get("motion") or "idle").lower(),
            facing=str(data.get("facing") or "camera").lower(),
        )


@dataclass(frozen=True, slots=True)
class ShotPlan:
    id: str
    duration: float
    location_id: str
    background_prompt: str
    camera: str
    speaker_id: str | None
    dialogue: str
    emotion: str
    actors: tuple[ActorPlan, ...]
    ambience_tags: tuple[str, ...] = ()
    sfx_tags: tuple[str, ...] = ()
    transition: str = "cut"

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int) -> "ShotPlan":
        actors = tuple(ActorPlan.from_dict(x) for x in data.get("actors", []) if isinstance(x, dict))
        speaker = str(data.get("speaker_id") or "").strip()
        duration = max(1.0, min(12.0, float(data.get("duration", 3.0))))
        return cls(
            id=safe_id(str(data.get("id") or f"shot_{index + 1}"), f"shot_{index + 1}"),
            duration=duration,
            location_id=safe_id(str(data.get("location_id") or "location"), "location"),
            background_prompt=str(data.get("background_prompt") or "Korean drama interior").strip(),
            camera=str(data.get("camera") or "medium").lower(),
            speaker_id=safe_id(speaker, "speaker") if speaker else None,
            dialogue=str(data.get("dialogue") or "").strip(),
            emotion=str(data.get("emotion") or "neutral").lower(),
            actors=actors,
            ambience_tags=tuple(str(x).lower() for x in data.get("ambience_tags", []) if str(x).strip()),
            sfx_tags=tuple(str(x).lower() for x in data.get("sfx_tags", []) if str(x).strip()),
            transition=str(data.get("transition") or "cut").lower(),
        )


@dataclass(frozen=True, slots=True)
class EpisodePlan:
    title: str
    synopsis: str
    characters: tuple[CharacterPlan, ...]
    shots: tuple[ShotPlan, ...]
    music_tags: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, raw: str) -> "EpisodePlan":
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ProductionPlanError(f"Gemini returned an invalid shot plan: {exc}") from exc
        characters = tuple(CharacterPlan.from_dict(x, i) for i, x in enumerate(data.get("characters", [])) if isinstance(x, dict))
        shots = tuple(ShotPlan.from_dict(x, i) for i, x in enumerate(data.get("shots", [])) if isinstance(x, dict))
        if not 1 <= len(characters) <= 3:
            raise ProductionPlanError("A production plan must contain one to three characters.")
        if not 2 <= len(shots) <= 12:
            raise ProductionPlanError("A production plan must contain two to twelve shots.")
        shot_ids = {shot.id for shot in shots}
        if len(shot_ids) != len(shots):
            raise ProductionPlanError("Shot IDs must be unique.")
        ids = {character.id for character in characters}
        if len(ids) != len(characters):
            raise ProductionPlanError("Character IDs must be unique.")
        for shot in shots:
            if not shot.actors:
                raise ProductionPlanError(f"{shot.id} must stage at least one character.")
            missing = {actor.character_id for actor in shot.actors} - ids
            if missing:
                raise ProductionPlanError(f"{shot.id} references unknown characters: {', '.join(sorted(missing))}")
            if shot.speaker_id and shot.speaker_id not in ids:
                raise ProductionPlanError(f"{shot.id} has an unknown speaker: {shot.speaker_id}")
        return cls(
            title=str(data.get("title") or "Abrar Drama").strip(),
            synopsis=str(data.get("synopsis") or "").strip(),
            characters=characters,
            shots=shots,
            music_tags=tuple(str(x).lower() for x in data.get("music_tags", []) if str(x).strip()),
        )

    @property
    def duration(self) -> float:
        return sum(shot.duration for shot in self.shots)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


@dataclass(slots=True)
class CharacterLock:
    character_id: str
    identity_prompt: str
    assets: dict[str, str] = field(default_factory=dict)
    checksums: dict[str, str] = field(default_factory=dict)

    def save(self, path: Path) -> Path:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "CharacterLock":
        return cls(**json.loads(path.read_text(encoding="utf-8")))
