"""Scene-aware selection of locally licensed music and sound effects.

Raw third-party audio is never downloaded or redistributed by the app. Users
place CC0 or personally licensed packs (such as Sonniss) in AudioLibrary; this
module indexes only filenames and builds a deterministic cue plan.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudioCue:
    role: str
    path: Path
    start_seconds: float
    gain_db: float


KEYWORDS = {
    "rain": ("rain", "storm", "thunder", "wet"),
    "phone": ("phone", "mobile", "ring", "vibrate", "notification"),
    "door": ("door", "handle", "lock", "creak", "slam"),
    "footstep": ("footstep", "footsteps", "shoe", "walk", "run"),
    "impact": ("impact", "hit", "boom", "whoosh", "sting", "riser"),
    "tense": ("tense", "suspense", "horror", "dark", "drone", "pulse"),
    "warm": ("warm", "piano", "hope", "gentle", "romance"),
    "city": ("city", "traffic", "street", "urban", "roomtone", "ambience"),
}


class AudioDirector:
    def __init__(self, library_root: Path) -> None:
        self.library_root = library_root
        self.files = sorted(
            path for path in library_root.rglob("*")
            if path.suffix.lower() in {".wav", ".mp3", ".ogg", ".m4a", ".aac"}
        ) if library_root.exists() else []

    def plan(self, script: str, duration: float) -> list[AudioCue]:
        """Choose a restrained mix: ambience, music, then only meaningful Foley."""
        normalized = script.lower()
        tags = {tag for tag, words in KEYWORDS.items() if any(word in normalized for word in words)}
        # Korean words keep the out-of-box planner useful before a pack has tags.
        if any(word in script for word in ("비", "폭풍", "천둥")):
            tags.update({"rain", "tense"})
        if any(word in script for word in ("전화", "휴대폰", "문자")): tags.add("phone")
        if any(word in script for word in ("문", "잠금")): tags.add("door")
        if any(word in script for word in ("걸어", "발걸음", "달려")): tags.add("footstep")
        if any(word in script for word in ("충격", "비밀", "사라", "무서")): tags.add("tense")
        cues: list[AudioCue] = []
        ambience = self._pick(tags & {"rain", "city"}, script)
        if ambience:
            cues.append(AudioCue("ambience", ambience, 0.0, -22.0))
        music = self._pick(tags & {"tense", "warm"}, script + "music")
        if music:
            cues.append(AudioCue("music", music, 0.0, -27.0))
        for index, tag in enumerate(("phone", "door", "footstep", "impact")):
            if tag in tags:
                effect = self._pick({tag}, script + tag)
                if effect:
                    cues.append(AudioCue(tag, effect, min(max(0.7, duration * (0.28 + index * 0.14)), max(0.7, duration - 0.8)), -11.0))
        return cues

    def _pick(self, tags: set[str], seed: str) -> Path | None:
        candidates = [path for path in self.files if any(word in path.name.lower() for tag in tags for word in KEYWORDS[tag])]
        if not candidates:
            return None
        number = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
        return candidates[number % len(candidates)]
