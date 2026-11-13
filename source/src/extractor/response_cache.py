"""Optional public-evaluation response cache. Never enabled for user uploads."""

import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4


def cache_path(directory: Path | None, request: dict, content: bytes = b"") -> Path | None:
    if directory is None:
        return None
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode() + content).hexdigest()
    return directory / f"{digest}.json"


def save_response(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class EvaluationBudget:
    """Sequential benchmark accounting; reservations survive interrupted calls."""

    def __init__(self, path: Path, ceiling: float = 2.99) -> None:
        self.path = path
        self.ceiling = ceiling
        self.spent = json.loads(path.read_text())["spent_or_reserved_usd"] if path.exists() else 0.0
        if not math.isfinite(self.spent) or self.spent < 0 or not 0 < ceiling < 3:
            raise ValueError("Invalid evaluation budget ledger or ceiling")

    def reserve(self, maximum: float) -> None:
        if not math.isfinite(maximum) or maximum < 0 or self.spent + maximum > self.ceiling:
            raise RuntimeError("Evaluation budget reached; no further API call was made")
        self.spent += maximum
        self.path.parent.mkdir(exist_ok=True)
        save_response(self.path, {"ceiling_usd": self.ceiling, "spent_or_reserved_usd": self.spent})

    def settle(self, maximum: float, actual: float | None) -> None:
        if actual is not None:
            if not math.isfinite(actual) or actual < 0:
                raise ValueError("Invalid provider cost; reservation retained")
            self.spent += actual - maximum
            save_response(self.path, {"ceiling_usd": self.ceiling, "spent_or_reserved_usd": self.spent})
