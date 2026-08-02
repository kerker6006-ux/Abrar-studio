from __future__ import annotations

import hashlib
import json
from pathlib import Path
from .models import CharacterManifest


class IdentityLockError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> CharacterManifest:
    with path.open("r", encoding="utf-8") as fh:
        return CharacterManifest.from_dict(json.load(fh))


def _locked_asset_paths(manifest_path: Path, manifest: CharacterManifest) -> list[str]:
    """Return every file that forms the immutable visual identity of a character.

    Articulated rigs introduce files that are not represented by the legacy pose fields.
    We therefore lock the rig definition and every sprite referenced by that definition,
    while retaining the legacy face/pose/gesture assets for close-up acting.
    """
    rel_paths = {
        manifest.reference_sheet,
        manifest.portrait,
        manifest.full_front,
        *manifest.expressions.values(),
        *manifest.mouths.values(),
        *manifest.poses.values(),
        *manifest.gestures.values(),
    }
    if manifest.articulated_rig:
        rel_paths.add(manifest.articulated_rig)
        rig_path = manifest_path.parent / manifest.articulated_rig
        if rig_path.exists():
            try:
                rig = json.loads(rig_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise IdentityLockError(f"Invalid articulated rig: {rig_path}: {exc}") from exc
            for item in rig.get("parts", {}).values():
                rel = item.get("file")
                if rel:
                    rel_paths.add(str(rel))
    return sorted(str(value) for value in rel_paths if value)


def calculate_manifest_checksums(manifest_path: Path) -> dict[str, str]:
    manifest = load_manifest(manifest_path)
    base = manifest_path.parent
    result: dict[str, str] = {}
    for rel in _locked_asset_paths(manifest_path, manifest):
        candidate = (base / rel).resolve()
        if not candidate.exists():
            raise IdentityLockError(f"Missing locked asset: {candidate}")
        result[rel] = sha256_file(candidate)
    return result


def verify_manifest(manifest_path: Path) -> tuple[bool, list[str]]:
    manifest = load_manifest(manifest_path)
    actual = calculate_manifest_checksums(manifest_path)
    errors: list[str] = []
    for rel, expected in manifest.asset_checksums.items():
        if rel not in actual:
            errors.append(f"Missing asset from manifest: {rel}")
        elif actual[rel] != expected:
            errors.append(f"Checksum mismatch: {rel}")
    for rel in actual:
        if rel not in manifest.asset_checksums:
            errors.append(f"Unlocked asset: {rel}")
    return not errors, errors
