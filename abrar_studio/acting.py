from __future__ import annotations

import math
from dataclasses import dataclass

from .models import ActorCue, Shot


@dataclass(frozen=True, slots=True)
class ActingPose:
    dx: float = 0.0
    dy: float = 0.0
    rotation: float = 0.0
    scale: float = 1.0


def _pose(emotion: str, acting: str, level_value: int, t: float, progress: float, speaking: bool, phase: float) -> ActingPose:
    emotion = emotion.lower().strip()
    acting = acting.lower().strip()
    level = max(0.2, min(1.0, level_value / 5.0))
    ease = progress * progress * (3.0 - 2.0 * progress)

    # Breathing, balance changes and head sway. Listener motion is quieter.
    strength = 1.0 if speaking else 0.58
    dx = math.sin(t * 1.1 + 0.5 + phase) * 0.9 * level * strength
    dy = math.sin(t * 2.0 + phase) * (1.2 + 1.8 * level) * strength
    rotation = math.sin(t * 1.25 + 0.8 + phase) * (0.38 + 0.62 * level) * strength
    scale = 1.0 + math.sin(t * 2.2 + phase) * (0.003 + 0.0045 * level) * strength

    if acting in {"walk", "walking"}:
        step = math.sin(t * 7.2 + phase)
        dy += abs(step) * 5.0
        rotation += step * 1.2
        dx += math.sin(t * 3.6 + phase) * 3.0
    elif acting in {"run", "running"}:
        step = math.sin(t * 11.5 + phase)
        dy += abs(step) * 9.0
        rotation += step * 2.1
        dx += math.sin(t * 5.75 + phase) * 5.0
        scale += 0.008
    elif acting in {"recoil", "shock_back"} or emotion in {"shock", "shocked"}:
        if progress < 0.22:
            kick = math.sin(progress / 0.22 * math.pi)
            dx -= 11.0 * kick
            rotation += 3.2 * kick
            scale += 0.025 * kick
    elif acting in {"lean_in", "confront"} or emotion == "anger":
        dx += 7.0 * ease
        rotation -= 1.8 * ease
        scale += 0.012 * ease
    elif acting in {"collapse", "breakdown"} or emotion in {"crying", "breakdown"}:
        dy += 13.0 * ease
        rotation += 2.2 * ease
        tremor = math.sin(t * 19.0 + phase) * 1.35 * level
        dx += tremor
        rotation += tremor * 0.35
    elif acting in {"shy", "look_away"} or emotion in {"embarrassed", "romantic", "love"}:
        dx -= 2.5 * ease
        rotation += 1.5 * ease
        dy += 2.0 * ease
    elif emotion == "fear":
        tremor = math.sin(t * 17.0 + phase) * 1.4 * level
        dx += tremor
        rotation += tremor * 0.4
        scale -= 0.006 * ease
    elif acting in {"nod", "agree"}:
        dy += math.sin(min(1.0, progress * 2.0) * math.pi * 2.0) * 4.0
    elif acting in {"head_shake", "deny"}:
        rotation += math.sin(min(1.0, progress * 2.0) * math.pi * 3.0) * 2.6
    elif acting in {"listen", "listener"}:
        # A delayed reaction keeps two-person dialogue alive without stealing focus.
        delayed = max(0.0, min(1.0, (progress - 0.18) / 0.55))
        dy += math.sin(delayed * math.pi) * 2.4
        rotation += math.sin(delayed * math.pi) * 0.9

    return ActingPose(dx=dx, dy=dy, rotation=rotation, scale=scale)


def acting_pose(shot: Shot, t: float, progress: float) -> ActingPose:
    return _pose(shot.emotion, shot.acting, shot.emotion_level, t, progress, True, 0.0)


def actor_pose(shot: Shot, actor: ActorCue, t: float, progress: float, index: int = 0) -> ActingPose:
    acting = actor.acting or (shot.acting if actor.speaking else "listen")
    return _pose(shot.emotion, acting, shot.emotion_level, t, progress, actor.speaking, index * 1.17)
