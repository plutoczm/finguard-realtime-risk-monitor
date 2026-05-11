import argparse
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path


DATASET_URL = "https://huggingface.co/datasets/aaronzeller/small-aml-data/resolve/main/amlworld_transactions_prepared.csv"
EXPECTED_BYTES = 1_451_216_131
DEFAULT_OUTPUT = "enterprise_data/raw/amlworld_transactions_prepared.csv"


def human_size(value: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(value)
    for unit in units:
        if size < 1024:
            return f"{size:.2f}{unit}"
        size /= 1024
    return f"{size:.2f}TB"


def download_with_resume(url: str, output: Path, expected_bytes: int, chunk_size: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    context = ssl.create_default_context()
    last_size = -1
    stale_rounds = 0
    attempt = 0

    while True:
        current_size = output.stat().st_size if output.exists() else 0
        if current_size >= expected_bytes:
            print(f"Dataset already complete: {output} ({human_size(current_size)})")
            return

        if current_size == last_size:
            stale_rounds += 1
        else:
            stale_rounds = 0
            last_size = current_size

        if stale_rounds >= 20:
            raise RuntimeError("Download made no progress after multiple retries.")

        headers = {
            "User-Agent": "FinGuard-enterprise-dataset-downloader/1.0",
            "Range": f"bytes={current_size}-",
        }
        request = urllib.request.Request(url, headers=headers)
        attempt += 1
        print(
            f"Attempt {attempt}: resume from {human_size(current_size)} / {human_size(expected_bytes)}"
        )

        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response:
                status = getattr(response, "status", response.getcode())
                if current_size > 0 and status == 200:
                    raise RuntimeError("Server ignored Range header. Keep partial file and retry later.")

                mode = "ab" if current_size > 0 else "wb"
                downloaded = current_size
                last_print = time.time()
                with output.open(mode) as file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        file.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_print >= 5:
                            pct = downloaded / expected_bytes * 100
                            print(f"  progress: {human_size(downloaded)} ({pct:.2f}%)")
                            last_print = now
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionResetError,
            OSError,
            RuntimeError,
        ) as exc:
            wait_seconds = min(30, 3 + attempt)
            print(f"  interrupted: {exc}. Retry in {wait_seconds}s.")
            time.sleep(wait_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download enterprise AML dataset with resume support.")
    parser.add_argument("--url", default=DATASET_URL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-bytes", type=int, default=EXPECTED_BYTES)
    parser.add_argument("--chunk-size", type=int, default=4 * 1024 * 1024)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    download_with_resume(
        url=args.url,
        output=Path(args.output),
        expected_bytes=args.expected_bytes,
        chunk_size=args.chunk_size,
    )


if __name__ == "__main__":
    main()
