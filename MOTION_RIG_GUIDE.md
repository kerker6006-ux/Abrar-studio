# Abrar Studio articulated-motion guide

## Actor fields

| Field | Meaning | Typical value |
|---|---|---|
| `pose` | Use `full_side` for articulated locomotion | `full_side` |
| `motion` | Reusable motion clip | `walk_normal` |
| `motion_speed` | Cycle speed, 0.2–3.0 | `1.0` |
| `travel_x` | Horizontal travel in screen widths | `0.55` |
| `facing` | `left`, `right`, or `auto` | `right` |
| `ground_y` | Normalized ground line | `0.95` |
| `cycle_offset` | Phase offset for crowds/pairs | `0.18` |
| `motion_intensity` | Movement exaggeration, 0.25–1.7 | `1.0` |

## Motion selection

- Calm entrance: `walk_slow`
- Ordinary hallway movement: `walk_normal`
- Heroic entrance: `walk_confident`
- Defeated exit: `walk_sad`
- Chase: `run_normal`
- Fear/chase comedy: `run_panicked`
- Begin from rest: `start_walk`
- Abrupt reaction: `stop_sudden`
- Defensive movement: `step_back`
- Impact reaction: `shock_recoil`

## Camera pairing

- `tracking`: follows locomotion without exposing frame edges
- `tracking_push`: follows and slowly pushes in
- `pan_left` / `pan_right`: small environmental pan
- `shake_push_in`: impact, shock or confrontation

## Automatic sound

When no explicit footstep cue is supplied, Abrar Studio inserts alternating `footstep_left` and `footstep_right` cues from the gait cadence. Running also inserts restrained `cloth_swish` layers. Add an explicit cue containing `foot` or `step` to replace automatic footsteps.

## Two-character chase example

```json
{
  "id": "CHASE_04",
  "duration": 2.6,
  "camera": "tracking",
  "background": "school_hallway_evening",
  "music": "chase_pulse",
  "ambience": "hallway_murmur",
  "emotion": "fear",
  "emotion_level": 4,
  "actors": [
    {
      "character_id": "seo_yeon",
      "pose": "full_side",
      "position": "left",
      "motion": "run_normal",
      "motion_speed": 1.05,
      "travel_x": 0.62,
      "facing": "right",
      "cycle_offset": 0.0
    },
    {
      "character_id": "min_jun",
      "pose": "full_side",
      "position": "far_left",
      "motion": "run_normal",
      "motion_speed": 1.0,
      "travel_x": 0.62,
      "facing": "right",
      "cycle_offset": 0.22,
      "depth": -1
    }
  ],
  "vfx": ["speed_lines"]
}
```
