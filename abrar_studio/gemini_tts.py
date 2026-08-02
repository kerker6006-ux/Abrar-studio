from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.request
import wave
import math
import os
import time
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CharacterManifest, Shot
from .constants import GEMINI_FLASH_TTS, VOICE_SEO_YEON


class TTSGenerationError(RuntimeError):
    pass


EMOTIONAL_STATES = {
    "anger", "angry", "fear", "afraid", "panic", "panicked", "crying", "sad",
    "breakdown", "romantic", "love", "shock", "shocked", "whisper", "shouting",
}


@dataclass(slots=True)
class TTSRequest:
    model: str
    voice: str
    prompt: str
    cache_key: str


class GeminiTTSClient:
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(self, api_key: str, timeout: int = 120) -> None:
        if not api_key:
            raise TTSGenerationError("Gemini API key is missing")
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def build_request(character: CharacterManifest, shot: Shot) -> TTSRequest:
        profile = character.voice_profile
        use_pro = shot.voice_model == "pro" or (
            shot.voice_model == "auto" and shot.emotion.lower() in EMOTIONAL_STATES
        )
        model = profile.emotional_model if use_pro else profile.normal_model
        direction = shot.voice_direction.strip() or _default_direction(shot.emotion, shot.emotion_level)
        prompt = (
            f"# AUDIO PROFILE: {character.display_name}\n"
            f"Korean dramatic animation character. Keep the same underlying speaker identity and vocal age.\n"
            f"{profile.audio_profile.strip()}\n\n"
            f"# SCENE\nA polished Korean supernatural drama scene.\n\n"
            f"# DIRECTOR'S NOTES\n{direction}\n"
            "Speak natural contemporary Korean. Do not change the character's identity. "
            "Keep pronunciation clear and emotionally believable.\n\n"
            f"# TRANSCRIPT\n{shot.dialogue.strip()}"
        )
        raw = "\0".join([character.character_id, profile.version, model, profile.voice_name, prompt])
        cache_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return TTSRequest(model=model, voice=profile.voice_name, prompt=prompt, cache_key=cache_key)

    def generate(self, request_data: TTSRequest, output_path: Path) -> Path:
        payload = {
            "model": request_data.model,
            "input": request_data.prompt,
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": request_data.voice}]},
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
                "Api-Revision": "2026-05-20",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TTSGenerationError(f"Gemini TTS HTTP {exc.code}: {detail[:500]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TTSGenerationError(f"Gemini TTS network error: {exc}") from exc

        audio_b64 = _extract_audio_base64(result)
        try:
            pcm = base64.b64decode(audio_b64)
        except Exception as exc:
            raise TTSGenerationError("Gemini returned invalid audio data") from exc
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(pcm)
        return output_path

    def test_connection(self, output_path: Path) -> dict[str, float]:
        """Make a short paid TTS request and validate the returned Korean WAV."""
        request_data = TTSRequest(
            model=GEMINI_FLASH_TTS,
            voice=VOICE_SEO_YEON,
            prompt="한국어로 자연스럽고 짧게 말하세요: 연결 확인이 완료되었습니다.",
            cache_key="connection-test",
        )
        self.generate(request_data, output_path)
        metrics = _score_wav(output_path)
        if metrics["score"] < 20 or metrics["duration"] < 0.35:
            output_path.unlink(missing_ok=True)
            raise TTSGenerationError("Gemini returned audio, but the connection-test WAV failed quality validation")
        return metrics

    def generate_best(self, request_data: TTSRequest, output_path: Path, takes: int = 1) -> Path:
        """Generate one or more performances and keep the cleanest usable take.

        Emotional lines normally request three takes. Selection is deterministic
        and checks clipping, silence, duration and vocal dynamics. The chosen WAV
        is cached permanently beside a JSON audit record.
        """
        takes = max(1, min(4, int(takes)))
        candidates: list[tuple[float, Path, dict[str, float]]] = []
        output_path.parent.mkdir(parents=True, exist_ok=True)
        for index in range(1, takes + 1):
            temp = output_path.with_name(f".{output_path.stem}.take{index}.wav")
            variant = TTSRequest(
                model=request_data.model, voice=request_data.voice, cache_key=request_data.cache_key,
                prompt=request_data.prompt + (f"\n\n# TAKE {index}\nGive a distinct but character-consistent performance." if takes > 1 else ""),
            )
            last_error: Exception | None = None
            for attempt in range(2):
                try:
                    self.generate(variant, temp)
                    last_error = None
                    break
                except TTSGenerationError as exc:
                    last_error = exc
                    if attempt == 0:
                        time.sleep(1.0)
            if last_error:
                continue
            metrics = _score_wav(temp, len(request_data.prompt))
            candidates.append((metrics["score"], temp, metrics))
        if not candidates:
            raise TTSGenerationError("All Gemini TTS performance takes failed")
        candidates.sort(key=lambda item: item[0], reverse=True)
        score, winner, metrics = candidates[0]
        os.replace(winner, output_path)
        for _, path, _ in candidates[1:]:
            path.unlink(missing_ok=True)
        audit = output_path.with_suffix(".json")
        audit.write_text(json.dumps({
            "model": request_data.model, "voice": request_data.voice, "takes": takes,
            "selected_score": score, "selected_metrics": metrics,
        }, indent=2), encoding="utf-8")
        return output_path


def _extract_audio_base64(result: dict[str, Any]) -> str:
    candidates: list[Any] = [
        result.get("output_audio", {}).get("data") if isinstance(result.get("output_audio"), dict) else None,
        result.get("audio", {}).get("data") if isinstance(result.get("audio"), dict) else None,
    ]
    outputs = result.get("outputs")
    if isinstance(outputs, list):
        for item in outputs:
            if isinstance(item, dict):
                candidates.extend([
                    item.get("audio", {}).get("data") if isinstance(item.get("audio"), dict) else None,
                    item.get("output_audio", {}).get("data") if isinstance(item.get("output_audio"), dict) else None,
                ])
    for value in candidates:
        if isinstance(value, str) and value:
            return value
    raise TTSGenerationError("Gemini response did not contain audio data")


def _default_direction(emotion: str, level: int) -> str:
    emotion = emotion.lower().strip() or "neutral"
    intensity = {1: "subtle", 2: "restrained", 3: "clear", 4: "intense", 5: "extreme but believable"}[level]
    notes = {
        "neutral": "Conversational, attentive, warm, with natural pauses.",
        "shock": "Start with a quick intake of breath, then speak with stunned disbelief.",
        "shocked": "Start with a quick intake of breath, then speak with stunned disbelief.",
        "anger": "Controlled anger first, stronger consonants near the end; do not become unintelligible.",
        "fear": "Tense breath, slightly uneven pace, trying to stay composed.",
        "crying": "Trembling breath and a small voice crack; words remain understandable.",
        "sad": "Quiet grief, delayed response, restrained breathiness.",
        "romantic": "Soft, sincere, intimate, with gentle pacing and no melodrama.",
        "comedy": "Fast, expressive reaction with crisp timing.",
        "suspicious": "Low, careful delivery with a questioning edge.",
        "determined": "Steady breath, firm pace, direct confidence.",
    }
    return f"Performance intensity: {intensity}. {notes.get(emotion, notes['neutral'])}"


def _score_wav(path: Path, prompt_length: int = 0) -> dict[str, float]:
    try:
        with wave.open(str(path), "rb") as wf:
            channels, width, rate, count = wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()
            raw = wf.readframes(count)
        if width != 2 or channels < 1 or count < 100:
            return {"score": -100.0, "duration": 0.0, "peak": 0.0, "rms": 0.0, "silence": 1.0, "clipping": 1.0}
        samples = array("h"); samples.frombytes(raw)
        if channels > 1: samples = array("h", samples[::channels])
        total = max(1, len(samples)); duration = total / max(1, rate)
        peak = max(abs(x) for x in samples) / 32768.0
        rms = math.sqrt(sum(float(x)*x for x in samples) / total) / 32768.0
        silence = sum(1 for x in samples if abs(x) < 180) / total
        clipping = sum(1 for x in samples if abs(x) > 32500) / total
        # Broad bounds avoid choosing empty, clipped or implausibly short responses.
        score = 100.0
        score -= max(0.0, silence - 0.52) * 110.0
        score -= clipping * 900.0
        score -= max(0.0, 0.025 - rms) * 600.0
        score -= max(0.0, peak - 0.985) * 500.0
        if duration < 0.35: score -= 80.0
        if duration > 45.0: score -= 15.0
        return {"score": round(score, 4), "duration": round(duration, 4), "peak": round(peak, 5), "rms": round(rms, 5), "silence": round(silence, 5), "clipping": round(clipping, 6)}
    except (OSError, wave.Error):
        return {"score": -100.0, "duration": 0.0, "peak": 0.0, "rms": 0.0, "silence": 1.0, "clipping": 1.0}
