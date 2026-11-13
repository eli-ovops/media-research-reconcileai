"""Rerun all no-key checks and record honest fixture results (never model quality)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.reconciliation.engine import reconcile_documents  # noqa: E402
from src.reconciliation.models import DocumentExtraction, DocumentType  # noqa: E402
from tests.test_real_eval_and_batch import BATCH_FAILED_COUNT, BATCH_FIXTURE_SIZE, BATCH_WORKERS  # noqa: E402


def main(with_docling: bool = False) -> None:
    subprocess.run([sys.executable, "scripts/generate_benchmark.py"], cwd=ROOT, check=True)
    frozen = (ROOT / "evals/benchmark_v1.1.0_manifest.json").read_bytes()
    generated = (ROOT / "evals/generated/manifest.json").read_bytes()
    assert generated == frozen, "Original benchmark changed"
    manifest = json.loads(frozen)
    cases = []
    for case in manifest["cases"]:
        documents = []
        for kind in (DocumentType.INVOICE, DocumentType.PURCHASE_ORDER):
            items = case["invoice_items" if kind == DocumentType.INVOICE else "purchase_order_items"]
            total = sum(item["total_price"] for item in items)
            documents.append(
                DocumentExtraction(
                    document_type=kind,
                    document_number=case["case_id"],
                    vendor_name="Fixture vendor",
                    currency="INR",
                    line_items=items,
                    subtotal=total,
                    total_amount=total,
                )
            )
        result = reconcile_documents(*documents)
        predicted = Counter(discrepancy.type.value for discrepancy in result.discrepancies)
        expected = Counter(case["expected_discrepancies"])
        assert predicted == expected, case["case_id"]
        cases.append(
            {
                "case_id": case["case_id"],
                "scenario": case["scenario"],
                "expected": dict(expected),
                "predicted": dict(predicted),
                "passed": True,
            }
        )
    sample = json.loads((ROOT / "demo/result.json").read_text())
    result = reconcile_documents(
        DocumentExtraction.model_validate(sample["invoice"]),
        DocumentExtraction.model_validate(sample["purchase_order"]),
    )
    assert result.summary.discrepancy_count == sample["summary"]["discrepancy_count"]
    with tempfile.TemporaryDirectory() as directory:
        junit = Path(directory) / "tests.xml"
        subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={junit}"], cwd=ROOT, check=True)
        suites = ET.parse(junit).getroot()
        tests = list(suites.iter("testcase"))
        assert not list(suites.iter("failure")) and not list(suites.iter("error"))
    report = {
        "run_at_utc": datetime.now(UTC).isoformat(),
        "environment": sys.version,
        "source_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path(__file__),
                ROOT / "src/reconciliation/engine.py",
                ROOT / "src/main.py",
                ROOT / "tests/test_real_eval_and_batch.py",
            ]
        },
        "benchmark_sha256": hashlib.sha256(frozen).hexdigest(),
        "synthetic_pairs": len(cases),
        "synthetic_scenarios": len({case["scenario"] for case in cases}),
        "fixture_cases_passed": sum(case["passed"] for case in cases),
        "model_quality_measured": False,
        "sample_findings": result.summary.discrepancy_count,
        "tests_passed": len(tests),
        "test_cases": [f"{test.attrib.get('classname')}.{test.attrib['name']}" for test in tests],
        "batch_fixture": {
            "documents": BATCH_FIXTURE_SIZE,
            "completed": BATCH_FIXTURE_SIZE - BATCH_FAILED_COUNT,
            "failed": BATCH_FAILED_COUNT,
            "max_concurrent_workers": BATCH_WORKERS,
            "provider": "stub; tests queue/SSE/failure contracts only",
        },
        "cases": cases,
        "rerun": "python scripts/verify_results.py",
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/verification.json").write_text(json.dumps(report, indent=2) + "\n")
    bullets = [
        "# Provisional resume bullets",
        "",
        "Verified features only. Live model-quality metrics and public Spaces deployment are excluded "
        "until measured and verified. Numeric sources: `verification.json`.",
        "",
        f"- Built invoice/PO reconciliation with deterministic controls verified against "
        f"{report['synthetic_pairs']} labeled synthetic pairs "
        f"across {report['synthetic_scenarios']} scenarios.",
        "- Added persistent batch jobs with SSE progress and document-level failure isolation, "
        f"verified with a {report['batch_fixture']['documents']}-document "
        "integration fixture using a stub extractor.",
        f"- Built a no-key Gradio review demo showing {report['sample_findings']} precomputed mismatches "
        "with highlighted PDF source evidence.",
    ]
    comparison_path = ROOT / "results/real_comparison.json"
    if comparison_path.exists():
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        backends = comparison["backends"]
        if all(
            name in backends
            and backends[name]["status"] == "measured"
            and backends[name]["held_out"]["completed"] > 0
            for name in ("gemini", "qwen", "docling_text_llm")
        ):
            held = backends["gemini"]["held_out"]["attempted"]
            scores = [
                f"{backends[name]['held_out']['micro']['f1']:.1%}"
                for name in ("gemini", "qwen", "docling_text_llm")
            ]
            gemini_label = {"gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite"}.get(
                comparison["gemini_model"], comparison["gemini_model"]
            )
            qwen_label = {"qwen/qwen3.8-27b": "Qwen3.8-27B"}.get(
                comparison["vlm_model"], comparison["vlm_model"]
            )
            qwen_label += f" ({comparison['vlm_provider'].title()})"
            bullets = [
                "# Resume bullets",
                "",
                "Numeric sources: `real_comparison.json` and `verification.json`. "
                "Field F1 uses frozen CORD annotations; fixture checks use a stub extractor.",
                "",
                f"- Evaluated {gemini_label}, {qwen_label}, and Docling OCR + {gemini_label} on "
                f"{len(comparison['requested_cases'])} public CORD receipts, achieving "
                f"{', '.join(scores)} field F1 respectively on {held} held-out receipts; "
                "normalized predictions enable offline scoring and confidence calibration.",
                bullets[4],
                f"- Added persistent batch processing with SSE progress, verified using a "
                f"{report['batch_fixture']['documents']}-document stub fixture, and a no-key "
                f"PDF review demo highlighting {report['sample_findings']} precomputed mismatches.",
            ]
    (ROOT / "results/RESUME_BULLETS.md").write_text("\n".join(bullets) + "\n")
    if with_docling:
        from src.parser.real_document_parser import parse_document

        cord = json.loads((ROOT / "results/cord_manifest.json").read_text(encoding="utf-8"))
        receipt = next(case for case in cord["cases"] if case["split"] == "held_out")
        rows = []
        for path in (ROOT / "demo/invoice.pdf", ROOT / receipt["image"]):
            started = time.perf_counter()
            parsed = asyncio.run(parse_document(path))
            assert parsed.page_count and parsed.text and parsed.evidence
            assert all(
                0 <= coordinate <= 1
                for evidence in parsed.evidence
                if evidence.bbox
                for coordinate in evidence.bbox
            )
            rows.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "pages": parsed.page_count,
                    "characters": len(parsed.text),
                    "evidence_regions": len(parsed.evidence),
                    "latency_seconds": time.perf_counter() - started,
                }
            )
        (ROOT / "results/ingestion.json").write_text(
            json.dumps(
                {
                    "documents": rows,
                    "docling_version": importlib.metadata.version("docling"),
                    "model_quality_measured": False,
                    "rerun": "python scripts/verify_results.py --with-docling",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"Recorded {len(cases)} fixture cases and {len(tests)} passing tests; no model-quality claim")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-docling", action="store_true", help="Also parse the sample PDF and a real CORD receipt"
    )
    main(parser.parse_args().with_docling)
