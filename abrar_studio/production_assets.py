"""Cloud artwork generation and immutable per-episode character locks."""
from __future__ import annotations

import hashlib
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

from .production_models import CharacterLock, CharacterPlan, EpisodePlan
from .vertex_cloud import VertexStudioClient


class AssetConsistencyError(RuntimeError):
    pass


EXTRACTION_VERSION = "3"


ACTING_STATES = {
    "neutral": "calm neutral expression, mouth naturally closed, relaxed arms",
    "talk_small": "speaking softly, natural slightly open mouth, relaxed body",
    "talk_wide": "speaking forcefully, naturally open mouth, expressive face",
    "angry_closed": "angry dramatic expression, tense shoulders, original lips firmly closed between words",
    "angry_talk": "angry dramatic expression, tense shoulders, original mouth naturally open while shouting",
    "crying_closed": "crying naturally with visible tears, trembling sad expression, original lips closed",
    "crying_talk": "crying naturally with visible tears, trembling sad expression, original mouth slightly open while speaking",
    "point": "pointing firmly with one hand toward another person",
    "wave": "raising one hand in a natural restrained wave",
    "show": "open palm naturally showing an object or direction",
    "bend": "bending forward naturally from the waist with balanced posture",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_green_screen(source: Path, output: Path) -> Path:
    """Remove only edge-connected chroma/white backdrop pixels.

    Gemini often returns a lime gradient plus white side gutters even when pure
    green is requested. Connectivity preserves white eyes, teeth, shoes and
    highlights inside the outlined character while removing those same colors
    when they belong to the outside backdrop.
    """
    image = Image.open(source).convert("RGBA")
    pixels = image.load()
    width, height = image.size
    total = width * height
    outside = bytearray(total)
    queue: deque[tuple[int, int]] = deque()

    def candidate(x: int, y: int) -> bool:
        red, green, blue, _alpha = pixels[x, y]
        near_white = min(red, green, blue) >= 232 and max(red, green, blue) - min(red, green, blue) <= 22
        chroma = green >= 88 and green - max(red, blue) >= 18
        return near_white or chroma

    for x in range(width):
        if candidate(x, 0): queue.append((x, 0))
        if candidate(x, height - 1): queue.append((x, height - 1))
    for y in range(height):
        if candidate(0, y): queue.append((0, y))
        if candidate(width - 1, y): queue.append((width - 1, y))
    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if outside[index] or not candidate(x, y):
            continue
        outside[index] = 255
        if x: queue.append((x - 1, y))
        if x + 1 < width: queue.append((x + 1, y))
        if y: queue.append((x, y - 1))
        if y + 1 < height: queue.append((x, y + 1))
        # Diagonal connectivity reaches narrow background channels between
        # legs, fingers and bent arms that four-way flood fill can trap.
        if x and y: queue.append((x - 1, y - 1))
        if x + 1 < width and y: queue.append((x + 1, y - 1))
        if x and y + 1 < height: queue.append((x - 1, y + 1))
        if x + 1 < width and y + 1 < height: queue.append((x + 1, y + 1))
    # Remove enclosed lime regions (for example the background trapped between
    # two legs). Match them to colors already proven to be connected backdrop;
    # this is safer than deleting every green pixel in a possible green outfit.
    backdrop_palette = {
        (pixels[index % width, index // width][0] // 16,
         pixels[index % width, index // width][1] // 16,
         pixels[index % width, index // width][2] // 16)
        for index, value in enumerate(outside) if value
    }
    expanded_backdrop_palette = {
        (bucket[0] + dr, bucket[1] + dg, bucket[2] + db)
        for bucket in backdrop_palette
        for dr in (-1, 0, 1) for dg in (-1, 0, 1) for db in (-1, 0, 1)
    }
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if outside[index]:
                continue
            red, green, blue, _alpha = pixels[x, y]
            if green < 110 or green - max(red, blue) < 20:
                continue
            bucket = (red // 16, green // 16, blue // 16)
            if bucket in expanded_backdrop_palette:
                outside[index] = 255
    background_mask = Image.frombytes("L", (width, height), bytes(outside)).filter(ImageFilter.GaussianBlur(1.15))
    alpha = background_mask.point(lambda value: 255 - value).filter(ImageFilter.MinFilter(3))
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.45))
    image.putalpha(alpha)
    foreground = sum(1 for value in alpha.getdata() if value >= 96)
    ratio = foreground / max(1, total)
    if not 0.025 <= ratio <= 0.78:
        raise AssetConsistencyError(
            f"Character extraction failed: foreground coverage was {ratio:.1%}. Regenerate the character."
        )
    bbox = alpha.point(lambda value: 255 if value >= 96 else 0).getbbox()
    if not bbox:
        raise AssetConsistencyError("Character extraction produced an empty image.")
    image = image.crop(bbox)
    # Remove lime RGB hidden under semi-transparent antialiased edge pixels.
    # Without spill neutralization those pixels become a neon outline after the
    # character is composited onto its story background.
    decontaminated = []
    for red, green, blue, opacity in image.getdata():
        if opacity < 252 and green > max(red, blue) + 8:
            green = max(red, blue)
        decontaminated.append((red, green, blue, opacity))
    image.putdata(decontaminated)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output


def validate_actor_variant(master: Path, candidate: Path) -> None:
    base = Image.open(master).convert("RGBA")
    other = Image.open(candidate).convert("RGBA")
    height_ratio = other.height / max(1, base.height)
    if not 0.68 <= height_ratio <= 1.35:
        raise AssetConsistencyError("A character state changed body height/proportions too much.")
    if min(other.width, other.height) < 180:
        raise AssetConsistencyError("A character state is too small for production rendering.")
    def palette(image: Image.Image) -> list[float]:
        bins = [0.0] * 512
        count = 0
        for red, green, blue, alpha in image.resize((96, 160), Image.Resampling.BILINEAR).getdata():
            if alpha < 96:
                continue
            bins[(red // 32) * 64 + (green // 32) * 8 + blue // 32] += 1.0
            count += 1
        return [value / max(1, count) for value in bins]
    similarity = sum(min(left, right) for left, right in zip(palette(base), palette(other)))
    if similarity < 0.30:
        raise AssetConsistencyError(f"A character state failed palette consistency ({similarity:.0%}).")


class CharacterBuilder:
    def __init__(self, client: VertexStudioClient, root: Path) -> None:
        self.client = client
        self.root = root

    def build(
        self,
        character: CharacterPlan,
        required_states: set[str] | None = None,
        state_directions: dict[str, str] | None = None,
        progress=None,
    ) -> CharacterLock:
        folder = self.root / "characters" / character.id
        folder.mkdir(parents=True, exist_ok=True)
        identity = (
            f"Original premium Korean 2D web-drama character. Name {character.name}. "
            f"Role: {character.role}. Age: {character.age}. Gender: {character.gender}. "
            f"Appearance: {character.appearance}. Outfit: {character.outfit}. "
            "Clean consistent modern manhwa linework, believable anatomy, full body from head to shoes."
        )
        master_source = folder / "master_source.png"
        master = folder / "master.png"
        last_error: Exception | None = None
        if master_source.exists() and master.exists():
            try:
                remove_green_screen(master_source, master)
                last_error = None
            except AssetConsistencyError as exc:
                last_error = exc
        else:
            last_error = AssetConsistencyError("Master character is not generated yet.")
        for attempt in range(1, 4) if last_error else ():
            try:
                self.client.generate_image(
                    identity + " Front three-quarter standing pose. Solid pure bright green chroma background, no scenery, no props, no text, no shadow on the background. "
                    f"Asset validation attempt {attempt}; obey the clean chroma requirement exactly.",
                    master_source,
                    aspect_ratio="9:16",
                )
                remove_green_screen(master_source, master)
                last_error = None
                break
            except AssetConsistencyError as exc:
                last_error = exc
        if last_error:
            raise last_error
        assets = {"neutral": master.name}
        reference_manifest_path = folder / "reference_manifest.json"
        reference_manifest = (
            json.loads(reference_manifest_path.read_text(encoding="utf-8"))
            if reference_manifest_path.exists() else {}
        )
        if state_directions is not None:
            states = list(state_directions.items())
        else:
            wanted = required_states or set(ACTING_STATES)
            states = [(name, direction) for name, direction in list(ACTING_STATES.items())[1:] if name in wanted]
        for index, (state, direction) in enumerate(states, 1):
            if progress:
                progress(index / (len(states) + 1), f"Locking {character.name}: {state}")
            raw = folder / f"{state}_source.png"
            clean = folder / f"{state}.png"
            reference_images = [master_source]
            mouth_pose_reference: Path | None = None
            if state.endswith(("_small", "_wide")):
                mouth_pose_reference = folder / f"{state.rsplit('_', 1)[0]}_closed_source.png"
                if mouth_pose_reference.exists():
                    reference_images.append(mouth_pose_reference)
            reference_signature = {
                "model": getattr(getattr(self.client, "config", None), "image_model", "test-image"),
                "sources": [sha256(path) for path in reference_images],
            }
            validation_reference = (
                folder / f"{state.rsplit('_', 1)[0]}_closed.png"
                if mouth_pose_reference else master
            )
            last_error = AssetConsistencyError(f"Character state {state} is not generated yet.")
            reference_is_current = mouth_pose_reference is None or reference_manifest.get(state) == reference_signature
            if raw.exists() and clean.exists() and reference_is_current:
                try:
                    remove_green_screen(raw, clean)
                    validate_actor_variant(validation_reference, clean)
                    last_error = None
                except AssetConsistencyError as exc:
                    last_error = exc
            for attempt in range(1, 4) if last_error else ():
                try:
                    self.client.generate_image(
                        identity
                        + f" {direction}. Preserve the same viewing angle and exact character identity. "
                        + ("Match the body, hands, face position and camera framing of the final reference exactly; change only the original lips. " if mouth_pose_reference else "")
                        + "Full body from head to shoes. Solid pure bright green chroma background, no scenery, no text, no labels. "
                        + f"Consistency validation attempt {attempt}.",
                        raw,
                        aspect_ratio="9:16",
                        reference_images=reference_images,
                    )
                    reference_manifest[state] = reference_signature
                    reference_manifest_path.write_text(
                        json.dumps(reference_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    remove_green_screen(raw, clean)
                    validate_actor_variant(validation_reference, clean)
                    last_error = None
                    break
                except AssetConsistencyError as exc:
                    last_error = exc
            if last_error:
                raise last_error
            assets[state] = clean.name
            reference_manifest[state] = reference_signature
            reference_manifest_path.write_text(
                json.dumps(reference_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        checksums = {name: sha256(folder / relative) for name, relative in assets.items()}
        lock = CharacterLock(character.id, identity, assets, checksums)
        lock.save(folder / "lock.json")
        (folder / "extraction_version.txt").write_text(EXTRACTION_VERSION, encoding="ascii")
        return lock


def validate_character_lock(folder: Path) -> CharacterLock:
    lock = CharacterLock.load(folder / "lock.json")
    for name, relative in lock.assets.items():
        path = folder / relative
        if not path.exists() or sha256(path) != lock.checksums.get(name):
            raise AssetConsistencyError(f"Locked character asset changed or is missing: {lock.character_id}/{name}")
    return lock


def build_backgrounds(client: VertexStudioClient, plan: EpisodePlan, root: Path, progress=None) -> dict[str, Path]:
    backgrounds: dict[str, Path] = {}
    unique: dict[str, str] = {}
    for shot in plan.shots:
        unique.setdefault(shot.location_id, shot.background_prompt)
    manifest_path = root / "backgrounds" / "lock.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for index, (location, prompt) in enumerate(unique.items(), 1):
        if progress:
            progress(index / max(1, len(unique)), f"Building locked location: {location}")
        output = root / "backgrounds" / f"{location}.png"
        locked = existing.get(location, {})
        if not output.exists() or sha256(output) != locked.get("sha256"):
            client.generate_image(
                "Original premium Korean 2D web-drama environment. Background only, absolutely no people, "
                "no characters, no silhouettes, no text. Wide establishing composition with foreground, midground and depth. "
                + prompt,
                output,
                aspect_ratio="9:16",
            )
        backgrounds[location] = output
    manifest = {key: {"file": path.name, "sha256": sha256(path)} for key, path in backgrounds.items()}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backgrounds
