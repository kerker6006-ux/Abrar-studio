"""Semantic local audio catalog and deterministic drama cue director."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".m4a", ".aac", ".flac"}


@dataclass(frozen=True, slots=True)
class AudioCue:
    role: str
    path: Path
    start_seconds: float
    gain_db: float
    tags: tuple[str, ...] = ()


SEMANTIC_WORDS = {
    "rain": ("rain", "storm", "thunder", "wet", "비", "폭풍", "천둥"),
    "phone": ("phone", "mobile", "ring", "vibrate", "notification", "전화", "휴대폰", "문자"),
    "door": ("door", "handle", "lock", "creak", "slam", "문", "잠금", "초인종"),
    "footstep": ("footstep", "footsteps", "shoe", "walk", "run", "걸어", "발걸음", "달려"),
    "impact": ("impact", "hit", "boom", "whoosh", "sting", "riser", "충격", "때려", "넘어"),
    "cloth": ("cloth", "clothing", "swish", "grab", "옷", "붙잡", "소매"),
    "crowd": ("crowd", "people", "gasp", "murmur", "손님", "사람들", "군중"),
    "store": ("store", "shop", "market", "cashier", "가게", "매장", "편의점"),
    "school": ("school", "classroom", "hallway", "학교", "교실", "복도"),
    "city": ("city", "traffic", "street", "urban", "도시", "거리", "자동차"),
    "roomtone": ("roomtone", "ambience", "hum", "interior", "실내", "방", "조용"),
    "tense": ("tense", "suspense", "horror", "dark", "drone", "pulse", "비밀", "무서", "긴장", "위험"),
    "sad": ("sad", "cry", "crying", "tears", "piano", "슬퍼", "울", "눈물", "이별"),
    "angry": ("angry", "anger", "argument", "fight", "화", "소리쳐", "싸움", "분노"),
    "warm": ("warm", "hope", "gentle", "romance", "따뜻", "희망", "사랑", "로맨스"),
    "mystery": ("mystery", "secret", "scanner", "unknown", "미스터리", "정체", "수상"),
    "chase": ("chase", "run", "escape", "panic", "추격", "도망", "달려"),
}

ROLE_TAGS = {
    "ambience": {"rain", "crowd", "store", "school", "city", "roomtone"},
    "music": {"tense", "sad", "angry", "warm", "mystery", "chase"},
    "event": {"phone", "door", "footstep", "impact", "cloth"},
}


def _tokens(path: Path) -> set[str]:
    text = " ".join([path.stem, *[p for p in path.parts[-4:-1]]]).lower()
    return {token for token in re.split(r"[^a-z0-9가-힣]+", text) if token}


class AudioDirector:
    """Index any-size licensed library and select cues by scene meaning.

    The installer library, optional CC0 packs, and the user's own Sonniss/audio
    folders all become one catalog. Selection is deterministic so regenerating
    a shot does not randomly change its sound design.
    """

    def __init__(self, library_root: Path | list[Path] | tuple[Path, ...]) -> None:
        roots = [library_root] if isinstance(library_root, Path) else list(library_root)
        unique: dict[str, Path] = {}
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                    unique[str(path.resolve()).lower()] = path.resolve()
        self.files = sorted(unique.values())
        self._file_tags = {path: self._tags_for_path(path) for path in self.files}

    @property
    def catalog_size(self) -> int:
        return len(self.files)

    def _tags_for_path(self, path: Path) -> set[str]:
        tokens = _tokens(path)
        text = " ".join(tokens)
        tags = {
            tag for tag, words in SEMANTIC_WORDS.items()
            if any(word.lower() in text for word in words if word.isascii())
        }
        parent = " ".join(part.lower() for part in path.parts[-5:-1])
        if "music" in parent or "jingle" in parent or "theme" in path.stem.lower():
            tags.add("music")
        if any(value in parent for value in ("sfx", "sound", "foley", "impact", "interface", "audio")):
            tags.add("sfx")
        return tags | tokens

    def semantic_tags(self, text: str) -> set[str]:
        normalized = text.lower()
        return {
            tag for tag, words in SEMANTIC_WORDS.items()
            if any(word.lower() in normalized for word in words)
        }

    def plan(
        self,
        script: str,
        duration: float,
        *,
        music_tags: tuple[str, ...] = (),
        ambience_tags: tuple[str, ...] = (),
        sfx_tags: tuple[str, ...] = (),
    ) -> list[AudioCue]:
        inferred = self.semantic_tags(script)
        cues: list[AudioCue] = []
        ambience_wanted = (inferred & ROLE_TAGS["ambience"]) | set(ambience_tags)
        music_wanted = (inferred & ROLE_TAGS["music"]) | set(music_tags)
        event_wanted = (inferred & ROLE_TAGS["event"]) | set(sfx_tags)
        ambience = self._pick(ambience_wanted, "ambience", script)
        if ambience:
            cues.append(AudioCue("ambience", ambience, 0.0, -22.0, tuple(sorted(ambience_wanted))))
        music = self._pick(music_wanted, "music", script + " music")
        if music:
            cues.append(AudioCue("music", music, 0.0, -27.0, tuple(sorted(music_wanted))))
        for index, tag in enumerate(sorted(event_wanted)):
            effect = self._pick({tag}, "event", script + tag)
            if effect:
                at = min(max(0.35, duration * (0.18 + (index % 5) * 0.16)), max(0.35, duration - 0.35))
                cues.append(AudioCue(tag, effect, at, -10.0, (tag,)))
        return cues

    def _pick(self, wanted: set[str], role: str, seed: str) -> Path | None:
        if not wanted:
            return None
        candidates: list[tuple[int, Path]] = []
        for path in self.files:
            tags = self._file_tags[path]
            score = len(wanted & tags) * 10
            if role == "music" and ("music" in tags or "music" in " ".join(path.parts).lower()):
                score += 5
            if role != "music" and "music" in tags:
                score -= 7
            if score > 0:
                candidates.append((score, path))
        if not candidates:
            return None
        best = max(score for score, _ in candidates)
        pool = sorted(path for score, path in candidates if score == best)
        number = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
        return pool[number % len(pool)]
