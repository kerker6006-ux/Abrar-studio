from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path

from .constants import APP_VERSION
from .locks import verify_manifest
from .models import Episode
from .paths import app_root
from .project import StudioProject
from .puppet import ArticulatedPuppetRenderer, RigDefinition
from .telemetry import _safe_text, system_profile, telemetry


@dataclass(slots=True)
class DiagnosticItem:
    name: str
    passed: bool
    detail: str


def run_diagnostics(project: StudioProject | None = None, ffmpeg_path: str = "ffmpeg") -> list[DiagnosticItem]:
    items: list[DiagnosticItem] = []
    items.append(DiagnosticItem("Python", sys.version_info >= (3, 11), platform.python_version()))
    items.append(DiagnosticItem("Application version", True, APP_VERSION))
    items.append(DiagnosticItem("64-bit runtime", sys.maxsize > 2**32, platform.machine()))

    ffmpeg = str(Path(ffmpeg_path)) if Path(ffmpeg_path).is_file() else shutil.which(ffmpeg_path)
    bundled = app_root() / "tools" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not ffmpeg and bundled.exists():
        ffmpeg = str(bundled)
    items.append(DiagnosticItem("FFmpeg", bool(ffmpeg), ffmpeg or "not found"))

    try:
        project = project or StudioProject.open_or_create_default()
        probe = project.root / ".diagnostic-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        items.append(DiagnosticItem("Project folder writable", True, "write test passed"))
    except Exception as exc:
        items.append(DiagnosticItem("Project folder writable", False, str(exc)))
        return items

    for cid in ("seo_yeon", "min_jun"):
        try:
            ok, errors = verify_manifest(project.character_manifest_path(cid))
            items.append(DiagnosticItem(f"Identity lock: {cid}", ok, "checksums match" if ok else "; ".join(errors)))
        except Exception as exc:
            items.append(DiagnosticItem(f"Identity lock: {cid}", False, str(exc)))
        try:
            character = project.character(cid)
            rig_path = project.character_manifest_path(cid).parent / character.articulated_rig
            rig = RigDefinition.load(rig_path)
            frame = ArticulatedPuppetRenderer().render(rig_path, "walk_normal", 0.18, 0.4)
            passed = frame.getbbox() is not None and {"walk_normal", "run_normal"}.issubset(set(rig.motions))
            items.append(DiagnosticItem(f"Articulated motion: {cid}", passed, f"{len(rig.parts)} parts; walk/run ready"))
        except Exception as exc:
            items.append(DiagnosticItem(f"Articulated motion: {cid}", False, str(exc)))

    try:
        episode = Episode.load(app_root() / "sample_project" / "episode_001.json")
        items.append(DiagnosticItem("Sample episode schema", episode.shot_count >= 1, f"{episode.shot_count} shots"))
    except Exception as exc:
        items.append(DiagnosticItem("Sample episode schema", False, str(exc)))

    # Security capability is a platform check; no secret is read or written here.
    items.append(DiagnosticItem("Secure key storage", os.name == "nt", "Windows DPAPI" if os.name == "nt" else "available in Windows build"))
    return items


def write_report(path: Path, items: list[DiagnosticItem]) -> Path:
    updater_log_path = telemetry.events_path.parent / "updater.log"
    try:
        updater_log = [_safe_text(line, 1200) for line in updater_log_path.read_text(encoding="utf-8-sig").splitlines()[-200:]]
    except OSError:
        updater_log = []
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": all(i.passed for i in items if i.name != "Secure key storage" or os.name == "nt"),
        "device": system_profile(include_gpu=True),
        "anonymous_installation_id": telemetry.installation_id,
        "anonymous_sharing_enabled": telemetry.enabled,
        "items": [asdict(i) for i in items],
        "recent_events": telemetry.recent_events(limit=300),
        "updater_log": updater_log,
        "privacy": "No API keys, scripts, dialogue, prompts, usernames, or media content are intentionally collected. Redacted local error descriptions and failing asset names may appear for troubleshooting.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
