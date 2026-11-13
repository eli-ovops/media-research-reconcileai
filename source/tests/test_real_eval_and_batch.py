import asyncio
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

import src.main as main
from scripts.run_real_eval import (
    FIELDS,
    aggregate,
    metrics,
    normalize,
    reliability,
    score_fields,
    tune_threshold,
)
from src.parser.real_document_parser import ParsedArtifact
from src.storage import JobStore
from tests.test_api import extraction

BATCH_FIXTURE_SIZE = 6
BATCH_FAILED_COUNT = 1
BATCH_WORKERS = 2


def test_field_scores_preserve_duplicates_and_penalize_failures():
    expected = {field: [] for field in FIELDS}
    expected["description"] = ["Coffee", "Coffee"]
    predicted = {"description": [{"value": "Coffee", "confidence": 1}]}
    counts, samples, errors = score_fields(expected, predicted)
    assert counts["description"] == {"tp": 1, "fp": 0, "fn": 1}
    assert samples[0]["correct"] == 1
    assert errors[0]["field"] == "description"
    failed_counts, _, _ = score_fields(expected, {})
    result = aggregate(
        [{"counts": failed_counts, "status": "failed", "cost_usd": None, "latency_seconds": 1}]
    )
    assert result["micro"]["f1"] == 0
    assert result["micro"]["fn"] == 2
    assert result["estimated_cost_per_document_usd"] is None
    assert result["paid_equivalent_cost_per_document_usd"] is None
    billed = aggregate(
        [
            {
                "counts": counts,
                "status": "completed",
                "cost_usd": 0,
                "latency_seconds": 1,
                "provider_metadata": {"paid_equivalent_usd": 0.002},
            }
        ]
    )
    assert billed["estimated_cost_per_document_usd"] == 0
    assert billed["paid_equivalent_cost_per_document_usd"] == 0.002
    assert normalize("Rp 18.000", "total_amount") == normalize(18000.0, "total_amount")
    assert normalize("1,5", "quantity") == "1.5"
    assert normalize("1.50", "quantity") == "1.5"
    assert normalize("1 x", "quantity") == "1"
    assert normalize("@ 28,000", "unit_price") == "28000"
    assert metrics({"tp": 0, "fp": 0, "fn": 0})["f1"] is None
    from scripts.run_real_eval import tag_errors

    tag_errors(errors, None, {"category": "schema"})
    assert errors[0]["category"] == "schema"


def test_cord_labels_exclude_keys_and_use_actual_sub_total_category():
    from scripts.prepare_cord import cord_labels

    labels = cord_labels(
        {
            "gt_parse": {
                "menu": [{"nm": "Coffee", "cnt": "1"}, {"nm": "Coffee", "cnt": "2"}],
                "sub_total": {"subtotal_price": ["10,000", "10,000"], "tax_price": "1,000"},
                "total": {"total_price": "11,000"},
            }
        }
    )
    assert labels["total_amount"] == ["11,000"]
    assert labels["subtotal"] == ["10,000", "10,000"] and labels["tax_amount"] == ["1,000"]
    assert labels["description"] == ["Coffee", "Coffee"]


def test_calibration_includes_endpoints_and_does_not_split_ties():
    assert reliability([{"confidence": 1, "correct": 0}, {"confidence": 0, "correct": 1}])["ece"] == 1
    with pytest.raises(ValueError):
        reliability([{"confidence": float("nan"), "correct": 1}])
    rows = [{"confidence": 0.5, "correct": False, "mandatory_review": False}] * 4
    selection = tune_threshold(rows, 0.2)
    assert selection["threshold"] == 0
    assert selection["target_achieved"] is False
    assert selection["review_rate"] == 0
    assert tune_threshold([{**rows[0], "mandatory_review": True}], 0.2)["review_rate"] == 1


def test_batch_validation_worker_limit_sse_failure_and_persistence(tmp_path, monkeypatch):
    database = tmp_path / "batch.db"
    monkeypatch.setattr(main, "store", JobStore(database))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main.settings, "BATCH_WORKERS", BATCH_WORKERS)
    active = maximum = 0

    async def parse(path):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        if path.read_bytes().endswith(b"fail"):
            raise ValueError("Broken input")
        return ParsedArtifact(text="sample", page_count=1)

    class Extractor:
        async def extract(self, path, document_id, kind, parsed):
            return extraction(kind)

    monkeypatch.setattr(main, "parse_document", parse)
    monkeypatch.setattr(main, "GeminiDocumentExtractor", Extractor)
    client = TestClient(main.app)
    invalid = client.post(
        "/api/v1/batches", files=[("documents", ("bad.pdf", BytesIO(b"bad"), "application/pdf"))]
    )
    assert invalid.status_code == 415
    assert not (tmp_path / "uploads").exists()
    files = [
        (
            "documents",
            (
                f"{i}.pdf",
                BytesIO(b"%PDF-1.7" + (b"fail" if i == BATCH_FIXTURE_SIZE - 1 else b"ok")),
                "application/pdf",
            ),
        )
        for i in range(BATCH_FIXTURE_SIZE)
    ]
    response = client.post("/api/v1/batches", files=files)
    assert response.status_code == 202
    batch_id = response.json()["job_id"]
    batch = client.get(f"/api/v1/batches/{batch_id}").json()
    assert (
        batch["total"] == BATCH_FIXTURE_SIZE
        and batch["completed"] == BATCH_FIXTURE_SIZE - BATCH_FAILED_COUNT
        and batch["failed"] == BATCH_FAILED_COUNT
        and batch["done"]
    )
    assert maximum == BATCH_WORKERS
    assert "invoice_path" not in batch["jobs"][0]
    with monkeypatch.context() as patch:
        snapshots = iter([batch, {**batch, "done": False, "completed": 0, "failed": 0}, batch])
        patch.setattr(main.store, "batch", lambda _: next(snapshots))
        stream = client.get(response.json()["events_url"])
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in stream.text and "event: done" in stream.text
    payload = json.loads(stream.text.split("data: ")[-1])
    assert payload["failed"] == BATCH_FAILED_COUNT and "jobs" not in payload
    assert JobStore(database).batch(batch_id)["completed"] == BATCH_FIXTURE_SIZE - BATCH_FAILED_COUNT
    assert client.get("/api/v1/batches/missing/events").status_code == 404
    job_id = batch["jobs"][0]["job_id"]
    assert client.get(f"/api/v1/jobs/{job_id}/documents/purchase_order").status_code == 404
    assert client.put(f"/api/v1/jobs/{job_id}/review", json={}).status_code == 409


def test_low_source_confidence_routes_to_review():
    from src.extractor.gemini_extractor import attach_evidence, document_confidence
    from src.parser.real_document_parser import EvidenceCandidate
    from src.reconciliation.models import DocumentType

    record = extraction(DocumentType.INVOICE)
    record.vendor_name = "Acme Network Systems"
    parsed = ParsedArtifact(
        text="", evidence=[EvidenceCandidate(page=1, text="Acme Network INV-1 Widget Total 10")]
    )
    attach_evidence(record, parsed)
    assert "Low source confidence for vendor_name" in record.review_flags
    assert 0.66 < document_confidence(record) < 0.67


def test_sample_highlights_precomputed_source():
    from demo_app import preview, sources

    choice = next(name for name in sources() if name.startswith("Finding"))
    highlighted = preview(choice)
    plain = preview("Invoice: whole page")
    assert highlighted.size == plain.size
    assert highlighted.tobytes() != plain.tobytes()
    assert "invoice: total_amount" in sources()


def test_groq_response_cache_skips_second_model_call(tmp_path, monkeypatch):
    import httpx

    from config import settings
    from src.extractor.open_vlm import OpenVLMExtractor
    from src.extractor.response_cache import EvaluationBudget
    from src.reconciliation.models import DocumentType

    monkeypatch.setattr(settings, "VLM_API_KEY", "fixture-key")
    monkeypatch.setattr(settings, "VLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setattr(settings, "VLM_MODEL", "qwen/test")
    calls = []
    raw = extraction(DocumentType.INVOICE).model_dump(mode="json")
    raw = {
        key: raw[key]
        for key in (
            "document_number",
            "document_date",
            "vendor_name",
            "buyer_name",
            "currency",
            "line_items",
            "subtotal",
            "tax_amount",
            "total_amount",
        )
    }

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 60

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, **kwargs):
            calls.append(kwargs["json"])
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "model": "qwen/test",
                    "choices": [{"message": {"content": json.dumps(raw)}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.001},
                },
            )

    monkeypatch.setattr(httpx, "Client", Client)
    path = tmp_path / "receipt.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    budget = EvaluationBudget(tmp_path / "budget.json")
    rates = {"context_length": 1000, "pricing": {"prompt": "0.000001", "completion": "0.000002"}}
    extractor = OpenVLMExtractor(cache_dir=tmp_path / "raw", budget=budget, rates=rates)
    parsed = ParsedArtifact(text="Widget 10", page_count=1)
    first = extractor._extract_sync(path, "first", DocumentType.INVOICE, parsed)
    second = extractor._extract_sync(path, "second", DocumentType.INVOICE, parsed)
    assert len(calls) == 1
    assert first.provider_metadata["cache_hit"] == 0 and second.provider_metadata["cache_hit"] == 1

    assert calls[0]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "provider" not in calls[0]
    assert first.provider_metadata["provider"] == "groq"
    assert budget.spent == pytest.approx(0.001)
    assert EvaluationBudget(tmp_path / "budget.json").spent == pytest.approx(0.001)
    with pytest.raises(RuntimeError, match="budget"):
        budget.reserve(3)
    with pytest.raises(RuntimeError, match="budget"):
        budget.reserve(float("nan"))


def test_gemini_text_only_and_raw_cache(tmp_path, monkeypatch):
    import httpx

    from config import settings
    from src.extractor import gemini_api
    from src.extractor.gemini_extractor import GeminiDocumentExtractor, GeminiExtraction
    from src.reconciliation.models import DocumentType

    calls = []
    payload = GeminiExtraction.model_validate(extraction(DocumentType.INVOICE).model_dump()).model_dump_json()

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, **kwargs):
            calls.append(kwargs["json"])
            return httpx.Response(
                200,
                json={
                    "model": settings.DEFAULT_VISION_MODEL,
                    "choices": [{"message": {"content": payload}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 10},
                },
            )

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(settings, "GEMINI_MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(gemini_api, "_next_call", 0)
    extractor = GeminiDocumentExtractor(api_key="test-key", text_only=True, cache_dir=tmp_path)
    path = tmp_path / "missing.png"
    first = extractor._extract_sync(path, "first", DocumentType.INVOICE, ParsedArtifact(text="Widget"))
    second = extractor._extract_sync(path, "second", DocumentType.INVOICE, ParsedArtifact(text="Widget"))
    assert len(calls) == 1
    assert all(part["type"] == "text" for part in calls[0]["messages"][0]["content"])
    assert first.provider_metadata["cache_hit"] == 0 and second.provider_metadata["cache_hit"] == 1
    assert first.provider_metadata["estimated_cost_usd"] == 0


def test_diagnostic_judge_is_blinded_and_does_not_change_scores(monkeypatch):
    import scripts.run_real_eval as evaluation

    calls = []

    def complete(request, *_, **kwargs):
        calls.append((request, kwargs))
        return {
            "choices": [{"message": {"content": '{"category":"uncertain","explanation":"Image needed"}'}}],
            "model": "returned-pro",
            "run_at_utc": "2026-10-06T00:00:00Z",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            "free_tier": True,
        }, False

    monkeypatch.setattr(evaluation, "completion", complete)
    row = {
        "backend": "secret-backend-identity",
        "predictions": {},
        "ocr_text": "receipt",
        "field_errors": [{"field": "total_amount"}],
    }
    before = dict(row)
    result = evaluation.judge_errors(row, {}, None)
    assert row == before and result["status"] == "completed"
    assert "secret-backend-identity" not in str(calls[0][0])
    assert calls[0][0]["temperature"] == 0 and calls[0][1]["free_tier"] is True
    assert result["cost_usd"] == 0.0


def test_comparison_reuses_actual_ocr_and_its_latency(tmp_path, monkeypatch):
    import hashlib

    import scripts.run_real_eval as evaluation

    (tmp_path / "src/parser").mkdir(parents=True)
    (tmp_path / "src/parser/real_document_parser.py").write_text("fixture parser version")
    image = tmp_path / "receipt.png"
    image.write_bytes(b"receipt image fixture")
    expected = {field: [] for field in FIELDS}
    expected.update(
        description=["Widget"],
        quantity=["1"],
        unit_price=["10"],
        line_total=["10"],
        subtotal=["10"],
        total_amount=["10"],
    )
    case = {
        "case_id": "fixture",
        "split": "held_out",
        "image": "receipt.png",
        "expected": expected,
        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
    }
    parse_calls = []

    async def parse(path):
        parse_calls.append(path)
        return ParsedArtifact(text="Actual OCR text", page_count=1)

    class Extractor:
        async def extract(self, path, document_id, kind, parsed):
            assert parsed.text == "Actual OCR text"  # Never the expected labels.
            result = extraction(kind)
            result.provider_metadata = {"provider_latency_seconds": 0.5, "estimated_cost_usd": 0.001}
            return result

    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    monkeypatch.setattr(evaluation, "parse_document", parse)
    first = asyncio.run(evaluation.evaluate(case, "gemini", Extractor()))
    second = asyncio.run(evaluation.evaluate(case, "qwen", Extractor()))
    assert len(parse_calls) == 1
    assert first["correct"] and second["correct"]
    assert first["latency_seconds"] == second["latency_seconds"] >= 0.5
    assert first["cost_usd"] == 0.001


def test_space_upload_allowlist_excludes_secrets_and_provider_code(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import httpx
    import huggingface_hub

    import scripts.deploy_space as deployment

    (tmp_path / "demo").mkdir()
    (tmp_path / "results").mkdir()
    (tmp_path / ".env").write_text("GEMINI_API_KEY=fixture-secret-not-for-upload\n")
    (tmp_path / "demo_app.py").write_text("# sample-only entrypoint")
    (tmp_path / "requirements-demo.txt").write_text("gradio>=5,<7\n")
    (tmp_path / "results/verification.json").write_text('{"sample_findings": 2}')
    for name in ("invoice.pdf", "purchase_order.pdf", "result.json"):
        (tmp_path / "demo" / name).write_bytes(b"sample asset")

    class API:
        def __init__(self, **_):
            pass

        def whoami(self):
            return {"name": "fixture-user"}

        def create_repo(self, *_, **kwargs):
            assert kwargs["space_sdk"] == "gradio"

        def upload_folder(self, **kwargs):
            files = sorted(
                path.relative_to(kwargs["folder_path"]).as_posix()
                for path in kwargs["folder_path"].rglob("*")
                if path.is_file()
            )
            assert files == [
                "README.md",
                "app.py",
                "demo/invoice.pdf",
                "demo/purchase_order.pdf",
                "demo/result.json",
                "requirements.txt",
            ]
            assert all(
                b"fixture-secret" not in path.read_bytes()
                for path in kwargs["folder_path"].rglob("*")
                if path.is_file()
            )
            return SimpleNamespace(oid="fixture-commit")

        def get_space_runtime(self, _):
            return SimpleNamespace(stage="RUNNING", raw={"domains": [{"domain": "fixture.example"}]})

    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setattr(huggingface_hub, "HfApi", API)
    monkeypatch.setenv("HF_TOKEN", "fixture-token")
    monkeypatch.setattr(
        httpx, "get", lambda *_, **__: httpx.Response(200, json={"title": "ReconcileAI sample review"})
    )
    deployment.main("fixture-space")
    report = json.loads((tmp_path / "results/deployment.json").read_text())
    assert report["public_ready"] and report["mode"] == "sample_only"


def test_vlm_settings_and_catalogue_without_architecture(tmp_path, monkeypatch):
    import httpx

    import scripts.run_real_eval as evaluation
    from config import AppSettings

    for name in ("VLM_API_KEY", "VLM_INPUT_USD_PER_M_TOKEN", "VLM_OUTPUT_USD_PER_M_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "VLM_API_KEY=fixture-key\nVLM_INPUT_USD_PER_M_TOKEN=0.80\nVLM_OUTPUT_USD_PER_M_TOKEN=4.00\n"
    )
    config = AppSettings(_env_file=env)
    assert config.VLM_API_KEY == "fixture-key"
    assert config.VLM_INPUT_USD_PER_M_TOKEN == 0.80 and config.VLM_OUTPUT_USD_PER_M_TOKEN == 4.00
    monkeypatch.setattr(evaluation, "settings", config)
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    (tmp_path / "results").mkdir()

    def get(url, **kwargs):
        assert url == "https://api.groq.com/openai/v1/models"
        assert kwargs["headers"]["Authorization"] == "Bearer fixture-key"
        return httpx.Response(200, json={"data": [{"id": config.VLM_MODEL, "context_window": 131072}]})

    monkeypatch.setattr(httpx, "get", get)
    record = evaluation.provider_catalog()
    assert record["provider"] == "groq" and record["id"] == config.VLM_MODEL
    assert record["input_modalities"] is None and record["context_length"] == 131072
    assert float(record["pricing"]["prompt"]) == pytest.approx(0.80 / 1_000_000)


def test_vlm_pdf_limit_preserves_all_accepted_pages(tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    from src.extractor.gemini_extractor import image_content

    for pages in (3, 4):
        path = tmp_path / f"{pages}-pages.pdf"
        canvas = Canvas(str(path))
        for page in range(pages):
            canvas.drawString(40, 700, f"Receipt page {page + 1}")
            canvas.showPage()
        canvas.save()
        if pages == 3:
            images = image_content(path, max_pages=3)
            assert len(images) == 3
            assert all(image["image_url"]["url"].startswith("data:image/png;base64,") for image in images)
        else:
            with pytest.raises(ValueError, match="split this document"):
                image_content(path, max_pages=3)


def test_offline_rescore_accepts_git_line_endings_without_api(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace

    import scripts.run_real_eval as evaluation

    output = tmp_path / "results"
    output.mkdir()
    manifest = b'{\n  "cases": []\n}\n'
    (output / "cord_manifest.json").write_bytes(manifest)
    report = {
        "dataset_sha256": hashlib.sha256(manifest.replace(b"\n", b"\r\n")).hexdigest(),
        "rows": [],
        "backends": {},
    }
    (output / "smoke_comparison.json").write_text(json.dumps(report))
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    monkeypatch.setattr(
        evaluation, "provider_catalog", lambda: pytest.fail("Offline rescore called provider")
    )
    captured = []
    monkeypatch.setattr(evaluation, "write_artifacts", lambda r, _: captured.append(r))
    asyncio.run(evaluation.main(SimpleNamespace(rescore="smoke_comparison.json", target_review_rate=0.2)))
    assert captured[0]["dataset_sha256"] == hashlib.sha256(manifest).hexdigest()
    assert captured[0]["original_dataset_sha256"] == report["dataset_sha256"]


def test_offline_label_migration_only_allows_verified_list_flattening(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace

    import scripts.run_real_eval as evaluation

    output = tmp_path / "results"
    output.mkdir()
    old = {"cases": [{"case_id": "receipt", "image": "same.png", "expected": {"subtotal": [["10", "10"]]}}]}
    previous = json.dumps(old).encode()
    (output / "previous.json").write_bytes(previous)
    old["cases"][0]["expected"]["subtotal"] = ["10", "10"]
    (output / "cord_manifest.json").write_text(json.dumps(old))
    report = {"dataset_sha256": hashlib.sha256(previous).hexdigest(), "rows": [], "backends": {}}
    (output / "smoke_comparison.json").write_text(json.dumps(report))
    monkeypatch.setattr(evaluation, "ROOT", tmp_path)
    captured = []
    monkeypatch.setattr(evaluation, "write_artifacts", lambda r, _: captured.append(r))
    args = SimpleNamespace(
        rescore="smoke_comparison.json", target_review_rate=0.2, previous_manifest="previous.json"
    )
    asyncio.run(evaluation.main(args))
    assert captured[0]["label_preparation_correction"]["changed_cases"] == ["receipt"]
    old["cases"][0]["image"] = "different.png"
    (output / "cord_manifest.json").write_text(json.dumps(old))
    with pytest.raises(SystemExit, match="Only verified"):
        asyncio.run(evaluation.main(args))
