from __future__ import annotations
import hashlib, json, py_compile, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [
    "INSTALL_ABRAR_STUDIO.bat", "START_ABRAR_STUDIO.bat", "UNINSTALL_ABRAR_STUDIO.bat",
    "VERIFY_INSTALLATION.bat", "app.py", "requirements.txt", "scripts/install.ps1",
    "abrar_studio/renderer.py", "abrar_studio/gemini_tts.py", "abrar_studio/ui.py",
    "assets/characters/seo_yeon/manifest.json", "assets/characters/min_jun/manifest.json",
    "sample_project/episode_001.json", "VERIFICATION_REPORT.md",
    "templates/episodes/school_betrayal.json", "templates/episodes/romance_confession.json",
    "abrar_studio/character_packs.py", "abrar_studio/puppet.py",
    "templates/episodes/articulated_motion_showcase.json",
    "assets/characters/seo_yeon/rig/rig.json", "assets/characters/min_jun/rig/rig.json",
]
errors=[]
for rel in REQUIRED:
    if not (ROOT/rel).exists(): errors.append(f"missing {rel}")
for p in list((ROOT/"abrar_studio").glob("*.py"))+[ROOT/"app.py",ROOT/"run_diagnostics.py"]:
    try: py_compile.compile(str(p), doraise=True)
    except Exception as exc: errors.append(f"compile {p.name}: {exc}")
for rel in ["sample_project/episode_001.json", "assets/characters/seo_yeon/manifest.json", "assets/characters/min_jun/manifest.json"]:
    try: json.loads((ROOT/rel).read_text(encoding="utf-8"))
    except Exception as exc: errors.append(f"json {rel}: {exc}")
needles=[bytes.fromhex("41512e416238524e36"),bytes.fromhex("41497a615379")]
for p in ROOT.rglob("*"):
    if not p.is_file() or p.suffix.lower() in {".png",".jpg",".jpeg",".ico",".wav",".mp4",".zip"}: continue
    try: data=p.read_bytes()
    except OSError: continue
    if any(n in data for n in needles): errors.append(f"possible embedded API key in {p.relative_to(ROOT)}")
result={"passed":not errors,"errors":errors,"required_files":len(REQUIRED)}
(ROOT/"package_audit.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2))
raise SystemExit(0 if not errors else 1)
