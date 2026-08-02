from __future__ import annotations

import unittest
from unittest.mock import patch

from abrar_studio.monitoring import _before_breadcrumb, _before_send, configure_sentry


class MonitoringTests(unittest.TestCase):
    def test_sentry_event_removes_private_context_and_source_content(self):
        event = {
            "request": {"url": "private"},
            "server_name": "private-computer",
            "extra": {"dialogue": "private script"},
            "contexts": {"device": {"name": "private-computer"}, "trace": {"trace_id": "abc"}},
            "exception": {"values": [{
                "type": "RuntimeError",
                "value": "api_key=AIza" + "A" * 30,
                "stacktrace": {"frames": [{
                    "filename": "private.py", "abs_path": "C:/Users/private/private.py",
                    "function": "render", "lineno": 12, "vars": {"dialogue": "private script"},
                    "context_line": "private script",
                }]},
            }]},
        }
        cleaned = _before_send(event, {})
        self.assertNotIn("request", cleaned)
        self.assertNotIn("server_name", cleaned)
        self.assertNotIn("extra", cleaned)
        self.assertNotIn("device", cleaned["contexts"])
        frame = cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]
        self.assertEqual(frame, {"function": "render", "lineno": 12})
        self.assertNotIn("AIza", str(cleaned))
        self.assertNotIn("private script", str(cleaned))

    def test_breadcrumb_keeps_metadata_but_drops_message_and_data(self):
        cleaned = _before_breadcrumb({
            "timestamp": 1, "type": "log", "category": "render", "level": "error",
            "message": "private dialogue", "data": {"path": "private"},
        }, {})
        self.assertEqual(cleaned, {"timestamp": 1, "type": "log", "category": "render", "level": "error"})

    def test_sentry_defaults_disable_pii_and_tracing(self):
        with patch("sentry_sdk.init") as init:
            self.assertTrue(configure_sentry(True))
        options = init.call_args.kwargs
        self.assertFalse(options["send_default_pii"])
        self.assertFalse(options["default_integrations"])
        self.assertFalse(options["include_local_variables"])
        self.assertEqual(options["traces_sample_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
