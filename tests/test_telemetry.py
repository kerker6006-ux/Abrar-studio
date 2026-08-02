from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from abrar_studio.telemetry import TelemetryRecorder, _safe_properties, _safe_text


class TelemetryTests(unittest.TestCase):
    def recorder(self, root: Path) -> TelemetryRecorder:
        return TelemetryRecorder(root / "events", root / "config" / "telemetry.json")

    def test_redacts_keys_and_private_properties(self):
        value = _safe_text("api_key=AIza" + "A" * 30)
        self.assertNotIn("AIza", value)
        safe = _safe_properties({"dialogue": "secret script", "operation": "voice", "duration_seconds": 1.2})
        self.assertNotIn("dialogue", safe)
        self.assertEqual(safe["operation"], "voice")

    def test_disabled_capture_stays_local(self):
        with tempfile.TemporaryDirectory() as td:
            recorder = self.recorder(Path(td))
            with patch.object(recorder, "_send") as send:
                recorder.capture("abrar_test", {"operation": "diagnostics"})
                send.assert_not_called()
            events = recorder.recent_events()
            self.assertEqual(events[-1]["event"], "abrar_test")
            self.assertEqual(events[-1]["properties"]["operation"], "diagnostics")

    def test_exception_record_has_no_source_filename(self):
        with tempfile.TemporaryDirectory() as td:
            recorder = self.recorder(Path(td))
            try:
                raise RuntimeError("api_key=AIza" + "B" * 30)
            except RuntimeError as exc:
                recorder.capture_exception("render", exc, 0.5)
            payload = json.dumps(recorder.recent_events()[-1])
            self.assertNotIn("AIza", payload)
            self.assertNotIn('"file"', payload)
            self.assertIn("redacted", payload)


if __name__ == "__main__":
    unittest.main()
