"""End-to-end script-to-locked-multi-shot production orchestration."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .audio_director import AudioDirector
from .paths import app_root, user_data_dir
from .production_assets import EXTRACTION_VERSION, CharacterBuilder, build_backgrounds, validate_character_lock
from .production_models import EpisodePlan, ProductionPlanError
from .production_renderer import ProductionRenderer
from .vertex_cloud import VertexStudioClient


PLAN_PROMPT = """You are the production planner for a Korean vertical 2D web-drama.
Return ONLY valid JSON, without Markdown. Plan 3 to 7 visually distinct shots and one to three recurring adult characters.
The total target duration is 10 to 24 seconds. Cut between speakers and reaction shots; never use continuous sideways scrolling.
Reuse the same location_id whenever shots happen in the same physical place so the background remains consistent.
Each actor position must be one of far_left,left,center_left,center,center_right,right,far_right.
Each actor state/motion must be selected from neutral,angry,crying,point,wave,show,bend,walk,recoil,idle.
Camera must be selected from wide,medium,closeup,reaction,push_in. Use a hard cut when switching speakers.
Dialogue must be natural Korean and short enough for the shot duration.
Choose meaningful ambience_tags, sfx_tags and music_tags from: rain,phone,door,footstep,impact,cloth,crowd,store,school,city,roomtone,tense,sad,angry,warm,mystery,chase.

JSON schema:
{
  "title":"Korean title",
  "synopsis":"short summary",
  "music_tags":["tense"],
  "characters":[{
    "id":"lowercase_id","name":"Korean name","role":"story role","age":"adult age",
    "gender":"woman/man","appearance":"specific face, hair and body description",
    "outfit":"specific outfit and colors","voice":"Kore"
  }],
  "shots":[{
    "id":"shot_01","duration":3.0,"location_id":"store","background_prompt":"specific empty location description",
    "camera":"medium","speaker_id":"character_id or empty","dialogue":"Korean dialogue","emotion":"angry",
    "actors":[{"character_id":"character_id","position":"left","state":"angry","motion":"point","facing":"right"}],
    "ambience_tags":["store"],"sfx_tags":["impact"],"transition":"cut"
  }]
}

Story/script:
"""


@dataclass(frozen=True, slots=True)
class ProductionResult:
    output: Path
    root: Path
    plan: EpisodePlan
    audio_catalog_size: int


class ProductionPipeline:
    def __init__(self, client: VertexStudioClient, ffmpeg_path: str, extra_audio_roots: list[Path] | None = None) -> None:
        self.client = client
        self.ffmpeg_path = ffmpeg_path
        self.audio_roots = [
            app_root() / "assets" / "music",
            app_root() / "assets" / "sfx",
            app_root() / "assets" / "audio_library",
            user_data_dir() / "AudioLibrary",
            *(extra_audio_roots or []),
        ]

    def _emit(self, progress, value: float, label: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, value)), label)

    def generate(self, script: str, *, progress=None) -> ProductionResult:
        episode_key = hashlib.sha256(script.strip().encode("utf-8")).hexdigest()[:14]
        root = user_data_dir() / "Productions" / episode_key
        root.mkdir(parents=True, exist_ok=True)
        self._emit(progress, 0.02, "Planning characters, performances and camera cuts")
        plan_path = root / "plan.json"
        if plan_path.exists():
            plan = EpisodePlan.from_json(plan_path.read_text(encoding="utf-8"))
        else:
            last_error: Exception | None = None
            plan = None
            correction = ""
            for _attempt in range(3):
                try:
                    plan = EpisodePlan.from_json(self.client.generate_text(PLAN_PROMPT + script.strip() + correction))
                    break
                except ProductionPlanError as exc:
                    last_error = exc
                    correction = f"\nPrevious JSON was rejected: {exc}. Return corrected JSON only."
            if plan is None:
                raise ProductionPlanError(f"Gemini could not produce a valid production plan: {last_error}")
            plan.save(plan_path)

        builder = CharacterBuilder(self.client, root)
        for index, character in enumerate(plan.characters):
            folder = root / "characters" / character.id
            start = 0.08 + 0.40 * index / len(plan.characters)
            span = 0.40 / len(plan.characters)
            state_directions: dict[str, str] = {}
            for shot in plan.shots:
                for actor in shot.actors:
                    if actor.character_id != character.id:
                        continue
                    base_direction = (
                        f"Story shot performance: emotion {shot.emotion}; body action {actor.motion}; "
                        f"acting state {actor.state}; facing {actor.facing}. Keep the action natural, balanced and readable."
                    )
                    if shot.speaker_id == character.id and shot.dialogue:
                        state_directions[f"{shot.id}_closed"] = base_direction + " Original lips naturally closed in a brief pause between words."
                        state_directions[f"{shot.id}_small"] = base_direction + " Original mouth slightly open for a soft Korean syllable."
                        state_directions[f"{shot.id}_wide"] = base_direction + " Original mouth naturally wider for a strong Korean syllable."
                    else:
                        state_directions[f"{shot.id}_still"] = base_direction + " Original mouth closed while listening or reacting."
            required = {"neutral", *state_directions}
            try:
                lock = validate_character_lock(folder)
                if not required.issubset(lock.assets):
                    raise RuntimeError("Locked character is missing required story states")
                extraction_marker = folder / "extraction_version.txt"
                if not extraction_marker.exists() or extraction_marker.read_text(encoding="ascii").strip() != EXTRACTION_VERSION:
                    raise RuntimeError("Locked character needs current chroma edge cleanup")
                mouth_states = {state for state in state_directions if state.endswith(("_small", "_wide"))}
                reference_manifest_path = folder / "reference_manifest.json"
                reference_manifest = (
                    json.loads(reference_manifest_path.read_text(encoding="utf-8"))
                    if reference_manifest_path.exists() else {}
                )
                image_model = getattr(getattr(self.client, "config", None), "image_model", "test-image")
                if any(reference_manifest.get(state, {}).get("model") != image_model for state in mouth_states):
                    raise RuntimeError("Locked mouth states need current exact-pose references")
                self._emit(progress, start + span, f"Reusing locked character: {character.name}")
            except (FileNotFoundError, OSError, ValueError, RuntimeError):
                self._emit(progress, start, f"Building and locking character: {character.name}")
                builder.build(
                    character,
                    required_states=required,
                    state_directions=state_directions,
                    progress=lambda part, label, s=start, w=span: self._emit(progress, s + w * part, label),
                )

        self._emit(progress, 0.49, "Building consistent story locations")
        backgrounds = build_backgrounds(
            self.client, plan, root,
            progress=lambda part, label: self._emit(progress, 0.49 + part * 0.12, label),
        )

        voices: dict[str, Path] = {}
        speaking_shots = [shot for shot in plan.shots if shot.dialogue and shot.speaker_id]
        character_map = {character.id: character for character in plan.characters}
        voice_manifest_path = root / "voices" / "lock.json"
        voice_manifest = (
            json.loads(voice_manifest_path.read_text(encoding="utf-8"))
            if voice_manifest_path.exists() else {}
        )
        client_config = getattr(self.client, "config", None)
        normal_tts_model = getattr(client_config, "tts_model", "test-tts")
        pro_tts_model = getattr(client_config, "tts_pro_model", normal_tts_model)
        complex_emotions = {"crying", "grief", "terrified", "desperate", "breakdown", "sobbing"}
        for index, shot in enumerate(speaking_shots):
            path = root / "voices" / f"{shot.id}.wav"
            character = character_map[shot.speaker_id]
            tts_model = pro_tts_model if shot.emotion in complex_emotions else normal_tts_model
            signature = {
                "model": tts_model,
                "voice": character.voice,
                "dialogue_sha256": hashlib.sha256(shot.dialogue.encode("utf-8")).hexdigest(),
                "emotion": shot.emotion,
            }
            if not path.exists() or voice_manifest.get(shot.id) != signature:
                self.client.generate_tts(
                    shot.dialogue,
                    path,
                    voice=character.voice,
                    style=f"natural Korean drama acting; emotion: {shot.emotion}; match the scene without exaggeration",
                    model=tts_model,
                )
                signature["model"] = getattr(self.client, "last_tts_model", tts_model)
                voice_manifest[shot.id] = signature
                voice_manifest_path.parent.mkdir(parents=True, exist_ok=True)
                voice_manifest_path.write_text(
                    json.dumps(voice_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            voices[shot.id] = path
            self._emit(progress, 0.61 + 0.10 * (index + 1) / max(1, len(speaking_shots)), f"Voicing shot {index + 1}/{len(speaking_shots)}")

        output = root / "AbrarDrama.mp4"
        renderer = ProductionRenderer(root, self.ffmpeg_path, self.audio_roots)
        renderer.render(
            plan, backgrounds, voices, script, output,
            progress=lambda part, label: self._emit(progress, 0.72 + part * 0.26, label),
        )
        catalog_size = AudioDirector(self.audio_roots).catalog_size
        manifest = {
            "episode_key": episode_key,
            "script_sha256": hashlib.sha256(script.strip().encode("utf-8")).hexdigest(),
            "plan": asdict(plan),
            "output": output.name,
            "audio_catalog_size": catalog_size,
        }
        (root / "production_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        self._emit(progress, 1.0, f"Finished {len(plan.shots)} shots with {len(plan.characters)} locked characters")
        return ProductionResult(output, root, plan, catalog_size)
