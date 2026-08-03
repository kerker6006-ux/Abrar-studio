from __future__ import annotations

import hashlib
import math
import os
import random
import subprocess
import wave
from array import array
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .constants import GEMINI_FLASH_TTS, GEMINI_PRO_TTS
from .gemini_tts import GeminiTTSClient, TTSGenerationError, TTSRequest
from .paths import app_root
from .signal214 import SignalBeat, SignalEpisode


ProgressFn = Callable[[float, str], None]


class SignalRenderError(RuntimeError):
    pass


def build_signal_tts_request(episode: SignalEpisode, *, pro: bool = True) -> TTSRequest:
    model = GEMINI_PRO_TTS if pro else GEMINI_FLASH_TTS
    voice = "Gacrux"
    prompt = (
        "Synthesize speech audio only. Never read headings or instructions aloud. "
        "Read the Korean transcript exactly without adding, deleting, translating, or paraphrasing words.\n\n"
        "# AUDIO PROFILE: 기록보관소 조사관\n"
        "A mature Korean documentary narrator with a calm, credible identity. The voice is intimate, "
        "controlled, and human; never theatrical, robotic, or like an advertisement.\n\n"
        "# SCENE\n"
        "A fictional late-night evidence archive. The narrator has found a disturbing inconsistency in a recovered recording.\n\n"
        "# DIRECTOR'S NOTES\n"
        "Speak natural contemporary Korean. Begin immediately with quiet urgency. Use short deliberate pauses at sentence boundaries. "
        "Build tension gradually. Make the final two sentences slower and more unsettling, but keep every word clear. "
        "Do not whisper so softly that consonants disappear. Do not announce that this is fiction.\n\n"
        f"# TRANSCRIPT\n{episode.script.strip()}"
    )
    key = hashlib.sha256("\0".join([model, voice, prompt]).encode("utf-8")).hexdigest()
    return TTSRequest(model=model, voice=voice, prompt=prompt, cache_key=key)


def generate_signal_narration(api_key: str, episode: SignalEpisode, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    pro_request = build_signal_tts_request(episode, pro=True)
    final_path = output_dir / f"{pro_request.cache_key}.wav"
    if final_path.exists() and _wav_duration(final_path) > 3.0:
        return final_path
    client = GeminiTTSClient(api_key, timeout=180)
    try:
        return client.generate_best(pro_request, final_path, takes=2)
    except TTSGenerationError as pro_error:
        flash_request = build_signal_tts_request(episode, pro=False)
        flash_path = output_dir / f"{flash_request.cache_key}.wav"
        if flash_path.exists() and _wav_duration(flash_path) > 3.0:
            return flash_path
        try:
            return client.generate_best(flash_request, flash_path, takes=1)
        except TTSGenerationError as flash_error:
            raise TTSGenerationError(
                f"고품질 음성 생성 실패: {pro_error} | 빠른 음성 대체도 실패: {flash_error}"
            ) from flash_error


class Signal214Renderer:
    """CPU-safe vertical evidence-horror renderer.

    It deliberately renders restrained 12 fps motion and encodes a 24 fps Short.
    The aesthetic depends on typography, evidence interfaces, camera movement and
    sound rather than fake articulated character animation.
    """

    def __init__(self, ffmpeg_path: str, asset_root: Path | None = None) -> None:
        self.ffmpeg_path = str(ffmpeg_path)
        self.asset_root = asset_root or (app_root() / "assets" / "signal214")
        self._font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._plate_cache: dict[tuple[str, int, int], Image.Image] = {}
        self._overlay_cache: dict[tuple[int, int], tuple[Image.Image, list[Image.Image]]] = {}

    def render(
        self,
        episode: SignalEpisode,
        output_path: Path,
        narration_path: Path | None = None,
        progress: ProgressFn | None = None,
        *,
        preview: bool = False,
    ) -> Path:
        self._verify_inputs(episode)
        if narration_path and narration_path.exists():
            self._sync_episode_to_voice(episode, narration_path)
        width, height = ((540, 960) if preview else episode.resolution)
        render_fps = episode.render_fps
        total_frames = max(1, round(episode.duration * render_fps))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_root = output_path.parent / ".signal214-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        soundbed = self._build_soundbed(episode, temp_root / f"{episode.episode_id}-soundbed.wav")
        staged = temp_root / f".{output_path.stem}.rendering.mp4"
        staged.unlink(missing_ok=True)

        command = [
            self.ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
            "-r", str(render_fps), "-i", "-",
        ]
        if narration_path and narration_path.exists():
            command.extend(["-i", str(narration_path), "-i", str(soundbed)])
            command.extend([
                "-filter_complex",
                "[1:a]highpass=f=70,volume=1.12[voice];[2:a]volume=0.34[bed];"
                "[voice][bed]amix=inputs=2:duration=longest:dropout_transition=0,"
                "loudnorm=I=-15:TP=-1.5:LRA=8,alimiter=limit=0.92[a]",
                "-map", "0:v", "-map", "[a]",
            ])
        else:
            command.extend(["-i", str(soundbed), "-map", "0:v", "-map", "1:a"])
        command.extend([
            "-vf", f"fps={episode.fps},format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-profile:v", "high",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", f"{episode.duration:.3f}", "-movflags", "+faststart",
            "-metadata", "title=Signal 2:14 Korean fictional evidence story",
            "-metadata", "comment=Fictional dramatization created by Abrar Studio",
            str(staged),
        ])

        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            raise SignalRenderError(f"FFmpeg를 시작할 수 없습니다: {exc}") from exc
        assert process.stdin is not None
        try:
            for frame_index in range(total_frames):
                frame = self._frame(episode, frame_index, width, height)
                process.stdin.write(frame.convert("RGB").tobytes())
                if progress and (frame_index % max(1, render_fps) == 0 or frame_index == total_frames - 1):
                    progress(frame_index * 95 / total_frames, f"세로 쇼츠 렌더링 {frame_index + 1}/{total_frames}")
        except (BrokenPipeError, OSError) as exc:
            process.stdin.close()
            detail = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            process.wait()
            raise SignalRenderError(f"영상 프레임 전송 실패: {detail[-1200:] or exc}") from exc
        process.stdin.close()
        detail = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        code = process.wait()
        if code != 0 or not staged.exists() or staged.stat().st_size < 50_000:
            staged.unlink(missing_ok=True)
            raise SignalRenderError(f"FFmpeg 렌더링 실패: {detail[-1600:] or f'exit {code}'}")
        self._verify_video(staged)
        os.replace(staged, output_path)
        if progress:
            progress(100, "완성된 쇼츠를 검증했습니다")
        return output_path

    def contact_sheet(self, episode: SignalEpisode, output_path: Path, columns: int = 3) -> Path:
        width, height = 360, 640
        thumbs: list[Image.Image] = []
        elapsed = 0.0
        for beat in episode.beats:
            midpoint = elapsed + beat.duration * (0.72 if beat.emphasis == "reveal" else 0.5)
            thumbs.append(self._frame(episode, round(midpoint * episode.render_fps), width, height))
            elapsed += beat.duration
        rows = math.ceil(len(thumbs) / columns)
        sheet = Image.new("RGB", (columns * width, rows * height), "black")
        for index, thumb in enumerate(thumbs):
            sheet.paste(thumb, ((index % columns) * width, (index // columns) * height))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(output_path, quality=92)
        return output_path

    def _verify_inputs(self, episode: SignalEpisode) -> None:
        ffmpeg = Path(self.ffmpeg_path)
        if not (ffmpeg.exists() or self.ffmpeg_path == "ffmpeg"):
            raise SignalRenderError(f"FFmpeg를 찾을 수 없습니다: {self.ffmpeg_path}")
        if episode.resolution[0] >= episode.resolution[1]:
            raise SignalRenderError("Signal 2:14 영상은 세로 9:16 해상도여야 합니다.")
        if not episode.beats:
            raise SignalRenderError("렌더링할 증거 장면이 없습니다.")
        missing = [beat.background for beat in episode.beats if not (self.asset_root / "backgrounds" / beat.background).exists()]
        if missing:
            raise SignalRenderError(f"배경 자산이 없습니다: {', '.join(sorted(set(missing)))}")

    def _sync_episode_to_voice(self, episode: SignalEpisode, narration_path: Path) -> None:
        audio_duration = _wav_duration(narration_path)
        if audio_duration <= 1.0:
            raise SignalRenderError("내레이션 음성이 비어 있거나 손상되었습니다.")
        desired = min(59.0, max(30.0, audio_duration + 1.5))
        scale = desired / max(0.1, sum(beat.duration for beat in episode.beats))
        for beat in episode.beats:
            beat.duration = round(beat.duration * scale, 3)
        episode.duration = round(sum(beat.duration for beat in episode.beats), 3)

    def _frame(self, episode: SignalEpisode, frame_index: int, width: int, height: int) -> Image.Image:
        t = min(episode.duration - 0.001, frame_index / episode.render_fps)
        beat, beat_start = self._beat_at(episode, t)
        local = max(0.0, min(1.0, (t - beat_start) / max(0.01, beat.duration)))
        scene = self._moving_plate(beat.background, width, height, local, beat.index)
        scene = self._grade(scene, beat, local)
        self._evidence_layer(scene, beat, local, t)
        self._camera_overlay(scene, episode, beat, t)
        self._caption(scene, beat.caption, beat.emphasis, local)
        vignette, grains = self._overlays(width, height)
        scene = Image.alpha_composite(scene.convert("RGBA"), grains[frame_index % len(grains)])
        scene = Image.alpha_composite(scene, vignette)
        return scene.convert("RGB")

    @staticmethod
    def _beat_at(episode: SignalEpisode, t: float) -> tuple[SignalBeat, float]:
        elapsed = 0.0
        for beat in episode.beats:
            if t < elapsed + beat.duration:
                return beat, elapsed
            elapsed += beat.duration
        return episode.beats[-1], max(0.0, elapsed - episode.beats[-1].duration)

    def _moving_plate(self, name: str, width: int, height: int, local: float, seed: int) -> Image.Image:
        key = (name, width, height)
        plate = self._plate_cache.get(key)
        if plate is None:
            source = Image.open(self.asset_root / "backgrounds" / name).convert("RGB")
            plate = ImageOps.fit(source, (round(width * 1.10), round(height * 1.10)), Image.Resampling.LANCZOS)
            self._plate_cache[key] = plate
        max_x = plate.width - width
        max_y = plate.height - height
        direction = -1 if seed % 2 else 1
        x = round(max_x * (0.5 + direction * (local - 0.5) * 0.55))
        y = round(max_y * (0.40 + math.sin(local * math.pi) * 0.12))
        return plate.crop((max(0, min(max_x, x)), max(0, min(max_y, y)), max(0, min(max_x, x)) + width, max(0, min(max_y, y)) + height)).convert("RGBA")

    @staticmethod
    def _grade(scene: Image.Image, beat: SignalBeat, local: float) -> Image.Image:
        rgb = scene.convert("RGB")
        rgb = ImageEnhance.Color(rgb).enhance(0.58)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.20)
        rgb = ImageEnhance.Brightness(rgb).enhance(0.88 + 0.04 * math.sin(local * math.pi))
        tint = Image.new("RGB", rgb.size, (5, 25, 29) if beat.kind not in {"elevator", "call"} else (24, 8, 12))
        return Image.blend(rgb, tint, 0.13).convert("RGBA")

    def _evidence_layer(self, image: Image.Image, beat: SignalBeat, local: float, t: float) -> None:
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        scale = width / 1080
        if beat.kind in {"cctv", "corridor"}:
            if local > 0.48:
                alpha = int(175 * min(1.0, (local - 0.48) / 0.20))
                cx, cy = width * 0.51, height * 0.48
                body_w, body_h = 18 * scale, 66 * scale
                shadow = (0, 0, 0, alpha)
                # A restrained distant human shape: head, shoulders, torso and
                # separated legs. Keeping it small preserves uncertainty without
                # the cheap triangular cutout used by the old renderer.
                draw.ellipse((cx - body_w * 0.34, cy - body_h * 0.62, cx + body_w * 0.34, cy - body_h * 0.43), fill=shadow)
                draw.ellipse((cx - body_w * 0.72, cy - body_h * 0.44, cx + body_w * 0.72, cy - body_h * 0.18), fill=shadow)
                draw.rounded_rectangle((cx - body_w * 0.48, cy - body_h * 0.37, cx + body_w * 0.48, cy + body_h * 0.20), radius=max(1, round(4 * scale)), fill=shadow)
                draw.polygon([(cx - body_w * 0.44, cy + body_h * 0.12), (cx - body_w * 0.10, cy + body_h * 0.56), (cx - body_w * 0.55, cy + body_h * 0.56)], fill=shadow)
                draw.polygon([(cx + body_w * 0.44, cy + body_h * 0.12), (cx + body_w * 0.55, cy + body_h * 0.56), (cx + body_w * 0.10, cy + body_h * 0.56)], fill=shadow)
                if beat.emphasis == "reveal":
                    box = (cx - 40 * scale, cy - 65 * scale, cx + 40 * scale, cy + 55 * scale)
                    self._corner_box(draw, box, (220, 42, 50, min(230, alpha + 40)), max(1, round(2 * scale)))
        elif beat.kind == "call":
            panel = (round(width * 0.10), round(height * 0.19), round(width * 0.90), round(height * 0.72))
            draw.rounded_rectangle(panel, radius=round(32 * scale), fill=(5, 10, 16, 222), outline=(118, 143, 151, 100), width=max(1, round(2 * scale)))
            draw.ellipse((width * 0.39, height * 0.26, width * 0.61, height * 0.38), fill=(39, 52, 59, 255))
            self._center_text(draw, "발신자 표시 제한", height * 0.43, self._font(round(42 * scale), True), (238, 242, 238, 255), width)
            self._center_text(draw, f"00:{int(local * beat.duration):02d}", height * 0.49, self._font(round(30 * scale)), (150, 170, 170, 255), width)
            pulse = 0.8 + math.sin(t * 5) * 0.1
            r = 68 * scale * pulse
            draw.ellipse((width / 2 - r, height * 0.62 - r, width / 2 + r, height * 0.62 + r), fill=(179, 36, 49, 235))
            self._center_text(draw, "통화 종료", height * 0.607, self._font(round(24 * scale), True), (255, 255, 255, 255), width)
        elif beat.kind == "waveform":
            panel = (round(width * 0.06), round(height * 0.25), round(width * 0.94), round(height * 0.65))
            draw.rounded_rectangle(panel, radius=round(18 * scale), fill=(4, 12, 15, 225), outline=(65, 170, 159, 140), width=max(1, round(2 * scale)))
            mid = height * 0.48
            left, right = width * 0.11, width * 0.89
            points = []
            for x in range(round(left), round(right), max(2, round(5 * scale))):
                p = (x - left) / max(1, right - left)
                amp = (math.sin(p * 55 + t * 1.2) + math.sin(p * 17)) * height * 0.018
                amp *= 0.35 + 0.65 * math.sin(p * math.pi)
                points.append((x, mid + amp))
            if len(points) > 1:
                draw.line(points, fill=(93, 228, 199, 235), width=max(1, round(3 * scale)))
            draw.line((left, mid, left + (right - left) * local, mid), fill=(235, 57, 67, 190), width=max(1, round(2 * scale)))
            draw.text((left, height * 0.29), "복구된 음성 기록", font=self._font(round(30 * scale), True), fill=(224, 236, 231, 255))
        elif beat.kind == "file":
            paper = (round(width * 0.10), round(height * 0.16), round(width * 0.90), round(height * 0.73))
            draw.rounded_rectangle(paper, radius=round(8 * scale), fill=(214, 211, 192, 243))
            draw.rectangle((paper[0], paper[1], paper[2], paper[1] + 90 * scale), fill=(79, 20, 24, 242))
            draw.text((paper[0] + 35 * scale, paper[1] + 24 * scale), "보안 기록 / 열람 제한", font=self._font(round(31 * scale), True), fill=(248, 240, 226, 255))
            labels = ("사건 번호", "발생 시각", "보관 상태", "확인 결과")
            values = ("S-214", "02:14:07", "복구됨", "불일치")
            y = paper[1] + 140 * scale
            for label, value in zip(labels, values):
                draw.text((paper[0] + 45 * scale, y), label, font=self._font(round(25 * scale), True), fill=(65, 60, 55, 255))
                draw.text((paper[0] + 270 * scale, y), value, font=self._font(round(25 * scale)), fill=(25, 27, 26, 255))
                draw.line((paper[0] + 40 * scale, y + 42 * scale, paper[2] - 40 * scale, y + 42 * scale), fill=(100, 97, 90, 100), width=max(1, round(scale)))
                y += 83 * scale
            photo = (paper[0] + 45 * scale, y + 15 * scale, paper[0] + 235 * scale, y + 245 * scale)
            draw.rectangle(photo, fill=(116, 116, 105, 180), outline=(70, 67, 62, 180), width=max(1, round(2 * scale)))
            pcx = (photo[0] + photo[2]) / 2
            draw.ellipse((pcx - 28 * scale, photo[1] + 37 * scale, pcx + 28 * scale, photo[1] + 93 * scale), fill=(63, 63, 59, 220))
            draw.ellipse((pcx - 62 * scale, photo[1] + 92 * scale, pcx + 62 * scale, photo[3] - 20 * scale), fill=(63, 63, 59, 220))
            draw.text((photo[0], photo[3] + 11 * scale), "학생 기록 사진", font=self._font(round(20 * scale), True), fill=(70, 66, 60, 230))
            line_left = paper[0] + 285 * scale
            for offset, fraction in ((22, 0.86), (78, 0.68), (134, 0.92), (190, 0.56)):
                line_y = y + offset * scale
                draw.rectangle((line_left, line_y, line_left + (paper[2] - line_left - 45 * scale) * fraction, line_y + 22 * scale), fill=(45, 44, 41, 215))
            stamp_x, stamp_y = paper[2] - 190 * scale, paper[3] - 120 * scale
            draw.ellipse((stamp_x - 62 * scale, stamp_y - 62 * scale, stamp_x + 62 * scale, stamp_y + 62 * scale), outline=(139, 29, 35, 210), width=max(2, round(5 * scale)))
            draw.text((stamp_x - 50 * scale, stamp_y - 21 * scale), "미확인", font=self._font(round(28 * scale), True), fill=(139, 29, 35, 220))
        elif beat.kind == "map":
            panel = (round(width * 0.08), round(height * 0.18), round(width * 0.92), round(height * 0.70))
            draw.rounded_rectangle(panel, radius=round(14 * scale), fill=(9, 18, 21, 228), outline=(83, 121, 125, 140), width=max(1, round(2 * scale)))
            for step in range(1, 7):
                x = panel[0] + (panel[2] - panel[0]) * step / 7
                y = panel[1] + (panel[3] - panel[1]) * step / 7
                draw.line((x, panel[1], x, panel[3]), fill=(68, 93, 94, 70), width=max(1, round(scale)))
                draw.line((panel[0], y, panel[2], y), fill=(68, 93, 94, 70), width=max(1, round(scale)))
            route = [(width * 0.18, height * 0.61), (width * 0.32, height * 0.49), (width * 0.51, height * 0.54), (width * 0.68, height * 0.39), (width * 0.78, height * 0.29)]
            draw.line(route, fill=(201, 50, 61, 235), width=max(2, round(7 * scale)), joint="curve")
            r = 20 * scale
            x, y = route[-1]
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(220, 49, 60, 245), outline=(255, 225, 225, 220), width=max(1, round(3 * scale)))
            draw.text((panel[0] + 28 * scale, panel[1] + 24 * scale), "마지막 확인 위치", font=self._font(round(30 * scale), True), fill=(227, 236, 232, 255))
        elif beat.kind == "elevator":
            if local > 0.58:
                alpha = int(220 * min(1, (local - 0.58) / 0.18))
                self._center_text(draw, "존재하지 않는 층", height * 0.31, self._font(round(50 * scale), True), (245, 55, 65, alpha), width)
        elif beat.kind == "monitor":
            for row in range(2):
                for col in range(2):
                    left = width * (0.08 + col * 0.43)
                    top = height * (0.23 + row * 0.20)
                    box = (left, top, left + width * 0.38, top + height * 0.16)
                    draw.rectangle(box, outline=(164, 190, 184, 135), width=max(1, round(2 * scale)))
                    draw.text((left + 12 * scale, top + 9 * scale), f"CAM {row * 2 + col + 1:02d}", font=self._font(round(20 * scale), True), fill=(205, 220, 215, 200))

    def _camera_overlay(self, image: Image.Image, episode: SignalEpisode, beat: SignalBeat, t: float) -> None:
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        scale = width / 1080
        margin = 52 * scale
        top = 70 * scale
        draw.ellipse((margin, top, margin + 22 * scale, top + 22 * scale), fill=(231, 40, 53, 240))
        draw.text((margin + 36 * scale, top - 6 * scale), "REC", font=self._font(round(30 * scale), True), fill=(244, 244, 237, 245))
        clock = f"02:14:{int(t) % 60:02d}"
        clock_width = draw.textbbox((0, 0), clock, font=self._font(round(28 * scale), True))[2]
        draw.text((width - margin - clock_width, top - 5 * scale), clock, font=self._font(round(28 * scale), True), fill=(235, 238, 232, 230))
        draw.text((margin, top + 48 * scale), f"{episode.series}  /  {episode.episode_id}", font=self._font(round(19 * scale), True), fill=(188, 207, 202, 205))
        line_y = height - 205 * scale
        draw.line((margin, line_y, width - margin, line_y), fill=(230, 235, 225, 80), width=max(1, round(scale)))
        draw.text((margin, height - 68 * scale), "본 영상은 허구의 기록을 재구성한 작품입니다.", font=self._font(round(19 * scale)), fill=(195, 205, 199, 175))

    def _caption(self, image: Image.Image, text: str, emphasis: str, local: float) -> None:
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        scale = width / 1080
        font_size = round((52 if emphasis == "normal" else 57) * scale)
        font = self._font(font_size, True)
        max_width = width - 150 * scale
        lines = self._wrap(draw, text, font, max_width, max_lines=3)
        line_height = round(font_size * 1.42)
        block_height = len(lines) * line_height
        y = height - 245 * scale - block_height
        alpha = int(255 * min(1.0, local / 0.10, (1.0 - local) / 0.08 if local > 0.92 else 1.0))
        color = (255, 236, 221, alpha) if emphasis == "reveal" else (247, 247, 240, alpha)
        accent = (242, 61, 72, alpha)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font, stroke_width=max(1, round(2 * scale)))
            x = (width - (bbox[2] - bbox[0])) / 2
            draw.text((x + 3 * scale, y + 5 * scale), line, font=font, fill=(0, 0, 0, min(210, alpha)), stroke_width=max(2, round(5 * scale)), stroke_fill=(0, 0, 0, min(180, alpha)))
            draw.text((x, y), line, font=font, fill=color, stroke_width=max(1, round(2 * scale)), stroke_fill=(5, 9, 10, alpha))
            y += line_height
        if emphasis in {"hook", "reveal"}:
            bar_y = height - 252 * scale - block_height
            bar_w = min(width * 0.46, max(120 * scale, width * local * 0.55))
            draw.rounded_rectangle((width / 2 - bar_w / 2, bar_y, width / 2 + bar_w / 2, bar_y + 7 * scale), radius=4, fill=accent)

    def _overlays(self, width: int, height: int) -> tuple[Image.Image, list[Image.Image]]:
        key = (width, height)
        cached = self._overlay_cache.get(key)
        if cached:
            return cached
        vignette_mask = Image.new("L", (width, height), 0)
        vdraw = ImageDraw.Draw(vignette_mask)
        for step in range(18, 0, -1):
            inset_x = round(width * 0.015 * step)
            inset_y = round(height * 0.012 * step)
            alpha = round(10 + (18 - step) * 4.0)
            vdraw.rounded_rectangle((inset_x, inset_y, width - inset_x, height - inset_y), radius=round(width * 0.04), outline=alpha, width=max(2, round(width * 0.012)))
        vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        vignette.putalpha(vignette_mask.filter(ImageFilter.GaussianBlur(max(2, width // 90))))
        scan = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(scan)
        for y in range(0, height, max(3, round(width / 270))):
            sdraw.line((0, y, width, y), fill=(0, 0, 0, 22), width=1)
        grains: list[Image.Image] = []
        for seed in range(4):
            random.seed(seed + width + height)
            small = Image.effect_noise((max(64, width // 4), max(96, height // 4)), 16 + seed * 2).convert("L")
            noise = small.resize((width, height), Image.Resampling.BILINEAR)
            alpha = noise.point(lambda value: max(0, min(18, abs(value - 128) // 3)))
            layer = scan.copy()
            white = Image.new("RGBA", (width, height), (205, 230, 220, 0))
            white.putalpha(alpha)
            layer = Image.alpha_composite(layer, white)
            grains.append(layer)
        self._overlay_cache[key] = (vignette, grains)
        return vignette, grains

    def _font(self, size: int, bold: bool = False):
        size = max(10, int(size))
        key = (size, bold)
        if key in self._font_cache:
            return self._font_cache[key]
        candidates = [
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / ("malgunbd.ttf" if bold else "malgun.ttf"),
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / ("NotoSansKR-Bold.ttf" if bold else "NotoSansKR-Regular.ttf"),
            Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        ]
        font = None
        for candidate in candidates:
            if candidate.exists():
                try:
                    font = ImageFont.truetype(str(candidate), size=size)
                    break
                except OSError:
                    continue
        if font is None:
            font = ImageFont.load_default(size=size)
        self._font_cache[key] = font
        return font

    @staticmethod
    def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: float, max_lines: int = 3) -> list[str]:
        words = text.split()
        if len(words) <= 1:
            words = list(text)
            spacer = ""
        else:
            spacer = " "
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current}{spacer if current else ''}{word}"
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            kept = lines[:max_lines]
            kept[-1] = kept[-1].rstrip("…") + "…"
            return kept
        return lines

    @staticmethod
    def _corner_box(draw: ImageDraw.ImageDraw, box, color, width: int) -> None:
        left, top, right, bottom = box
        length = min(right - left, bottom - top) * 0.28
        for points in (
            (left, top + length, left, top, left + length, top),
            (right - length, top, right, top, right, top + length),
            (right, bottom - length, right, bottom, right - length, bottom),
            (left + length, bottom, left, bottom, left, bottom - length),
        ):
            draw.line(points, fill=color, width=width, joint="curve")

    @staticmethod
    def _center_text(draw: ImageDraw.ImageDraw, text: str, y: float, font, fill, width: int) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (bbox[2] - bbox[0])) / 2, y), text, font=font, fill=fill)

    def _build_soundbed(self, episode: SignalEpisode, path: Path) -> Path:
        rate = 24000
        count = round(episode.duration * rate)
        starts: list[float] = []
        elapsed = 0.0
        for beat in episode.beats:
            starts.append(elapsed)
            elapsed += beat.duration
        samples = array("h")
        rng = random.Random(int(hashlib.sha256(episode.episode_id.encode()).hexdigest()[:8], 16))
        for index in range(count):
            t = index / rate
            hum = math.sin(2 * math.pi * 43 * t) * 380
            electrical = math.sin(2 * math.pi * 86.3 * t) * 130
            air = rng.uniform(-75, 75)
            pulse = 0.0
            for start in starts:
                delta = t - start
                if 0 <= delta < 0.65:
                    pulse += math.sin(2 * math.pi * (58 - delta * 26) * delta) * 1250 * math.exp(-delta * 7.5)
            if t > episode.duration - 7.0:
                hum += math.sin(2 * math.pi * 31 * t) * 210 * ((t - (episode.duration - 7.0)) / 7.0)
            value = int(max(-32767, min(32767, hum + electrical + air + pulse)))
            samples.append(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(samples.tobytes())
        return path

    def _verify_video(self, path: Path) -> None:
        result = subprocess.run(
            [self.ffmpeg_path, "-v", "error", "-i", str(path), "-t", "1", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=45,
        )
        if result.returncode != 0:
            raise SignalRenderError(f"완성된 MP4 검증 실패: {result.stderr[-1000:]}")


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / max(1, wf.getframerate())
    except (OSError, wave.Error):
        return 0.0
