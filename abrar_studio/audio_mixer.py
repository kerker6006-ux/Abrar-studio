"""FFmpeg dialogue-first music, ambience and SFX mastering."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .audio_director import AudioCue


class AudioMixError(RuntimeError):
    pass


def mix_video_audio(video: Path, cues: list[AudioCue], output: Path, ffmpeg_path: str) -> Path:
    if not cues:
        if video.resolve() != output.resolve():
            shutil.copy2(video, output)
        return output
    executable = shutil.which(ffmpeg_path) or (ffmpeg_path if Path(ffmpeg_path).exists() else None)
    if not executable:
        raise AudioMixError("FFmpeg was not found for final audio mastering.")
    inputs = [executable, "-y", "-hide_banner", "-i", str(video)]
    for cue in cues:
        if cue.role in {"music", "ambience"}:
            inputs += ["-stream_loop", "-1"]
        inputs += ["-i", str(cue.path)]
    filters = ["[0:a]aresample=48000,volume=1.0[dialogue]"]
    mix_inputs = ["[dialogue]"]
    for index, cue in enumerate(cues, 1):
        delay = max(0, round(cue.start_seconds * 1000))
        linear = 10 ** (cue.gain_db / 20.0)
        label = f"cue{index}"
        chain = f"[{index}:a]aresample=48000,volume={linear:.6f}"
        if delay:
            chain += f",adelay={delay}|{delay}"
        chain += f"[{label}]"
        filters.append(chain)
        mix_inputs.append(f"[{label}]")
    mix = "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=1.5,"
    analysis_filters = [*filters, mix + "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json[analysis]"]
    analysis = subprocess.run(
        inputs + ["-loglevel", "info", "-filter_complex", ";".join(analysis_filters), "-map", "[analysis]", "-f", "null", os.devnull],
        capture_output=True, text=True, timeout=360,
    )
    matches = re.findall(r'\{\s*"input_i".*?\}', analysis.stderr, flags=re.S)
    if analysis.returncode or not matches:
        raise AudioMixError((analysis.stderr or "FFmpeg loudness analysis failed")[-2000:])
    measured = json.loads(matches[-1])
    loudnorm = (
        "loudnorm=I=-16:TP=-1.5:LRA=11"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )
    filters.append(
        mix + loudnorm
        + ",alimiter=limit=0.84:attack=5:release=80:level=false,aformat=channel_layouts=stereo[mix]"
    )
    command = inputs + [
        "-loglevel", "error",
        "-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[mix]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
        "-movflags", "+faststart", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=360)
    if result.returncode:
        raise AudioMixError(result.stderr[-2000:])
    return output
