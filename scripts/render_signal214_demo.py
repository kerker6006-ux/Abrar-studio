from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from abrar_studio.credentials import CredentialStore
from abrar_studio.project import StudioProject
from abrar_studio.settings import SettingsStore
from abrar_studio.signal214 import SAMPLE_KOREAN_SCRIPT, SignalScriptCompiler
from abrar_studio.signal214_renderer import Signal214Renderer, generate_signal_narration


def main() -> int:
    project = StudioProject.open_or_create_default()
    compiler = SignalScriptCompiler()
    episode = compiler.compile(SAMPLE_KOREAN_SCRIPT, "새벽 2시 14분, 3번 카메라")
    report = compiler.quality(episode, project.root / "signal214" / "history.json")
    if report.problems:
        raise RuntimeError("Signal quality gate failed: " + " | ".join(report.problems))
    key = CredentialStore().get_api_key()
    if not key:
        raise RuntimeError("Save the Gemini API key in Abrar Studio Settings first")
    settings = SettingsStore().load()
    installed_ffmpeg = Path.home() / "AppData" / "Local" / "Programs" / "AbrarStudio" / "tools" / "ffmpeg.exe"
    ffmpeg = str(installed_ffmpeg if installed_ffmpeg.exists() else settings.ffmpeg_path)
    renderer = Signal214Renderer(ffmpeg, project.assets_dir / "signal214")
    voice = generate_signal_narration(key, episode, project.audio_dir / "signal214")
    output = project.render_dir / "Signal214_Korean_Demo_1080x1920.mp4"

    def progress(value: float, text: str) -> None:
        print(f"{value:5.1f}%")

    renderer.render(episode, output, voice, progress)
    episode.save(project.root / "signal214" / "episodes" / f"{episode.episode_id}.json")
    renderer.contact_sheet(episode, project.temp_dir / "Signal214_Korean_Demo_contact_sheet.jpg")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
