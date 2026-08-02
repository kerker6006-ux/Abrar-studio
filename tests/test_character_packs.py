from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from abrar_studio.character_packs import CharacterPackError, import_character_pack
from abrar_studio.locks import calculate_manifest_checksums
from tests.common import make_project


def _make_guest_pack(tmp_path: Path, project) -> Path:
    source = project.assets_dir / "characters" / "seo_yeon"
    pack = tmp_path / "guest_pack"
    shutil.copytree(source, pack)
    manifest_path = pack / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["character_id"] = "guest_student"
    data["display_name"] = "Guest Student"
    data["voice_profile"]["character_id"] = "guest_student"
    data["voice_profile"]["profile_id"] = "GUEST_STUDENT_VOICE_1"
    data["voice_profile"]["voice_name"] = "Kore"
    data["asset_checksums"] = {}
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    data["asset_checksums"] = calculate_manifest_checksums(manifest_path)
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return pack


def test_import_guest_character_pack(tmp_path: Path):
    temp, project = make_project()
    pack = _make_guest_pack(tmp_path, project)
    target = tmp_path / "characters"
    manifest = import_character_pack(target, pack)
    assert manifest.character_id == "guest_student"
    assert (target / "guest_student" / "manifest.json").exists()


def test_rejects_unlocked_character_pack(tmp_path: Path):
    temp, project = make_project()
    pack = _make_guest_pack(tmp_path, project)
    manifest_path = pack / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["identity_locked"] = False
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CharacterPackError):
        import_character_pack(tmp_path / "characters", pack)
