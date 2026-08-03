from __future__ import annotations

import json
import math
import shutil
import struct
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from abrar_studio.production_assets import remove_green_screen, validate_character_lock
from abrar_studio.production_pipeline import ProductionPipeline
from abrar_studio.production_models import EpisodePlan
from abrar_studio.production_renderer import ProductionRenderer


PLAN = {
    "title": "가게의 눈물",
    "synopsis": "서연이 손님과 충돌한다.",
    "music_tags": ["sad", "tense"],
    "characters": [
        {"id": "seo", "name": "서연", "role": "직원", "age": "26", "gender": "woman", "appearance": "black bob hair", "outfit": "blue store uniform"},
        {"id": "customer", "name": "민수", "role": "손님", "age": "35", "gender": "man", "appearance": "short brown hair", "outfit": "gray coat"},
    ],
    "shots": [
        {"id": "wide", "duration": 1.0, "location_id": "store", "background_prompt": "empty Korean convenience store", "camera": "wide", "speaker_id": "seo", "dialogue": "그만하세요!", "emotion": "angry", "actors": [
            {"character_id": "seo", "position": "left", "state": "angry", "motion": "point", "facing": "right"},
            {"character_id": "customer", "position": "right", "state": "neutral", "motion": "recoil", "facing": "left"}], "ambience_tags": ["store"], "sfx_tags": ["impact"], "transition": "cut"},
        {"id": "cry", "duration": 1.0, "location_id": "store", "background_prompt": "empty Korean convenience store", "camera": "closeup", "speaker_id": "seo", "dialogue": "정말 힘들었어요.", "emotion": "crying", "actors": [
            {"character_id": "seo", "position": "center", "state": "crying", "motion": "idle", "facing": "camera"}], "ambience_tags": ["store"], "sfx_tags": ["cloth"], "transition": "cut"},
    ],
}


class FakeVertexClient:
    def __init__(self):
        self.image_calls: list[tuple[str, list[Path]]] = []

    def generate_text(self, _prompt: str) -> str:
        return json.dumps(PLAN, ensure_ascii=False)

    def generate_image(self, prompt: str, output: Path, **kwargs) -> Path:
        self.image_calls.append((output.name, list(kwargs.get("reference_images") or [])))
        output.parent.mkdir(parents=True, exist_ok=True)
        if "Background only" in prompt:
            image = Image.new("RGB", (360, 640), (33, 56, 82))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 390, 360, 640), fill=(72, 64, 58))
            draw.rectangle((25, 80, 335, 330), fill=(61, 94, 113))
        else:
            image = Image.new("RGB", (360, 640), (0, 255, 0))
            draw = ImageDraw.Draw(image)
            color = (58, 92, 170) if "서연" in prompt else (105, 91, 84)
            draw.ellipse((112, 35, 248, 180), fill=(232, 194, 168), outline=(35, 28, 28), width=4)
            draw.rounded_rectangle((70, 160, 290, 610), radius=38, fill=color, outline=(30, 30, 38), width=5)
            if "_wide_source" in output.name:
                draw.ellipse((158, 108, 202, 142), fill=(55, 18, 22), outline=(30, 20, 20), width=3)
            elif "_small_source" in output.name:
                draw.ellipse((166, 116, 194, 132), fill=(65, 22, 25), outline=(30, 20, 20), width=2)
            else:
                draw.line((165, 124, 195, 124), fill=(50, 25, 25), width=3)
            if "pointing" in prompt:
                draw.rectangle((250, 240, 348, 274), fill=(232, 194, 168))
        image.save(output)
        return output

    def generate_tts(self, _text: str, output: Path, **_kwargs) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        rate = 24000
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
            wav.writeframes(b"".join(struct.pack("<h", round(math.sin(i / 18) * 4200)) for i in range(round(rate * 0.72))))
        return output


def test_plan_validates_multi_character_camera_cuts():
    plan = EpisodePlan.from_json(json.dumps(PLAN, ensure_ascii=False))
    assert len(plan.characters) == 2
    assert [shot.camera for shot in plan.shots] == ["wide", "closeup"]
    assert plan.shots[0].location_id == plan.shots[1].location_id


def test_plan_normalizes_descriptive_voice_to_supported_voice():
    invalid = json.loads(json.dumps(PLAN, ensure_ascii=False))
    invalid["characters"][0]["voice"] = "Korean female, slightly strained"
    invalid["characters"][1]["voice"] = "deep Korean man"
    plan = EpisodePlan.from_json(json.dumps(invalid, ensure_ascii=False))
    assert [character.voice for character in plan.characters] == ["Kore", "Orus"]


def test_extractor_removes_enclosed_chroma_and_green_spill(tmp_path: Path):
    source = tmp_path / "source.png"
    output = tmp_path / "clean.png"
    image = Image.new("RGB", (160, 240), (150, 210, 112))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((35, 15, 125, 225), radius=24, fill=(45, 52, 68), outline=(15, 18, 25), width=5)
    draw.rectangle((68, 105, 92, 205), fill=(150, 210, 112))  # enclosed background gap
    image.save(source)
    remove_green_screen(source, output)
    clean = Image.open(output).convert("RGBA")
    assert clean.getpixel((clean.width // 2, clean.height // 2))[3] == 0
    assert not any(
        0 < alpha < 252 and green > max(red, blue) + 8
        for red, green, blue, alpha in clean.getdata()
    )


def test_complete_offline_pipeline_locks_and_renders():
    ffmpeg = shutil.which("ffmpeg") or "C:/Users/alvi/AppData/Local/Programs/AbrarStudio/tools/ffmpeg.exe"
    if not Path(ffmpeg).exists():
        pytest.skip("FFmpeg is not installed")
    with tempfile.TemporaryDirectory() as raw:
        data = Path(raw)
        client = FakeVertexClient()
        with patch("abrar_studio.production_pipeline.user_data_dir", return_value=data):
            result = ProductionPipeline(client, ffmpeg).generate("가게에서 직원이 손님에게 화낸 뒤 운다")
        assert result.output.exists() and result.output.stat().st_size > 20_000
        assert result.audio_catalog_size >= 400
        assert len(result.plan.shots) == 2
        validate_character_lock(result.root / "characters" / "seo")
        validate_character_lock(result.root / "characters" / "customer")
        assert (result.root / "backgrounds" / "lock.json").exists()
        assert (result.root / "production_manifest.json").exists()
        assert (result.root / "audio_manifest.json").exists()
        seo_lock = json.loads((result.root / "characters" / "seo" / "lock.json").read_text(encoding="utf-8"))
        assert {"wide_closed", "wide_small", "wide_wide", "cry_closed", "cry_small", "cry_wide"} <= set(seo_lock["assets"])
        mouth_calls = [(name, references) for name, references in client.image_calls if "_small_source" in name or "_wide_source" in name]
        assert mouth_calls and all(len(references) == 2 for _name, references in mouth_calls)
        renderer = ProductionRenderer(result.root, ffmpeg, [])
        closed = renderer._actor_sprite("seo", "wide_closed", 500, "right")
        speaking = renderer._actor_sprite("seo", "wide_wide", 500, "right")
        assert speaking.size == closed.size
        assert speaking.tobytes() != closed.tobytes()
        lower = (0, 180, closed.width, closed.height)
        assert speaking.crop(lower).tobytes() == closed.crop(lower).tobytes()
