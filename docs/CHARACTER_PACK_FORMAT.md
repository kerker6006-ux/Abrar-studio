# Abrar Studio locked character-pack format

A guest/supporting character pack is a ZIP containing one `manifest.json` and every referenced image. Abrar Studio verifies the complete SHA-256 manifest before copying the pack into a project.

Required manifest fields:

- `character_id`: lowercase identifier such as `ji_woo`
- `display_name`, `rig_version`, `outfit_id`, `palette_id`
- `reference_sheet`, `portrait`, `full_front`
- one or more `expressions`
- one or more full-body `poses`
- optional `gestures`
- five mouth shapes: `closed`, `open`, `wide`, `round`, `narrow`
- one permanent `voice_profile` with `language: ko-KR` and `locked: true`
- `identity_locked: true`
- SHA-256 `asset_checksums` for every referenced image

## Reference-limited motion

Walking and running use complete character drawings, never independently
rotated body parts. Set `visual_tier` to `reference_limited_v1` only after the
artwork has been reviewed, then add a locked loop:

```json
"animations": {
  "walk": {
    "frames": [
      "animations/walk/frame_01.png",
      "animations/walk/frame_02.png",
      "animations/walk/frame_03.png",
      "animations/walk/frame_04.png",
      "animations/walk/frame_05.png",
      "animations/walk/frame_06.png"
    ],
    "fps": 6,
    "loop": true
  }
}
```

Every loop frame must be a transparent PNG on one consistent canvas and at
least 384x720. Include every frame in `asset_checksums`. An optional normalized
`mouth_anchor: [x, y]` keeps simple mouth movement active in a full-body shot.

The two protagonists have additional fixed voice rules. Imported guest characters may use another Gemini voice, but that choice becomes immutable after import.

Abrar Studio rejects unsafe ZIP paths, duplicate manifests, missing files, changed checksums, unlocked identities and incomplete voice profiles.
