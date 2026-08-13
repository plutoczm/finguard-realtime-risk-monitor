from __future__ import annotations

import argparse
import json
import re
import shutil
import tarfile
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


def safe_filename(value: str, limit: int = 60) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_.-")
    return (value or "vertex")[:limit]


def collect_flink(base: str, job_name: str, output_dir: Path) -> None:
    overview = fetch_json(f"{base}/jobs/overview")
    write_json(output_dir / "jobs-overview.json", overview)
    jobs = overview.get("jobs", []) if isinstance(overview, dict) else []
    job = latest_job([item for item in jobs if isinstance(item, dict)], job_name)
    if not job or not job.get("jid"):
        return

    job_id = str(job["jid"])
    endpoints = {
        "job.json": f"{base}/jobs/{job_id}",
        "exceptions.json": f"{base}/jobs/{job_id}/exceptions?maxExceptions=20",
        "checkpoints.json": f"{base}/jobs/{job_id}/checkpoints",
        "job-metrics.json": f"{base}/jobs/{job_id}/metrics",
    }
    for name, endpoint in endpoints.items():
        try:
            write_json(output_dir / name, fetch_json(endpoint))
        except Exception as exc:
            write_json(output_dir / name, {"collection_error": f"{type(exc).__name__}: {exc}"})

    try:
        detail = fetch_json(f"{base}/jobs/{job_id}")
        vertices = detail.get("vertices", []) if isinstance(detail, dict) else []
        for vertex in vertices:
            vertex_id = vertex.get("id")
            if not vertex_id:
                continue
            metrics = fetch_json(f"{base}/jobs/{job_id}/vertices/{vertex_id}/subtasks/metrics")
            name = safe_filename(str(vertex.get("name") or vertex_id))
            write_json(output_dir / f"vertex-{name}-{vertex_id}-metrics.json", metrics)
    except Exception as exc:
        write_json(output_dir / "vertex-metrics-error.json", {"collection_error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Flink diagnostics for a failed streaming benchmark.")
    parser.add_argument("--flink-url", default="http://127.0.0.1:8081")
    parser.add_argument("--job-name", default="FinGuard Realtime Risk Monitor")
    parser.add_argument("--output-dir", default="reports/benchmarks/runtime")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        collect_flink(args.flink_url.rstrip("/"), args.job_name, output_dir)
    except Exception as exc:
        write_json(output_dir / "collection-error.json", {"collection_error": f"{type(exc).__name__}: {exc}"})

    archive = output_dir.parent / "streaming-diagnostics.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(output_dir, arcname="runtime")
    shutil.rmtree(output_dir)
    print(f"Wrote diagnostic archive: {archive}")


if __name__ == "__main__":
    main()
