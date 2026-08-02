# Abrar Studio — complete project context for future AI chats

> Read this file before changing the project. It is the canonical high-level handoff for Abrar Studio 3.0.3. After reading it, inspect the implementation files named in the module map before making technical claims or edits.

## 1. Project identity

- **Product:** Abrar Studio
- **Current source version:** 3.0.3
- **Repository:** `kerker6006-ux/Abrar-studio`
- **Platform:** local-first Windows desktop application
- **Language/runtime:** Python 3.11+, Tkinter UI, Pillow image composition, FFmpeg rendering
- **Primary output:** 1280×720 motion-webtoon video at constant 24 FPS, H.264 video, AAC 48 kHz audio
- **Production language:** Korean (`ko-KR`)
- **Core creative target:** limited 2D bone/cutout Korean webtoon drama animation—not frame-by-frame television anime
- **Story universe:** **The 2:14 Scanner**, a supernatural romantic mystery/drama centered on a convenience store and events that recur around 2:14 a.m.

Abrar Studio converts structured episode JSON into a finished cinematic motion-webtoon. It uses locked reusable character artwork, articulated side-view puppet rigs, expression and hand swaps, Korean speech, lip shapes, camera movement, visual effects, subtitles, music, ambience, and timed sound effects.

The system is deliberately local-first. Recurring characters, rigs, backgrounds, music, and SFX are installed once and reused. Internet access is needed only for actions such as generating new Gemini TTS dialogue and checking/downloading GitHub releases.

## 2. Non-negotiable product principles

1. **Recurring characters are never regenerated during normal production.** Seo-yeon and Min-jun must be assembled from their approved local assets.
2. **Identity is checksum locked.** Editing a locked character file without intentionally updating and reviewing its manifest must fail validation.
3. **Voice identity is permanent.** Seo-yeon uses Gemini voice `Leda`; Min-jun uses `Orus`. Emotion changes through direction and model choice, not by changing the speaker.
4. **Approved voice audio is cached.** Re-rendering the same approved line should reuse the cached WAV instead of making another paid request.
5. **Final export is gated.** Identity, voice, rig, acting, sound, music, pacing, FFmpeg, and continuity checks must pass.
6. **The quality target is honest.** This is an efficient motion-webtoon/puppet pipeline. It is not unrestricted frame-by-frame anime, full 3D, or generative video.
7. **Do not embed secrets.** The Gemini API key must never appear in source, project JSON, logs, releases, or rendered output.

## 3. Creative concept: The 2:14 Scanner

The initial episode concept is a supernatural Korean drama set around the Night24 convenience store. At 2:14 a.m., a scanner produces impossible information connected to people, memories, fate, and past events. Seo-yeon encounters the phenomenon during her night shift. Min-jun appears to know more than he initially reveals. Their relationship develops through mystery, danger, protection, mistrust, empathy, and restrained romance.

The sample episode establishes:

- a fast supernatural hook involving the scanner;
- a message implying a customer was already scanned fifteen years earlier;
- Min-jun warning Seo-yeon not to trust the message without context;
- Seo-yeon confronting him about appearing at 2:13 a.m.;
- the idea that the scanner tells a truth without supplying its context;
- a choice to alter someone’s fate before dawn, but at an unknown price.

The intended tone combines supernatural mystery, romance, school/convenience-store drama, betrayal, revenge, fear, crying scenes, chases, and emotionally charged cliffhangers. Bundled templates provide examples for school betrayal, romance confession, revenge reveal, crying breakdown, and articulated motion.

## 4. Locked lead characters

### Han Seo-yeon (`seo_yeon`)

- **Korean name:** 한서연
- **Age:** approximately 23–25
- **Height:** 162 cm
- **Role:** Night24 convenience-store night worker; story heroine
- **Visual identity:** long dark hair, soft brown eyes, pink hair clip, gray hoodie, navy/black Night24 work vest, dark pants, black canvas sneakers, Night24 name badge
- **Personality:** kind and warm, but courageous and resolute when facing injustice; emotionally honest; deeply empathetic toward other people’s pain
- **Arc:** an ordinary young woman pulled into supernatural events during the night shift who grows into a protector of other people’s nights
- **Themes/keywords:** justice, empathy, courage, growth, heroine
- **Outfit ID:** `night24_uniform_01`
- **Palette ID:** `seo_yeon_locked_palette_v1`
- **Rig:** `ARTICULATED_SIDE_RIG_3.0`
- **Voice profile:** `SY_VOICE_1.0`
- **Gemini voice:** `Leda`
- **Voice description in source:** a warm but alert young Korean woman in her mid-twenties; courageous, emotionally transparent, never childish
- **Special rig behavior:** delayed back-hair motion for follow-through

Her reference sheet, portrait, poses, expressions, gestures, mouth shapes, and articulated rig live under `assets/characters/seo_yeon/`.

### Kang Min-jun (`min_jun`)

- **Korean name:** 강민준
- **Age:** approximately 26–28
- **Height:** 188 cm
- **Role:** Night24 night worker and freelance photographer; mystery/protector lead
- **Visual identity:** tousled black hair, dark brown eyes, black hoodie and charcoal/black Night24 jacket, dark pants, black sneakers, Night24 name badge
- **Personality:** calm, rational, observant, and strongly responsible; does not trust people easily, but remains loyal once committed; protects others and solves problems under pressure
- **Emotional style:** restrained expression; sincerity is shown primarily through actions
- **Themes/keywords:** cool-headedness, protector, romantic skepticism, persistence, mystery
- **Outfit ID:** `black_jacket_01`
- **Palette ID:** `min_jun_locked_palette_v1`
- **Rig:** `ARTICULATED_SIDE_RIG_3.0`
- **Voice profile:** `MJ_VOICE_1.0`
- **Gemini voice:** `Orus`
- **Voice description:** see `assets/characters/min_jun/manifest.json`; the manifest is the authority for voice wording and version

His reference sheet, portrait, poses, expressions, gestures, mouth shapes, and articulated rig live under `assets/characters/min_jun/`.

### Shared approved character assets

Each lead has:

- reference sheet, portrait, UI card, and full-front art;
- `full_front`, `full_three_quarter`, and `full_side` poses;
- expressions: `neutral`, `smile`, `suspicious`, `shock`, `anger`, `embarrassed`, `sad`, and `breakdown`;
- gestures: `relaxed`, `fist`, `write`, `phone`, `palm`, `chest`, `point`, and `stop`;
- mouth sprites: `closed`, `open`, `wide`, `round`, `narrow`, and `soft`;
- an articulated side rig with head, torso, front/back arm chains, front/back leg chains, and feet;
- SHA-256 checksums recorded in `manifest.json`.

Do not casually replace or edit these files. A deliberate character revision requires a new reviewed/versioned asset pack and updated checksums.

## 5. Animation model

Abrar Studio uses two complementary visual modes.

### Close-up and acting shots

Portrait/expression cards are used for dialogue and emotional close-ups. The renderer can add:

- mouth/viseme overlays on expression cards considered safe for overlay;
- breathing, balance shifts, head sway, tremble, recoil, leaning, collapse, shy movement, fear tremor, nodding, head shaking, and listener reactions;
- optional hand/gesture overlays;
- gaze influence and multi-character depth/positioning.

Intense cards with painted shouting or crying mouths intentionally avoid a generic mouth overlay to prevent double-mouth artifacts.

### Full-body articulated motion

Full-body side-view locomotion is generated from layered sprites and joint rotations. The puppet engine performs hierarchical transforms, ground-contact correction, facing/mirroring, cached pose cycles, and character travel.

Supported canonical motion names:

- `idle_breathe`
- `walk_slow`
- `walk_normal`
- `walk_confident`
- `walk_sad`
- `run_normal`
- `run_panicked`
- `start_walk`
- `stop_sudden`
- `step_back`
- `shock_recoil`

Aliases such as `walk`, `walking`, `run`, `running`, `confident_walk`, `sad_walk`, `panic_run`, `recoil`, and `shock_back` are normalized by `abrar_studio/puppet.py`.

Motion controls on an actor:

| Field | Meaning | Allowed range/default |
|---|---|---|
| `motion` | motion clip or `auto` | default `auto` |
| `motion_speed` | gait/cycle multiplier | 0.2–3.0, default 1.0 |
| `travel_x` | horizontal travel in screen widths | -1.5–1.5, default 0 |
| `ground_y` | normalized ground line | 0.55–1.05, default 0.95 |
| `facing` | `left`, `right`, or inferred from travel | default `auto` |
| `cycle_offset` | phase offset for multiple actors | -2.0–2.0 |
| `motion_intensity` | movement exaggeration | 0.25–1.7 |

For articulated motion, use a non-close-up pose—normally `full_side`. Tracking shots should have meaningful `travel_x`.

### Automatic gait audio

`footstep_times()` derives two foot contacts per gait cycle. When a shot does not provide an explicit foot/step SFX cue, the renderer inserts alternating `footstep_left` and `footstep_right` sounds. Their stereo pan follows actor position. Running may also add low-volume `cloth_swish` cues. `cycle_offset` prevents two actors from stepping in mechanical unison.

## 6. Voice and Korean lip synchronization

### Gemini TTS

`abrar_studio/gemini_tts.py` sends requests to the Gemini Interactions endpoint.

- Normal delivery uses the locked character’s flash TTS model.
- Emotional states or `voice_model: "pro"` use the locked emotional/pro model.
- The prompt includes the character audio profile, Korean-drama context, director’s notes, emotion direction, and the exact transcript.
- The cache key is SHA-256 over character ID, voice-profile version, model, voice name, and full prompt.
- The API key is not included in the cache key.
- Output is written as mono, 16-bit, 24 kHz PCM WAV and later mastered to the episode format by FFmpeg.
- `generate_best()` can request up to four takes, score silence/clipping/level/duration, keep the best take, and write a JSON audit record.
- The UI’s connection test makes a real paid request and validates the returned Korean WAV.

Default performance directions exist for neutral, shock, anger, fear, crying, sadness, romance, comedy, suspicion, and determination. A shot can override them using `voice_direction`.

### Lip synchronization

Approved WAV audio is analyzed locally. Abrar Studio detects the actual speech bounds and distributes Korean text units across the spoken duration. Hangul medial vowels map to five principal visual shapes: closed, open, wide, round, and narrow. Audio energy closes the mouth during silence. Alignment data is cached beside the WAV as `.align.json`.

This is deterministic syllable/energy-based lip timing, not phoneme-perfect forced alignment.

## 7. Episode data model

An episode JSON contains metadata, scenes, and shots.

### Episode fields

- `project_id`
- `episode_id`
- `title`
- `resolution` (minimum 640×360; production default 1280×720)
- `fps` (`12`, `15`, `24`, `25`, or `30`; production default 24)
- `version`
- `language` (default `ko-KR`)
- `content_rating` (default `teen`)
- `scenes`

### Scene fields

- `id`
- `title`
- `location`
- `dramatic_goal`
- `shots` (at least one)

### Shot fields

Important supported fields include:

- identity/timing: `id`, `duration` (0.08–120 seconds);
- dialogue: `character_id`, `dialogue`, `emotion`, `emotion_level` (1–5), `voice_model`, `voice_direction`;
- picture: `background`, `camera`, `vfx`, `transition`, `position`, `acting`, `gaze`;
- audio: `music`, `music_volume`, `ambience`, `ambience_volume`, `sfx`;
- text: `subtitle`, `subtitle_style`;
- cast: `actors`;
- production notes: `notes`.

Legacy/simplified shots may specify a top-level `character_id` without `actors`; the model constructs one actor automatically. For robust multi-character work, use the explicit `actors` array.

### Actor fields

- `character_id`
- `expression`
- `pose`
- `position`: `far_left`, `left`, `center_left`, `center`, `center_right`, `right`, or `far_right`
- `scale` (0.35–2.0)
- `depth`
- `acting`
- `gaze`
- `gesture`
- `mirror`
- `speaking`
- `opacity` (0–1)
- all motion controls listed earlier

### SFX fields

An SFX entry can be a simple name or an object with:

- `cue`
- `at` (seconds from shot start)
- `volume` (0–3)
- `pan` (-1 left to +1 right)

### Minimal articulated example

```json
{
  "id": "WALK_IN",
  "duration": 2.8,
  "background": "school_hallway_evening",
  "camera": "tracking_push",
  "music": "school_tension",
  "ambience": "hallway_murmur",
  "emotion": "determined",
  "emotion_level": 3,
  "transition": "cut",
  "actors": [
    {
      "character_id": "seo_yeon",
      "expression": "neutral",
      "pose": "full_side",
      "position": "left",
      "motion": "walk_confident",
      "motion_speed": 1.0,
      "travel_x": 0.55,
      "facing": "right",
      "ground_y": 0.95,
      "speaking": false
    }
  ],
  "sfx": [],
  "vfx": []
}
```

## 8. Camera, effects, transitions, subtitles, and audio mixing

### Camera behavior

Camera names are composable strings. Implemented name fragments include:

- `push` / `push_in`: ease into a zoom;
- `pull` / `pull_out`: ease out from a zoom;
- `pan_left` and `pan_right`;
- `tracking`: follow average actor travel while maintaining safe frame edges;
- `handheld`: subtle deterministic sway;
- `shake`: diminishing impact shake.

Examples used by templates include `static`, `push_in`, `pull_out`, `pan_left`, `pan_right`, `shake_push_in`, `tracking`, `tracking_push`, and handheld variants.

### Visual effects

Implemented effects include ambient grain/speckle, speed lines, anger rays, rain, scanner sweep/glow, glitch bars, shock flash, emotional color grading, and strength-based vignette.

### Transitions

Validated transition values are:

- `cut`
- `fade`
- `dip_black`
- `flash`
- `whip`

### Subtitles

Dialogue subtitles support cinematic and minimal presentation. Cinematic subtitles include the character display name and character-specific name color. Text is wrapped and limited to a practical number of lines.

### Audio master

Each shot can mix voice, looping music, looping ambience, explicit SFX, automatic footsteps, and running cloth swishes. Voice receives filtering/compression. Music is automatically quieter under dialogue. All inputs are resampled to stereo 48 kHz, delayed/panned/leveled, faded where appropriate, mixed, limited, and encoded as 256 kbps AAC.

## 9. Bundled media inventory

### Backgrounds

`bedroom_blue_night`, `bus_stop_rain`, `cafe_warm_evening`, `classroom_after_school`, `convenience_store_night`, `rainy_alley_night`, `scanner_closeup`, `school_hallway_evening`, `school_rooftop_sunset`, and `store_entrance`.

### Music

`betrayal_pulse`, `chase_pulse`, `child_ghost_theme`, `confrontation_rise`, `crying_piano`, `min_jun_mystery`, `revenge_resolve`, `scanner_mystery_low`, `scanner_reveal`, `school_tension`, `tender_romance`, and `unresolved_truth`.

### Sound effects and ambience

`bass_hit`, `breath_shaky`, `classroom_roomtone`, `clock_tick`, `clothing_grab`, `cloth_swish`, `crowd_gasp`, `door_chime`, `electric_glitch`, `fluorescent_flicker`, `footsteps_hall`, `footstep_left`, `footstep_right`, `hallway_murmur`, `heartbeat`, `impact`, `low_impact`, `phone_buzz`, `rain_distant`, `rain_window`, `revenge_hit`, `romantic_chime`, `scanner_beep`, `scanner_power_down`, `school_bell`, `slap_impact`, and `store_hum`.

### Episode templates

- `articulated_motion_reference`
- `articulated_motion_showcase`
- `crying_breakdown`
- `revenge_reveal`
- `romance_confession`
- `school_betrayal`

## 10. Rendering pipeline

The full render flow is:

1. Load and validate episode JSON into dataclasses.
2. Resolve the default project and copy bundled assets into it.
3. Verify locked character manifests and requested rig/media assets.
4. Resolve cached voice WAV and build/load Korean alignment data.
5. Render each shot frame-by-frame with Pillow at the episode FPS.
6. Select expression cards or render an articulated rig for every actor.
7. Apply acting, gaze, gestures, travel, shadows, camera, VFX, transitions, and subtitles.
8. Pipe RGB frames to FFmpeg and encode a temporary H.264 visual clip.
9. Build the shot audio mix with FFmpeg and encode AAC.
10. Mux shot picture and audio.
11. Concatenate shots in timeline order.
12. Produce a constant-FPS H.264/AAC MP4 with `yuv420p` and `faststart`.

The renderer extends shot duration when a cached voice line is longer than the requested duration, adding a small tail so speech is not cut off.

## 11. Quality validation gates

`QualityValidator` produces weighted gate results and a score. Current gates are:

1. **Character identity lock:** manifests exist and every locked checksum matches.
2. **Korean voice identity/cache:** permanent lead voices/models/language remain correct; optional final validation can require cached WAVs and inspect their validity.
3. **Pose, articulated motion, and lip rig:** requested poses/expressions/gestures/parts/motions and five required mouth shapes exist.
4. **Acting and blocking:** speaking actors, appropriate intense expressions/cameras, non-overlapping positions, listener staging, and valid full-body locomotion.
5. **Sound effects and ambience:** important actions have cues; files exist; cues do not start after the shot ends.
6. **Scene music:** every scene has playable music.
7. **Pacing and transitions:** first shot is no longer than 3.5 seconds, no overly long static shots, and transitions are recognized.
8. **FFmpeg:** executable is available.
9. **Continuity and IDs:** shot IDs are unique and references resolve.

Final production should never bypass a failed gate merely to force an export.

## 12. Desktop UI

The Tkinter application window is defined in `abrar_studio/ui.py`. It provides these pages:

- **Dashboard:** project/episode overview and status
- **Characters:** locked character cards and guest character-pack import
- **Episode Script:** raw JSON editor, validation, loading, saving, and templates
- **Shot Builder:** visual editing for shot and motion fields, shot add/delete, still preview, and motion preview
- **Voice Studio:** character voice profile and preview generation
- **Production:** bulk voice generation and episode rendering
- **Quality Check:** validation gates and report display
- **Diagnostics:** device health, redacted local event history, full checks, and support-report export
- **Settings:** secure Gemini key controls, connection test, FFmpeg path, project folder, and updater settings

Long-running work runs in background tasks and reports progress to the UI queue.

## 13. Project storage and local data

On first launch, `StudioProject.open_or_create_default()` creates a default project named `TwoFourteen` in the user project directory. It creates:

- `project.json`
- `episodes/`
- `audio/`
- `renders/`
- `.temp/`
- `assets/`

Bundled characters, music, SFX, and backgrounds are copied into the project. The sample episode becomes `episodes/episode_001.json` when no episode exists.

Voice WAVs, alignment JSON, settings, and credentials are local data and should not be committed unless they are deliberate non-secret fixtures.

## 14. Security model

- On Windows, the Gemini API key is encrypted with Windows DPAPI and tied to the current Windows account.
- On non-Windows development systems, `GEMINI_API_KEY` may be read from the environment, but the application does not persist it.
- Character ZIP imports reject path traversal and require exactly one valid manifest.
- Guest characters require lowercase IDs, locked identity and voice, required mouth shapes, expressions, poses, and valid checksums.
- In-place updates require `AbrarStudio-Update.zip` and `AbrarStudio-Update.zip.sha256`; the digest and archive paths are verified before an external helper replaces program files and restarts the app.
- Publicly exposed API keys must be revoked and replaced.
- Code signing is recommended for public Windows distribution.

## 15. Installation and operation

### End-user Windows install

1. Extract the release ZIP completely.
2. Run `INSTALL_ABRAR_STUDIO.bat`.
3. Keep internet access available while dependencies and FFmpeg are installed.
4. Allow the installer verification to finish.
5. Launch Abrar Studio from the Desktop or Start Menu shortcut.
6. Open Settings, save a newly generated Gemini key, and run **Test Gemini**.
7. Open a bundled episode template or edit an episode JSON.
8. Run Preflight/Quality Check.
9. Generate and approve dialogue.
10. Run final validation and render.

### Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python app.py
```

FFmpeg must be available on `PATH`, selected in Settings, or installed as the bundled `tools/ffmpeg.exe`.

### Windows installer build

Use `scripts/build_windows.ps1` on Windows with Python 3.11+, PyInstaller, and Inno Setup 6. The Inno Setup definition is `installer/AbrarStudio.iss`.

## 16. Verification status and honest boundaries

The recovered release includes `VERIFICATION_REPORT.md`, which records three local verification cycles with 37 automated tests passed, one display-only UI test skipped in a headless Linux environment, and 13 release-render checks passed per cycle. A fresh checkout must rerun the tests rather than assuming those historical results remain valid.

The release verification checks include articulated rigs, distinct walk/run frames, facing, footsteps, quality gates, output existence/size, 1280×720 dimensions, H.264, AAC, constant 24 FPS, 48 kHz audio, duration, and secret scan. `verification_sample_720p_v3.mp4` and `AbrarStudio_v3_Articulated_Motion_Demo_720p.mp4` are generated release artifacts, not committed source files.

Known boundaries:

- Native Windows installer execution and visual desktop testing require Windows.
- A paid live Gemini request is not part of ordinary offline tests; use **Test Gemini** with the user’s replacement key.
- Motion is limited bone/cutout animation. There is no unrestricted frame-by-frame animation.
- The rig does not provide detailed finger simulation or physically simulated cloth/hair.
- Complex front-facing action, fighting, unusual poses, and new outfits require a new approved layered pack.
- Lip synchronization is deterministic Hangul/energy timing, not perfect linguistic forced alignment.
- AI TTS quality can vary; multi-take scoring reduces risk but does not guarantee perfect acting.

## 17. GitHub build and update flow

The repository workflow at `.github/workflows/windows-release.yml` is intended to run on pushes to `main` and manual dispatch. It should:

1. check out the source;
2. install Python 3.11 and build dependencies;
3. read `APP_VERSION`;
4. install Inno Setup;
5. build and verify three times;
6. upload the installer, in-place update package, checksums, and verification reports;
7. create or update a `v<version>` GitHub Release;
8. upload the installer pair plus `AbrarStudio-Update.zip` and its SHA-256 file.

The app’s updater checks the repository’s latest release, verifies the update ZIP and SHA-256 file, closes the running app, builds a staged copy beside the installation, preserves installer metadata, atomically swaps directories, verifies the installed executable hash, and reopens automatically. Failure rolls back to the previous installation, persists `updater.log` and `update-result.json`, and suppresses an immediate repeat prompt. Settings, encrypted credentials, projects, renders and cached voices are stored outside the installation directory and remain untouched.

## 18. Source module map

- `app.py` — application entry point
- `abrar_studio/ui.py` — complete Tkinter desktop UI and task orchestration
- `abrar_studio/models.py` — episode, scene, shot, actor, SFX, character, and voice schemas
- `abrar_studio/project.py` — project folders, bundled assets, episodes, and caches
- `abrar_studio/renderer.py` — Pillow/FFmpeg frame, camera, VFX, subtitle, and audio renderer
- `abrar_studio/puppet.py` — articulated rig loading, motion math, footstep timing, hierarchical sprite rendering
- `abrar_studio/acting.py` — non-articulated acting motion and listener reactions
- `abrar_studio/gemini_tts.py` — Gemini request construction, generation, take scoring, and audit
- `abrar_studio/alignment.py` — WAV energy analysis and deterministic syllable timing
- `abrar_studio/visemes.py` — Hangul vowel-to-mouth-shape mapping
- `abrar_studio/validator.py` — production quality gates
- `abrar_studio/locks.py` — SHA-256 identity verification
- `abrar_studio/character_packs.py` — safe validated guest-character import
- `abrar_studio/credentials.py` — Windows DPAPI credential storage
- `abrar_studio/settings.py` — local application settings
- `abrar_studio/updater.py` — GitHub release update/checksum flow
- `abrar_studio/diagnostics.py` — Python, FFmpeg, project, identity, rig, schema, and security diagnostics
- `abrar_studio/telemetry.py` — opt-in PostHog events, anonymous installation identity, privacy filtering, and capped local history
- `abrar_studio/monitoring.py` — consent-gated Sentry initialization, exception capture, release tags, and PII/source-context filtering
- `assets/` — all bundled characters and media
- `templates/episodes/` — ready-to-edit production examples
- `tests/` — unit and smoke tests
- `scripts/verify_release.py` — encoded release verification
- `scripts/build_windows.ps1` — Windows application/installer build
- `tools/generate_articulated_rigs.py` — articulated asset-generation utility

## 19. How to extend the project safely

### New episode

Start from a bundled template, use unique shot IDs, stage speaker and listener, keep the opening shot under 3.5 seconds, assign music per scene, add ambience per location, and add timed foreground effects for important actions. Validate before rendering.

### New motion

Add the canonical name to the rig manifest and motion normalization as needed, implement its state in `motion_state()`, consider footstep cadence, add tests for distinct frames/contact/facing, and add a template demonstration.

### New lead outfit or rig revision

Do not overwrite the current locked pack in place. Create a versioned reviewed pack, update rig/outfit/palette IDs, regenerate checksums, visually approve it, and add regression tests.

### New supporting character

Follow `docs/CHARACTER_PACK_FORMAT.md`. Include one manifest, required portrait/poses/expressions/mouths, a locked Korean voice profile, and checksums. Import through the UI or `import_character_pack()`.

### New background/music/SFX

Add the file to the correct `assets` folder, refer to it by base name in episode JSON, and ensure validation and packaging include it.

## 20. Instructions for the next AI assistant

When a new chat receives this repository:

1. Read this entire `gpt.md`.
2. Read `README.md`, `VERIFICATION_REPORT.md`, and the relevant source modules before editing.
3. Run `git status -sb` and preserve unrelated user changes.
4. Treat manifests and reference sheets as the authority for character identity.
5. Do not claim a feature works merely because it appears in this document; confirm the current code and tests.
6. Do not expose, request, commit, or log the Gemini API key.
7. Keep Seo-yeon/Min-jun appearance and voice identity locked.
8. Maintain the limited Korean webtoon puppet target unless the user explicitly changes the product direction.
9. Run relevant tests and, for renderer changes, a real render verification.
10. Update this file whenever architecture, schema, character canon, workflow, or product boundaries materially change.

This file explains the whole concept; the source code and manifests remain the final technical authority.
