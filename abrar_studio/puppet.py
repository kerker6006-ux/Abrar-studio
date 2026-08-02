from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps


ARTICULATED_MOTIONS = {
    "idle_breathe", "walk_slow", "walk_normal", "walk_confident", "walk_sad",
    "run_normal", "run_panicked", "start_walk", "stop_sudden", "step_back", "shock_recoil",
    "walking", "walk", "running", "run",
}


@dataclass(frozen=True, slots=True)
class PartSpec:
    name: str
    file: str
    pivot: tuple[float, float]
    parent: str | None
    rest_offset: tuple[float, float]
    z: int
    brightness: float = 1.0
    lag: float = 0.0


@dataclass(slots=True)
class RigDefinition:
    path: Path
    character_id: str
    source_size: tuple[int, int]
    root: tuple[float, float]
    ground_y: float
    joints: dict[str, tuple[float, float]]
    parts: dict[str, PartSpec]
    motions: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "RigDefinition":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("format") != "abrar_articulated_rig_v1":
            raise ValueError(f"Unsupported articulated rig: {path}")
        parts: dict[str, PartSpec] = {}
        for name, item in raw.get("parts", {}).items():
            parts[name] = PartSpec(
                name=name,
                file=str(item["file"]),
                pivot=(float(item["pivot"][0]), float(item["pivot"][1])),
                parent=item.get("parent"),
                rest_offset=(float(item.get("rest_offset", [0, 0])[0]), float(item.get("rest_offset", [0, 0])[1])),
                z=int(item.get("z", 0)),
                brightness=float(item.get("brightness", 1.0)),
                lag=float(item.get("lag", 0.0)),
            )
        return cls(
            path=path,
            character_id=str(raw["character_id"]),
            source_size=(int(raw["source_size"][0]), int(raw["source_size"][1])),
            root=(float(raw["root"][0]), float(raw["root"][1])),
            ground_y=float(raw["ground_y"]),
            joints={k: (float(v[0]), float(v[1])) for k, v in raw.get("joints", {}).items()},
            parts=parts,
            motions=tuple(str(x) for x in raw.get("motions", [])),
        )


@dataclass(frozen=True, slots=True)
class MotionState:
    angles: dict[str, float] = field(default_factory=dict)
    root_dx: float = 0.0
    root_dy: float = 0.0
    body_scale_x: float = 1.0
    body_scale_y: float = 1.0
    phase: float = 0.0


def normalize_motion(value: str | None, acting: str | None = None) -> str:
    raw = (value or "auto").strip().lower()
    if raw in {"", "auto", "none"}:
        raw = (acting or "idle_breathe").strip().lower()
    aliases = {
        "idle": "idle_breathe", "listen": "idle_breathe", "listener": "idle_breathe",
        "walk": "walk_normal", "walking": "walk_normal", "run": "run_normal", "running": "run_normal",
        "confident_walk": "walk_confident", "sad_walk": "walk_sad", "panic_run": "run_panicked",
        "recoil": "shock_recoil", "shock_back": "shock_recoil",
    }
    return aliases.get(raw, raw)


def uses_articulated_motion(motion: str | None, acting: str | None = None) -> bool:
    return normalize_motion(motion, acting) in ARTICULATED_MOTIONS


def _smoothstep(value: float) -> float:
    v = max(0.0, min(1.0, value))
    return v * v * (3.0 - 2.0 * v)


def motion_state(name: str, t: float, progress: float, speed: float = 1.0, cycle_offset: float = 0.0, intensity: float = 1.0) -> MotionState:
    name = normalize_motion(name)
    speed = max(0.2, min(3.0, speed))
    intensity = max(0.25, min(1.7, intensity))
    angles: dict[str, float] = {}
    root_dx = 0.0
    root_dy = 0.0
    sx = sy = 1.0

    if name == "idle_breathe" or name not in ARTICULATED_MOTIONS:
        phase = t * 2.0 * math.pi / 3.2 + cycle_offset * 2.0 * math.pi
        breath = math.sin(phase)
        angles["torso"] = breath * 0.35 * intensity
        angles["head"] = -breath * 0.25 * intensity
        angles["arm_front_upper"] = breath * 0.35
        angles["arm_back_upper"] = -breath * 0.25
        root_dy = -abs(breath) * 0.9
        sy = 1.0 + breath * 0.0025
        return MotionState(angles, root_dx, root_dy, sx, sy, phase)

    settings = {
        "walk_slow": (0.78, 16.0, 25.0, 7.0, 3.0, 1.0),
        "walk_normal": (1.18, 23.0, 36.0, 12.0, 4.3, 1.5),
        "walk_confident": (1.08, 25.0, 33.0, 15.0, 3.5, 3.0),
        "walk_sad": (0.72, 14.0, 27.0, 7.0, 2.3, -2.5),
        "run_normal": (1.85, 36.0, 58.0, 23.0, 7.0, 7.0),
        "run_panicked": (2.18, 42.0, 67.0, 28.0, 9.0, 9.5),
        "start_walk": (1.05, 22.0, 34.0, 11.0, 4.0, 1.5),
        "stop_sudden": (1.0, 13.0, 20.0, 6.0, 2.0, -7.0),
        "step_back": (0.86, 18.0, 31.0, 8.0, 3.0, -3.0),
        "shock_recoil": (0.9, 8.0, 12.0, 4.0, 1.0, -10.0),
    }
    cadence, thigh_amp, knee_amp, arm_amp, bob, lean = settings.get(name, settings["walk_normal"])
    blend = 1.0
    if name == "start_walk":
        blend = _smoothstep(progress / 0.35)
    elif name == "stop_sudden":
        blend = 1.0 - _smoothstep((progress - 0.42) / 0.36)
    phase = t * cadence * speed * 2.0 * math.pi + cycle_offset * 2.0 * math.pi
    s = math.sin(phase)
    c = math.cos(phase)
    gait = intensity * blend

    angles["torso"] = lean * gait + s * (0.8 if "run" in name else 0.45) * gait
    angles["head"] = -angles["torso"] * 0.42 + math.sin(phase * 0.5) * 0.35
    angles["hair_back"] = -angles["head"] * 0.18 - s * (2.2 if "run" in name else 1.0) * gait

    angles["leg_front_upper"] = -s * thigh_amp * gait
    angles["leg_back_upper"] = s * thigh_amp * gait
    angles["leg_front_lower"] = max(0.0, s) * knee_amp * gait + max(0.0, -c) * knee_amp * 0.18 * gait
    angles["leg_back_lower"] = max(0.0, -s) * knee_amp * gait + max(0.0, c) * knee_amp * 0.18 * gait
    angles["foot_front"] = -angles["leg_front_upper"] * 0.48 - angles["leg_front_lower"] * 0.62 + c * 5.0 * gait
    angles["foot_back"] = -angles["leg_back_upper"] * 0.48 - angles["leg_back_lower"] * 0.62 - c * 5.0 * gait

    angles["arm_front_upper"] = s * arm_amp * gait
    angles["arm_back_upper"] = -s * arm_amp * gait
    elbow = 5.0 if "walk" in name else 13.0
    angles["arm_front_lower"] = elbow + max(0.0, -s) * (9.0 if "run" in name else 4.0) * gait
    angles["arm_back_lower"] = elbow + max(0.0, s) * (9.0 if "run" in name else 4.0) * gait

    root_dy = -abs(c) * bob * gait
    if name == "walk_confident":
        root_dx += math.sin(phase * 0.5) * 0.7
    elif name == "walk_sad":
        angles["head"] += 7.0 * _smoothstep(progress)
        angles["torso"] -= 2.0
        sy = 0.995
    elif name == "run_panicked":
        root_dx += math.sin(t * 17.0) * 1.4
        angles["head"] += math.sin(t * 13.0) * 1.8
    elif name == "stop_sudden":
        stop = _smoothstep((progress - 0.50) / 0.22)
        angles["torso"] -= 10.0 * stop
        angles["head"] += 5.0 * stop
        root_dx -= 7.0 * math.sin(stop * math.pi)
    elif name == "step_back":
        root_dx -= _smoothstep(progress) * 8.0
    elif name == "shock_recoil":
        kick = math.sin(min(1.0, progress / 0.26) * math.pi) if progress < 0.26 else 0.0
        angles["torso"] -= 12.0 * kick
        angles["head"] += 7.0 * kick
        root_dx -= 13.0 * kick
        sx = 1.0 + 0.015 * kick
        sy = 1.0 - 0.012 * kick

    return MotionState(angles, root_dx, root_dy, sx, sy, phase)


def _steady_phase_bin(name: str, t: float, speed: float, cycle_offset: float) -> tuple[int, int] | None:
    cadence = {
        "walk_slow": 0.78, "walk_normal": 1.18, "walk_confident": 1.08, "walk_sad": 0.72,
        "run_normal": 1.85, "run_panicked": 2.18,
    }.get(name)
    if cadence is None:
        return None
    bins = 10 if name == "walk_slow" else (16 if name.startswith("run") else 12)
    phase = (t * cadence * max(0.2, speed) + cycle_offset) % 1.0
    return int(round(phase * bins)) % bins, bins


def footstep_times(motion: str, duration: float, speed: float = 1.0, cycle_offset: float = 0.0) -> list[float]:
    name = normalize_motion(motion)
    cadence = {
        "walk_slow": 0.78, "walk_normal": 1.18, "walk_confident": 1.08, "walk_sad": 0.72,
        "run_normal": 1.85, "run_panicked": 2.18, "start_walk": 1.05,
    }.get(name)
    if cadence is None or duration <= 0:
        return []
    # Two contacts per gait cycle. Offset keeps actor pairs from sounding mechanically identical.
    interval = 1.0 / max(0.1, cadence * max(0.2, speed) * 2.0)
    first = ((0.25 - cycle_offset) % 0.5) / max(0.1, cadence * max(0.2, speed))
    values: list[float] = []
    t = first
    while t < duration - 0.05:
        values.append(round(max(0.0, t), 3))
        t += interval
    return values


def _rotate_vector(vector: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    x, y = vector
    return x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)


def _transform_part(image: Image.Image, pivot: tuple[float, float], world_pivot: tuple[float, float], angle_deg: float, scale: float, brightness: float) -> tuple[Image.Image, tuple[int, int]]:
    width = max(1, int(round(image.width * scale)))
    height = max(1, int(round(image.height * scale)))
    sprite = image.resize((width, height), Image.Resampling.LANCZOS)
    if brightness != 1.0:
        rgb = ImageEnhance.Brightness(sprite.convert("RGB")).enhance(brightness).convert("RGBA")
        rgb.putalpha(sprite.getchannel("A"))
        sprite = rgb
    px, py = pivot[0] * scale, pivot[1] * scale
    radius = int(math.ceil(max(px, py, width - px, height - py) * 1.45 + 8))
    pad = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
    pad.alpha_composite(sprite, (int(round(radius - px)), int(round(radius - py))))
    # Our forward-kinematics angles are clockwise in screen coordinates; Pillow positive angles are CCW.
    rotated = pad.rotate(-angle_deg, resample=Image.Resampling.BICUBIC, expand=False)
    return rotated, (int(round(world_pivot[0] - radius)), int(round(world_pivot[1] - radius)))


class ArticulatedPuppetRenderer:
    def __init__(self) -> None:
        self._rigs: dict[Path, RigDefinition] = {}
        self._images: dict[Path, Image.Image] = {}
        self._rotated: dict[tuple[Path, int, int], tuple[Image.Image, int]] = {}
        self._cycles: dict[tuple[Path, str, int, int, int, str], Image.Image] = {}

    def rig(self, path: Path) -> RigDefinition:
        path = path.resolve()
        if path not in self._rigs:
            self._rigs[path] = RigDefinition.load(path)
        return self._rigs[path]

    def _image(self, path: Path) -> Image.Image:
        path = path.resolve()
        if path not in self._images:
            self._images[path] = Image.open(path).convert("RGBA")
        return self._images[path]

    def _part_sprite(self, path: Path, image: Image.Image, pivot: tuple[float, float], angle: float, brightness: float) -> tuple[Image.Image, int]:
        quantized_angle = int(round(angle))
        brightness_key = int(round(brightness * 100))
        key = (path.resolve(), quantized_angle, brightness_key)
        cached = self._rotated.get(key)
        if cached is not None:
            return cached[0], cached[1]
        width, height = image.size
        px, py = pivot
        radius = int(math.ceil(max(px, py, width - px, height - py) * 1.45 + 8))
        pad = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
        sprite = image
        if brightness != 1.0:
            rgb = ImageEnhance.Brightness(sprite.convert("RGB")).enhance(brightness).convert("RGBA")
            rgb.putalpha(sprite.getchannel("A")); sprite = rgb
        pad.alpha_composite(sprite, (int(round(radius - px)), int(round(radius - py))))
        rotated = pad.rotate(-quantized_angle, resample=Image.Resampling.BICUBIC, expand=False)
        self._rotated[key] = (rotated, radius)
        if len(self._rotated) > 1800:
            self._rotated.clear()
        return rotated, radius

    def render(self, rig_path: Path, motion: str, t: float, progress: float, speed: float = 1.0,
               cycle_offset: float = 0.0, intensity: float = 1.0, facing: str = "right") -> Image.Image:
        rig_path = rig_path.resolve()
        rig = self.rig(rig_path)
        motion = normalize_motion(motion)
        steady = _steady_phase_bin(motion, t, speed, cycle_offset)
        cycle_key = None
        if steady is not None:
            phase_bin, bins = steady
            cycle_key = (rig_path, motion, phase_bin, bins, int(round(intensity * 100)), facing.lower())
            cached_cycle = self._cycles.get(cycle_key)
            if cached_cycle is not None:
                return cached_cycle.copy()
        state = motion_state(motion, t, progress, speed, cycle_offset, intensity)
        canvas_w = max(330, rig.source_size[0] + 160)
        canvas_h = max(710, rig.source_size[1] + 45)
        ground = canvas_h - 18
        root_x = canvas_w * 0.53 + state.root_dx

        angles = dict(state.angles)
        # Calculate cumulative part transforms once. Parent rotation affects child anchor placement.
        pivots: dict[str, tuple[float, float]] = {}
        cumulative: dict[str, float] = {}

        def calculate(name: str) -> tuple[tuple[float, float], float]:
            if name in pivots:
                return pivots[name], cumulative[name]
            part = rig.parts[name]
            local = angles.get(name, 0.0)
            if part.parent is None:
                pivots[name] = (root_x, 0.0)
                cumulative[name] = local
            else:
                parent_pivot, parent_angle = calculate(part.parent)
                ox, oy = _rotate_vector(part.rest_offset, parent_angle)
                pivots[name] = (parent_pivot[0] + ox, parent_pivot[1] + oy)
                cumulative[name] = parent_angle + local
            return pivots[name], cumulative[name]

        # Ground correction based on both articulated toe endpoints.
        provisional_root_y = 0.0
        pivots["torso"] = (root_x, provisional_root_y)
        cumulative["torso"] = angles.get("torso", 0.0)
        toe = rig.joints.get("toe", (rig.root[0] - 50.0, rig.ground_y - 8.0))
        ankle = rig.joints.get("ankle", (rig.root[0], rig.ground_y - 40.0))
        toe_offset = (toe[0] - ankle[0], toe[1] - ankle[1])
        endpoints: list[float] = []
        for suffix in ("front", "back"):
            foot_name = f"foot_{suffix}"
            if foot_name not in rig.parts:
                continue
            foot_pivot, foot_angle = calculate(foot_name)
            _, toe_y = _rotate_vector(toe_offset, foot_angle)
            endpoints.append(foot_pivot[1] + toe_y)
        correction = ground - (max(endpoints) if endpoints else rig.ground_y - rig.root[1]) + state.root_dy
        # Resolve every part before translating the complete skeleton to the ground line.
        for name in rig.parts:
            calculate(name)
        for name in list(pivots):
            pivots[name] = (pivots[name][0], pivots[name][1] + correction)

        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        for part in sorted(rig.parts.values(), key=lambda item: item.z):
            pivot_world, angle = pivots[part.name], cumulative[part.name]
            if part.lag:
                angle += angles.get(part.name, 0.0) * part.lag
            image_path = rig.path.parent.parent / part.file
            sprite, radius = self._part_sprite(image_path, self._image(image_path), part.pivot, angle, part.brightness)
            position = (int(round(pivot_world[0] - radius)), int(round(pivot_world[1] - radius)))
            canvas.alpha_composite(sprite, position)

        if state.body_scale_x != 1.0 or state.body_scale_y != 1.0:
            new_size = (max(1, int(canvas.width * state.body_scale_x)), max(1, int(canvas.height * state.body_scale_y)))
            canvas = canvas.resize(new_size, Image.Resampling.LANCZOS)
        bbox = canvas.getbbox()
        if bbox:
            left = max(0, bbox[0] - 14); top = max(0, bbox[1] - 12)
            right = min(canvas.width, bbox[2] + 14); bottom = min(canvas.height, max(bbox[3] + 10, ground + 4))
            canvas = canvas.crop((left, top, right, bottom))
        if facing.lower() == "left":
            canvas = ImageOps.mirror(canvas)
        if cycle_key is not None:
            self._cycles[cycle_key] = canvas.copy()
            if len(self._cycles) > 320:
                self._cycles.clear()
        return canvas
