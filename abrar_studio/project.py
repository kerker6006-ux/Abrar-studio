from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from .models import CharacterManifest, Episode
from .locks import load_manifest
from .paths import app_root, projects_dir
from .character_packs import import_character_pack


class ProjectError(RuntimeError):
    pass


class StudioProject:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.episodes_dir = self.root / "episodes"
        self.audio_dir = self.root / "audio"
        self.render_dir = self.root / "renders"
        self.temp_dir = self.root / ".temp"
        self.assets_dir = self.root / "assets"
        self.project_file = self.root / "project.json"

    @classmethod
    def create(cls, root: Path, name: str = "2:14 Convenience Store") -> "StudioProject":
        project = cls(root)
        for folder in [project.episodes_dir, project.audio_dir, project.render_dir, project.temp_dir, project.assets_dir]:
            folder.mkdir(parents=True, exist_ok=True)
        project.ensure_bundled_assets()
        payload = {
            "name": name,
            "schema_version": 3,
            "resolution": [1280, 720],
            "fps": 24,
            "character_ids": ["seo_yeon", "min_jun"],
        }
        project.project_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        sample = app_root() / "sample_project" / "episode_001.json"
        episode_target = project.episodes_dir / "episode_001.json"
        if sample.exists() and not episode_target.exists():
            shutil.copy2(sample, episode_target)
        return project

    @classmethod
    def open_or_create_default(cls) -> "StudioProject":
        root = projects_dir() / "TwoFourteen"
        project = cls(root) if (root / "project.json").exists() else cls.create(root)
        project.ensure_bundled_assets()
        return project

    def ensure_bundled_assets(self) -> None:
        bundled_root = app_root() / "assets"
        for name in ["characters", "music", "sfx", "backgrounds"]:
            source = bundled_root / name
            target = self.assets_dir / name
            if source.exists():
                self._copytree_overwrite(source, target)

    def _copytree_overwrite(self, source: Path, target: Path) -> None:
        for path in source.rglob("*"):
            rel = path.relative_to(source)
            destination = target / rel
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                try:
                    os.chmod(destination, 0o666)
                except OSError:
                    pass
            shutil.copy2(path, destination)

    def character_manifest_path(self, character_id: str) -> Path:
        return self.assets_dir / "characters" / character_id / "manifest.json"

    def character(self, character_id: str) -> CharacterManifest:
        path = self.character_manifest_path(character_id)
        if not path.exists():
            raise ProjectError(f"Unknown character: {character_id}")
        return load_manifest(path)


    def import_character(self, pack_path: Path, *, replace: bool = False) -> CharacterManifest:
        manifest = import_character_pack(self.assets_dir / "characters", pack_path, replace=replace)
        if self.project_file.exists():
            data = json.loads(self.project_file.read_text(encoding="utf-8"))
            ids = list(data.get("character_ids", []))
            if manifest.character_id not in ids:
                ids.append(manifest.character_id)
                data["character_ids"] = ids
                self.project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def character_ids(self) -> list[str]:
        root = self.assets_dir / "characters"
        return sorted(p.parent.name for p in root.glob("*/manifest.json"))

    def episode_files(self) -> list[Path]:
        return sorted(self.episodes_dir.glob("*.json"))

    def load_episode(self, path: Path | None = None) -> Episode:
        choices = self.episode_files()
        if path is None:
            if not choices:
                raise ProjectError("Project has no episode JSON files")
            path = choices[0]
        return Episode.load(path)

    def voice_cache_path(self, character_id: str, cache_key: str) -> Path:
        return self.audio_dir / character_id / f"{cache_key}.wav"

    def alignment_cache_path(self, character_id: str, cache_key: str) -> Path:
        return self.audio_dir / character_id / f"{cache_key}.align.json"
