"""Download the public Sample Superstore source file."""
from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = PROJECT_ROOT / "data" / "raw" / "raw_superstore.csv"
SOURCE_URL = (
    "https://raw.githubusercontent.com/thummam/superstore-sales-dashboard/"
    "main/data/raw_superstore.csv"
)


def download(destination: Path = DEFAULT_DESTINATION) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "superstore-sales-analysis/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
    except Exception as exc:  # pragma: no cover - network-dependent
        raise RuntimeError(
            "Could not download the dataset. Check your internet connection or "
            "download it manually from the source URL in README.md and save it "
            f"to {destination}. Original error: {exc}"
        ) from exc

    if len(payload) < 10_000 or b"Order ID" not in payload[:1_000]:
        raise RuntimeError("The downloaded file does not look like the expected CSV.")

    destination.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    print(f"Saved dataset: {destination}")
    print(f"Bytes: {len(payload):,} | SHA-256: {digest}")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    download(args.output)
