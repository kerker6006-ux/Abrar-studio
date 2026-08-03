from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .constants import APP_NAME, APP_VERSION
from .paths import app_root, user_data_dir
from .settings import SettingsStore
from .simple_motion import render_talking_shot
from .updater import GitHubUpdater, ReleaseInfo, UpdateError
from .vertex_cloud import VertexCloudError, VertexStudioClient

BG, PANEL, TEXT, MUTED, PURPLE, GREEN, RED = "#0d111d", "#161d30", "#f7f4ff", "#a6b1c9", "#875ce8", "#69d29e", "#ff6c7b"


def _gcloud_project() -> str:
    try:
        result = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True, timeout=12)
        return "" if result.stdout.strip() in {"", "(unset)"} else result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


class SimpleStudioApp(tk.Tk):
    """A deliberately small, scrollable one-prompt production screen."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1000x760")
        self.minsize(760, 580)
        self.configure(bg=BG)
        self.store = SettingsStore()
        self.settings = self.store.load()
        bundled_ffmpeg = app_root() / "tools" / "ffmpeg.exe"
        if self.settings.ffmpeg_path == "ffmpeg" and bundled_ffmpeg.exists():
            self.settings.ffmpeg_path = str(bundled_ffmpeg)
        if not self.settings.google_cloud_project:
            self.settings.google_cloud_project = _gcloud_project()
            self.store.save(self.settings)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.current_output: Path | None = None
        self.updater = GitHubUpdater(self.settings.update_owner, self.settings.update_repo, APP_VERSION)
        self._build()
        self.after(120, self._poll)
        if self.settings.auto_check_updates and getattr(sys, "frozen", False):
            self.after(1800, self._auto_update_check)

    def _build(self) -> None:
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        shell = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=shell, anchor="nw")
        shell.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(-1 * (event.delta // 120), "units"))
        content = tk.Frame(shell, bg=BG)
        content.pack(fill="both", expand=True, padx=38, pady=28)

        header = tk.Frame(content, bg=BG)
        header.pack(fill="x", pady=(0, 20))
        tk.Label(header, text="ABRAR", bg=BG, fg=TEXT, font=("Segoe UI", 29, "bold")).pack(side="left")
        tk.Label(header, text="Korean drama generator", bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(side="left", padx=(14, 0), pady=(11, 0))
        self.connection_badge = tk.Label(header, text=" CLOUD READY ", bg="#183b35", fg=GREEN, padx=9, pady=5, font=("Segoe UI", 9, "bold"))
        self.connection_badge.pack(side="right", pady=(6, 0))

        cloud = tk.Frame(content, bg=PANEL, padx=18, pady=14)
        cloud.pack(fill="x")
        tk.Label(cloud, text="GOOGLE CLOUD PROJECT", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row = tk.Frame(cloud, bg=PANEL)
        row.pack(fill="x", pady=(7, 0))
        self.project_var = tk.StringVar(value=self.settings.google_cloud_project)
        tk.Entry(row, textvariable=self.project_var, bg="#222c44", fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 10)).pack(side="left", fill="x", expand=True, ipady=7)
        self.test_button = tk.Button(row, text="Check", command=self._test_cloud, bg="#27344f", fg=TEXT, relief="flat", padx=16, pady=7, font=("Segoe UI", 9, "bold"))
        self.test_button.pack(side="left", padx=(10, 0))

        editor = tk.Frame(content, bg=PANEL, padx=20, pady=18)
        editor.pack(fill="both", expand=True, pady=(18, 0))
        tk.Label(editor, text="Your episode", bg=PANEL, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(editor, text="Paste a Korean script or describe the scene. Abrar makes a 10-second test first.", bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 12))
        self.prompt = tk.Text(editor, height=13, bg="#101728", fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", font=("Segoe UI", 12), padx=14, pady=14)
        self.prompt.pack(fill="both", expand=True)
        self.prompt.insert("1.0", "비 오는 밤, 오래된 아파트 복도에서 지연은 사라진 동생에게서 온 전화를 받는다.")

        action = tk.Frame(content, bg=BG)
        action.pack(fill="x", pady=(17, 0))
        self.generate_button = tk.Button(action, text="Generate video", command=self._generate, bg=PURPLE, fg="white", activebackground="#aa78ff", relief="flat", padx=26, pady=13, font=("Segoe UI", 11, "bold"))
        self.generate_button.pack(side="left")
        self.open_button = tk.Button(action, text="Open video", command=self._open_video, state="disabled", bg="#27344f", fg=TEXT, relief="flat", padx=18, pady=13, font=("Segoe UI", 10, "bold"))
        self.open_button.pack(side="left", padx=(10, 0))
        self.progress = ttk.Progressbar(content, maximum=100, value=0)
        self.progress.pack(fill="x", pady=(18, 0))
        self.status = tk.Label(content, text="Ready. Paste your episode and generate a 10-second test.", bg=BG, fg=MUTED, anchor="w", justify="left", wraplength=850, font=("Segoe UI", 10))
        self.status.pack(fill="x", pady=(10, 0))

    def _client(self) -> VertexStudioClient:
        project = self.project_var.get().strip()
        if not project:
            raise VertexCloudError("Enter your Google Cloud project ID first.")
        self.settings.google_cloud_project = project
        self.store.save(self.settings)
        return VertexStudioClient.from_environment(project)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.generate_button.configure(state=state)
        self.test_button.configure(state=state)

    def _test_cloud(self) -> None:
        self._set_busy(True)
        self.status.configure(text="Checking Google Cloud sign-in…", fg=MUTED)
        threading.Thread(target=self._task_test, daemon=True).start()

    def _task_test(self) -> None:
        try:
            self._client().verify_credentials()
            self.events.put(("ok", "Google Cloud is ready: Gemini Flash Image and Gemini TTS use this project."))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _generate(self) -> None:
        prompt = self.prompt.get("1.0", "end").strip()
        if len(prompt) < 12:
            messagebox.showwarning("Add your idea", "Please enter a longer story idea or Korean script.", parent=self)
            return
        self._set_busy(True)
        self.open_button.configure(state="disabled")
        self.progress.configure(value=1)
        threading.Thread(target=self._task_generate, args=(prompt,), daemon=True).start()

    def _task_generate(self, prompt: str) -> None:
        try:
            client = self._client(); client.verify_credentials()
            self.events.put(("progress", (8, "Writing the Korean scene…")))
            narration = client.generate_text("Write ONLY one Korean dramatic monologue of 24 to 34 Korean words. Safe fictional drama, emotional but restrained. Story idea: " + prompt)
            root = user_data_dir() / "Generations" / time.strftime("%Y%m%d_%H%M%S"); root.mkdir(parents=True, exist_ok=True)
            self.events.put(("progress", (18, "Generating scene artwork…")))
            background = client.generate_image("Original premium Korean web-drama 2D animation background only; no people, no text. Scene: " + prompt, root / "background.png", aspect_ratio="9:16")
            self.events.put(("progress", (34, "Generating locked mouth sheet…")))
            sheet = client.generate_image("Original premium Korean 2D drama sprite sheet, exactly six equal portrait cells in a 3 by 2 grid. Same adult Korean character, face, hair, clothes, pose and lighting in every cell. Only natural mouth state differs. No text, labels or borders. Story style: " + prompt, root / "mouth_sheet.png", aspect_ratio="9:16")
            self.events.put(("progress", (48, "Generating Korean voice…")))
            audio = client.generate_tts(narration, root / "voice.wav", style="quietly tense Korean drama performance, natural pauses")
            self.events.put(("progress", (55, "Animating locally…")))
            output = root / "AbrarDrama_10s.mp4"
            render_talking_shot(background_path=background, mouth_sheet_path=sheet, audio_path=audio, caption=narration, output_path=output, ffmpeg_path=self.settings.ffmpeg_path, progress=lambda value, label: self.events.put(("progress", (round(value * 100), label))))
            self.events.put(("video", output))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _auto_update_check(self) -> None:
        threading.Thread(target=self._task_update_check, daemon=True).start()

    def _task_update_check(self) -> None:
        try:
            release = self.updater.check()
            if release:
                self.events.put(("update", release))
        except UpdateError:
            pass

    def _install_update(self, release: ReleaseInfo) -> None:
        try:
            self.status.configure(text=f"Installing update {release.version}…", fg=MUTED)
            prepared = self.updater.prepare_update(release)
            self.updater.launch_prepared(prepared)
            self.after(350, self.destroy)
        except UpdateError as exc:
            self.status.configure(text=f"Update could not install: {exc}", fg=RED)

    def _poll(self) -> None:
        try:
            while True:
                event, data = self.events.get_nowait()
                if event == "progress":
                    value, label = data; self.progress.configure(value=value); self.status.configure(text=label, fg=MUTED)
                elif event == "ok":
                    self._set_busy(False); self.connection_badge.configure(text=" CLOUD READY ", bg="#183b35", fg=GREEN); self.status.configure(text=str(data), fg=GREEN)
                elif event == "video":
                    self._set_busy(False); self.current_output = data; self.progress.configure(value=100); self.status.configure(text=f"Finished: {data}", fg=GREEN); self.open_button.configure(state="normal")
                elif event == "update":
                    self._install_update(data)
                elif event == "error":
                    self._set_busy(False); self.progress.configure(value=0); self.connection_badge.configure(text=" CLOUD CHECK NEEDED ", bg="#4b242b", fg=RED); self.status.configure(text=str(data), fg=RED); messagebox.showerror("Generation stopped", str(data), parent=self)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _open_video(self) -> None:
        if self.current_output and self.current_output.exists():
            subprocess.Popen(["explorer", "/select,", str(self.current_output)])
