from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from abrar_studio.production_pipeline import ProductionPipeline
from abrar_studio.vertex_cloud import VertexStudioClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real Vertex AI production test")
    parser.add_argument("--project", required=True)
    script_group = parser.add_mutually_exclusive_group(required=True)
    script_group.add_argument("--script")
    script_group.add_argument("--script-file", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    client = VertexStudioClient.from_environment(args.project)
    client.verify_credentials()
    script = args.script if args.script is not None else args.script_file.read_text(encoding="utf-8")
    result = ProductionPipeline(client, args.ffmpeg).generate(
        script,
        progress=lambda value, label: print(f"{value:.0%} {label}", flush=True),
    )
    print(f"OUTPUT={result.output}", flush=True)
    print(f"SHOTS={len(result.plan.shots)} CHARACTERS={len(result.plan.characters)} AUDIO={result.audio_catalog_size}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
