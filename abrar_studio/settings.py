from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from .paths import user_config_dir


@dataclass(slots=True)
class AppSettings:
    ffmpeg_path: str = "ffmpeg"
    update_owner: str = "kerker6006-ux"
    update_repo: str = "Abrar-studio"
    auto_check_updates: bool = True
    project_path: str = ""


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (user_config_dir() / "settings.json")

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        allowed = AppSettings.__dataclass_fields__.keys()
        return AppSettings(**{k: v for k, v in data.items() if k in allowed})

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
