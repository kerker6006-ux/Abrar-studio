from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from abrar_studio.models import Episode
from abrar_studio.project import StudioProject
from abrar_studio.renderer import AnimaticRenderer


OUTPUT = ROOT / "verification_sample_limited_walk.mp4"


with tempfile.TemporaryDirectory(prefix="abrar-limited-preview-") as temporary:
    project = StudioProject.create(Path(temporary) / "project")
    episode = Episode.from_dict({
        "project_id": "abrar_studio", "episode_id": "LIMITED_WALK", "title": "Limited walk preview",
        "resolution": [1280, 720], "fps": 24,
        "scenes": [{"id": "preview", "title": "preview", "shots": [{
            "id": "walk", "duration": 2.0, "background": "school_hallway_webtoon",
            "camera": "pan_right", "music": "mystery",
            "actors": [{
                "character_id": "min_jun", "pose": "full_side", "position": "left",
                "acting": "walk", "motion": "walk", "travel_x": 0.28,
                "ground_y": 0.96, "facing": "right"
            }]
        }]}],
    })
    renderer = AnimaticRenderer(project, shutil.which("ffmpeg") or "ffmpeg", video_preset="veryfast", crf=18)
    renderer.render(episode, OUTPUT)

print(OUTPUT)
