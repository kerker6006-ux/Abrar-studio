from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import APP_VERSION
from .paths import user_config_dir, user_data_dir


POSTHOG_API_KEY = "phc_tFiJLtJDkKaMnoTYWKpqWtvsqAaTpmgyqLiMnD3aQ296"
POSTHOG_CAPTURE_URL = "https://us.i.posthog.com/capture/"
MAX_LOCAL_EVENTS = 2000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: object, limit: int = 1200) -> str:
    text = str(value)
    home = str(Path.home())
    if home:
        text = text.replace(home, "<user-folder>")
    text = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "<redacted-api-key>", text)
    text = re.sub(r"AQ\.[0-9A-Za-z._-]{20,}", "<redacted-api-key>", text)
    text = re.sub(r"(?i)(api[_ -]?key|authorization|token)(\s*[:=]\s*)[^\s,;]+", r"\1\2<redacted>", text)
    return text[:limit]


def _safe_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    def clean(value: Any, depth: int = 0) -> Any:
        if depth > 3:
            return _safe_text(value, 300)
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            return _safe_text(value)
        if isinstance(value, (list, tuple)):
            return [clean(item, depth + 1) for item in value[:50]]
        if isinstance(value, dict):
            return {str(k): clean(v, depth + 1) for k, v in list(value.items())[:50]}
        return _safe_text(value)

    result: dict[str, Any] = {}
    for key, value in (properties or {}).items():
        if key.lower() in {"api_key", "dialogue", "prompt", "project_path", "file_path", "username", "hostname"}:
            continue
        result[key] = clean(value)
    return result


def _memory_gb() -> float | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.total_physical / (1024**3), 1)
    except Exception:
        pass
    return None


def _gpu_name() -> str:
    if os.name != "nt":
        return "unknown"
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name",
            ],
            capture_output=True, text=True, timeout=5, creationflags=flags,
        )
        return _safe_text(result.stdout.strip() or "unknown", 160)
    except Exception:
        return "unknown"


def system_profile(include_gpu: bool = False) -> dict[str, Any]:
    try:
        disk = shutil.disk_usage(user_data_dir())
        free_disk_gb: float | None = round(disk.free / (1024**3), 1)
    except OSError:
        free_disk_gb = None
    return {
        "app_version": APP_VERSION,
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "cpu": _safe_text(platform.processor() or "unknown", 160),
        "cpu_cores": os.cpu_count(),
        "ram_gb": _memory_gb(),
        "gpu": _gpu_name() if include_gpu else None,
        "free_disk_gb": free_disk_gb,
        "frozen_build": bool(getattr(sys, "frozen", False)),
        "python_version": platform.python_version(),
    }


def _error_category(exc: BaseException) -> str:
    text = str(exc).lower()
    categories = (
        ("quota_or_rate_limit", ("429", "quota", "rate limit")),
        ("authentication_or_permission", ("401", "403", "permission", "unauthorized", "api key")),
        ("network_or_timeout", ("timeout", "timed out", "connection", "network", "urlerror")),
        ("provider_unavailable", ("500", "502", "503", "504", "unavailable")),
        ("missing_dependency", ("not found", "no such file", "missing")),
        ("invalid_input", ("400", "invalid", "malformed")),
    )
    return next((category for category, markers in categories if any(marker in text for marker in markers)), "application_error")


class TelemetryRecorder:
    def __init__(self, folder: Path | None = None, identity_path: Path | None = None) -> None:
        self.enabled = False
        self._folder = folder or (user_data_dir() / "diagnostics")
        self._folder.mkdir(parents=True, exist_ok=True)
        self.events_path = self._folder / "events.jsonl"
        self.identity_path = identity_path or (user_config_dir() / "telemetry.json")
        self.identity = self._load_identity()
        self._lock = threading.Lock()

    @property
    def installation_id(self) -> str:
        return str(self.identity["installation_id"])

    def _load_identity(self) -> dict[str, Any]:
        try:
            data = json.loads(self.identity_path.read_text(encoding="utf-8"))
            if data.get("installation_id"):
                return data
        except (OSError, json.JSONDecodeError):
            pass
        data = {"installation_id": str(uuid.uuid4()), "install_reported": False}
        self.identity_path.parent.mkdir(parents=True, exist_ok=True)
        self.identity_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def configure(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if self.enabled and not self.identity.get("install_reported"):
            self.capture("abrar_install", system_profile(include_gpu=True))
            self.identity["install_reported"] = True
            self.identity_path.write_text(json.dumps(self.identity, indent=2), encoding="utf-8")

    def capture(
        self,
        event: str,
        properties: dict[str, Any] | None = None,
        remote_properties: dict[str, Any] | None = None,
    ) -> None:
        safe = _safe_properties(properties)
        record = {
            "timestamp": _utc_now(),
            "event": _safe_text(event, 100),
            "installation_id": self.installation_id,
            "properties": {"app_version": APP_VERSION, **safe},
        }
        self._append_local(record)
        if self.enabled:
            remote_record = dict(record)
            if remote_properties is not None:
                remote_record["properties"] = {"app_version": APP_VERSION, **_safe_properties(remote_properties)}
            threading.Thread(target=self._send, args=(remote_record,), daemon=True).start()

    def capture_exception(self, operation: str, exc: BaseException, duration_seconds: float | None = None) -> None:
        stack = [
            {"line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(exc.__traceback__)[-16:]
        ]
        properties: dict[str, Any] = {
            "operation": operation,
            "error_type": type(exc).__name__,
            "error_message": _safe_text(exc),
            "stack": stack,
        }
        if duration_seconds is not None:
            properties["duration_seconds"] = round(duration_seconds, 3)
        remote = {
            "operation": operation,
            "error_type": type(exc).__name__,
            "error_category": _error_category(exc),
            "stack": stack,
        }
        if duration_seconds is not None:
            remote["duration_seconds"] = round(duration_seconds, 3)
        self.capture("abrar_error", properties, remote_properties=remote)

    def recent_events(self, limit: int = 300) -> list[dict[str, Any]]:
        try:
            lines = self.events_path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]
        except OSError:
            return []
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _append_local(self, record: dict[str, Any]) -> None:
        try:
            with self._lock:
                with self.events_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                lines = self.events_path.read_text(encoding="utf-8").splitlines()
                if len(lines) > MAX_LOCAL_EVENTS:
                    self.events_path.write_text("\n".join(lines[-MAX_LOCAL_EVENTS:]) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _send(self, record: dict[str, Any]) -> None:
        payload = {
            "api_key": POSTHOG_API_KEY,
            "event": record["event"],
            "distinct_id": self.installation_id,
            "timestamp": record["timestamp"],
            "properties": {
                "$process_person_profile": False,
                **record["properties"],
            },
        }
        request = urllib.request.Request(
            POSTHOG_CAPTURE_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "AbrarStudio-Telemetry"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                response.read(64)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._append_local({
                "timestamp": _utc_now(), "event": "telemetry_delivery_failed",
                "installation_id": self.installation_id,
                "properties": {"error_type": type(exc).__name__, "error_message": _safe_text(exc)},
            })


telemetry = TelemetryRecorder()
