from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from .locks import verify_manifest
from .models import CharacterManifest


class CharacterPackError(RuntimeError):
    pass


_SAFE_ID = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    root = target.resolve()
    for info in zf.infolist():
        candidate = (target / info.filename).resolve()
        if root not in candidate.parents and candidate != root:
            raise CharacterPackError("Character pack contains an unsafe path")
    zf.extractall(target)


def _find_manifest(root: Path) -> Path:
    direct = root / "manifest.json"
    if direct.exists():
        return direct
    manifests = [p for p in root.rglob("manifest.json") if "__MACOSX" not in p.parts]
    if len(manifests) != 1:
        raise CharacterPackError("Pack must contain exactly one manifest.json")
    return manifests[0]


def validate_character_pack(manifest_path: Path) -> CharacterManifest:
    try:
        manifest = CharacterManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise CharacterPackError(f"Invalid character manifest: {exc}") from exc
    if not _SAFE_ID.fullmatch(manifest.character_id):
        raise CharacterPackError("character_id must use lowercase letters, numbers and underscores")
    if not manifest.identity_locked or not manifest.voice_profile.locked:
        raise CharacterPackError("Character and voice profile must be identity-locked")
    if manifest.voice_profile.character_id != manifest.character_id:
        raise CharacterPackError("Voice profile character_id does not match the character")
    required_mouths = {"closed", "open", "wide", "round", "narrow"}
    if not required_mouths.issubset(manifest.mouths):
        raise CharacterPackError("Pack requires closed/open/wide/round/narrow mouth shapes")
    if not manifest.expressions or not manifest.poses:
        raise CharacterPackError("Pack requires expressions and full-body poses")
    ok, errors = verify_manifest(manifest_path)
    if not ok:
        raise CharacterPackError("Checksum verification failed: " + "; ".join(errors))
    return manifest


def import_character_pack(project_characters_dir: Path, pack_path: Path, *, replace: bool = False) -> CharacterManifest:
    project_characters_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="abrar-character-pack-") as temp:
        unpacked = Path(temp)
        if pack_path.is_dir():
            source_root = pack_path
        elif pack_path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(pack_path) as zf:
                    _safe_extract(zf, unpacked)
            except zipfile.BadZipFile as exc:
                raise CharacterPackError("The selected file is not a valid ZIP") from exc
            source_root = unpacked
        else:
            raise CharacterPackError("Select a character pack folder or ZIP")
        manifest_path = _find_manifest(source_root)
        manifest = validate_character_pack(manifest_path)
        destination = project_characters_dir / manifest.character_id
        if destination.exists() and not replace:
            raise CharacterPackError(f"Character '{manifest.character_id}' already exists")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(manifest_path.parent, destination)
        copied = destination / "manifest.json"
        validate_character_pack(copied)
        return manifest
