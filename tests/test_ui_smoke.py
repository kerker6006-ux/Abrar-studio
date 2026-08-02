from __future__ import annotations

import os
import unittest


def _display_works() -> bool:
    if os.name == "nt":
        return True
    if not os.environ.get("DISPLAY"):
        return False
    try:
        import tkinter as tk
        root = tk.Tk(); root.withdraw(); root.update_idletasks(); root.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(_display_works(), "GUI display required")
class UISmokeTests(unittest.TestCase):
    def test_window_builds_and_pages_exist(self):
        from abrar_studio.ui import StudioApp
        app = StudioApp()
        app.withdraw()
        app.update_idletasks()
        self.assertIn("Production", app._pages)
        self.assertIn("Shot Builder", app._pages)
        self.assertIn("Characters", app._pages)
        self.assertEqual(app.current_episode.resolution, (1280, 720))
        app.destroy()


if __name__ == "__main__":
    unittest.main()
