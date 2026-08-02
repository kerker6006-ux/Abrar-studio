# Production guide

## Recommended shot length

Use 1.5–3.5 seconds for ordinary shots. Long dialogue should be split into speaker and listener reaction shots. Put the reveal, conflict or impossible scanner result inside the first eight seconds.

## Supported shot controls

```json
{
  "id": "S01_SH01",
  "duration": 2.8,
  "character_id": "seo_yeon",
  "expression": "suspicious",
  "dialogue": "새벽 두 시 십사 분. 또 시작이네.",
  "emotion": "suspicious",
  "emotion_level": 3,
  "camera": "push_in",
  "position": "right",
  "acting": "alert",
  "gaze": "camera",
  "vfx": ["clock_glow"],
  "sfx": ["clock_tick", "store_hum"],
  "music": "scanner_mystery_low",
  "background": "convenience_store_night",
  "voice_model": "auto"
}
```

Camera values may include `static`, `push_in`, `pull_out`, `pan_left`, `pan_right`, `shake`, and names containing `full`, `walk` or `run` to request full-body framing.

## Voice direction

The same locked voice is used across all situations. Change acting, not identity. Good direction describes internal conflict, pace, breath and where the line changes.

```text
She is angry but afraid the truth is real. Begin controlled and low. Pause before the last phrase, then let one small voice crack through. Keep every Korean word understandable.
```

## Character consistency

Do not replace files inside `assets/characters/seo_yeon` or `assets/characters/min_jun`. Modified files fail the identity gate. Add a new outfit as a separately reviewed versioned character package rather than overwriting the master.
