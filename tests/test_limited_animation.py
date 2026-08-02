from __future__ import annotations

from abrar_studio.limited_animation import frame_path, inspect_sequence, sequence_name
from tests.common import make_project


def test_complete_frame_walk_loop_cycles_without_bone_warping():
    temp, project = make_project()
    try:
        character = project.character("min_jun")
        root = project.character_manifest_path("min_jun").parent
        name = sequence_name(character, "auto", "walk")
        assert name == "walk"
        sequence = character.animations[name]
        assert len(sequence.frames) == 6
        assert frame_path(root, sequence, 0.0).name == "frame_01.png"
        assert frame_path(root, sequence, 1.0).name == "frame_01.png"
        assert inspect_sequence(root, sequence) == []
    finally:
        temp.cleanup()


def test_static_actor_does_not_request_walk_sequence():
    temp, project = make_project()
    try:
        character = project.character("min_jun")
        assert sequence_name(character, "auto", "listen") is None
    finally:
        temp.cleanup()
