"""CPU-safe multi-shot renderer for locked complete-frame characters."""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import wave
from array import array
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .audio_director import AudioCue, AudioDirector
from .audio_mixer import mix_video_audio
from .production_assets import validate_character_lock
from .production_models import ActorPlan, EpisodePlan, ShotPlan


class ProductionRenderError(RuntimeError):
    pass


POSITION_X = {"far_left": 0.12, "left": 0.25, "center_left": 0.38, "center": 0.5,
              "center_right": 0.62, "right": 0.75, "far_right": 0.88}


def _font(size: int, bold: bool = True):
    candidates = [
        Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / max(1, wav.getframerate())


def _shot_duration(shot: ShotPlan, voice: Path | None) -> float:
    return max(shot.duration, (_wav_duration(voice) + 0.25) if voice else 0.0)


def _voice_levels(path: Path | None, frames: int, fps: int) -> list[float]:
    if not path or not path.exists():
        return [0.0] * frames
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        return [0.0] * frames
    samples = array("h"); samples.frombytes(raw)
    if channels > 1:
        samples = array("h", samples[::channels])
    per = max(1, round(rate / fps))
    values: list[float] = []
    for index in range(frames):
        segment = samples[index * per:(index + 1) * per]
        values.append(math.sqrt(sum(float(value) * value for value in segment) / len(segment)) if segment else 0.0)
    peak = max(values) or 1.0
    return [sum(values[max(0, i - 1):min(frames, i + 2)]) / len(values[max(0, i - 1):min(frames, i + 2)]) / peak for i in range(frames)]


def _mouth_state(level: float, previous: str, held: int) -> str:
    if held < 3:
        return previous
    if level < 0.055:
        return "neutral"
    if level < 0.32:
        return "talk_small"
    return "talk_wide"


def _subtitle(frame: Image.Image, text: str) -> None:
    if not text:
        return
    draw = ImageDraw.Draw(frame, "RGBA")
    font = _font(34)
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        if current and draw.textbbox((0, 0), trial, font=font)[2] > frame.width * 0.82:
            lines.append(current); current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    lines = lines[:2]
    height = len(lines) * 48 + 24
    y = frame.height - height - 56
    draw.rounded_rectangle((48, y - 12, frame.width - 48, y + height), radius=18, fill=(4, 5, 12, 174))
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font, stroke_width=2)
        x = (frame.width - (box[2] - box[0])) // 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=3, stroke_fill=(0, 0, 0, 210))
        y += 48


class ProductionRenderer:
    def __init__(self, root: Path, ffmpeg_path: str, audio_roots: list[Path]) -> None:
        self.root = root
        self.ffmpeg_path = ffmpeg_path
        self.audio_roots = audio_roots
        self._images: dict[Path, Image.Image] = {}

    def _ffmpeg(self) -> str:
        found = shutil.which(self.ffmpeg_path) or (self.ffmpeg_path if Path(self.ffmpeg_path).exists() else None)
        if not found:
            raise ProductionRenderError("FFmpeg was not found.")
        return found

    def _image(self, path: Path) -> Image.Image:
        if path not in self._images:
            self._images[path] = Image.open(path).convert("RGBA")
        return self._images[path]

    def _actor_sprite(self, character_id: str, state: str, height: int, facing: str) -> Image.Image:
        folder = self.root / "characters" / character_id
        lock = validate_character_lock(folder)
        state = state if state in lock.assets else "neutral"
        actor = self._image(folder / lock.assets[state]).copy()
        ratio = height / max(1, actor.height)
        actor = actor.resize((max(1, round(actor.width * ratio)), height), Image.Resampling.LANCZOS)
        # Speaking variants are AI-drawn full characters so the mouth is part of
        # the original face, not a synthetic oval pasted over it. Keep the locked
        # closed-pose body pixel-stable and feather in only the variant face;
        # otherwise tiny regenerated outfit/hand details shimmer at 24 FPS.
        if state.endswith(("_small", "_wide")):
            closed_state = f"{state.rsplit('_', 1)[0]}_closed"
            if closed_state in lock.assets:
                base_source = self._image(folder / lock.assets[closed_state]).copy()
                base_ratio = height / max(1, base_source.height)
                base = base_source.resize(
                    (max(1, round(base_source.width * base_ratio)), height), Image.Resampling.LANCZOS
                )

                def head_center(image: Image.Image) -> float:
                    alpha = image.getchannel("A")
                    scan_height = max(1, round(image.height * 0.18))
                    centers: list[float] = []
                    for y in range(scan_height):
                        row = alpha.crop((0, y, alpha.width, y + 1)).getbbox()
                        if row:
                            centers.append((row[0] + row[2]) / 2.0)
                    return sum(centers) / len(centers) if centers else image.width / 2.0

                aligned = Image.new("RGBA", base.size, (0, 0, 0, 0))
                offset_x = round(head_center(base) - head_center(actor))
                aligned.alpha_composite(actor, (offset_x, 0))
                center_x = round(head_center(base))
                center_y = round(height * 0.145)
                radius_x = round(height * 0.095)
                radius_y = round(height * 0.090)
                mask = Image.new("L", base.size, 0)
                ImageDraw.Draw(mask).ellipse(
                    (center_x - radius_x, center_y - radius_y, center_x + radius_x, center_y + radius_y),
                    fill=255,
                )
                mask = mask.filter(ImageFilter.GaussianBlur(max(2, round(height * 0.006))))
                actor = Image.composite(aligned, base, mask)
        if facing == "left":
            actor = ImageOps.mirror(actor)
        return actor

    def _actor_state(self, actor: ActorPlan, shot: ShotPlan, speaking: bool, level: float, previous: str, held: int) -> str:
        if speaking:
            if held < 3:
                return previous
            if level < 0.055:
                return f"{shot.id}_closed"
            if level < 0.32:
                return f"{shot.id}_small"
            return f"{shot.id}_wide"
        return f"{shot.id}_still"

    def _render_shot(self, shot: ShotPlan, background: Path, voice: Path | None, output: Path, progress=None) -> Path:
        ffmpeg = self._ffmpeg()
        width, height, fps = 720, 1280, 24
        duration = _shot_duration(shot, voice)
        total = max(1, math.ceil(duration * fps))
        levels = _voice_levels(voice, total, fps)
        frames_dir = output.parent / f"{output.stem}_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        bg = ImageOps.fit(self._image(background).convert("RGB"), (width, height), Image.Resampling.LANCZOS)
        previous: dict[str, str] = {actor.character_id: "neutral" for actor in shot.actors}
        held: dict[str, int] = {actor.character_id: 99 for actor in shot.actors}
        for frame_index in range(total):
            t = frame_index / fps
            progress_ratio = frame_index / max(1, total - 1)
            canvas = bg.copy().convert("RGBA")
            for actor_index, actor in enumerate(shot.actors):
                speaking = actor.character_id == shot.speaker_id and bool(shot.dialogue)
                state = self._actor_state(actor, shot, speaking, levels[frame_index], previous[actor.character_id], held[actor.character_id])
                held[actor.character_id] = held[actor.character_id] + 1 if state == previous[actor.character_id] else 0
                previous[actor.character_id] = state
                target_h = round(height * (0.78 if shot.camera in {"wide", "establishing"} else 0.88))
                sprite = self._actor_sprite(actor.character_id, state, target_h, actor.facing)
                x_ratio = POSITION_X.get(actor.position, 0.5)
                x = round(width * x_ratio - sprite.width / 2)
                # Smooth independent movement. Complete drawings preserve anatomy;
                # motion curves only translate/scale the locked frame.
                phase = t * (1.05 + actor_index * 0.13) + actor_index * 0.7
                bob = math.sin(phase * math.pi * 2) * 1.4
                if actor.motion in {"walk", "walk_normal"}:
                    direction = -1 if actor.facing == "left" else 1
                    x += round(direction * width * 0.16 * (progress_ratio - 0.5))
                    bob += abs(math.sin(t * 7.2 * math.pi)) * -3.0
                elif actor.motion in {"recoil", "step_back"}:
                    x += round(math.sin(min(1.0, progress_ratio * 4) * math.pi) * -18)
                elif shot.emotion == "crying":
                    x += round(math.sin(t * 17.0) * 0.7)
                    bob += abs(math.sin(t * 3.2)) * 1.2
                y = round(height * 0.965 - sprite.height + bob)
                canvas.alpha_composite(sprite, (x, y))
            # Stable cinematic reframing replaces the old continuous scrolling.
            zoom_start = 1.0
            zoom_end = 1.065 if shot.camera in {"push_in", "closeup", "close", "reaction"} else 1.018
            zoom = zoom_start + (zoom_end - zoom_start) * (progress_ratio * progress_ratio * (3 - 2 * progress_ratio))
            if zoom > 1.001:
                enlarged = canvas.resize((round(width * zoom), round(height * zoom)), Image.Resampling.LANCZOS)
                focus = next((a for a in shot.actors if a.character_id == shot.speaker_id), shot.actors[0] if shot.actors else None)
                focus_x = POSITION_X.get(focus.position, 0.5) if focus else 0.5
                left = round((enlarged.width - width) * focus_x)
                top = round((enlarged.height - height) * 0.42)
                canvas = enlarged.crop((left, top, left + width, top + height))
            vignette = Image.new("L", (width, height), 0)
            ImageDraw.Draw(vignette).rectangle((0, 0, width, height), outline=105, width=36)
            shade = Image.new("RGBA", (width, height), (0, 0, 0, 0)); shade.putalpha(vignette.filter(ImageFilter.GaussianBlur(24)))
            canvas = Image.alpha_composite(canvas, shade)
            _subtitle(canvas, shot.dialogue)
            canvas.convert("RGB").save(frames_dir / f"frame_{frame_index:05d}.jpg", quality=93)
            if progress and frame_index % 24 == 0:
                progress(frame_index / total, f"Rendering {shot.id}: {frame_index}/{total}")
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "frame_%05d.jpg")]
        if voice:
            command += ["-i", str(voice), "-af", "apad"]
        else:
            command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        command += ["-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=360)
        if result.returncode:
            raise ProductionRenderError(result.stderr[-2000:])
        return output

    def render(self, plan: EpisodePlan, backgrounds: dict[str, Path], voices: dict[str, Path], script: str, output: Path, progress=None) -> Path:
        temp = self.root / "render_work"
        clips = temp / "clips"; clips.mkdir(parents=True, exist_ok=True)
        clip_paths: list[Path] = []
        for index, shot in enumerate(plan.shots):
            if progress:
                progress(index / max(1, len(plan.shots)), f"Rendering shot {index + 1}/{len(plan.shots)}")
            clip = clips / f"{index:03d}_{shot.id}.mp4"
            self._render_shot(shot, backgrounds[shot.location_id], voices.get(shot.id), clip)
            clip_paths.append(clip)
        concat = temp / "concat.txt"
        concat.write_text("\n".join(f"file '{path.as_posix()}'" for path in clip_paths), encoding="utf-8")
        base = temp / "picture_dialogue.mp4"
        result = subprocess.run([
            self._ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c", "copy", str(base),
        ], capture_output=True, text=True, timeout=360)
        if result.returncode:
            raise ProductionRenderError(result.stderr[-2000:])
        director = AudioDirector(self.audio_roots)
        rendered_duration = sum(_shot_duration(shot, voices.get(shot.id)) for shot in plan.shots)
        cues = [cue for cue in director.plan(script, rendered_duration, music_tags=plan.music_tags) if cue.role == "music"]
        timeline = 0.0
        for shot in plan.shots:
            duration = _shot_duration(shot, voices.get(shot.id))
            shot_cues = director.plan(
                shot.dialogue + " " + shot.background_prompt,
                duration,
                ambience_tags=shot.ambience_tags,
                sfx_tags=shot.sfx_tags,
            )
            for cue in shot_cues:
                if cue.role == "music":
                    continue
                cues.append(AudioCue(cue.role, cue.path, timeline + cue.start_seconds, cue.gain_db, cue.tags))
            timeline += duration
        (self.root / "audio_manifest.json").write_text(
            json.dumps(
                {
                    "catalog_size": director.catalog_size,
                    "duration_seconds": rendered_duration,
                    "cues": [
                        {
                            "role": cue.role,
                            "file": cue.path.name,
                            "start_seconds": round(cue.start_seconds, 3),
                            "gain_db": cue.gain_db,
                            "tags": cue.tags,
                        }
                        for cue in cues
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        return mix_video_audio(base, cues, output, self.ffmpeg_path)
