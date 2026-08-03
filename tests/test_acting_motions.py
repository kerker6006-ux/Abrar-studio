from pathlib import Path

from abrar_studio.puppet import ARTICULATED_MOTIONS, ArticulatedPuppetRenderer


def test_seo_yeon_rig_renders_every_new_acting_motion():
    rig = Path("assets/characters/seo_yeon/rig/rig.json")
    renderer = ArticulatedPuppetRenderer()
    for motion in ("head_nod", "head_shake", "wave", "point", "show", "bend", "plead", "argue"):
        assert motion in ARTICULATED_MOTIONS
        image = renderer.render(rig, motion, 0.6, 0.45)
        assert image.mode == "RGBA"
        assert image.width > 40 and image.height > 100
