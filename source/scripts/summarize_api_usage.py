"""Offline HTTP attempt accounting, including failures and the Pro access probe."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(paths):
    models = {}
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        summary = models.setdefault(
            record["model"], {"requests": 0, "http_attempts": 0, "statuses": Counter(), "backoff_seconds": 0}
        )
        summary["requests"] += 1
        for attempt in record["attempts"]:
            summary["http_attempts"] += 1
            summary["statuses"][str(attempt["http_status"])] += 1
            summary["backoff_seconds"] += attempt["backoff_seconds"]
    return models


if __name__ == "__main__":
    paths = sorted((ROOT / "results/raw").rglob("*.attempts.json"))
    if not paths:
        raise SystemExit("Local ignored attempt caches are required; existing summaries were not changed")
    result = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "models": summarize(paths),
        "source_files": [p.relative_to(ROOT).as_posix() for p in paths],
        "local_cache_sha256": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ("raw", "parsed")
            for p in sorted((ROOT / "results" / directory).rglob("*.json"))
        },
        "note": "Unique cached request keys; cache reads do not add HTTP calls. Includes Pro access probe.",
        "rerun": "python scripts/summarize_api_usage.py",
    }
    (ROOT / "results/rate_limiting.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["models"], indent=2))
