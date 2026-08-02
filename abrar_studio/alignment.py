from __future__ import annotations

import json
import math
import statistics
import wave
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path

from .visemes import shape_for_character


@dataclass(frozen=True, slots=True)
class AlignmentSegment:
    start: float
    end: float
    viseme: str
    text: str
    energy: float = 0.0


def _mono_samples(path: Path) -> tuple[array, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError("Only 16-bit PCM WAV is supported for alignment")
    values = array("h")
    values.frombytes(raw)
    if channels > 1:
        values = array("h", values[::channels])
    return values, rate


def _energy_frames(samples: array, rate: int, frame_ms: int = 20) -> list[float]:
    per = max(1, int(rate * frame_ms / 1000))
    result: list[float] = []
    for start in range(0, len(samples), per):
        block = samples[start:start + per]
        if not block:
            continue
        rms = math.sqrt(sum(float(v) * v for v in block) / len(block)) / 32768.0
        result.append(rms)
    return result


def _speech_bounds(energy: list[float], duration: float) -> tuple[float, float]:
    if not energy or duration <= 0:
        return 0.0, max(0.0, duration)
    nonzero = [x for x in energy if x > 0.0002]
    baseline = statistics.median(nonzero) if nonzero else 0.002
    peak = max(energy)
    threshold = max(0.002, min(0.05, baseline * 1.7, peak * 0.22))
    active = [i for i, value in enumerate(energy) if value >= threshold]
    if not active:
        return 0.0, duration
    unit = duration / len(energy)
    start = max(0.0, active[0] * unit - 0.06)
    end = min(duration, (active[-1] + 1) * unit + 0.08)
    if end - start < 0.25:
        return 0.0, duration
    return start, end


def _units(text: str) -> list[tuple[str, float, bool]]:
    pause_chars = set(" \t\r\n,.;:!?…—-()[]{}\"'·")
    units: list[tuple[str, float, bool]] = []
    for ch in text.strip():
        if ch in pause_chars:
            weight = 1.15 if ch in ".!?…" else 0.58
            units.append((ch, weight, True))
        else:
            units.append((ch, 1.0, False))
    return units or [("", 1.0, True)]


def build_alignment(text: str, wav_path: Path, output_path: Path | None = None) -> list[AlignmentSegment]:
    """Create deterministic Korean syllable/viseme timing from the actual WAV.

    This requires no cloud model or GPU. It detects real leading/trailing silence
    and uses the spoken duration to allocate Hangul syllables and punctuation.
    The result is cached beside the approved voice file.
    """
    samples, rate = _mono_samples(wav_path)
    duration = len(samples) / max(1, rate)
    energy = _energy_frames(samples, rate)
    speech_start, speech_end = _speech_bounds(energy, duration)
    items = _units(text)
    total_weight = sum(weight for _, weight, _ in items)
    spoken = max(0.12, speech_end - speech_start)
    cursor = speech_start
    segments: list[AlignmentSegment] = []
    for index, (ch, weight, pause) in enumerate(items):
        length = spoken * weight / total_weight
        end = speech_end if index == len(items) - 1 else min(speech_end, cursor + length)
        if pause:
            shape = "closed"
            e = 0.0
        else:
            shape = shape_for_character(ch)
            midpoint = (cursor + end) * 0.5
            energy_index = min(len(energy) - 1, max(0, int(midpoint / max(duration, 1e-6) * len(energy)))) if energy else 0
            e = energy[energy_index] if energy else 0.0
        segments.append(AlignmentSegment(round(cursor, 4), round(end, 4), shape, ch, round(e, 6)))
        cursor = end
    if speech_start > 0.02:
        segments.insert(0, AlignmentSegment(0.0, round(speech_start, 4), "closed", "", 0.0))
    if speech_end < duration - 0.02:
        segments.append(AlignmentSegment(round(speech_end, 4), round(duration, 4), "closed", "", 0.0))
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({
            "schema": 1,
            "wav": wav_path.name,
            "duration": round(duration, 4),
            "text": text,
            "segments": [asdict(item) for item in segments],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return segments


def load_alignment(path: Path) -> list[AlignmentSegment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [AlignmentSegment(**item) for item in data.get("segments", [])]


def alignment_at(segments: list[AlignmentSegment], t: float, amplitude: float = 0.0) -> str:
    for item in segments:
        if item.start <= t < item.end:
            if amplitude < 0.012 and item.viseme != "closed":
                return "closed"
            return item.viseme
    return "closed"
