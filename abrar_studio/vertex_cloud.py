"""Google Cloud Vertex AI client used by the simple Abrar Studio workflow.

This module deliberately uses Application Default Credentials (ADC), not a
Gemini Developer API key.  The user signs in once with ``gcloud auth
application-default login`` and Windows keeps the refresh token in the Google
Cloud credential store.
"""
from __future__ import annotations

import os
import mimetypes
import time
import wave
from dataclasses import dataclass
from pathlib import Path


class VertexCloudError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VertexConfig:
    project_id: str
    location: str = "us-central1"
    image_model: str = "gemini-3.1-flash-image"
    tts_model: str = "gemini-3.1-flash-tts-preview"
    tts_pro_model: str = "gemini-2.5-pro-tts"
    text_model: str = "gemini-2.5-flash"
    image_min_interval_seconds: float = 15.0


class VertexStudioClient:
    """Small, testable wrapper around the official Google Gen AI SDK."""

    def __init__(self, config: VertexConfig) -> None:
        self.config = config
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - installer issue
            raise VertexCloudError("Google Cloud support is not installed. Run the Abrar Studio installer again.") from exc
        self._genai = genai
        self._client = genai.Client(vertexai=True, project=config.project_id, location=config.location)
        self._last_image_request = 0.0
        self.last_tts_model = config.tts_model

    @classmethod
    def from_environment(cls, project_id: str | None = None) -> "VertexStudioClient":
        project = (project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        if not project:
            raise VertexCloudError("Google Cloud project ID is missing. Connect Google Cloud in Abrar Studio first.")
        return cls(VertexConfig(project_id=project))

    def verify_credentials(self) -> None:
        try:
            import google.auth
            import google.auth.transport.requests
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            credentials.refresh(google.auth.transport.requests.Request())
        except Exception as exc:
            raise VertexCloudError(
                "Google Cloud sign-in is missing. Run: gcloud auth application-default login"
            ) from exc

    def generate_text(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(model=self.config.text_model, contents=prompt)
            text = (response.text or "").strip()
        except Exception as exc:
            raise VertexCloudError(f"Gemini story planning failed: {exc}") from exc
        if not text:
            raise VertexCloudError("Gemini returned an empty story plan.")
        return text

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        seed: int = 0,
        aspect_ratio: str = "9:16",
        reference_images: list[Path] | None = None,
    ) -> Path:
        """Generate one PNG through Gemini Flash Image on Vertex AI.

        Gemini image generation is conversational rather than seed-deterministic.
        The production workflow therefore keeps each generated mouth-sheet as a
        reusable character identity asset instead of regenerating it per shot.
        """
        try:
            from google.genai import types
            image_client = self._genai.Client(vertexai=True, project=self.config.project_id, location="global")
            contents: list[object] = [
                "Generate exactly one image. "
                f"Vertical {aspect_ratio} composition. {prompt}"
            ]
            for reference in reference_images or []:
                mime = mimetypes.guess_type(reference.name)[0] or "image/png"
                contents.append(types.Part.from_bytes(data=reference.read_bytes(), mime_type=mime))
            if reference_images:
                contents.append(
                    "The supplied images are locked identity references. Preserve the exact face, hair, "
                    "skin tone, body proportions, outfit design, palette and drawing style."
                )
            elapsed = time.monotonic() - self._last_image_request
            if elapsed < self.config.image_min_interval_seconds:
                time.sleep(self.config.image_min_interval_seconds - elapsed)
            response = None
            for attempt in range(1, 4):
                try:
                    self._last_image_request = time.monotonic()
                    response = image_client.models.generate_content(
                        model=self.config.image_model,
                        contents=contents,
                        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
                    )
                    break
                except Exception as exc:
                    if "429" not in str(exc) or attempt == 3:
                        raise
                    time.sleep(30.0 * attempt)
            if response is None:
                raise VertexCloudError("Gemini Flash Image did not return a response.")
            image_data = next(
                (part.inline_data.data for part in response.candidates[0].content.parts if part.inline_data and part.inline_data.data),
                None,
            )
            if not image_data:
                raise VertexCloudError("Gemini Flash Image returned text but no image. Please retry.")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_data)
            return output_path
        except Exception as exc:
            raise VertexCloudError(f"Gemini Flash Image artwork generation failed: {exc}") from exc

    def generate_tts(
        self, text: str, output_path: Path, *, voice: str = "Kore", style: str = "", model: str | None = None
    ) -> Path:
        """Generate PCM with Vertex Gemini TTS and write a portable WAV file."""
        try:
            from google.genai import types
            instruction = "Read the Korean dialogue naturally. Do not add any words."
            if style:
                instruction += f" Performance direction: {style.strip()}"
            requested_model = model or self.config.tts_model
            candidates = [requested_model]
            if requested_model != self.config.tts_model:
                candidates.append(self.config.tts_model)
            response = None
            last_error: Exception | None = None
            for candidate_model in candidates:
                for attempt in range(1, 4):
                    try:
                        response = self._client.models.generate_content(
                            model=candidate_model,
                            contents=f"{instruction}\n\nDialogue:\n{text.strip()}",
                            config=types.GenerateContentConfig(
                                response_modalities=["AUDIO"],
                                speech_config=types.SpeechConfig(
                                    language_code="ko-KR",
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                                    )
                                ),
                            ),
                        )
                        self.last_tts_model = candidate_model
                        break
                    except Exception as exc:
                        last_error = exc
                        retryable = any(token in str(exc) for token in ("429", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "timeout"))
                        if retryable and attempt < 3:
                            time.sleep(15.0 * attempt)
                            continue
                        break
                if response is not None:
                    break
            if response is None:
                raise last_error or VertexCloudError("Gemini TTS did not return a response.")
            pcm = response.candidates[0].content.parts[0].inline_data.data
        except Exception as exc:
            raise VertexCloudError(f"Gemini TTS generation failed: {exc}") from exc
        if not pcm:
            raise VertexCloudError("Gemini TTS returned no audio.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        return output_path
