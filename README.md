# Abrar Studio 3.1.1

Abrar Studio is a local-first Windows application for Korean 2D cinematic motion-webtoon production. The reference-limited renderer uses approved complete character drawings for basic walking, speaking-mouth movement, blinks, expression swaps and camera moves. It does not generate a new video frame with an AI model during production.

## Included limited-animation system

Locked character packs can include local, reusable complete-frame loops with:

- whole-character walk drawings on one consistent transparent canvas
- low-frame-rate holds that preserve anatomy and clean line art
- simple speaking-mouth shapes and natural blink timing
- locked portrait expressions and full-body pose swaps
- speed, facing, phase-offset, ground-line and travel controls
- multi-character staging, camera pans/zooms and timed footsteps

These rig and motion files are installed once and remain on the PC. They are not downloaded for each video.

## Diagnostics and privacy

Version 3.0.5 provides opt-in PostHog fleet health and Sentry crash reporting alongside the Diagnostics page, full local checks, recent redacted errors, workflow timing, device health and an exportable support report. It uses a random installation ID and sends only app/device metadata, operation names and timing, quality scores, privacy-filtered exception types and stack locations. API keys, dialogue, prompts, project paths, filenames, usernames and media are never intentionally sent. Sentry PII collection, local-variable capture and performance tracing are disabled.

Gemini TTS multi-take failures now retain the underlying provider response, so quota, permission, model and network failures can be diagnosed instead of appearing only as a generic error. Audio quality measurements reject silent, clipped or implausibly short takes and record privacy-safe quality metrics.

## Automatic updates

After the initial installation, Abrar Studio checks its GitHub release channel at startup. A newer release is downloaded as a checksum-verified update package; the app closes, replaces its program files, and reopens automatically. User settings, encrypted credentials, projects, renders and cached voices are preserved, so future versions do not require reinstalling.

Version 3.0.3 makes this replacement atomic: the existing installation is preserved until the staged executable is hash-verified, the directory swap succeeds, and the installed executable matches the staged hash. A failed update rolls back, writes a persistent updater log, shows the actual failure on the next launch, and suppresses an immediate repeat prompt.

Version 3.0.4 routes normal dialogue to Gemini 3.1 Flash TTS, retains Gemini 2.5 Pro TTS for complex and emotional performances, and reads audio from Google's current Interactions `steps` response schema.

Version 3.0.5 prepares updates before shutdown, launches the PowerShell helper from the UI thread without detached-process mode, verifies that the helper survived startup, and records early launch failures in the support report.

Version 3.1.1 repairs upgraded default projects by force-refreshing bundled character and background assets, and maps legacy walking motion names to the approved complete-frame walk loop.

## Complete episode pipeline

1. Create or import an episode JSON.
2. Run Preflight to verify character checksums, fixed voice profiles, complete-frame loops, music, SFX and pacing.
3. Generate new Korean dialogue with Gemini TTS. Approved WAV files are cached locally.
4. Abrar Studio derives mouth timing from the audio and applies close-up facial acting.
5. Full-body locomotion uses checksum-locked complete drawings instead of rotating limb pieces.
6. The renderer adds listener reactions, camera movement, transitions, VFX, subtitles, ambience, music ducking, footsteps and timed SFX.
7. Final Validation blocks export if any identity, voice, rig, media or continuity gate fails.
8. The episode renders at 1280×720, constant 24 FPS, H.264 video and 48 kHz AAC audio.

## Install on Windows

1. Extract the ZIP completely.
2. Double-click `INSTALL_ABRAR_STUDIO.bat`.
3. Keep the internet connected while Python dependencies and the private FFmpeg runtime are installed.
4. The installer runs the unit suite and a real articulated 720p render three times before creating shortcuts.
5. Launch **Abrar Studio** from the Desktop.
6. Open Settings, save a newly generated Gemini API key, and click **Test Gemini**.

Do not reuse the Gemini key posted earlier in chat. It is exposed and is not stored in this package.

## Try the reference motion

Open `templates/episodes/articulated_motion_showcase.json`. It demonstrates:

- Seo-yeon walking confidently through a school hallway
- a sudden stop and dramatic reaction
- Seo-yeon and Min-jun running together with separate gait phases
- auto-generated footstep cues, music, ambience, camera tracking and effects

Run `python scripts/render_quality_demo.py` to generate `AbrarStudio_v3_Articulated_Motion_Demo_720p.mp4` with the same renderer. Generated MP4 files are release artifacts and are not stored in the source repository.

## Locked consistency

- Character identity assets and complete-frame animation drawings are SHA-256 locked.
- Seo-yeon permanently uses Gemini voice `Leda`.
- Min-jun permanently uses Gemini voice `Orus`.
- Approved dialogue is cached and is not regenerated during later renders.
- Main characters are never redrawn by a generative image or video model during normal production.

## Quality boundary

Abrar Studio targets limited webtoon drama: reusable complete-frame loops, face/pose swaps, simple talking and blinking, camera work, cuts and strong audio design. It does not claim frame-by-frame television-anime animation or detailed finger, cloth and hair simulation. New outfits and complex actions still require one-time approved artwork. “Technical readiness” verifies known file, timing and rendering failures; it never claims that a human has approved the final visual result.
