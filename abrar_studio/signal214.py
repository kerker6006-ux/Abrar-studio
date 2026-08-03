from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path


SAMPLE_KOREAN_SCRIPT = """새벽 2시 14분, 폐쇄된 한빛중학교의 3번 카메라가 혼자 켜졌다.
경비실에는 아무도 없었지만, 복도 끝에서 젖은 운동화 소리가 들렸다.
화면을 확대하자 십 년 전 실종된 학생의 이름표가 바닥에 놓여 있었다.
그 순간 학교 대표번호로 음성 메시지 하나가 도착했다.
메시지 속 아이는 아주 작게, 절대 뒤를 보지 말라고 말했다.
그런데 마지막 프레임에는 카메라를 바라보는 경비원의 뒷모습이 찍혀 있었다.
문제는 그 경비원이 그날 밤 출근하지 않았다는 것이다.
당신이라면 3번 카메라를 다시 재생하겠습니까?"""


class SignalScriptError(ValueError):
    pass


@dataclass(slots=True)
class SignalBeat:
    index: int
    kind: str
    narration: str
    caption: str
    duration: float
    background: str
    emphasis: str = "normal"


@dataclass(slots=True)
class SignalEpisode:
    episode_id: str
    title: str
    script: str
    hook: str
    beats: list[SignalBeat]
    duration: float
    resolution: tuple[int, int] = (1080, 1920)
    fps: int = 24
    render_fps: int = 12
    series: str = "2:14 기록보관소"
    language: str = "ko-KR"
    metadata: dict[str, str] = field(default_factory=dict)

    def save(self, path: Path) -> Path:
        payload = asdict(self)
        payload["resolution"] = list(self.resolution)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "SignalEpisode":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["resolution"] = tuple(data.get("resolution", [1080, 1920]))
        data["beats"] = [SignalBeat(**beat) for beat in data["beats"]]
        return cls(**data)


@dataclass(slots=True)
class SignalQualityReport:
    technical: int
    story: int
    visual: int
    passed: bool
    problems: list[str]
    notes: list[str]

    @property
    def overall(self) -> int:
        return round(self.technical * 0.25 + self.story * 0.45 + self.visual * 0.30)


class SignalScriptCompiler:
    """Turn a Korean narration script into varied, timed evidence-horror beats.

    This is intentionally deterministic and CPU-only. It never invents factual
    claims or pretends a fictional incident is real.
    """

    _bad_encoding = ("Ã", "Â", "â€", "ï¿½", "�")
    _backgrounds = {
        "cctv": "school_corridor_night.png",
        "corridor": "school_corridor_night.png",
        "call": "security_room_night.png",
        "waveform": "security_room_night.png",
        "file": "security_room_night.png",
        "monitor": "security_room_night.png",
        "elevator": "apartment_elevator_night.png",
        "map": "apartment_elevator_night.png",
    }
    _sequence = ("monitor", "cctv", "file", "waveform", "elevator", "call", "corridor", "map")

    def compile(self, script: str, title: str = "") -> SignalEpisode:
        normalized = self._normalize(script)
        segments = self._segments(normalized)
        if len(normalized.replace(" ", "")) < 90:
            raise SignalScriptError("한국어 대본이 너무 짧습니다. 최소 90자 이상의 완성된 이야기를 입력하세요.")
        if len(segments) < 5:
            raise SignalScriptError("이야기에는 최소 5개의 사건 또는 문장이 필요합니다.")

        episode_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
        episode_id = f"S214-{episode_hash.upper()}"
        chosen_title = title.strip() or self._title_from(segments[0])
        total_duration = min(58.0, max(32.0, len(normalized) / 6.0 + 5.0))
        weights = [max(8, len(part.replace(" ", ""))) for part in segments]
        total_weight = sum(weights)
        durations = [max(2.7, total_duration * weight / total_weight) for weight in weights]
        scale = total_duration / sum(durations)
        durations = [round(value * scale, 3) for value in durations]

        beats: list[SignalBeat] = []
        previous_kind = ""
        for index, (segment, duration) in enumerate(zip(segments, durations)):
            kind = self._kind_for(segment, index, len(segments), previous_kind)
            previous_kind = kind
            emphasis = "hook" if index == 0 else "reveal" if index >= len(segments) - 2 else "normal"
            beats.append(SignalBeat(
                index=index,
                kind=kind,
                narration=segment,
                caption=segment,
                duration=duration,
                background=self._backgrounds[kind],
                emphasis=emphasis,
            ))

        return SignalEpisode(
            episode_id=episode_id,
            title=chosen_title,
            script=normalized,
            hook=segments[0],
            beats=beats,
            duration=round(sum(beat.duration for beat in beats), 3),
            metadata={
                "fiction": "true",
                "format": "vertical-evidence-horror",
                "youtube_disclosure": "fictional dramatization",
            },
        )

    def quality(self, episode: SignalEpisode, history_path: Path | None = None) -> SignalQualityReport:
        problems: list[str] = []
        notes: list[str] = []
        technical = 100
        story = 100
        visual = 100

        korean_chars = len(re.findall(r"[가-힣]", episode.script))
        visible_chars = max(1, len(re.findall(r"\S", episode.script)))
        if korean_chars / visible_chars < 0.45:
            technical -= 35
            problems.append("대본이 자연스러운 한국어 중심으로 작성되지 않았습니다.")
        if not 30 <= episode.duration <= 60:
            story -= 25
            problems.append("쇼츠 길이는 30~60초여야 합니다.")
        if not 5 <= len(episode.beats) <= 12:
            story -= 20
            problems.append("장면 수가 너무 적거나 많습니다.")
        if len(episode.hook.replace(" ", "")) > 54:
            story -= 12
            notes.append("첫 문장이 깁니다. 첫 화면에서는 두 줄로 압축됩니다.")
        if not any(token in episode.hook for token in ("2시 14분", "2:14", "새벽", "카메라", "전화", "사라")):
            story -= 15
            problems.append("첫 문장에 즉시 이해되는 미스터리 훅이 없습니다.")
        kinds = {beat.kind for beat in episode.beats}
        if len(kinds) < 4:
            visual -= 25
            problems.append("시각 증거 형식이 충분히 다양하지 않습니다.")
        if any(beat.duration > 8.5 for beat in episode.beats):
            visual -= 15
            problems.append("한 장면이 너무 오래 유지됩니다.")
        if not any(word in episode.script for word in ("그런데", "하지만", "문제는", "순간", "마지막")):
            story -= 12
            notes.append("명확한 반전 연결어가 없어 결말의 충격이 약할 수 있습니다.")
        if not episode.script.rstrip().endswith(("?", "까요?", "습니까?", "나요?")):
            story -= 8
            notes.append("댓글을 유도하는 마지막 질문을 추가하면 좋습니다.")

        if history_path and history_path.exists():
            try:
                entries = json.loads(history_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                entries = []
            ratios = [SequenceMatcher(None, episode.script, str(item.get("script", ""))).ratio() for item in entries[-50:]]
            if ratios and max(ratios) >= 0.72:
                story -= 35
                problems.append("최근 영상과 대본이 너무 비슷합니다. 반복 콘텐츠로 보일 수 있습니다.")

        passed = technical >= 85 and story >= 72 and visual >= 78 and not problems
        return SignalQualityReport(
            technical=max(0, technical), story=max(0, story), visual=max(0, visual),
            passed=passed, problems=problems, notes=notes,
        )

    @staticmethod
    def remember(episode: SignalEpisode, history_path: Path) -> None:
        try:
            entries = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
        except (OSError, json.JSONDecodeError):
            entries = []
        entries.append({"episode_id": episode.episode_id, "title": episode.title, "script": episode.script})
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(entries[-100:], ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize(self, script: str) -> str:
        text = unicodedata.normalize("NFC", script or "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            raise SignalScriptError("한국어 대본을 입력하세요.")
        if any(marker in text for marker in self._bad_encoding):
            raise SignalScriptError("대본의 글자가 깨졌습니다. 원본 한국어를 다시 붙여 넣으세요.")
        return text

    @staticmethod
    def _segments(text: str) -> list[str]:
        raw = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if part.strip()]
        expanded: list[str] = []
        for part in raw:
            if len(part) > 72:
                clauses = [c.strip() for c in re.split(r"(?<=[,，])\s*|(?<=지만)\s*|(?<=는데)\s*", part) if c.strip()]
                expanded.extend(clauses if len(clauses) > 1 else [part])
            else:
                expanded.append(part)
        while len(expanded) > 12:
            smallest = min(range(len(expanded) - 1), key=lambda i: len(expanded[i]) + len(expanded[i + 1]))
            expanded[smallest:smallest + 2] = [f"{expanded[smallest]} {expanded[smallest + 1]}"]
        return expanded

    def _kind_for(self, text: str, index: int, total: int, previous: str) -> str:
        mapping = (
            (("전화", "음성", "메시지", "통화"), "call"),
            (("엘리베이터", "층", "계단"), "elevator"),
            (("지도", "위치", "도로", "주소", "GPS"), "map"),
            (("문서", "기록", "신고", "이름", "명단"), "file"),
            (("소리", "녹음", "목소리", "들렸다"), "waveform"),
            (("복도", "학교", "교실", "문"), "corridor"),
            (("화면", "카메라", "CCTV", "프레임", "찍"), "cctv"),
        )
        for words, kind in mapping:
            if any(word in text for word in words) and kind != previous:
                return kind
        kind = self._sequence[index % len(self._sequence)]
        if index >= total - 2:
            kind = "cctv" if previous != "cctv" else "monitor"
        if kind == previous:
            kind = self._sequence[(index + 2) % len(self._sequence)]
        return kind

    @staticmethod
    def _title_from(hook: str) -> str:
        core = re.sub(r"^[새벽\s]*2시\s*14분[,，:]?\s*", "", hook).strip(" .!?。！？")
        if len(core) > 28:
            core = core[:27].rstrip() + "…"
        return core or "3번 카메라가 켜진 밤"
