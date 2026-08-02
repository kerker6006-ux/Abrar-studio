from __future__ import annotations
import shutil
import unittest
from abrar_studio.diagnostics import run_diagnostics
from tests.common import make_project

class DiagnosticTests(unittest.TestCase):
    def test_core_diagnostics(self):
        temp, project = make_project(); self.addCleanup(temp.cleanup)
        items = run_diagnostics(project, shutil.which("ffmpeg") or "ffmpeg")
        by_name = {x.name: x for x in items}
        self.assertTrue(by_name["Python"].passed)
        self.assertTrue(by_name["FFmpeg"].passed)
        self.assertTrue(by_name["Identity lock: seo_yeon"].passed)
        self.assertTrue(by_name["Identity lock: min_jun"].passed)

if __name__ == "__main__": unittest.main()
