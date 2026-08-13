from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any


def fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def latest_job(jobs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [job for job in jobs if job.get("name") == name]
    return max(matches, key=lambda job: job.get("start-time", 0)) if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Flink/Kafka diagnostics for a failed streaming benchmark.")
    parser.add_argument("--flink-url", default="http://127.0.0.1:8081")
    parser.add_argument("--job-name", default="FinGuard Realtime Risk Monitor")
    parser.add_argument("--compose", default="docker compose")
    parser.add_argument("--output-dir", default="reports/benchmarks/runtime")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = args.flink_url.rstrip("/")

    try:
        overview = fetch_json(f"{base}/jobs/overview")
        write_json(output_dir / "jobs-overview.json", overview)
        jobs = overview.get("jobs", []) if isinstance(overview, dict) else []
        job = latest_job([item for item in jobs if isinstance(item, dict)], args.job_name)
        if job and job.get("jid"):
            job_id = str(job["jid"])
            for name, endpoint in (
                ("job.json", f"{base}/jobs/{job_id}"),
                ("exceptions.json", f"{base}/jobs/{job_id}/exceptions?maxExceptions=20"),
                ("checkpoints.json", f"{base}/jobs/{job_id}/checkpoints"),
                ("job-metrics.json", f"{base}/jobs/{job_id}/metrics"),
            ):
                try:
                    write_json(output_dir / name, fetch_json(endpoint))
                except Exception as exc:
                    write_json(output_dir / name, {"collection_error": f"{exc.__class__.__name__}: {exc}"})

            try:
                detail = fetch_json(f"{base}/jobs/{job_id}")
                for vertex in detail.get("vertices", []) if isinstance(detail, dict) else []:
                    vertex_id = vertex.get("id")
                    if not vertex_id:
                        continue
                    metrics = fetch_json(f"{base}/jobs/{job_id}/vertices/{vertex_id}/subtasks/metrics")
                    safe_name = str(vertex.get("name") or vertex_id).replace("/", "_")[:80]
                    write_json(output_dir / f"vertex-{safe_name}-{vertex_id}-metrics.json", metrics)
            except Exception as exc:
                write_json(output_dir / "vertex-metrics-error.json", {"collection_error": f"{exc.__class__.__name__}: {exc}"})
    except Exception as exc:
        write_json(output_dir / "flink-collection-error.json", {"collection_error": f"{exc.__class__.__name__}: {exc}"})

    result = subprocess.run([*args.compose.split(), "logs", "--no-color"], capture_output=True, text=True)
    (output_dir / "compose.log").write_text(
        (result.stdout or "") + ("\n" + result.stderr if result.stderr else ""), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
