from __future__ import annotations

from abrar_studio.models import Episode
from abrar_studio.paths import app_root
from abrar_studio.validator import QualityValidator
from tests.common import make_project


def test_all_episode_templates_load_and_pass_local_gates():
    temp, project = make_project()
    try:
        template_dir = app_root() / "templates" / "episodes"
        files = sorted(template_dir.glob("*.json"))
        assert len(files) >= 4
        for path in files:
            episode = Episode.load(path)
            report = QualityValidator(project).validate(episode, require_voices=False)
            failed = [(x.gate, x.detail) for x in report.results if not x.passed and x.gate != "FFmpeg"]
            assert not failed, f"{path.name}: {failed}"
    finally:
        temp.cleanup()
