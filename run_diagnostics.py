from pathlib import Path
from abrar_studio.diagnostics import run_diagnostics, write_report

items = run_diagnostics()
for item in items:
    print(("PASS" if item.passed else "FAIL") + f" | {item.name}: {item.detail}")
report = write_report(Path("diagnostics_report.json"), items)
print(f"Report: {report.resolve()}")
raise SystemExit(0 if all(i.passed for i in items if i.name != "Secure key storage") else 1)
