from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .constants import APP_VERSION


SENTRY_DSN = "https://1788e7f95cf616262006c31762afe908@o4511839527960576.ingest.us.sentry.io/4511839530254336"
_enabled = False


def _redact_text(value: object, limit: int = 500) -> str:
    text = str(value)
    home = str(Path.home())
    if home:
        text = text.replace(home, "<user-folder>")
    text = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "<redacted-api-key>", text)
    text = re.sub(r"AQ\.[0-9A-Za-z._-]{20,}", "<redacted-api-key>", text)
    text = re.sub(r"(?i)(api[_ -]?key|authorization|token)(\s*[:=]\s*)[^\s,;]+", r"\1\2<redacted>", text)
    return text[:limit]


def _error_category(value: object) -> str:
    text = str(value).lower()
    categories = (
        ("quota_or_rate_limit", ("429", "quota", "rate limit")),
        ("authentication_or_permission", ("401", "403", "permission", "unauthorized", "api key")),
        ("network_or_timeout", ("timeout", "timed out", "connection", "network", "urlerror")),
        ("provider_unavailable", ("500", "502", "503", "504", "unavailable")),
        ("missing_dependency", ("not found", "no such file", "missing")),
        ("invalid_input", ("400", "invalid", "malformed")),
    )
    return next((category for category, markers in categories if any(marker in text for marker in markers)), "application_error")


def _before_breadcrumb(breadcrumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
    return {
        key: breadcrumb[key]
        for key in ("timestamp", "type", "category", "level")
        if key in breadcrumb
    }


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
    event.pop("request", None)
    event.pop("server_name", None)
    event.pop("extra", None)
    event.pop("modules", None)

    contexts = event.get("contexts")
    if isinstance(contexts, dict):
        event["contexts"] = {"trace": contexts["trace"]} if isinstance(contexts.get("trace"), dict) else {}

    exception = event.get("exception")
    if isinstance(exception, dict) and isinstance(exception.get("values"), list):
        for item in exception["values"]:
            if not isinstance(item, dict):
                continue
            original = item.get("value", "")
            category = _error_category(original)
            item["value"] = f"Privacy-safe {category}"
            stacktrace = item.get("stacktrace")
            if isinstance(stacktrace, dict) and isinstance(stacktrace.get("frames"), list):
                for frame in stacktrace["frames"]:
                    if not isinstance(frame, dict):
                        continue
                    for key in ("abs_path", "filename", "vars", "pre_context", "context_line", "post_context"):
                        frame.pop(key, None)
            event.setdefault("tags", {})["error_category"] = category

    if "message" in event:
        event["message"] = _redact_text(event["message"])

    # Keep only the random app installation identifier; never attach account identity.
    try:
        from .telemetry import telemetry

        event["user"] = {"id": telemetry.installation_id}
    except Exception:
        event.pop("user", None)
    return event


def configure_sentry(enabled: bool) -> bool:
    global _enabled
    try:
        import sentry_sdk

        if not enabled:
            sentry_sdk.init(dsn="")
            _enabled = False
            return False
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            release=f"abrar-studio@{APP_VERSION}",
            environment="production",
            send_default_pii=False,
            default_integrations=False,
            include_local_variables=False,
            attach_stacktrace=True,
            sample_rate=1.0,
            traces_sample_rate=0.0,
            auto_session_tracking=True,
            before_send=_before_send,
            before_breadcrumb=_before_breadcrumb,
        )
        _enabled = True
        return True
    except (ImportError, RuntimeError, ValueError):
        _enabled = False
        return False


def capture_exception(exc: BaseException, operation: str) -> str | None:
    if not _enabled:
        return None
    try:
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("operation", _redact_text(operation, 80))
            scope.set_tag("app_version", APP_VERSION)
            return sentry_sdk.capture_exception(exc)
    except Exception:
        return None


def flush(timeout: float = 2.0) -> None:
    if not _enabled:
        return
    try:
        import sentry_sdk

        sentry_sdk.flush(timeout=timeout)
    except Exception:
        pass
