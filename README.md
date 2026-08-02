# Abrar Studio 3.0.1

Abrar Studio is a local-first Windows application for Korean 2D cinematic motion-webtoon production. Version 3 adds an articulated side-view puppet engine so Seo-yeon and Min-jun can walk, run, stop, recoil and move across scenes with independently rotated limb segments, automatic footstep timing and tracking-camera travel.

## Included motion system

The two locked lead characters include local, reusable articulated rigs with:

- head and torso hierarchy
- front/back upper arms and forearms
- front/back thighs, lower legs and feet
- Seo-yeon's delayed back-hair layer
- idle breathing
- slow, normal, confident and sad walks
- normal and panicked runs
- start-walk, sudden-stop, step-back and shock-recoil motions
- speed, intensity, facing, phase-offset, ground-line and travel controls
- two-person locomotion with staggered footsteps

These rig and motion files are installed once and remain on the PC. They are not downloaded for each video.

## Automatic updates

After the initial installation, Abrar Studio checks its GitHub release channel at startup. A newer release is downloaded as a checksum-verified update package; the app closes, replaces its program files, and reopens automatically. User settings, encrypted credentials, projects, renders and cached voices are preserved, so future versions do not require reinstalling.

## Complete episode pipeline

1. Create or import an episode JSON.
2. Run Preflight to verify character checksums, fixed voice profiles, poses, articulated rigs, music, SFX and pacing.
3. Generate new Korean dialogue with Gemini TTS. Approved WAV files are cached locally.
4. Abrar Studio derives mouth timing from the audio and applies close-up facial acting.
5. Full-body shots use the articulated puppet engine for walk/run/action motion.
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

- Character identity assets and articulated rig parts are SHA-256 locked.
- Seo-yeon permanently uses Gemini voice `Leda`.
- Min-jun permanently uses Gemini voice `Orus`.
- Approved dialogue is cached and is not regenerated during later renders.
- Main characters are never redrawn by FLUX, Wan or another generative video model during normal production.

## Quality boundary

Abrar Studio 3 matches the limited 2D bone/cutout motion style of webtoon drama channels: reusable walk/run loops, limb rotations, face/hand swaps in acting shots, fast camera work, effects and strong audio design. It does not claim frame-by-frame television-anime animation or detailed independent finger, cloth and hair simulation. New outfits and complex new actions still require a one-time approved layered asset pack.
