"""Run the real ReconcileAI pipeline over a generated benchmark split."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor.gemini_extractor import GeminiDocumentExtractor  # noqa: E402
from src.parser.real_document_parser import parse_document  # noqa: E402
from src.reconciliation.engine import reconcile_documents  # noqa: E402
from src.reconciliation.models import DocumentType  # noqa: E402
from config import settings  # noqa: E402

DATA = ROOT / "evals" / "generated"


def score_items(extraction, expected: list[dict], row_tops: list[float]) -> dict:
    """Score exact row values and whether evidence lands on the labeled row."""
    actual_by_sku = {item.sku: item for item in extraction.line_items if item.sku}
    exact = located = 0
    for index, item in enumerate(expected):
        actual = actual_by_sku.get(item["sku"])
        if actual is None:
            continue
        if all(Decimal(str(getattr(actual, key))) == Decimal(str(item[key]))
               for key in ("quantity", "unit_price", "total_price")):
            exact += 1
        evidence = actual.evidence
        if evidence and evidence.page == 1 and evidence.bbox:
            middle_y = (evidence.bbox[1] + evidence.bbox[3]) / 2
            if abs(middle_y - row_tops[index]) <= 0.04:
                located += 1
    return {"expected_rows": len(expected), "exact_rows": exact, "located_rows": located}


async def evaluate_case(case: dict) -> dict:
    started = time.perf_counter()
    invoice_path = DATA / case["invoice"]
    po_path = DATA / case["purchase_order"]
    invoice_parsed, po_parsed = await asyncio.gather(parse_document(invoice_path), parse_document(po_path))
    extractor = GeminiDocumentExtractor()
    invoice, po = await asyncio.gather(
        extractor.extract(invoice_path, f"{case['case_id']}_invoice", DocumentType.INVOICE, invoice_parsed),
        extractor.extract(po_path, f"{case['case_id']}_po", DocumentType.PURCHASE_ORDER, po_parsed),
    )
    result = reconcile_documents(invoice, po)
    predicted = Counter(item.type.value for item in result.discrepancies)
    expected = Counter(case["expected_discrepancies"])
    row_scores = [
        score_items(invoice, case["invoice_items"], case["row_top_fractions"]),
        score_items(po, case["purchase_order_items"], case["row_top_fractions"]),
    ]
    return {
        "case_id": case["case_id"],
        "status": "completed",
        "expected": dict(expected),
        "predicted": dict(predicted),
        "true_positives": sum((predicted & expected).values()),
        "false_positives": sum((predicted - expected).values()),
        "false_negatives": sum((expected - predicted).values()),
        "expected_rows": sum(row["expected_rows"] for row in row_scores),
        "exact_rows": sum(row["exact_rows"] for row in row_scores),
        "located_rows": sum(row["located_rows"] for row in row_scores),
        "review_required": result.summary.status == "review_required",
        "provider_metadata": [invoice.provider_metadata, po.provider_metadata],
        "latency_seconds": round(time.perf_counter() - started, 3),
    }


async def main(split: str) -> None:
    manifest_path = DATA / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Run scripts/generate_benchmark.py first")
    if not settings.GEMINI_API_KEY:
        raise SystemExit("Set GEMINI_API_KEY locally before running the live evaluation")
    manifest_bytes = manifest_path.read_bytes()
    frozen_bytes = (ROOT / "evals" / "benchmark_v1.1.0_manifest.json").read_bytes()
    if manifest_bytes != frozen_bytes:
        raise SystemExit("Generated manifest differs from the frozen v1.1.0 benchmark")
    manifest = json.loads(manifest_bytes)
    if manifest["version"] != "1.1.0":
        raise SystemExit("Regenerate benchmark v1.1.0 before running this scorer")
    cases = [case for case in manifest["cases"] if case["split"] == split]
    results = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case['case_id']}")
        started = time.perf_counter()
        try:
            results.append(await evaluate_case(case))
        except Exception as exc:
            results.append({"case_id": case["case_id"], "status": "failed",
                            "error_type": type(exc).__name__, "error": str(exc),
                            "latency_seconds": round(time.perf_counter() - started, 3)})
    completed = [row for row in results if row["status"] == "completed"]
    tp = sum(row["true_positives"] for row in completed)
    fp = sum(row["false_positives"] for row in completed)
    fn = sum(row["false_negatives"] for row in completed)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    expected_rows = sum(row["expected_rows"] for row in completed)
    latencies = sorted(row["latency_seconds"] for row in results)
    report = {
        "benchmark": manifest["name"],
        "version": manifest["version"],
        "split": split,
        "run_at_utc": datetime.now(UTC).isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dataset_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "provider": "Gemini", "model": settings.DEFAULT_VISION_MODEL,
        "prompt_version": "src/extractor/gemini_extractor.py at commit",
        "environment": f"Python {sys.version.split()[0]}",
        "attempted_cases": len(results), "completed_cases": len(completed),
        "failed_cases": len(results) - len(completed),
        "discrepancy_precision": round(precision, 4) if precision is not None else None,
        "discrepancy_recall": round(recall, 4) if recall is not None else None,
        "discrepancy_f1": round(f1, 4) if f1 is not None else None,
        "exact_row_rate": round(sum(row["exact_rows"] for row in completed) / expected_rows, 4) if expected_rows else None,
        "evidence_row_location_rate": round(sum(row["located_rows"] for row in completed) / expected_rows, 4) if expected_rows else None,
        "review_rate": round(sum(row["review_required"] for row in completed) / len(completed), 4) if completed else None,
        "latency_p50_seconds": latencies[len(latencies) // 2] if latencies else None,
        "latency_p95_seconds": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None,
        "estimated_cost_usd": round(sum(float(meta.get("estimated_cost_usd", 0)) for row in completed for meta in row["provider_metadata"]), 6),
        "limits": "Synthetic single-page pairs; type counts do not identify the affected discrepancy row. Row and evidence scores evaluate extraction separately. Failed cases are excluded from completed-case quality denominators and counted explicitly.",
        "results": results,
    }
    report_dir = ROOT / "evals" / "reports"
    report_dir.mkdir(exist_ok=True)
    target = report_dir / f"{split}.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "held_out"), default="held_out")
    args = parser.parse_args()
    asyncio.run(main(args.split))
