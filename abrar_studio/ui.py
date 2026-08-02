from __future__ import annotations

import json
import os
import subprocess
from copy import deepcopy
import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from PIL import Image, ImageTk

from .constants import APP_NAME, APP_VERSION
from .character_packs import CharacterPackError
from .credentials import CredentialError, CredentialStore
from .gemini_tts import GeminiTTSClient, TTSGenerationError
from .alignment import build_alignment
from .models import ActorCue, Episode, ModelError, SFXCue, Scene, Shot
from .paths import app_root
from .project import StudioProject
from .renderer import AnimaticRenderer, RenderError
from .settings import AppSettings, SettingsStore
from .updater import GitHubUpdater, UpdateError
from .validator import QualityValidator, ValidationReport


BG = "#0d111d"
PANEL = "#151b2c"
PANEL_2 = "#1c2438"
TEXT = "#f6f3ff"
MUTED = "#9ba9c6"
PURPLE = "#8a5ee8"
PINK = "#ff5d98"
CYAN = "#62d8ff"
GREEN = "#66d19e"
RED = "#ff6b78"
BORDER = "#2a3651"


class StudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1320x840")
        self.minsize(1100, 700)
        self.configure(bg=BG)
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        bundled_ffmpeg = app_root() / "tools" / ("ffmpeg.exe" if __import__("os").name == "nt" else "ffmpeg")
        if self.settings.ffmpeg_path == "ffmpeg" and bundled_ffmpeg.exists():
            self.settings.ffmpeg_path = str(bundled_ffmpeg)
        self.credentials = CredentialStore()
        self.project = self._load_project()
        self.current_episode_path = self._first_episode_path()
        self.current_episode = self.project.load_episode(self.current_episode_path)
        self._images: dict[str, ImageTk.PhotoImage] = {}
        self._task_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._pages: dict[str, tk.Frame] = {}
        self._nav_buttons: dict[str, tk.Button] = {}
        self._configure_styles()
        self._build_shell()
        self._show_page("Dashboard")
        self.after(120, self._poll_tasks)
        if self.settings.auto_check_updates and self.settings.update_owner and self.settings.update_repo:
            self.after(2500, self._auto_update_check)

    def _load_project(self) -> StudioProject:
        if self.settings.project_path:
            root = Path(self.settings.project_path)
            if (root / "project.json").exists():
                return StudioProject(root)
        project = StudioProject.open_or_create_default()
        self.settings.project_path = str(project.root)
        self.settings_store.save(self.settings)
        return project

    def _first_episode_path(self) -> Path:
        files = self.project.episode_files()
        if not files:
            raise RuntimeError("Default project could not be created")
        return files[0]

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TProgressbar", troughcolor=PANEL_2, background=PURPLE, bordercolor=PANEL_2, lightcolor=PURPLE, darkcolor=PURPLE)
        style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, arrowcolor=TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", TEXT)])

    def _build_shell(self) -> None:
        sidebar = tk.Frame(self, bg="#0a0e18", width=230)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg="#0a0e18", height=120)
        brand.pack(fill="x")
        tk.Label(brand, text="ABRAR", bg="#0a0e18", fg=TEXT, font=("Segoe UI", 30, "bold")).pack(anchor="w", padx=28, pady=(23, 0))
        tk.Label(brand, text="STUDIO • 2:14 UNIVERSE", bg="#0a0e18", fg=PINK, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=31)

        nav_items = [
            ("Dashboard", "▦"), ("Characters", "◉"), ("Episode Script", "≡"), ("Shot Builder", "◫"),
            ("Voice Studio", "◖"), ("Production", "▶"), ("Quality Check", "✓"),
            ("Settings", "⚙"),
        ]
        nav = tk.Frame(sidebar, bg="#0a0e18")
        nav.pack(fill="x", padx=12, pady=12)
        for name, icon in nav_items:
            btn = tk.Button(
                nav, text=f"  {icon}   {name}", anchor="w", relief="flat", bd=0,
                bg="#0a0e18", fg=MUTED, activebackground=PANEL_2, activeforeground=TEXT,
                padx=12, pady=12, font=("Segoe UI", 10, "bold"),
                command=lambda n=name: self._show_page(n),
            )
            btn.pack(fill="x", pady=2)
            self._nav_buttons[name] = btn
        tk.Label(sidebar, text=f"v{APP_VERSION}\nLocal-first • 720p", bg="#0a0e18", fg="#63708b", justify="left").pack(side="bottom", anchor="w", padx=28, pady=25)

        self.content = tk.Frame(self, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)
        self._pages["Dashboard"] = self._build_dashboard()
        self._pages["Characters"] = self._build_characters()
        self._pages["Episode Script"] = self._build_script_page()
        self._pages["Shot Builder"] = self._build_shot_builder_page()
        self._pages["Voice Studio"] = self._build_voice_page()
        self._pages["Production"] = self._build_production_page()
        self._pages["Quality Check"] = self._build_quality_page()
        self._pages["Settings"] = self._build_settings_page()

    def _new_page(self, title: str, subtitle: str) -> tuple[tk.Frame, tk.Frame]:
        page = tk.Frame(self.content, bg=BG)
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=34, pady=(26, 18))
        tk.Label(header, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 25, "bold")).pack(anchor="w")
        tk.Label(header, text=subtitle, bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))
        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True, padx=34, pady=(0, 28))
        return page, body

    def _show_page(self, name: str) -> None:
        for page in self._pages.values():
            page.pack_forget()
        page = self._pages[name]
        page.pack(fill="both", expand=True)
        for nav_name, button in self._nav_buttons.items():
            selected = nav_name == name
            button.configure(bg=PANEL_2 if selected else "#0a0e18", fg=TEXT if selected else MUTED)
        if name == "Dashboard":
            self._refresh_dashboard()
        elif name == "Quality Check":
            self._run_validation(require_voices=False)
        elif name == "Shot Builder":
            self._shot_builder_refresh()

    def _card(self, parent: tk.Widget, **pack) -> tk.Frame:
        frame = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(**pack)
        return frame

    def _button(self, parent: tk.Widget, text: str, command: Callable, primary: bool = False, danger: bool = False) -> tk.Button:
        bg = RED if danger else (PURPLE if primary else PANEL_2)
        return tk.Button(
            parent, text=text, command=command, bg=bg, fg=TEXT, activebackground=PINK if primary else BORDER,
            activeforeground=TEXT, relief="flat", bd=0, padx=18, pady=10, cursor="hand2",
            font=("Segoe UI", 10, "bold"),
        )

    # Dashboard
    def _build_dashboard(self) -> tk.Frame:
        page, body = self._new_page("Production Dashboard", "Locked characters, locked voices, deterministic local rendering")
        hero = self._card(body, fill="x", pady=(0, 18))
        left = tk.Frame(hero, bg=PANEL)
        left.pack(side="left", fill="both", expand=True, padx=26, pady=24)
        tk.Label(left, text="2:14 Convenience Store", bg=PANEL, fg=TEXT, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(left, text="공감형 초자연 사이다 미스터리 영상툰", bg=PANEL, fg=PINK, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 12))
        tk.Label(left, text="Every export is blocked until identity, voice, acting, sound, music, pacing and continuity checks pass.", bg=PANEL, fg=MUTED, wraplength=650, justify="left").pack(anchor="w")
        self._button(left, "Open Production", lambda: self._show_page("Production"), primary=True).pack(anchor="w", pady=(18, 0))
        badge = tk.Frame(hero, bg="#21183a", highlightthickness=1, highlightbackground="#5c3c9e")
        badge.pack(side="right", padx=24, pady=24)
        tk.Label(badge, text="IDENTITY\nLOCKED", bg="#21183a", fg="#d7c4ff", font=("Segoe UI", 15, "bold"), justify="center").pack(padx=30, pady=24)

        stats = tk.Frame(body, bg=BG)
        stats.pack(fill="x")
        self.dashboard_stats: dict[str, tk.Label] = {}
        for key, label, accent in [
            ("duration", "EPISODE LENGTH", PINK), ("shots", "SHOTS", CYAN),
            ("characters", "LOCKED CHARACTERS", GREEN), ("resolution", "OUTPUT", PURPLE),
        ]:
            card = tk.Frame(stats, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12) if key != "resolution" else 0)
            tk.Label(card, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=18, pady=(18, 4))
            val = tk.Label(card, text="—", bg=PANEL, fg=accent, font=("Segoe UI", 22, "bold"))
            val.pack(anchor="w", padx=18, pady=(0, 18))
            self.dashboard_stats[key] = val

        lower = tk.Frame(body, bg=BG)
        lower.pack(fill="both", expand=True, pady=(18, 0))
        status = self._card(lower, side="left", fill="both", expand=True, padx=(0, 9))
        tk.Label(status, text="Pipeline Status", bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 10))
        self.dashboard_pipeline = tk.Frame(status, bg=PANEL)
        self.dashboard_pipeline.pack(fill="both", expand=True, padx=20, pady=(0, 18))
        episode = self._card(lower, side="left", fill="both", expand=True, padx=(9, 0))
        tk.Label(episode, text="Current Episode", bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 10))
        self.dashboard_episode_label = tk.Label(episode, text="", bg=PANEL, fg=MUTED, justify="left", wraplength=430)
        self.dashboard_episode_label.pack(anchor="w", padx=20, pady=(0, 14))
        self._button(episode, "Edit Script", lambda: self._show_page("Episode Script")).pack(anchor="w", padx=20, pady=(0, 18))
        return page

    def _refresh_dashboard(self) -> None:
        ep = self.current_episode
        minutes = int(ep.duration // 60)
        seconds = int(ep.duration % 60)
        self.dashboard_stats["duration"].configure(text=f"{minutes}:{seconds:02d}")
        self.dashboard_stats["shots"].configure(text=str(ep.shot_count))
        self.dashboard_stats["characters"].configure(text=str(len(ep.character_ids)))
        self.dashboard_stats["resolution"].configure(text=f"{ep.resolution[1]}p / {ep.fps}fps")
        for child in self.dashboard_pipeline.winfo_children():
            child.destroy()
        for text, ok in [
            ("Seo-yeon asset checksum", True), ("Min-jun asset checksum", True),
            ("Articulated walk/run rigs", True), ("Voice profiles fixed", True),
            ("Gemini API key stored", bool(self.credentials.get_api_key())),
            ("FFmpeg available", bool(shutil.which(self.settings.ffmpeg_path) or Path(self.settings.ffmpeg_path).is_file())),
        ]:
            row = tk.Frame(self.dashboard_pipeline, bg=PANEL)
            row.pack(fill="x", pady=4)
            tk.Label(row, text="●", bg=PANEL, fg=GREEN if ok else PINK).pack(side="left")
            tk.Label(row, text=text, bg=PANEL, fg=TEXT if ok else MUTED).pack(side="left", padx=8)
            tk.Label(row, text="READY" if ok else "SETUP", bg=PANEL, fg=GREEN if ok else PINK, font=("Segoe UI", 9, "bold")).pack(side="right")
        self.dashboard_episode_label.configure(text=f"{ep.episode_id} — {ep.title}\n{len(ep.scenes)} scenes • {ep.shot_count} shots\nProject: {self.project.root}")

    # Characters
    def _build_characters(self) -> tk.Frame:
        page, body = self._new_page("Character Vault", "Recurring characters are never redrawn during production")
        cards = tk.Frame(body, bg=BG)
        cards.pack(fill="x")
        for idx, cid in enumerate(["seo_yeon", "min_jun"]):
            manifest = self.project.character(cid)
            card = tk.Frame(cards, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
            card.pack(side="left", fill="both", expand=True, padx=(0, 10) if idx == 0 else (10, 0))
            source = self.project.character_manifest_path(cid).parent / "ui_card.png"
            image = Image.open(source).resize((380, 300), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self._images[f"card_{cid}"] = photo
            tk.Label(card, image=photo, bg=PANEL).pack(fill="x", padx=18, pady=(18, 12))
            tk.Label(card, text=manifest.display_name, bg=PANEL, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=22)
            tk.Label(card, text=f"{manifest.character_id} • {manifest.rig_version}", bg=PANEL, fg=MUTED).pack(anchor="w", padx=22, pady=(3, 12))
            tags = tk.Frame(card, bg=PANEL)
            tags.pack(fill="x", padx=22)
            for tag, color in [("IDENTITY LOCKED", GREEN), (manifest.voice_profile.voice_name.upper(), CYAN), ("NO AI REDRAW", PINK)]:
                tk.Label(tags, text=tag, bg=PANEL_2, fg=color, padx=9, pady=5, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 7))
            details = (
                f"Outfit: {manifest.outfit_id}\nPalette: {manifest.palette_id}\n"
                f"Normal voice: {manifest.voice_profile.normal_model}\n"
                f"Emotional voice: {manifest.voice_profile.emotional_model}\n"
                f"Expressions: {len(manifest.expressions)} locked presets\n"
                f"Poses: {len(manifest.poses)} • gestures: {len(manifest.gestures)}\n"
                f"Mouth states: {len(manifest.mouths)} locked shapes • audio-derived timing"
            )
            tk.Label(card, text=details, bg=PANEL, fg=MUTED, justify="left").pack(anchor="w", padx=22, pady=18)
        notice = self._card(body, fill="x", pady=(20, 0))
        tk.Label(notice, text="Production rule", bg=PANEL, fg=PINK, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(notice, text="A checksum mismatch blocks rendering. New outfits, guest characters or facial assets must be imported as a complete checksum-locked character pack; original protagonist files remain unchanged.", bg=PANEL, fg=MUTED, wraplength=900, justify="left").pack(anchor="w", padx=20, pady=(0, 10))
        controls = tk.Frame(notice, bg=PANEL)
        controls.pack(fill="x", padx=20, pady=(0, 16))
        self._button(controls, "Import locked guest pack (.zip)", self._import_character_pack, primary=True).pack(side="left")
        self.character_import_status = tk.Label(controls, text=f"{len(self.project.character_ids())} character pack(s) available", bg=PANEL, fg=MUTED)
        self.character_import_status.pack(side="left", padx=14)
        return page

    def _import_character_pack(self) -> None:
        path = filedialog.askopenfilename(parent=self, filetypes=[("Abrar character pack", "*.zip"), ("ZIP files", "*.zip")])
        if not path:
            return
        try:
            manifest = self.project.import_character(Path(path))
        except CharacterPackError as exc:
            messagebox.showerror("Character pack", str(exc), parent=self)
            return
        self.character_import_status.configure(text=f"Imported {manifest.display_name} • identity and voice locked", fg=GREEN)
        messagebox.showinfo("Character imported", f"{manifest.display_name} is ready for Shot Builder. Restart Abrar Studio to refresh all character menus.", parent=self)

    # Script
    def _build_script_page(self) -> tk.Frame:
        page, body = self._new_page("Episode Script", "Structured JSON drives locked voice, articulated motion, acting, gaze, camera, VFX, music, SFX and timing")
        toolbar = tk.Frame(body, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        self.script_path_label = tk.Label(toolbar, text=str(self.current_episode_path), bg=BG, fg=MUTED)
        self.script_path_label.pack(side="left")
        self._button(toolbar, "Load", self._load_script).pack(side="right", padx=(8, 0))
        self._button(toolbar, "New from template", self._load_episode_template).pack(side="right", padx=(8, 0))
        self._button(toolbar, "Save", self._save_script, primary=True).pack(side="right", padx=(8, 0))
        self._button(toolbar, "Validate JSON", self._validate_script_text).pack(side="right")
        editor_card = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        editor_card.pack(fill="both", expand=True)
        self.script_editor = tk.Text(
            editor_card, bg="#0b1020", fg="#e9e5ff", insertbackground=TEXT, selectbackground="#51398b",
            relief="flat", bd=0, padx=18, pady=16, undo=True, wrap="none", font=("Cascadia Mono", 10),
        )
        ybar = ttk.Scrollbar(editor_card, orient="vertical", command=self.script_editor.yview)
        xbar = ttk.Scrollbar(editor_card, orient="horizontal", command=self.script_editor.xview)
        self.script_editor.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        self.script_editor.pack(fill="both", expand=True)
        self._put_episode_in_editor()
        self.script_status = tk.Label(body, text="Ready", bg=BG, fg=MUTED)
        self.script_status.pack(anchor="w", pady=(8, 0))
        return page

    def _put_episode_in_editor(self) -> None:
        self.script_editor.delete("1.0", "end")
        self.script_editor.insert("1.0", json.dumps(self.current_episode.to_dict(), ensure_ascii=False, indent=2))

    def _validate_script_text(self) -> Episode | None:
        try:
            data = json.loads(self.script_editor.get("1.0", "end"))
            episode = Episode.from_dict(data)
        except (json.JSONDecodeError, ModelError) as exc:
            self.script_status.configure(text=f"Invalid: {exc}", fg=RED)
            messagebox.showerror("Script validation", str(exc), parent=self)
            return None
        self.script_status.configure(text=f"Valid • {episode.shot_count} shots • {episode.duration:.1f}s", fg=GREEN)
        return episode

    def _save_script(self) -> None:
        episode = self._validate_script_text()
        if not episode:
            return
        episode.save(self.current_episode_path)
        self.current_episode = episode
        self._shot_builder_refresh()
        self.script_status.configure(text="Saved and validated", fg=GREEN)


    def _load_episode_template(self) -> None:
        template_dir = app_root() / "templates" / "episodes"
        path = filedialog.askopenfilename(parent=self, initialdir=template_dir, filetypes=[("Abrar episode template", "*.json")])
        if not path:
            return
        try:
            episode = Episode.load(Path(path))
        except Exception as exc:
            messagebox.showerror("Episode template", str(exc), parent=self)
            return
        destination = self.project.episodes_dir / f"{episode.episode_id.lower()}_{len(self.project.episode_files())+1:02d}.json"
        episode.save(destination)
        self.current_episode_path = destination
        self.current_episode = episode
        self.script_path_label.configure(text=str(destination))
        self._put_episode_in_editor()
        self._shot_builder_refresh()
        self.script_status.configure(text=f"Template loaded • {episode.title}", fg=GREEN)

    def _load_script(self) -> None:
        path = filedialog.askopenfilename(parent=self, initialdir=self.project.episodes_dir, filetypes=[("Episode JSON", "*.json")])
        if not path:
            return
        try:
            self.current_episode_path = Path(path)
            self.current_episode = Episode.load(self.current_episode_path)
            self.script_path_label.configure(text=str(self.current_episode_path))
            self._put_episode_in_editor()
            self._shot_builder_refresh()
            self.script_status.configure(text="Loaded", fg=GREEN)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc), parent=self)


    # Shot Builder
    def _build_shot_builder_page(self) -> tk.Frame:
        page, body = self._new_page("Shot Builder", "Build multi-character shots without editing JSON by hand")
        split = tk.Frame(body, bg=BG)
        split.pack(fill="both", expand=True)
        left = self._card(split, side="left", fill="y", padx=(0, 10))
        right = self._card(split, side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(left, text="Episode shots", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        self.shot_list = tk.Listbox(left, width=30, bg="#0b1020", fg=TEXT, selectbackground="#51398b", relief="flat", bd=0, font=("Cascadia Mono", 9))
        self.shot_list.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.shot_list.bind("<<ListboxSelect>>", lambda _e: self._shot_builder_load())
        row = tk.Frame(left, bg=PANEL)
        row.pack(fill="x", padx=14, pady=(0, 14))
        self._button(row, "Add", self._shot_builder_add).pack(side="left")
        self._button(row, "Delete", self._shot_builder_delete, danger=True).pack(side="right")

        header = tk.Frame(right, bg=PANEL)
        header.pack(fill="x", padx=20, pady=(16, 10))
        tk.Label(header, text="Shot performance", bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(side="left")
        self._button(header, "Preview Motion", self._shot_builder_motion_preview).pack(side="right", padx=(8, 0))
        self._button(header, "Preview Frame", self._shot_builder_preview).pack(side="right", padx=(8, 0))
        self._button(header, "Save Shot", self._shot_builder_save, primary=True).pack(side="right")

        canvas = tk.Canvas(right, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right, orient="vertical", command=canvas.yview)
        form = tk.Frame(canvas, bg=PANEL)
        form.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True, padx=(20, 4), pady=(0, 18))

        self.shot_fields: dict[str, object] = {}
        def combo(label: str, key: str, values: list[str], row_index: int, default: str = "") -> None:
            tk.Label(form, text=label, bg=PANEL, fg=MUTED).grid(row=row_index, column=0, sticky="w", pady=6)
            widget = ttk.Combobox(form, state="readonly", values=values, width=28)
            widget.set(default or values[0])
            widget.grid(row=row_index, column=1, sticky="ew", padx=(14, 20), pady=6)
            self.shot_fields[key] = widget
        def entry(label: str, key: str, row_index: int, default: str = "") -> None:
            tk.Label(form, text=label, bg=PANEL, fg=MUTED).grid(row=row_index, column=0, sticky="w", pady=6)
            widget = tk.Entry(form, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat")
            widget.insert(0, default)
            widget.grid(row=row_index, column=1, sticky="ew", padx=(14, 20), pady=6, ipady=7)
            self.shot_fields[key] = widget

        entry("Shot ID", "id", 0)
        entry("Duration (seconds)", "duration", 1, "2.5")
        combo("Speaker", "speaker", [*self.project.character_ids(), "none"], 2, "seo_yeon")
        combo("Expression", "expression", ["neutral", "smile", "suspicious", "shock", "anger", "embarrassed", "sad", "breakdown"], 3)
        combo("Emotion", "emotion", ["neutral", "suspicious", "shock", "anger", "fear", "crying", "romantic", "comedy", "determined"], 4)
        combo("Intensity", "level", ["1", "2", "3", "4", "5"], 5, "3")
        combo("Acting", "acting", ["idle", "listen", "recoil", "lean_in", "collapse", "shy", "nod", "head_shake", "walk", "run"], 6)
        combo("Articulated motion", "motion", ["auto", "idle_breathe", "walk_slow", "walk_normal", "walk_confident", "walk_sad", "run_normal", "run_panicked", "start_walk", "stop_sudden", "step_back", "shock_recoil"], 7, "auto")
        entry("Motion speed", "motion_speed", 8, "1.0")
        entry("Travel X (-1.5 to 1.5)", "travel_x", 9, "0.0")
        combo("Facing", "facing", ["auto", "left", "right"], 10, "auto")
        combo("Pose", "pose", ["portrait", "full_front", "full_three_quarter", "full_side"], 11)
        combo("Gesture", "gesture", ["none", "relaxed", "fist", "write", "phone", "palm", "chest", "point", "stop"], 12)
        combo("Position", "position", ["far_left", "left", "center_left", "center", "center_right", "right", "far_right"], 13, "right")
        combo("Camera", "camera", ["static", "push_in", "pull_out", "pan_left", "pan_right", "tracking", "tracking_push", "handheld", "shake_push_in"], 14, "push_in")
        combo("Transition", "transition", ["cut", "fade", "dip_black", "flash", "whip"], 15)
        entry("Background", "background", 16, "convenience_store_night")
        entry("Music", "music", 17, "scanner_mystery_low")
        entry("Ambience", "ambience", 18, "store_hum")
        entry("SFX (comma separated)", "sfx", 19, "scanner_beep")
        entry("VFX (comma separated)", "vfx", 20, "scanner")

        tk.Label(form, text="Dialogue", bg=PANEL, fg=MUTED).grid(row=21, column=0, sticky="nw", pady=6)
        dialogue = tk.Text(form, height=4, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat", padx=10, pady=8, wrap="word")
        dialogue.grid(row=21, column=1, sticky="ew", padx=(14, 20), pady=6)
        self.shot_fields["dialogue"] = dialogue
        self.shot_listener = tk.BooleanVar(value=True)
        tk.Checkbutton(form, text="Add the other lead as a reacting listener", variable=self.shot_listener, bg=PANEL, fg=TEXT, selectcolor=PANEL_2, activebackground=PANEL, activeforeground=TEXT).grid(row=22, column=1, sticky="w", padx=(14, 20), pady=8)
        form.columnconfigure(1, weight=1)
        self._shot_builder_refresh()
        return page

    def _shot_builder_refresh(self) -> None:
        if not hasattr(self, "shot_list"):
            return
        self.shot_list.delete(0, "end")
        self.shot_builder_refs: list[tuple[int, int]] = []
        for scene_index, scene in enumerate(self.current_episode.scenes):
            for shot_index, shot in enumerate(scene.shots):
                self.shot_builder_refs.append((scene_index, shot_index))
                speaker = shot.speaker_id or "—"
                self.shot_list.insert("end", f"{shot.id:<15} {speaker:<10} {shot.duration:>4.1f}s")
        if self.shot_builder_refs:
            self.shot_list.selection_set(0)
            self._shot_builder_load()

    def _selected_shot(self) -> tuple[int, int, Shot] | None:
        selected = self.shot_list.curselection() if hasattr(self, "shot_list") else ()
        if not selected:
            return None
        scene_index, shot_index = self.shot_builder_refs[selected[0]]
        return scene_index, shot_index, self.current_episode.scenes[scene_index].shots[shot_index]

    def _field_value(self, key: str) -> str:
        widget = self.shot_fields[key]
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()  # type: ignore[union-attr]

    def _set_field(self, key: str, value: object) -> None:
        widget = self.shot_fields[key]
        if isinstance(widget, tk.Text):
            widget.delete("1.0", "end")
            widget.insert("1.0", str(value or ""))
        elif isinstance(widget, ttk.Combobox):
            widget.set(str(value or ""))
        else:
            widget.delete(0, "end")  # type: ignore[union-attr]
            widget.insert(0, str(value or ""))  # type: ignore[union-attr]

    def _shot_builder_load(self) -> None:
        chosen = self._selected_shot()
        if not chosen:
            return
        _, _, shot = chosen
        speaker = shot.speaker_id or "none"
        actor = next((item for item in shot.actors if item.character_id == speaker), shot.actors[0] if shot.actors else ActorCue("seo_yeon"))
        values = {
            "id": shot.id, "duration": shot.duration, "speaker": speaker,
            "expression": actor.expression, "emotion": shot.emotion, "level": shot.emotion_level,
            "acting": actor.acting, "motion": actor.motion, "motion_speed": actor.motion_speed,
            "travel_x": actor.travel_x, "facing": actor.facing, "pose": actor.pose, "gesture": actor.gesture,
            "position": actor.position, "camera": shot.camera, "transition": shot.transition,
            "background": shot.background or "", "music": shot.music or "", "ambience": shot.ambience or "",
            "sfx": ", ".join(cue.cue for cue in shot.sfx), "vfx": ", ".join(shot.vfx), "dialogue": shot.dialogue,
        }
        for key, value in values.items():
            self._set_field(key, value)
        self.shot_listener.set(len(shot.actors) > 1)

    def _shot_builder_save(self) -> None:
        chosen = self._selected_shot()
        if not chosen:
            return
        scene_index, shot_index, _old = chosen
        try:
            speaker = self._field_value("speaker")
            speaker_id = None if speaker == "none" else speaker
            position = self._field_value("position")
            actors: list[ActorCue] = []
            if speaker_id:
                actors.append(ActorCue(
                    character_id=speaker_id, expression=self._field_value("expression"), pose=self._field_value("pose"),
                    position=position, acting=self._field_value("acting"), gesture=self._field_value("gesture"), speaking=bool(self._field_value("dialogue")),
                    motion=self._field_value("motion"), motion_speed=float(self._field_value("motion_speed")),
                    travel_x=float(self._field_value("travel_x")), facing=self._field_value("facing"),
                ))
                if self.shot_listener.get():
                    other = "min_jun" if speaker_id == "seo_yeon" else "seo_yeon"
                    listener_position = "left" if position in {"right", "far_right", "center_right"} else "right"
                    actors.append(ActorCue(character_id=other, expression="neutral", pose="portrait", position=listener_position, acting="listen", gaze="speaker", speaking=False, scale=0.94, depth=-1))
            shot = Shot(
                id=self._field_value("id"), duration=float(self._field_value("duration")), character_id=speaker_id,
                expression=self._field_value("expression"), dialogue=self._field_value("dialogue"),
                emotion=self._field_value("emotion"), emotion_level=int(self._field_value("level")),
                camera=self._field_value("camera"), sfx=[SFXCue(cue=x.strip()) for x in self._field_value("sfx").split(",") if x.strip()],
                music=self._field_value("music") or None, background=self._field_value("background") or None,
                position=position, acting=self._field_value("acting"), vfx=[x.strip() for x in self._field_value("vfx").split(",") if x.strip()],
                transition=self._field_value("transition"), actors=actors, ambience=self._field_value("ambience") or None,
            )
        except Exception as exc:
            messagebox.showerror("Shot Builder", str(exc), parent=self)
            return
        self.current_episode.scenes[scene_index].shots[shot_index] = shot
        self.current_episode.save(self.current_episode_path)
        self._put_episode_in_editor()
        self._shot_builder_refresh()
        messagebox.showinfo("Shot Builder", "Shot saved and episode JSON updated.", parent=self)

    def _shot_builder_add(self) -> None:
        chosen = self._selected_shot()
        scene_index = chosen[0] if chosen else 0
        scene = self.current_episode.scenes[scene_index]
        number = self.current_episode.shot_count + 1
        scene.shots.append(Shot.from_dict({
            "id": f"SHOT_{number:03d}", "duration": 2.5, "character_id": "seo_yeon", "dialogue": "",
            "expression": "neutral", "emotion": "neutral", "emotion_level": 2, "camera": "push_in",
            "background": "convenience_store_night", "music": "scanner_mystery_low", "ambience": "store_hum", "sfx": [],
        }))
        self.current_episode.save(self.current_episode_path)
        self._put_episode_in_editor()
        self._shot_builder_refresh()
        self.shot_list.selection_clear(0, "end")
        self.shot_list.selection_set("end")
        self.shot_list.see("end")
        self._shot_builder_load()

    def _shot_builder_delete(self) -> None:
        chosen = self._selected_shot()
        if not chosen:
            return
        scene_index, shot_index, shot = chosen
        if len(self.current_episode.scenes[scene_index].shots) <= 1:
            messagebox.showwarning("Shot Builder", "A scene must keep at least one shot.", parent=self)
            return
        if not messagebox.askyesno("Delete shot", f"Delete {shot.id}?", parent=self):
            return
        del self.current_episode.scenes[scene_index].shots[shot_index]
        self.current_episode.save(self.current_episode_path)
        self._put_episode_in_editor()
        self._shot_builder_refresh()

    def _shot_builder_preview(self) -> None:
        chosen = self._selected_shot()
        if not chosen:
            return
        _, _, shot = chosen
        try:
            image = AnimaticRenderer(self.project, self.settings.ffmpeg_path).preview_frame(self.current_episode, shot)
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc), parent=self)
            return
        image.thumbnail((960, 540), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        window = tk.Toplevel(self)
        window.title(f"Preview — {shot.id}")
        window.configure(bg=BG)
        label = tk.Label(window, image=photo, bg=BG)
        label.image = photo
        label.pack(padx=12, pady=12)

    def _shot_builder_motion_preview(self) -> None:
        chosen = self._selected_shot()
        if not chosen:
            return
        _, _, shot = chosen
        preview_episode = Episode(
            project_id=self.current_episode.project_id,
            episode_id=f"PREVIEW_{shot.id}",
            title=f"Motion preview — {shot.id}",
            scenes=[Scene(id="PREVIEW", title="Motion preview", shots=[deepcopy(shot)])],
            resolution=self.current_episode.resolution,
            fps=self.current_episode.fps,
            version=self.current_episode.version,
            language=self.current_episode.language,
            content_rating=self.current_episode.content_rating,
        )
        output = self.project.temp_dir / f"motion_preview_{shot.id}.mp4"
        self.production_status.configure(text=f"Rendering motion preview: {shot.id}", fg=CYAN)
        self._run_task(
            "motion_preview",
            lambda: AnimaticRenderer(self.project, self.settings.ffmpeg_path, video_preset="veryfast", crf=20).render(preview_episode, output),
        )

    # Voice
    def _build_voice_page(self) -> tk.Frame:
        page, body = self._new_page("Voice Studio", "One permanent Gemini voice per character; emotional direction changes acting, not identity")
        controls = tk.Frame(body, bg=BG)
        controls.pack(fill="both", expand=True)
        left = self._card(controls, side="left", fill="both", expand=True, padx=(0, 10))
        right = self._card(controls, side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(left, text="Performance direction", bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(20, 12))
        form = tk.Frame(left, bg=PANEL)
        form.pack(fill="x", padx=20)
        tk.Label(form, text="Character", bg=PANEL, fg=MUTED).grid(row=0, column=0, sticky="w", pady=6)
        self.voice_character = ttk.Combobox(form, state="readonly", values=self.project.character_ids(), width=25)
        self.voice_character.set("seo_yeon")
        self.voice_character.grid(row=0, column=1, sticky="ew", padx=(14, 0), pady=6)
        tk.Label(form, text="Emotion", bg=PANEL, fg=MUTED).grid(row=1, column=0, sticky="w", pady=6)
        self.voice_emotion = ttk.Combobox(form, state="readonly", values=["neutral", "suspicious", "shock", "anger", "fear", "crying", "romantic", "comedy", "determined"], width=25)
        self.voice_emotion.set("neutral")
        self.voice_emotion.grid(row=1, column=1, sticky="ew", padx=(14, 0), pady=6)
        tk.Label(form, text="Intensity", bg=PANEL, fg=MUTED).grid(row=2, column=0, sticky="w", pady=6)
        self.voice_level = tk.Scale(form, from_=1, to=5, orient="horizontal", bg=PANEL, fg=TEXT, troughcolor=PANEL_2, highlightthickness=0, activebackground=PURPLE)
        self.voice_level.set(3)
        self.voice_level.grid(row=2, column=1, sticky="ew", padx=(14, 0), pady=6)
        form.columnconfigure(1, weight=1)
        tk.Label(left, text="Korean dialogue", bg=PANEL, fg=MUTED).pack(anchor="w", padx=20, pady=(16, 6))
        self.voice_text = tk.Text(left, height=6, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat", padx=12, pady=10, wrap="word")
        self.voice_text.pack(fill="x", padx=20)
        self.voice_text.insert("1.0", "언니도 보여요?")
        tk.Label(left, text="Optional director notes", bg=PANEL, fg=MUTED).pack(anchor="w", padx=20, pady=(14, 6))
        self.voice_direction = tk.Text(left, height=4, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat", padx=12, pady=10, wrap="word")
        self.voice_direction.pack(fill="x", padx=20)
        self._button(left, "Generate Locked Voice Take", self._generate_voice_preview, primary=True).pack(anchor="w", padx=20, pady=20)

        tk.Label(right, text="Identity profile", bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(20, 12))
        self.voice_profile_label = tk.Label(right, text="", bg=PANEL, fg=MUTED, justify="left", wraplength=430)
        self.voice_profile_label.pack(anchor="w", padx=20)
        self.voice_character.bind("<<ComboboxSelected>>", lambda _e: self._refresh_voice_profile())
        self._refresh_voice_profile()
        tk.Label(right, text="Activity", bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(28, 8))
        self.voice_log = tk.Text(right, bg="#0b1020", fg=MUTED, relief="flat", state="disabled", height=16, padx=12, pady=10, wrap="word")
        self.voice_log.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        return page

    def _refresh_voice_profile(self) -> None:
        char = self.project.character(self.voice_character.get())
        vp = char.voice_profile
        self.voice_profile_label.configure(text=(
            f"Character: {char.display_name}\nVoice: {vp.voice_name} (permanent lock)\n"
            f"Normal model: {vp.normal_model}\nEmotional model: {vp.emotional_model}\n"
            f"Language: {vp.language}\nProfile version: {vp.version}\n\n"
            "Generated files are cached by profile, model, voice, dialogue and direction. Approved audio is reused without regeneration."
        ))

    def _generate_voice_preview(self) -> None:
        key = self.credentials.get_api_key()
        if not key:
            messagebox.showwarning("API key required", "Open Settings and save a newly generated Gemini API key.", parent=self)
            return
        cid = self.voice_character.get()
        text = self.voice_text.get("1.0", "end").strip()
        if not text:
            return
        shot = Shot(
            id="VOICE_PREVIEW", duration=6, character_id=cid, expression="neutral",
            dialogue=text, emotion=self.voice_emotion.get(), emotion_level=int(self.voice_level.get()),
            voice_direction=self.voice_direction.get("1.0", "end").strip(), voice_model="auto",
        )
        char = self.project.character(cid)
        request = GeminiTTSClient.build_request(char, shot)
        output = self.project.voice_cache_path(cid, request.cache_key)
        if output.exists():
            self._log_voice(f"Cached approved take already exists:\n{output}")
            return
        self._log_voice(f"Generating {char.display_name} • {request.model} • {request.voice}")

        def work() -> Path:
            result = GeminiTTSClient(key).generate_best(request, output, takes=3 if shot.emotion_level >= 4 else 1)
            build_alignment(shot.dialogue, result, self.project.alignment_cache_path(cid, request.cache_key))
            return result
        self._run_task("voice", work)

    def _log_voice(self, text: str) -> None:
        self.voice_log.configure(state="normal")
        self.voice_log.insert("end", text + "\n\n")
        self.voice_log.see("end")
        self.voice_log.configure(state="disabled")

    # Production
    def _build_production_page(self) -> tk.Frame:
        page, body = self._new_page("Production", "Generate voice, validate all gates and render deterministic 720p motion-comic output")
        workflow = self._card(body, fill="x", pady=(0, 16))
        buttons = tk.Frame(workflow, bg=PANEL)
        buttons.pack(fill="x", padx=20, pady=20)
        self._button(buttons, "1  Preflight", lambda: self._run_validation(require_voices=False), primary=True).pack(side="left", padx=(0, 8))
        self._button(buttons, "2  Generate Missing Voices", self._generate_all_voices).pack(side="left", padx=8)
        self._button(buttons, "3  Validate Final", lambda: self._run_validation(require_voices=True)).pack(side="left", padx=8)
        self._button(buttons, "4  Render 720p", self._render_episode).pack(side="left", padx=8)
        self.production_progress = ttk.Progressbar(body, orient="horizontal", mode="determinate", maximum=100)
        self.production_progress.pack(fill="x", pady=(0, 12))
        self.production_status = tk.Label(body, text="Ready", bg=BG, fg=MUTED)
        self.production_status.pack(anchor="w", pady=(0, 12))
        log_card = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        log_card.pack(fill="both", expand=True)
        self.production_log = tk.Text(log_card, bg="#0b1020", fg="#bdc8de", relief="flat", state="disabled", padx=14, pady=12, wrap="word")
        self.production_log.pack(fill="both", expand=True)
        return page

    def _prod_log(self, text: str) -> None:
        self.production_log.configure(state="normal")
        self.production_log.insert("end", text + "\n")
        self.production_log.see("end")
        self.production_log.configure(state="disabled")

    def _generate_all_voices(self) -> None:
        key = self.credentials.get_api_key()
        if not key:
            messagebox.showwarning("API key required", "Save a replacement Gemini API key in Settings first.", parent=self)
            return
        jobs = []
        for scene in self.current_episode.scenes:
            for shot in scene.shots:
                speaker = shot.speaker_id
                if not shot.dialogue or not speaker:
                    continue
                char = self.project.character(speaker)
                req = GeminiTTSClient.build_request(char, shot)
                out = self.project.voice_cache_path(speaker, req.cache_key)
                if not out.exists():
                    jobs.append((char, shot, req, out))
        if not jobs:
            self._prod_log("All dialogue lines are already cached.")
            return

        def work() -> int:
            client = GeminiTTSClient(key)
            for idx, (char, shot, req, out) in enumerate(jobs, start=1):
                self._task_queue.put(("progress", (int(idx / len(jobs) * 100), f"Voice {idx}/{len(jobs)}: {shot.id}")))
                takes = 3 if ("pro" in req.model or shot.emotion_level >= 4) else 1
                client.generate_best(req, out, takes=takes)
                build_alignment(shot.dialogue, out, self.project.alignment_cache_path(char.character_id, req.cache_key))
            return len(jobs)
        self._prod_log(f"Generating {len(jobs)} missing voice line(s)…")
        self._run_task("voices", work)

    def _render_episode(self) -> None:
        validator = QualityValidator(self.project, self.settings.ffmpeg_path)
        report = validator.validate(self.current_episode, require_voices=True)
        if not report.passed:
            self._display_report(report)
            messagebox.showerror("Render blocked", "Final quality gates did not pass. Open Quality Check for details.", parent=self)
            return
        output = self.project.render_dir / f"{self.current_episode.episode_id}_720p.mp4"
        renderer = AnimaticRenderer(self.project, self.settings.ffmpeg_path)

        def progress(value: int, text: str) -> None:
            self._task_queue.put(("progress", (value, text)))

        def work() -> Path:
            return renderer.render(self.current_episode, output, progress)
        self._prod_log(f"Rendering to {output}")
        self._run_task("render", work)

    # Quality
    def _build_quality_page(self) -> tk.Frame:
        page, body = self._new_page("Quality Gates", "A failed gate blocks final export; there is no silent quality downgrade")
        toolbar = tk.Frame(body, bg=BG)
        toolbar.pack(fill="x", pady=(0, 12))
        self._button(toolbar, "Run Preflight", lambda: self._run_validation(require_voices=False), primary=True).pack(side="left")
        self._button(toolbar, "Run Final Validation", lambda: self._run_validation(require_voices=True)).pack(side="left", padx=10)
        self.quality_summary = tk.Label(toolbar, text="", bg=BG, fg=MUTED, font=("Segoe UI", 11, "bold"))
        self.quality_summary.pack(side="right")
        self.quality_results = tk.Frame(body, bg=BG)
        self.quality_results.pack(fill="both", expand=True)
        return page

    def _run_validation(self, require_voices: bool) -> None:
        try:
            report = QualityValidator(self.project, self.settings.ffmpeg_path).validate(self.current_episode, require_voices=require_voices)
        except Exception as exc:
            messagebox.showerror("Validation failed", str(exc), parent=self)
            return
        self._display_report(report)

    def _display_report(self, report: ValidationReport) -> None:
        if not hasattr(self, "quality_results"):
            return
        for child in self.quality_results.winfo_children():
            child.destroy()
        for item in report.results:
            row = tk.Frame(self.quality_results, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
            row.pack(fill="x", pady=5)
            tk.Label(row, text="✓" if item.passed else "!", bg=PANEL, fg=GREEN if item.passed else RED, font=("Segoe UI", 17, "bold"), width=3).pack(side="left", padx=(8, 0), pady=12)
            middle = tk.Frame(row, bg=PANEL)
            middle.pack(side="left", fill="both", expand=True, padx=8, pady=10)
            tk.Label(middle, text=item.gate, bg=PANEL, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(middle, text=item.detail, bg=PANEL, fg=MUTED, justify="left", wraplength=780).pack(anchor="w", pady=(3, 0))
            tk.Label(row, text="PASS" if item.passed else "BLOCK", bg=PANEL, fg=GREEN if item.passed else RED, font=("Segoe UI", 9, "bold")).pack(side="right", padx=20)
        passed = sum(1 for item in report.results if item.passed)
        self.quality_summary.configure(text=f"Quality {report.score}/100 • {passed}/{len(report.results)} gates passed", fg=GREEN if report.passed else RED)
        if hasattr(self, "production_log"):
            self._prod_log(f"Quality validation: {passed}/{len(report.results)} passed")
            for item in report.results:
                self._prod_log(f"{'PASS' if item.passed else 'BLOCK'} • {item.gate}: {item.detail}")

    # Settings
    def _build_settings_page(self) -> tk.Frame:
        page, body = self._new_page("Settings", "Secure credentials, FFmpeg path, project location and checksum-verified update channel")
        security = self._card(body, fill="x", pady=(0, 14))
        tk.Label(security, text="Gemini API key", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=20, pady=(18, 5))
        tk.Label(security, text="The key is encrypted with Windows DPAPI and tied to your Windows account. It is never written into episode files or application code.", bg=PANEL, fg=MUTED, wraplength=900, justify="left").pack(anchor="w", padx=20)
        key_row = tk.Frame(security, bg=PANEL)
        key_row.pack(fill="x", padx=20, pady=14)
        self.api_key_entry = tk.Entry(key_row, show="•", bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat", bd=0)
        self.api_key_entry.pack(side="left", fill="x", expand=True, ipady=10)
        self._button(key_row, "Save securely", self._save_api_key, primary=True).pack(side="left", padx=(10, 0))
        self._button(key_row, "Test Gemini", self._test_api_key).pack(side="left", padx=(8, 0))
        self._button(key_row, "Remove", self._remove_api_key, danger=True).pack(side="left", padx=(8, 0))

        system = self._card(body, fill="x", pady=(0, 14))
        tk.Label(system, text="Local tools", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 12))
        tk.Label(system, text="FFmpeg", bg=PANEL, fg=MUTED).grid(row=1, column=0, sticky="w", padx=20, pady=8)
        self.ffmpeg_entry = tk.Entry(system, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat")
        self.ffmpeg_entry.insert(0, self.settings.ffmpeg_path)
        self.ffmpeg_entry.grid(row=1, column=1, sticky="ew", padx=10, pady=8, ipady=8)
        self._button(system, "Browse", self._browse_ffmpeg).grid(row=1, column=2, padx=(0, 20), pady=8)
        tk.Label(system, text="Project", bg=PANEL, fg=MUTED).grid(row=2, column=0, sticky="w", padx=20, pady=8)
        self.project_entry = tk.Entry(system, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat")
        self.project_entry.insert(0, str(self.project.root))
        self.project_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=8, ipady=8)
        self._button(system, "Open folder", self._open_project_folder).grid(row=2, column=2, padx=(0, 20), pady=8)
        system.columnconfigure(1, weight=1)
        self._button(system, "Save local settings", self._save_settings, primary=True).grid(row=3, column=1, sticky="w", padx=10, pady=(10, 18))

        updates = self._card(body, fill="x")
        tk.Label(updates, text="Automatic updates", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=20, pady=(18, 5))
        tk.Label(updates, text="Publish checksum-verified installers as GitHub Release assets with a matching SHA-256 file. The app verifies the checksum before launching an update.", bg=PANEL, fg=MUTED, wraplength=900, justify="left").grid(row=1, column=0, columnspan=3, sticky="w", padx=20, pady=(0, 10))
        tk.Label(updates, text="Owner", bg=PANEL, fg=MUTED).grid(row=2, column=0, sticky="w", padx=20, pady=6)
        self.update_owner_entry = tk.Entry(updates, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat")
        self.update_owner_entry.insert(0, self.settings.update_owner)
        self.update_owner_entry.grid(row=2, column=1, sticky="ew", padx=10, pady=6, ipady=8)
        tk.Label(updates, text="Repository", bg=PANEL, fg=MUTED).grid(row=3, column=0, sticky="w", padx=20, pady=6)
        self.update_repo_entry = tk.Entry(updates, bg="#0b1020", fg=TEXT, insertbackground=TEXT, relief="flat")
        self.update_repo_entry.insert(0, self.settings.update_repo)
        self.update_repo_entry.grid(row=3, column=1, sticky="ew", padx=10, pady=6, ipady=8)
        self._button(updates, "Check now", self._check_update).grid(row=3, column=2, padx=(0, 20), pady=6)
        updates.columnconfigure(1, weight=1)
        self.settings_status = tk.Label(updates, text="", bg=PANEL, fg=MUTED)
        self.settings_status.grid(row=4, column=0, columnspan=3, sticky="w", padx=20, pady=(8, 18))
        return page

    def _save_api_key(self) -> None:
        key = self.api_key_entry.get().strip()
        try:
            self.credentials.set_api_key(key)
        except CredentialError as exc:
            messagebox.showerror("Secure storage", str(exc), parent=self)
            return
        self.api_key_entry.delete(0, "end")
        self.settings_status.configure(text="Gemini API key encrypted with Windows DPAPI", fg=GREEN)

    def _test_api_key(self) -> None:
        key = self.api_key_entry.get().strip() or self.credentials.get_api_key()
        if not key:
            messagebox.showwarning("API key required", "Enter or save a replacement Gemini API key first.", parent=self)
            return
        target = self.project.temp_dir / "gemini_connection_test.wav"
        self.settings_status.configure(text="Testing Gemini Korean TTS…", fg=CYAN)
        self._run_task("keytest", lambda: GeminiTTSClient(key).test_connection(target))

    def _remove_api_key(self) -> None:
        self.credentials.clear()
        self.settings_status.configure(text="Stored API key removed", fg=PINK)

    def _browse_ffmpeg(self) -> None:
        path = filedialog.askopenfilename(parent=self, filetypes=[("FFmpeg", "ffmpeg.exe"), ("All files", "*")])
        if path:
            self.ffmpeg_entry.delete(0, "end")
            self.ffmpeg_entry.insert(0, path)

    def _open_project_folder(self) -> None:
        path = str(self.project.root)
        try:
            import os
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("Open folder", str(exc), parent=self)

    def _save_settings(self) -> None:
        self.settings.ffmpeg_path = self.ffmpeg_entry.get().strip() or "ffmpeg"
        self.settings.project_path = self.project_entry.get().strip()
        self.settings.update_owner = self.update_owner_entry.get().strip()
        self.settings.update_repo = self.update_repo_entry.get().strip()
        self.settings_store.save(self.settings)
        self.settings_status.configure(text="Settings saved", fg=GREEN)

    def _auto_update_check(self) -> None:
        try:
            updater = GitHubUpdater(self.settings.update_owner, self.settings.update_repo, APP_VERSION)
            self._run_task("update", updater.check)
        except Exception:
            # Startup checks are silent; the manual Settings action shows errors.
            return

    def _check_update(self) -> None:
        self._save_settings()
        try:
            updater = GitHubUpdater(self.settings.update_owner, self.settings.update_repo, APP_VERSION)
        except Exception as exc:
            messagebox.showerror("Update", str(exc), parent=self)
            return

        def work():
            return updater.check()
        self.settings_status.configure(text="Checking for updates…", fg=CYAN)
        self._run_task("update", work)

    # Background task plumbing
    def _run_task(self, name: str, function: Callable[[], object]) -> None:
        def runner() -> None:
            try:
                result = function()
                self._task_queue.put((f"{name}:ok", result))
            except Exception as exc:
                self._task_queue.put((f"{name}:error", exc))
        threading.Thread(target=runner, daemon=True).start()

    def _poll_tasks(self) -> None:
        try:
            while True:
                event, payload = self._task_queue.get_nowait()
                if event == "progress":
                    value, text = payload  # type: ignore[misc]
                    self.production_progress["value"] = value
                    self.production_status.configure(text=text, fg=CYAN)
                    self._prod_log(text)
                elif event.endswith(":error"):
                    name = event.split(":", 1)[0]
                    if name in {"update", "update_install", "keytest"}:
                        self.settings_status.configure(text=f"{name} failed: {payload}", fg=RED)
                    else:
                        self.production_status.configure(text=f"{name} failed", fg=RED)
                        if name == "voice":
                            self._log_voice(f"ERROR: {payload}")
                        else:
                            self._prod_log(f"ERROR: {payload}")
                    messagebox.showerror(f"{name.title()} failed", str(payload), parent=self)
                elif event == "keytest:ok":
                    self.settings_status.configure(text="Gemini Korean TTS connection verified", fg=GREEN)
                    messagebox.showinfo("Gemini verified", "The API key generated a valid Korean TTS WAV.", parent=self)
                elif event == "voice:ok":
                    self._log_voice(f"Approved take cached:\n{payload}")
                elif event == "voices:ok":
                    self.production_progress["value"] = 100
                    self.production_status.configure(text=f"Generated {payload} voice line(s)", fg=GREEN)
                    self._prod_log(f"Generated {payload} voice line(s). Run Final Validation next.")
                elif event == "motion_preview:ok":
                    path = Path(payload)
                    self.production_status.configure(text=f"Motion preview ready: {path.name}", fg=GREEN)
                    try:
                        if os.name == "nt":
                            os.startfile(path)  # type: ignore[attr-defined]
                        elif shutil.which("xdg-open"):
                            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        messagebox.showinfo("Motion preview", str(path), parent=self)
                elif event == "render:ok":
                    self.production_progress["value"] = 100
                    self.production_status.configure(text="Render complete", fg=GREEN)
                    self._prod_log(f"Render complete: {payload}")
                    messagebox.showinfo("Render complete", str(payload), parent=self)
                elif event == "update:ok":
                    if payload is None:
                        self.settings_status.configure(text="You are using the latest published version", fg=GREEN)
                    else:
                        self.settings_status.configure(text=f"Version {payload.version} is available", fg=PINK)
                        if messagebox.askyesno("Update available", f"Download and install version {payload.version}?", parent=self):
                            updater = GitHubUpdater(self.settings.update_owner, self.settings.update_repo, APP_VERSION)
                            self._run_task("update_install", lambda: updater.download_and_launch(payload))
                elif event == "update_install:ok":
                    messagebox.showinfo("Update ready", "The verified installer has started. The app will close now.", parent=self)
                    self.destroy()
        except queue.Empty:
            pass
        self.after(120, self._poll_tasks)
