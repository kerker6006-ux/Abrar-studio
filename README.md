# Abrar Studio 4.1

Abrar Studio is a one-prompt Windows application for producing short vertical Korean 2D web-drama videos. Google Vertex AI creates the story artwork and Korean voices; the installed app performs character locking, compositing, limited motion, camera cuts, subtitles, audio direction, mixing, and H.264 rendering locally on the CPU.

## One-prompt workflow

1. Paste a Korean script or scene idea.
2. Gemini plans 3–7 shots and up to three recurring characters.
3. Every character is created first. The master and all required performance frames are SHA-256 locked before shot rendering begins.
4. Each speaking pose receives closed, small, and wide original-mouth drawings conditioned on the exact same body-pose reference. No mouth sticker is placed over the face.
5. One locked background is generated per story location and reused across its shots.
6. The CPU renderer stages multiple characters, applies independent smooth limited motion, cuts between speakers and reactions, and uses slow push-ins instead of a scrolling background.
7. Gemini 3.1 Flash TTS handles normal Korean dialogue. Gemini 2.5 Pro TTS is reserved for complex crying, grief, terror, and breakdown performances.
8. The audio director selects music, ambience, and timed SFX from the indexed licensed catalog, then FFmpeg mixes and masters the finished 720×1280, 24 FPS video.

The same script hash reuses its locked characters, backgrounds, approved voice cache, and audio choices. A changed model, dialogue, reference image, or checksum invalidates only the affected cached asset.

## Audio catalog

The installer contains 408 indexed music and sound-effect files, including 369 CC0 files from official Kenney packs. The catalog supports WAV, MP3, OGG, M4A, AAC, and FLAC and is selected semantically from Korean or English scene meaning.

The index is intentionally unbounded. Place additional licensed files in `%LOCALAPPDATA%\AbrarStudio\AudioLibrary`, or add directories through `audio_library_paths` in the settings file; they become part of the same deterministic catalog without rebuilding the app. Source and license details for bundled third-party audio are in `assets/audio_library/README.md`.

## Google Cloud setup

Abrar Studio uses Application Default Credentials and the selected Google Cloud project. Billing and the Vertex AI API must be enabled for that project.

```powershell
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project YOUR_PROJECT_ID
```

Enter `YOUR_PROJECT_ID` in the app and click **Check**. The production path uses:

- `gemini-3.1-flash-image` for character, pose, mouth, and background artwork
- `gemini-3.1-flash-tts-preview` for normal dialogue
- `gemini-2.5-pro-tts` for complex emotional dialogue
- `gemini-2.5-flash` for short JSON shot planning

Cloud artwork and TTS incur Google Cloud usage. Rendering, motion, camera work, subtitles, audio selection, and encoding run locally and do not require a rented GPU.

## Install and automatic updates

Install `AbrarStudio-Setup.exe` once. Abrar Studio checks its GitHub release channel at startup. A newer checksum-verified update is staged, the app closes, its program files are replaced atomically, and it reopens. Settings, credentials, productions, locked artwork, and voice caches are preserved. Future versions do not require reinstalling.

## Development verification

```powershell
python -m pytest -q
python scripts/run_cloud_production_test.py --project YOUR_PROJECT_ID --script-file story-ko.txt --ffmpeg C:\path\to\ffmpeg.exe
```

The Windows release workflow runs the complete suite and render verification three times before publishing the installer and automatic-update ZIP.

## Privacy and diagnostics

Sentry crash reporting and PostHog fleet-health analytics are opt-in. Telemetry is designed to exclude API credentials, dialogue, prompts, media, project paths, filenames, and usernames. Local support reports keep privacy-filtered error types, stack locations, device health, operation timing, and quality results.

## Honest quality boundary

Abrar Studio produces polished limited-motion webtoon drama: consistent generated drawings, acting poses, original-mouth changes, multi-character staging, walking/recoil/crying motion, reaction cuts, push-ins, subtitles, and strong sound design. It is not frame-by-frame television anime, physics-based cloth/hair animation, or Veo-style generative video. Visual quality still depends on the generated reference artwork and should be reviewed before publishing.
