from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import wave
from array import array
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .acting import ActingPose, actor_pose
from .alignment import alignment_at, build_alignment, load_alignment
from .constants import POSITION_X
from .gemini_tts import GeminiTTSClient
from .limited_animation import frame_path as sequence_frame_path, sequence_name
from .models import ActorCue, Episode, SFXCue, Shot
from .project import StudioProject
from .puppet import ArticulatedPuppetRenderer, footstep_times, normalize_motion, uses_articulated_motion
from .visemes import viseme_shape


class RenderError(RuntimeError):
    pass


ProgressFn = Callable[[int, str], None]


def _font(size: int, bold: bool = False):
    candidates: list[Path] = []
    if os.name == "nt":
        candidates += [
            Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/NanumGothicBold.ttf" if bold else "C:/Windows/Fonts/NanumGothic.ttf"),
        ]
    candidates += [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        if current and draw.textbbox((0, 0), trial, font=font)[2] > max_width:
            lines.append(current)
            current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or [""]


def _transparent_white(image: Image.Image) -> Image.Image:
    """Remove connected-looking light paper while preserving skin and clothing."""
    rgba = image.convert("RGBA")
    alpha_min, _alpha_max = rgba.getchannel("A").getextrema()
    if alpha_min < 255:
        return rgba
    px = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, original_alpha = px[x, y]
            brightness = (r + g + b) / 3.0
            saturation = max(r, g, b) - min(r, g, b)
            if brightness >= 232 and saturation < 30:
                computed = 0
            elif brightness > 207 and saturation < 21:
                computed = int(max(0, min(255, (232 - brightness) / 25 * 255)))
            else:
                computed = 255
            px[x, y] = (r, g, b, min(original_alpha, computed))
    return rgba


def _wav_duration(path: Path | None) -> float:
    if not path or not path.exists():
        return 0.0
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / max(1, wf.getframerate())
    except wave.Error:
        return 0.0


def _wav_envelope(path: Path | None, fps: int, duration: float) -> list[float]:
    frames = max(1, round(duration * fps))
    if not path or not path.exists():
        return [0.0] * frames
    try:
        with wave.open(str(path), "rb") as wf:
            channels, width, rate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        if width != 2:
            return [0.0] * frames
        samples = array("h")
        samples.frombytes(raw)
        if channels > 1:
            samples = array("h", samples[::channels])
        per = max(1, int(rate / fps))
        env: list[float] = []
        for i in range(frames):
            segment = samples[i * per:(i + 1) * per]
            if not segment:
                env.append(0.0)
            else:
                rms = math.sqrt(sum(float(v) * v for v in segment) / len(segment)) / 32768.0
                env.append(min(1.0, rms * 7.0))
        return env
    except (wave.Error, OSError):
        return [0.0] * frames


def _text_mouth(text: str, frame: int, fps: int, duration: float) -> float:
    if not text:
        return 0.0
    t = frame / fps
    if t < 0.15 or t > duration - 0.18:
        return 0.0
    speed = max(3.7, min(7.2, len(text) / max(0.8, duration) * 0.75))
    phase = t * speed
    idx = min(len(text) - 1, int(t / duration * len(text)))
    if text[idx] in " ,.?!…\n":
        return 0.0
    return max(0.0, math.sin(math.pi * (phase % 1.0)))


class AnimaticRenderer:
    """Deterministic Korean limited-animation renderer.

    Approved complete-frame loops are preferred over articulated cutouts.  This keeps
    anatomy and line work intact while still supporting basic walking, talking,
    blinking, expression swaps, camera moves and layered sound on CPU-only PCs.
    """

    def __init__(self, project: StudioProject, ffmpeg_path: str = "ffmpeg", *, video_preset: str = "medium", crf: int = 17) -> None:
        self.project = project
        self.ffmpeg_path = ffmpeg_path
        self.video_preset = video_preset
        self.crf = max(0, min(51, int(crf)))
        self._asset_cache: dict[Path, Image.Image] = {}
        self._transparent_cache: dict[Path, Image.Image] = {}
        self._scene_cache: dict[tuple, Image.Image] = {}
        self._vignette_cache: dict[tuple[int, int, int], Image.Image] = {}
        self._subtitle_cache: dict[tuple, Image.Image] = {}
        self._alignment_cache: dict[Path, list] = {}
        self._puppet = ArticulatedPuppetRenderer()

    def render(self, episode: Episode, output_path: Path, progress: ProgressFn | None = None) -> Path:
        ffmpeg = self._find_ffmpeg()
        temp = self.project.temp_dir / f"render_{episode.episode_id}"
        shutil.rmtree(temp, ignore_errors=True)
        clips = temp / "clips"
        clips.mkdir(parents=True, exist_ok=True)
        shots = [s for scene in episode.scenes for s in scene.shots]
        clip_paths: list[Path] = []
        for index, shot in enumerate(shots, 1):
            if progress:
                progress(int((index - 1) / max(1, len(shots)) * 88), f"Rendering {shot.id}")
            clip = clips / f"{index:04d}_{shot.id}.mp4"
            self._render_shot(ffmpeg, episode, shot, clip)
            clip_paths.append(clip)
        concat = temp / "concat.txt"
        concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in clip_paths), encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if progress:
            progress(92, "Joining and mastering episode")
        self._run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat),
            "-vf", f"fps={episode.fps},format=yuv420p", "-r", str(episode.fps),
            "-c:v", "libx264", "-preset", self.video_preset, "-crf", str(self.crf),
            "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
            "-movflags", "+faststart", str(output_path),
        ])
        if progress:
            progress(100, "720p production master complete")
        return output_path

    def preview_frame(self, episode: Episode, shot: Shot, at: float = 0.45) -> Image.Image:
        frames = max(1, round(shot.duration * episode.fps))
        index = min(frames - 1, max(0, round(frames * at)))
        return self._frame(episode, shot, index, frames, 0.45 if shot.dialogue else 0.0, "open")

    def _find_ffmpeg(self) -> str:
        candidate = Path(self.ffmpeg_path)
        if candidate.is_file():
            return str(candidate)
        bundled = Path(__file__).resolve().parent.parent / "tools" / "ffmpeg.exe"
        if bundled.exists():
            return str(bundled)
        found = shutil.which(self.ffmpeg_path) or shutil.which("ffmpeg")
        if not found:
            raise RenderError("FFmpeg was not found. Run INSTALL_ABRAR_STUDIO.bat or select ffmpeg.exe in Settings.")
        return found

    def _voice_path(self, shot: Shot) -> Path | None:
        speaker = shot.speaker_id
        if not shot.dialogue or not speaker:
            return None
        char = self.project.character(speaker)
        request = GeminiTTSClient.build_request(char, shot)
        path = self.project.voice_cache_path(speaker, request.cache_key)
        return path if path.exists() else None

    def _alignment(self, shot: Shot, voice: Path | None) -> list:
        speaker = shot.speaker_id
        if not voice or not speaker or not shot.dialogue:
            return []
        char = self.project.character(speaker)
        request = GeminiTTSClient.build_request(char, shot)
        path = self.project.alignment_cache_path(speaker, request.cache_key)
        if not path.exists():
            build_alignment(shot.dialogue, voice, path)
        if path not in self._alignment_cache:
            self._alignment_cache[path] = load_alignment(path)
        return self._alignment_cache[path]

    def _render_shot(self, ffmpeg: str, episode: Episode, shot: Shot, clip: Path) -> None:
        voice = self._voice_path(shot)
        duration = max(shot.duration, _wav_duration(voice) + 0.35 if voice else 0.0)
        visual = clip.with_suffix(".visual.mp4")
        audio = clip.with_suffix(".audio.m4a")
        self._render_visual(ffmpeg, episode, shot, visual, duration, voice)
        self._render_audio(ffmpeg, shot, audio, duration, voice)
        self._run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(visual), "-i", str(audio),
            "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(clip),
        ])

    def _render_visual(self, ffmpeg: str, episode: Episode, shot: Shot, output: Path, duration: float, voice: Path | None) -> None:
        width, height = episode.resolution
        frames = max(1, round(duration * episode.fps))
        envelope = _wav_envelope(voice, episode.fps, duration)
        alignment = self._alignment(shot, voice)
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", str(episode.fps), "-i", "-", "-an",
            "-c:v", "libx264", "-preset", self.video_preset, "-crf", str(self.crf), "-pix_fmt", "yuv420p", str(output),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for frame_index in range(frames):
                amp = envelope[frame_index] if frame_index < len(envelope) else 0.0
                if voice is None:
                    amp = _text_mouth(shot.dialogue, frame_index, episode.fps, duration)
                frame_time = frame_index / episode.fps
                if alignment:
                    shape = alignment_at(alignment, frame_time, amp)
                else:
                    shape = viseme_shape(shot.dialogue, frame_index / max(1, frames - 1), amp)
                frame = self._frame(episode, shot, frame_index, frames, amp, shape)
                proc.stdin.write(frame.convert("RGB").tobytes())
            proc.stdin.close()
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            if proc.stderr:
                proc.stderr.close()
            code = proc.wait()
            if code:
                raise RenderError(stderr.strip() or "FFmpeg visual encoder failed")
        except Exception:
            proc.kill()
            raise

    def _background(self, shot: Shot, size: tuple[int, int]) -> Image.Image:
        width, height = size
        path = self._resolve("backgrounds", shot.background)
        if path:
            source = self._load(path).convert("RGB")
            scale = max(width / source.width, height / source.height)
            source = source.resize((math.ceil(source.width * scale), math.ceil(source.height * scale)), Image.Resampling.LANCZOS)
            x, y = (source.width - width) // 2, (source.height - height) // 2
            return source.crop((x, y, x + width, y + height))
        base = Image.new("RGB", size, (12, 16, 30))
        draw = ImageDraw.Draw(base)
        for y in range(height):
            ratio = y / max(1, height - 1)
            draw.line((0, y, width, y), fill=(int(12 + 20 * ratio), int(16 + 15 * ratio), int(30 + 35 * ratio)))
        return base

    def _frame(self, episode: Episode, shot: Shot, i: int, total: int, mouth_amp: float, mouth_shape: str = "closed") -> Image.Image:
        width, height = episode.resolution
        t = i / episode.fps
        progress = i / max(1, total - 1)
        scene_key = (shot.background or "", width, height, shot.emotion.lower(), shot.emotion_level)
        if scene_key not in self._scene_cache:
            self._scene_cache[scene_key] = self._grade(self._background(shot, (width, height)).convert("RGBA"), shot)
        scene = self._scene_cache[scene_key].copy()
        self._ambient_vfx(scene, shot, t, i)

        actors = sorted(shot.actors, key=lambda item: item.depth)
        for index, actor in enumerate(actors):
            self._draw_actor(scene, shot, actor, index, t, progress, mouth_amp, mouth_shape)

        self._dramatic_vfx(scene, shot, t, progress)
        self._transition_vfx(scene, shot, t, total / episode.fps)
        scene = self._camera(scene, shot, t, progress, i)
        self._subtitle(scene, shot)
        return scene.convert("RGB")

    def _draw_actor(self, scene: Image.Image, shot: Shot, cue: ActorCue, index: int, t: float, progress: float, mouth_amp: float, mouth_shape: str) -> None:
        width, height = scene.size
        char = self.project.character(cue.character_id)
        root = self.project.character_manifest_path(cue.character_id).parent
        close = cue.pose in {"portrait", "close", "closeup"} or cue.pose not in char.poses
        animation_name = None if close else sequence_name(char, cue.motion, cue.acting)
        complete_frames = animation_name is not None
        articulated = bool(char.articulated_rig) and not close and not complete_frames and uses_articulated_motion(cue.motion, cue.acting)
        speaking = cue.speaking and cue.character_id == shot.speaker_id

        if complete_frames:
            sequence = char.animations[animation_name]
            asset_path = sequence_frame_path(root, sequence, t, cue.motion_speed, cue.cycle_offset)
            if asset_path not in self._transparent_cache:
                self._transparent_cache[asset_path] = _transparent_white(self._load(asset_path))
            actor = self._transparent_cache[asset_path].copy()
            if speaking and char.mouth_anchor and char.mouths:
                shape = mouth_shape if mouth_shape in char.mouths else ("closed" if mouth_amp < 0.18 else "open")
                patch = self._load(root / char.mouths[shape]).convert("RGBA")
                alpha = patch.getchannel("A").point(lambda value: 0 if value < 72 else min(255, int((value - 72) * 1.4)))
                patch.putalpha(alpha)
                bbox = patch.getbbox()
                if bbox:
                    patch = patch.crop(bbox)
                    desired_w = max(10, int(actor.width * (0.028 if shape == "closed" else 0.034)))
                    ratio = desired_w / max(1, patch.width)
                    patch = patch.resize((desired_w, max(2, int(patch.height * ratio))), Image.Resampling.LANCZOS)
                    anchor_x, anchor_y = char.mouth_anchor
                    actor.alpha_composite(patch, (int(actor.width * anchor_x - patch.width / 2), int(actor.height * anchor_y - patch.height / 2)))
            visible = actor.getbbox()
            if visible:
                actor = actor.crop(visible)
        elif articulated:
            motion = normalize_motion(cue.motion, cue.acting)
            facing = cue.facing.lower()
            if facing not in {"left", "right"}:
                facing = "left" if cue.travel_x < 0 else "right"
            actor = self._puppet.render(
                root / char.articulated_rig,
                motion=motion,
                t=t,
                progress=progress,
                speed=cue.motion_speed,
                cycle_offset=cue.cycle_offset,
                intensity=cue.motion_intensity,
                facing=facing,
            )
        else:
            if close:
                rel = char.expressions.get(cue.expression, char.expressions.get("neutral", char.portrait))
            else:
                rel = char.poses.get(cue.pose, char.poses.get("full_front", char.full_front))
            asset_path = root / rel
            if asset_path not in self._transparent_cache:
                source = self._load(asset_path)
                if close and source.width > 12 and source.height > 12:
                    source = source.crop((4, 4, source.width - 4, source.height - 4))
                self._transparent_cache[asset_path] = _transparent_white(source)
            actor = self._transparent_cache[asset_path].copy()
            if close:
                actor = self._facial_overlays(actor, root, char, shot, cue, t, mouth_amp if speaking else 0.0, mouth_shape if speaking else "closed", index)

        target_h = int(height * (0.88 if not close else 0.73) * cue.scale)
        ratio = target_h / max(1, actor.height)
        target_w = int(actor.width * ratio)
        max_width = int(width * (0.52 if articulated else (0.48 if len(shot.actors) > 1 else 0.58)))
        if target_w > max_width:
            ratio *= max_width / target_w
            target_w = max_width
            target_h = int(actor.height * ratio)
        actor = actor.resize((max(1, target_w), max(1, target_h)), Image.Resampling.LANCZOS)
        if cue.mirror and not articulated:
            actor = ImageOps.mirror(actor)

        # Approved hand/gesture cut-ins remain available for non-locomotion acting.
        if not articulated and cue.gesture not in {"", "none"} and cue.gesture in char.gestures:
            gesture_path = root / char.gestures[cue.gesture]
            if gesture_path not in self._transparent_cache:
                self._transparent_cache[gesture_path] = _transparent_white(self._load(gesture_path))
            gesture = self._transparent_cache[gesture_path].copy()
            gw = max(38, int(actor.width * (0.27 if close else 0.29)))
            gr = gw / max(1, gesture.width)
            gesture = gesture.resize((gw, max(1, int(gesture.height * gr))), Image.Resampling.LANCZOS)
            canvas_w = actor.width + int(gesture.width * 0.34)
            canvas_h = max(actor.height, int(actor.height * 0.80) + gesture.height)
            canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            actor_x = 0 if cue.position in {"left", "far_left", "center_left"} else canvas_w - actor.width
            canvas.alpha_composite(actor, (actor_x, 0))
            gx = canvas_w - gesture.width if actor_x == 0 else 0
            gy = int(actor.height * (0.68 if close else 0.46))
            canvas.alpha_composite(gesture, (gx, gy))
            actor = canvas

        # Complete drawings are held cleanly.  Only tiny whole-body offsets are used;
        # limbs are never independently rotated or warped.
        pose = ActingPose() if (articulated or complete_frames) else actor_pose(shot, cue, t, progress, index)
        gaze_shift = {"left": -2.2, "right": 2.2, "down": 0.8, "away": -1.6}.get(cue.gaze, 0.0)
        actor = actor.resize((max(1, int(actor.width * pose.scale)), max(1, int(actor.height * pose.scale))), Image.Resampling.LANCZOS)
        actor = actor.rotate(pose.rotation + gaze_shift * 0.25, resample=Image.Resampling.BICUBIC, expand=True)
        if cue.opacity < 0.999:
            alpha = actor.getchannel("A").point(lambda value: int(value * cue.opacity))
            actor.putalpha(alpha)

        x_ratio = POSITION_X.get(cue.position, 0.75)
        travel_ease = progress * progress * (3.0 - 2.0 * progress)
        travel_amount = cue.travel_x
        if complete_frames and abs(travel_amount) < 0.01:
            facing = cue.facing.lower()
            travel_amount = -0.14 if facing == "left" else 0.14
        travel = travel_amount * width * travel_ease if (articulated or complete_frames) else 0.0
        x = int(width * x_ratio - actor.width / 2 + pose.dx + gaze_shift + travel)
        ground_line = int(height * cue.ground_y) if (articulated or complete_frames) else height - 34
        y = int(ground_line - actor.height + pose.dy)

        # Soft contact shadow anchors cutouts and follows the moving feet.
        shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow, "RGBA")
        shadow_w = max(45, int(actor.width * (0.46 if (articulated or complete_frames) else 0.58)))
        shadow_h = 18 if (articulated or complete_frames) else 26
        sd.ellipse((x + actor.width // 2 - shadow_w // 2, ground_line - shadow_h // 2,
                    x + actor.width // 2 + shadow_w // 2, ground_line + shadow_h // 2), fill=(0, 0, 0, 72))
        scene.alpha_composite(shadow)
        scene.alpha_composite(actor, (x, y))

    def _facial_overlays(self, actor: Image.Image, root: Path, char, shot: Shot, cue: ActorCue, t: float, mouth_amp: float, mouth_shape: str, index: int) -> Image.Image:
        out = actor.copy()
        # Intense expression cards already contain carefully drawn shouting/crying mouths.
        # Overlaying a generic mouth on those cards creates a visible double-mouth artifact,
        # so viseme overlays are restricted to the restrained expression set.
        overlay_safe = cue.expression in {"neutral", "sad", "suspicious", "embarrassed"}
        if cue.speaking and shot.dialogue and char.mouths and overlay_safe:
            shape = mouth_shape if mouth_shape in char.mouths else ("closed" if mouth_amp < 0.16 else ("open" if mouth_amp < 0.78 else "wide"))
            patch = self._load(root / char.mouths[shape]).convert("RGBA")
            # Remove the almost-transparent rectangular matte left by sheet extraction.
            alpha = patch.getchannel("A").point(lambda value: 0 if value < 72 else min(255, int((value - 72) * 1.4)))
            patch.putalpha(alpha)
            bbox = patch.getbbox()
            if bbox:
                patch = patch.crop(bbox)
            desired_w = max(14, int(out.width * (0.145 if shape not in {"wide", "round"} else 0.175)))
            ratio = desired_w / max(1, patch.width)
            stretch_y = 0.88 + min(1.0, mouth_amp) * 0.16
            patch = patch.resize((desired_w, max(2, int(patch.height * ratio * stretch_y))), Image.Resampling.LANCZOS)
            x, y = int(out.width * 0.505 - patch.width / 2), int(out.height * 0.658 - patch.height / 2)
            out.alpha_composite(patch, (x, y))

        blink_phase = (t + index * 0.83) % (3.4 + index * 0.35)
        blink = blink_phase < 0.10 or (2.02 < blink_phase < 2.08 and shot.emotion.lower() in {"fear", "shock"})
        draw = ImageDraw.Draw(out, "RGBA")
        if blink and cue.expression not in {"smile", "breakdown"}:
            skin = out.getpixel((max(1, out.width // 2), max(1, int(out.height * 0.52))))[:3]
            eye_y = int(out.height * 0.40)
            for eye_x in (int(out.width * 0.37), int(out.width * 0.64)):
                draw.ellipse((eye_x - 13, eye_y - 7, eye_x + 13, eye_y + 7), fill=(*skin, 245))
                draw.arc((eye_x - 13, eye_y - 5, eye_x + 13, eye_y + 8), 195, 345, fill=(45, 30, 34, 230), width=2)
        emotion = shot.emotion.lower()
        if emotion in {"crying", "breakdown", "sad"} and shot.emotion_level >= 3:
            for eye_x in (int(out.width * 0.40), int(out.width * 0.62)):
                drop = 4 + int((t * 32 + eye_x) % 18)
                draw.ellipse((eye_x - 2, int(out.height * 0.45) + drop, eye_x + 4, int(out.height * 0.45) + drop + 13), fill=(125, 205, 255, 180))
        if emotion in {"embarrassed", "romantic", "love"}:
            y = int(out.height * 0.52)
            draw.ellipse((int(out.width * 0.25), y, int(out.width * 0.43), y + 18), fill=(255, 115, 145, 55))
            draw.ellipse((int(out.width * 0.58), y, int(out.width * 0.76), y + 18), fill=(255, 115, 145, 55))
        return out

    def _grade(self, image: Image.Image, shot: Shot) -> Image.Image:
        emotion = shot.emotion.lower()
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        color = {
            "fear": (22, 50, 95, 40), "shock": (90, 40, 120, 32), "anger": (150, 15, 25, 28),
            "crying": (40, 65, 120, 30), "sad": (45, 65, 100, 25), "romantic": (150, 45, 90, 22),
            "comedy": (235, 180, 50, 16), "determined": (30, 75, 120, 20),
        }.get(emotion, (20, 15, 45, 18))
        ImageDraw.Draw(overlay).rectangle((0, 0, *image.size), fill=color)
        out = Image.alpha_composite(image, overlay)
        return ImageEnhance.Contrast(out).enhance(1.06)

    def _ambient_vfx(self, image: Image.Image, shot: Shot, t: float, frame: int) -> None:
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        rng = random.Random(hash(shot.id) + frame // 3)
        for _ in range(42):
            x, y = rng.randrange(width), rng.randrange(height)
            alpha = rng.randrange(3, 11)
            draw.point((x, y), fill=(255, 255, 255, alpha))
        cues = [cue.cue for cue in shot.sfx]
        emotion = shot.emotion.lower()
        if "speed_lines" in shot.vfx:
            center_x = width * POSITION_X.get(shot.position, 0.72)
            center_y = height * 0.42
            for angle in range(0, 360, 24):
                rad = math.radians(angle)
                draw.line((center_x + math.cos(rad) * 250, center_y + math.sin(rad) * 150,
                           center_x + math.cos(rad) * 620, center_y + math.sin(rad) * 380), fill=(255, 255, 255, 16), width=2)
        if emotion == "anger" and shot.emotion_level >= 4:
            center_x = width * POSITION_X.get(shot.position, 0.72)
            center_y = height * 0.42
            for angle in range(0, 360, 30):
                rad = math.radians(angle)
                draw.line((center_x, center_y, center_x + math.cos(rad) * width, center_y + math.sin(rad) * width), fill=(255, 55, 55, 16), width=2)
        if any("rain" in cue for cue in cues) or "rain" in shot.vfx:
            for _ in range(25):
                x, y = rng.randrange(width), rng.randrange(height)
                draw.line((x, y, x - 5, y + 18), fill=(175, 210, 255, 35), width=1)

    def _dramatic_vfx(self, image: Image.Image, shot: Shot, t: float, progress: float) -> None:
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        emotion, level = shot.emotion.lower(), shot.emotion_level
        cues = [cue.cue for cue in shot.sfx]
        if any("scanner" in cue for cue in cues) or (shot.music and "scanner" in shot.music) or "scanner" in shot.vfx:
            y = int((t * 260) % height)
            draw.rectangle((0, y - 2, width, y + 2), fill=(170, 90, 255, 110))
            draw.rectangle((0, y - 20, width, y + 20), fill=(120, 70, 255, 15))
        if "glitch" in shot.vfx:
            rng = random.Random(int(t * 18) + hash(shot.id))
            for _ in range(3):
                y = rng.randrange(height)
                draw.rectangle((0, y, width, y + rng.randrange(2, 10)), fill=(90, 45, 180, rng.randrange(6, 18)))
        if emotion in {"shock", "shocked"} and progress < 0.10:
            alpha = int(150 * (1 - progress / 0.10))
            draw.rectangle((0, 0, width, height), fill=(255, 255, 255, alpha))
        strength = 106 if level >= 4 else 72
        key = (width, height, strength)
        darkness = self._vignette_cache.get(key)
        if darkness is None:
            vignette = Image.new("L", (width, height), 0)
            vd = ImageDraw.Draw(vignette)
            vd.ellipse((-width * 0.15, -height * 0.35, width * 1.15, height * 1.35), fill=255)
            vignette = vignette.filter(ImageFilter.GaussianBlur(int(min(width, height) * 0.14)))
            darkness = Image.new("RGBA", (width, height), (0, 0, 0, strength))
            darkness.putalpha(Image.eval(vignette, lambda value: 255 - value))
            self._vignette_cache[key] = darkness
        image.alpha_composite(darkness)

    def _transition_vfx(self, image: Image.Image, shot: Shot, t: float, duration: float) -> None:
        transition = shot.transition.lower()
        if transition == "cut":
            return
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        fade = 0.22
        alpha = 0
        color = (0, 0, 0)
        if transition in {"fade", "dip_black"}:
            if t < fade:
                alpha = int(255 * (1 - t / fade))
            elif duration - t < fade:
                alpha = int(255 * (1 - (duration - t) / fade))
        elif transition == "flash" and t < 0.15:
            alpha = int(210 * (1 - t / 0.15))
            color = (255, 255, 255)
        elif transition == "whip" and t < 0.12:
            alpha = int(95 * (1 - t / 0.12))
            color = (230, 230, 255)
        if alpha > 0:
            draw.rectangle((0, 0, width, height), fill=(*color, min(255, max(0, alpha))))

    def _camera(self, image: Image.Image, shot: Shot, t: float, progress: float, frame: int) -> Image.Image:
        width, height = image.size
        camera = shot.camera.lower()
        zoom, dx, dy = 1.0, 0.0, 0.0
        ease = progress * progress * (3 - 2 * progress)
        if "push" in camera:
            zoom = 1.0 + 0.075 * ease
        if "pull" in camera:
            zoom = 1.075 - 0.075 * ease
        if "pan_left" in camera:
            dx = 22 * (1 - 2 * ease)
        if "pan_right" in camera:
            dx = -22 * (1 - 2 * ease)
        if "tracking" in camera:
            moving = [actor for actor in shot.actors if abs(actor.travel_x) > 0.001]
            if moving:
                average = sum(actor.travel_x for actor in moving) / len(moving)
                dx += max(-width * 0.055, min(width * 0.055, -average * width * ease * 0.08))
                zoom = max(zoom, 1.065 if "push" not in camera else 1.075 + 0.025 * ease)
        if "handheld" in camera:
            dx += math.sin(t * 6.1) * 1.7
            dy += math.sin(t * 7.4 + 1.2) * 1.2
            zoom = max(zoom, 1.008)
        if "shake" in camera:
            rng = random.Random(frame * 9973)
            dx = rng.uniform(-7, 7) * (1 - progress)
            dy = rng.uniform(-5, 5) * (1 - progress)
            zoom = 1.025
        if (dx or dy) and zoom == 1.0:
            zoom = 1.035
        if zoom != 1.0:
            new_width, new_height = int(width * zoom), int(height * zoom)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            margin_x = max(0, (new_width - width) // 2)
            margin_y = max(0, (new_height - height) // 2)
            dx = max(-margin_x + 1, min(margin_x - 1, dx)) if margin_x > 1 else 0
            dy = max(-margin_y + 1, min(margin_y - 1, dy)) if margin_y > 1 else 0
            left = margin_x + int(dx)
            top = margin_y + int(dy)
            return image.crop((left, top, left + width, top + height))
        return image

    def _subtitle(self, image: Image.Image, shot: Shot) -> None:
        if not shot.dialogue or not shot.subtitle:
            return
        width, height = image.size
        speaker = shot.speaker_id or ""
        key = (width, height, shot.dialogue, speaker, shot.subtitle_style)
        overlay = self._subtitle_cache.get(key)
        if overlay is None:
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay, "RGBA")
            font, name_font = _font(36, True), _font(18, True)
            lines = _wrap(draw, shot.dialogue, font, width - 180)[:3]
            box_height = 44 + len(lines) * 48
            top = height - box_height - 30
            if shot.subtitle_style == "minimal":
                draw.rounded_rectangle((110, top, width - 110, height - 35), radius=18, fill=(0, 0, 0, 176))
            else:
                draw.rounded_rectangle((45, top, width - 45, height - 30), radius=24, fill=(5, 7, 14, 218), outline=(255, 255, 255, 40), width=2)
            if speaker:
                name = self.project.character(speaker).display_name
                name_color = (235, 118, 184, 255) if speaker == "seo_yeon" else (154, 174, 255, 255)
                draw.text((78, top + 13), name, font=name_font, fill=name_color)
            y = top + 42
            for line in lines:
                draw.text((78, y), line, font=font, fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0, 180))
                y += 48
            self._subtitle_cache[key] = overlay
        image.alpha_composite(overlay)

    def _render_audio(self, ffmpeg: str, shot: Shot, output: Path, duration: float, voice: Path | None) -> None:
        music = self._resolve("music", shot.music)
        ambience = self._resolve("sfx", shot.ambience) if shot.ambience else None
        effects: list[tuple[SFXCue, Path]] = []
        for cue in shot.sfx:
            path = self._resolve("sfx", cue.cue)
            if path:
                effects.append((cue, path))
        explicit_steps = any("foot" in cue.cue.lower() or "step" in cue.cue.lower() for cue in shot.sfx)
        if not explicit_steps:
            step_paths = [self._resolve("sfx", "footstep_left"), self._resolve("sfx", "footstep_right")]
            cloth_path = self._resolve("sfx", "cloth_swish")
            if all(step_paths):
                for actor_index, actor in enumerate(shot.actors):
                    motion = normalize_motion(actor.motion, actor.acting)
                    times = footstep_times(motion, duration, actor.motion_speed, actor.cycle_offset)
                    for step_index, at in enumerate(times):
                        pan = max(-0.75, min(0.75, (POSITION_X.get(actor.position, 0.5) - 0.5) * 1.4))
                        volume = 0.68 if "run" in motion else 0.44
                        chosen = step_paths[(step_index + actor_index) % 2]
                        assert chosen is not None
                        effects.append((SFXCue(chosen.stem, at=at, volume=volume, pan=pan), chosen))
                        if cloth_path and "run" in motion and step_index % 2 == 0:
                            effects.append((SFXCue("cloth_swish", at=max(0.0, at - 0.04), volume=0.24, pan=pan), cloth_path))
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        inputs: list[tuple[str, int, float, float, float]] = []
        if voice:
            cmd += ["-i", str(voice)]
            inputs.append(("voice", len(inputs), 0.0, 1.08, 0.0))
        if music:
            cmd += ["-stream_loop", "-1", "-i", str(music)]
            inputs.append(("music", len(inputs), 0.0, (0.12 if voice else 0.22) * shot.music_volume, 0.0))
        if ambience:
            cmd += ["-stream_loop", "-1", "-i", str(ambience)]
            inputs.append(("ambience", len(inputs), 0.0, 0.16 * shot.ambience_volume, 0.0))
        for cue, path in effects:
            cmd += ["-i", str(path)]
            inputs.append(("sfx", len(inputs), cue.at, 0.62 * cue.volume, cue.pan))
        if not inputs:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            inputs = [("silence", 0, 0.0, 1.0, 0.0)]
        filters: list[str] = []
        labels: list[tuple[str, str]] = []
        for number, (kind, index, at, volume, pan) in enumerate(inputs):
            label = f"a{number}"
            delay = max(0, int(at * 1000))
            chain = f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo"
            if kind == "voice":
                chain += ",highpass=f=70,lowpass=f=15000,acompressor=threshold=0.08:ratio=2.4:attack=5:release=80"
            chain += f",volume={volume:.4f}"
            if abs(pan) > 0.01:
                left = max(0.0, min(2.0, 1.0 - pan))
                right = max(0.0, min(2.0, 1.0 + pan))
                chain += f",pan=stereo|c0={left:.3f}*c0|c1={right:.3f}*c1"
            if delay:
                chain += f",adelay={delay}|{delay}"
            if kind in {"music", "ambience"}:
                chain += f",afade=t=in:st=0:d=0.35,afade=t=out:st={max(0, duration - 0.45):.3f}:d=0.45"
            chain += f",apad=pad_dur={duration}[{label}]"
            filters.append(chain)
            labels.append((kind, label))
        mixlabels = "".join(f"[{label}]" for _, label in labels)
        filters.append(f"{mixlabels}amix=inputs={len(labels)}:duration=longest:normalize=0,highpass=f=38,alimiter=limit=0.94,atrim=duration={duration}[mix]")
        cmd += ["-filter_complex", ";".join(filters), "-map", "[mix]", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", f"{duration:.3f}", str(output)]
        self._run(cmd)

    def _resolve(self, kind: str, cue: str | None) -> Path | None:
        if not cue:
            return None
        raw = Path(cue)
        if raw.is_file():
            return raw
        folder = self.project.assets_dir / kind
        candidate = folder / cue
        if candidate.exists():
            return candidate
        for extension in (".wav", ".mp3", ".flac", ".ogg", ".jpg", ".jpeg", ".png", ".webp"):
            path = folder / f"{cue}{extension}"
            if path.exists():
                return path
        return None

    def _load(self, path: Path) -> Image.Image:
        if path not in self._asset_cache:
            self._asset_cache[path] = Image.open(path).copy()
        return self._asset_cache[path].copy()

    @staticmethod
    def _run(cmd: list[str]) -> None:
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if process.returncode:
            raise RenderError(process.stderr.strip() or "FFmpeg command failed")
