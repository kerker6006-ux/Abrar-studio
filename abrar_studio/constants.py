from __future__ import annotations

APP_NAME = "Abrar Studio"
APP_ID = "com.abrar.studio"
APP_VERSION = "3.0.4"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 24
GEMINI_FLASH_TTS = "gemini-3.1-flash-tts-preview"
GEMINI_PRO_TTS = "gemini-2.5-pro-preview-tts"
VOICE_SEO_YEON = "Leda"
VOICE_MIN_JUN = "Orus"
CREDENTIAL_TARGET = "AbrarStudio.GeminiAPIKey"
UPDATE_ASSET_NAME = "AbrarStudio-Update.zip"

LOCKED_VOICE_PROFILES = {
    "seo_yeon": {
        "voice_name": VOICE_SEO_YEON,
        "normal_model": GEMINI_FLASH_TTS,
        "emotional_model": GEMINI_PRO_TTS,
        "language": "ko-KR",
    },
    "min_jun": {
        "voice_name": VOICE_MIN_JUN,
        "normal_model": GEMINI_FLASH_TTS,
        "emotional_model": GEMINI_PRO_TTS,
        "language": "ko-KR",
    },
}

POSITION_X = {
    "far_left": 0.10,
    "left": 0.25,
    "center_left": 0.39,
    "center": 0.50,
    "center_right": 0.61,
    "right": 0.75,
    "far_right": 0.90,
}
