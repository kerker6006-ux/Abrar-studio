from __future__ import annotations

import tempfile
from pathlib import Path
from abrar_studio.project import StudioProject


def make_project() -> tuple[tempfile.TemporaryDirectory, StudioProject]:
    temp = tempfile.TemporaryDirectory()
    project = StudioProject.create(Path(temp.name) / "project")
    return temp, project
