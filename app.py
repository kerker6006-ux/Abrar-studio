from __future__ import annotations

import sys
import traceback
from pathlib import Path


def main() -> int:
    try:
        from abrar_studio.monitoring import configure_sentry
        from abrar_studio.settings import SettingsStore

        configure_sentry(SettingsStore().load().telemetry_enabled)
        from abrar_studio.ui import StudioApp
        app = StudioApp()
        app.mainloop()
        return 0
    except Exception as exc:
        try:
            from abrar_studio.monitoring import capture_exception, flush

            capture_exception(exc, "startup")
            flush()
        except Exception:
            pass
        crash = Path.home() / "AbrarStudio_crash.log"
        crash.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            import tkinter.messagebox as messagebox
            messagebox.showerror("Abrar Studio", f"The application could not start:\n{exc}\n\nCrash log: {crash}")
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
