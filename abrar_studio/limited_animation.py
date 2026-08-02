from __future__ import annotations

from pathlib import Path

from PIL import Image

from .models import AnimationSequence, CharacterManifest
from .puppet import normalize_motion


LOCOMOTION_NAMES = {"walk", "walk_normal", "walk_slow", "run", "run_urgent"}


def sequence_name(manifest: CharacterManifest, motion: str, acting: str) -> str | None:
    """Return the best complete-frame sequence for an actor cue."""
    normalized = normalize_motion(motion, acting)
    candidates = [normalized]
    if normalized.startswith("walk"):
        candidates += ["walk", "walk_normal"]
    elif normalized.startswith("run"):
        candidates += ["run", "run_urgent", "walk"]
    elif normalized in {"idle", "idle_breathe"}:
        candidates += ["idle", "idle_breathe"]
    for candidate in candidates:
        if candidate in manifest.animations:
            return candidate
    return None


def frame_path(root: Path, sequence: AnimationSequence, t: float, speed: float = 1.0, offset: float = 0.0) -> Path:
    elapsed = max(0.0, t * max(0.01, speed) + offset)
    index = int(elapsed * sequence.fps)
    if sequence.loop:
        index %= len(sequence.frames)
    else:
        index = min(index, len(sequence.frames) - 1)
    return root / sequence.frames[index]


def inspect_sequence(root: Path, sequence: AnimationSequence) -> list[str]:
    """Check the properties that make a complete-frame loop render safely."""
    errors: list[str] = []
    dimensions: set[tuple[int, int]] = set()
    for rel in sequence.frames:
        path = root / rel
        if not path.exists():
            errors.append(f"missing {rel}")
            continue
        try:
            with Image.open(path) as image:
                dimensions.add(image.size)
                if image.mode not in {"RGBA", "LA", "P"}:
                    errors.append(f"{rel} has no transparency")
                if image.width < 384 or image.height < 720:
                    errors.append(f"{rel} is {image.width}x{image.height}; minimum is 384x720")
                alpha = image.convert("RGBA").getchannel("A")
                if alpha.getbbox() is None:
                    errors.append(f"{rel} is empty")
        except OSError:
            errors.append(f"unreadable {rel}")
    if len(dimensions) > 1:
        errors.append("frames do not share one canvas size")
    return errors
