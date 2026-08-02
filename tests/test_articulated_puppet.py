from __future__ import annotations

from pathlib import Path

from abrar_studio.paths import app_root
from abrar_studio.puppet import ArticulatedPuppetRenderer, RigDefinition, footstep_times, motion_state, normalize_motion
from abrar_studio.models import Episode
from abrar_studio.renderer import AnimaticRenderer
from tests.common import make_project


def test_main_character_articulated_rigs_are_complete():
    root = app_root()
    required = {"torso", "head", "leg_front_upper", "leg_front_lower", "foot_front", "leg_back_upper", "leg_back_lower", "foot_back", "arm_front_upper", "arm_front_lower"}
    for character_id in ["seo_yeon", "min_jun"]:
        path = root / "assets" / "characters" / character_id / "rig" / "rig.json"
        rig = RigDefinition.load(path)
        assert required.issubset(rig.parts)
        assert {"walk_normal", "run_normal", "stop_sudden"}.issubset(set(rig.motions))
        for part in rig.parts.values():
            assert (path.parent.parent / part.file).is_file()


def test_walk_and_run_states_are_articulated_and_different():
    walk = motion_state("walk_normal", 0.22, 0.5)
    run = motion_state("run_normal", 0.22, 0.5)
    assert abs(walk.angles["leg_front_upper"]) > 1
    assert abs(run.angles["leg_front_upper"] - walk.angles["leg_front_upper"]) > 1
    assert run.angles["arm_front_upper"] != walk.angles["arm_front_upper"]
    assert normalize_motion("walk") == "walk_normal"


def test_puppet_frames_change_without_changing_character_source():
    path = app_root() / "assets" / "characters" / "seo_yeon" / "rig" / "rig.json"
    renderer = ArticulatedPuppetRenderer()
    a = renderer.render(path, "walk_normal", 0.00, 0.4)
    b = renderer.render(path, "walk_normal", 0.23, 0.4)
    assert a.getbbox() and b.getbbox()
    assert a.tobytes() != b.tobytes()
    assert a.height > 500 and b.height > 500


def test_footstep_schedule_has_two_contacts_per_cycle():
    walk = footstep_times("walk_normal", 2.0, 1.0)
    run = footstep_times("run_normal", 2.0, 1.0)
    assert 3 <= len(walk) <= 6
    assert len(run) > len(walk)
    assert walk == sorted(walk)


def test_integrated_preview_uses_articulated_motion():
    temp, project = make_project()
    try:
        episode = Episode.from_dict({
            "project_id": "test", "episode_id": "RIG", "title": "Rig", "resolution": [1280, 720], "fps": 24,
            "scenes": [{"id": "S", "title": "Walk", "shots": [{
                "id": "WALK", "duration": 2.0, "background": "school_hallway_evening", "music": "chase_pulse", "ambience": "hallway_murmur",
                "camera": "tracking", "emotion": "determined", "emotion_level": 3, "sfx": [],
                "actors": [{"character_id": "seo_yeon", "pose": "full_side", "position": "left", "motion": "walk_normal", "travel_x": 0.55, "facing": "right"}]
            }]}]
        })
        renderer = AnimaticRenderer(project)
        frame_a = renderer.preview_frame(episode, episode.scenes[0].shots[0], at=0.15)
        frame_b = renderer.preview_frame(episode, episode.scenes[0].shots[0], at=0.65)
        assert frame_a.size == (1280, 720)
        assert frame_a.tobytes() != frame_b.tobytes()
    finally:
        temp.cleanup()
