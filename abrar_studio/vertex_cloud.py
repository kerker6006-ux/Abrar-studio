"""Google Cloud Vertex AI client used by the simple Abrar Studio workflow.

This module deliberately uses Application Default Credentials (ADC), not a
Gemini Developer API key.  The user signs in once with ``gcloud auth
application-default login`` and Windows keeps the refresh token in the Google
Cloud credential store.
"""
from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from pathlib import Path


class VertexCloudError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VertexConfig:
    project_id: str
    location: str = "us-central1"
    image_model: str = "gemini-2.5-flash-image"
    tts_model: str = "gemini-2.5-flash-tts"
    text_model: str = "gemini-2.5-flash"


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

    def generate_image(self, prompt: str, output_path: Path, *, seed: int = 0, aspect_ratio: str = "9:16") -> Path:
        """Generate one PNG through Gemini Flash Image on Vertex AI.

        Gemini image generation is conversational rather than seed-deterministic.
        The production workflow therefore keeps each generated mouth-sheet as a
        reusable character identity asset instead of regenerating it per shot.
        """
        try:
            from google.genai import types
            image_client = self._genai.Client(vertexai=True, project=self.config.project_id, location="global")
            response = image_client.models.generate_content(
                model=self.config.image_model,
                contents=f"Generate exactly one image. Vertical {aspect_ratio} composition. {prompt}",
                config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
            )
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

    def generate_tts(self, text: str, output_path: Path, *, voice: str = "Kore", style: str = "") -> Path:
        """Generate PCM with Vertex Gemini TTS and write a portable WAV file."""
        try:
            from google.genai import types
            instruction = "Read the Korean dialogue naturally. Do not add any words."
            if style:
                instruction += f" Performance direction: {style.strip()}"
            response = self._client.models.generate_content(
                model=self.config.tts_model,
                contents=f"{instruction}\n\nDialogue:\n{text.strip()}",
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                        )
                    ),
                ),
            )
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
