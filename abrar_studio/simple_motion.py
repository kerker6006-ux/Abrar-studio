"""CPU-friendly Korean drama talking-shot renderer.

The actor is a six-cell Imagen sprite sheet.  Each cell is a complete generated
portrait with its own mouth, so speech never uses a mouth sticker over a face.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


class MotionRenderError(RuntimeError):
    pass


def audio_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / max(1, wav.getframerate())


def speech_mouth_states(path: Path, frame_count: int, fps: int, state_count: int) -> list[int]:
    """Pick complete-face mouth frames from real voice energy.

    This is intentionally audio-driven rather than a repeating animation loop:
    silence settles to the closed-mouth portrait, while louder syllables use
    progressively wider generated mouth states. It remains CPU-only and works
    for Korean dialogue without pretending to offer impossible phoneme-perfect
    lip sync from a generic voice file.
    """
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width != 2 or rate <= 0:
        return [0] * frame_count
    import audioop
    samples_per_frame = max(1, round(rate / fps))
    levels: list[float] = []
    for index in range(frame_count):
        start = index * samples_per_frame * width * channels
        end = min(len(raw), start + samples_per_frame * width * channels)
        chunk = raw[start:end]
        levels.append(float(audioop.rms(chunk, width)) if chunk else 0.0)
    peak = max(levels) or 1.0
    smoothed: list[float] = []
    for index, level in enumerate(levels):
        near = levels[max(0, index - 1):min(len(levels), index + 2)]
        smoothed.append(sum(near) / len(near) / peak)
    states: list[int] = []
    previous = 0
    for value in smoothed:
        if value < 0.055:
            state = 0
        elif value < 0.16:
            state = min(state_count - 1, 1)
        elif value < 0.33:
            state = min(state_count - 1, 2)
        elif value < 0.57:
            state = min(state_count - 1, 3)
        else:
            state = min(state_count - 1, 4)
        # Briefly hold a shape so natural syllables read as motion instead of
        # flickering at the video frame rate.
        if state != previous and states and len(states) % 2:
            state = previous
        states.append(state)
        previous = state
    return states


def split_mouth_sheet(sheet_path: Path) -> list[Image.Image]:
    sheet = Image.open(sheet_path).convert("RGBA")
    width, height = sheet.size
    cells: list[Image.Image] = []
    for row in range(2):
        for column in range(3):
            left, top = round(column * width / 3), round(row * height / 2)
            right, bottom = round((column + 1) * width / 3), round((row + 1) * height / 2)
            cells.append(sheet.crop((left, top, right, bottom)))
    return cells


def _font(size: int, bold: bool = True):
    fonts = [
        Path("C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in fonts:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def _caption(draw: ImageDraw.ImageDraw, text: str, width: int, height: int) -> None:
    font = _font(max(22, width // 21))
    words = text.split() or list(text)
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width * 0.84:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    lines = lines[:2]
    y = height * 0.78
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font, stroke_width=2)
        x = (width - (box[2] - box[0])) / 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=4, stroke_fill=(0, 0, 0, 220))
        y += font.size * 1.24


def render_talking_shot(*, background_path: Path, mouth_sheet_path: Path, audio_path: Path, caption: str, output_path: Path, ffmpeg_path: str, progress=None) -> Path:
    executable = shutil.which(ffmpeg_path) or (ffmpeg_path if Path(ffmpeg_path).exists() else None)
    if not executable:
        raise MotionRenderError("FFmpeg was not found. Install Abrar Studio's FFmpeg component first.")
    width, height, fps = 720, 1280, 24
    duration = max(3.0, audio_duration(audio_path))
    frames = max(1, math.ceil(duration * fps))
    frames_dir = output_path.parent / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    background = ImageOps.fit(Image.open(background_path).convert("RGB"), (width + 80, height + 80), Image.Resampling.LANCZOS)
    actors = [ImageOps.contain(cell, (round(width * 0.90), round(height * 0.67)), Image.Resampling.LANCZOS) for cell in split_mouth_sheet(mouth_sheet_path)]
    mouth_states = speech_mouth_states(audio_path, frames, fps, len(actors))
    for index in range(frames):
        t = index / fps
        pan = round(40 * (0.5 + 0.5 * math.sin(t * 0.42)))
        frame = background.crop((pan, 35, pan + width, 35 + height)).convert("RGBA")
        # Six complete face images create real mouth states driven by the
        # narrator's actual waveform, never a mouth sticker over a face.
        mouth = mouth_states[index]
        actor = actors[mouth]
        # A restrained breathing/acting curve is more believable than constant
        # bouncing. Larger movement is reserved for explicit walk assets.
        bob = round(math.sin(t * 1.15) * 3 + math.sin(t * 0.37) * 2)
        x, y = (width - actor.width) // 2, height - actor.height + bob - 80
        frame.alpha_composite(actor, (x, y))
        shade = Image.new("RGBA", (width, height), (10, 12, 28, 32))
        frame = Image.alpha_composite(frame, shade)
        frame = ImageEnhance.Contrast(frame.convert("RGB")).enhance(1.08).convert("RGBA")
        draw = ImageDraw.Draw(frame, "RGBA")
        draw.rectangle((0, 0, width, 68), fill=(6, 8, 18, 142))
        draw.text((28, 21), "ABRAR DRAMA", font=_font(26), fill=(255, 221, 234, 245))
        _caption(draw, caption, width, height)
        vignette = Image.new("L", (width, height), 0)
        vd = ImageDraw.Draw(vignette)
        vd.rectangle((0, 0, width, height), outline=120, width=45)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay.putalpha(vignette.filter(ImageFilter.GaussianBlur(28)))
        frame = Image.alpha_composite(frame, overlay)
        frame.convert("RGB").save(frames_dir / f"frame_{index:05d}.jpg", quality=92)
        if progress and index % 12 == 0:
            progress(0.55 + 0.37 * index / frames, f"Animating locally: {index}/{frames} frames")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [executable, "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%05d.jpg"), "-i", str(audio_path), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output_path)]
    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=300)
    if result.returncode:
        raise MotionRenderError(result.stderr[-1500:])
    return output_path
