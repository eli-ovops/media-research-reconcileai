import pytest

from config import settings
from src.extractor.gemini_extractor import GeminiDocumentExtractor, attach_evidence
from src.parser.real_document_parser import EvidenceCandidate, ParsedArtifact
from src.reconciliation.models import DocumentExtraction, DocumentType, ExtractedLineItem


def test_evidence_is_resolved_from_parser_coordinates():
    parsed = ParsedArtifact(
        text="Invoice INV-22 from Acme. Widget A 2 50 100. Total 100.",
        page_count=1,
        evidence=[
            EvidenceCandidate(page=1, text="Invoice INV-22 from Acme", bbox=(0.1, 0.1, 0.8, 0.2)),
            EvidenceCandidate(page=1, text="Widget A 2 50 100", bbox=(0.1, 0.3, 0.8, 0.4)),
            EvidenceCandidate(page=1, text="Total 100", bbox=(0.6, 0.8, 0.9, 0.9)),
        ],
    )
    extraction = DocumentExtraction(
        document_id="doc-1",
        document_type=DocumentType.INVOICE,
        document_number="INV-22",
        vendor_name="Acme",
        currency="USD",
        line_items=[ExtractedLineItem(description="Widget A", quantity=2, unit_price=50, total_price=100)],
        subtotal=100,
        total_amount=100,
    )

    grounded = attach_evidence(extraction, parsed)
    assert grounded.field_evidence["document_number"].bbox == (0.1, 0.1, 0.8, 0.2)
    assert grounded.line_items[0].evidence.page == 1
    assert not grounded.review_flags


def test_gemini_request_timeout_is_bounded_and_propagated(tmp_path, monkeypatch):
    import httpx

    from src.extractor import gemini_api

    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, *_, **__):
            raise httpx.TimeoutException("provider request timed out")

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(gemini_api, "_next_call", 0)
    path = tmp_path / "invoice.png"
    path.write_bytes(b"image")
    with pytest.raises(httpx.TimeoutException, match="provider request timed out"):
        GeminiDocumentExtractor(api_key="test-key")._extract_sync(
            path,
            "invoice-1",
            DocumentType.INVOICE,
            ParsedArtifact(text="", page_count=1, evidence=[]),
        )
    assert captured["timeout"] == settings.GEMINI_TIMEOUT_MS / 1000


def test_gemini_429_backoff_and_cache(tmp_path, monkeypatch):
    import httpx

    from src.extractor import gemini_api

    calls, sleeps = [], []

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, *_, **kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                return httpx.Response(429)
            return httpx.Response(200, json={"model": "exact-returned-id", "choices": [], "usage": {}})

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(gemini_api.time, "sleep", sleeps.append)
    monkeypatch.setattr(gemini_api, "_next_call", 0)
    monkeypatch.setattr(settings, "GEMINI_MIN_INTERVAL_SECONDS", 0)
    request = {"model": "agent-id", "temperature": 0}
    first, hit = gemini_api.completion(request, "fake-secret", tmp_path)
    second, hit2 = gemini_api.completion(request, "fake-secret", tmp_path)
    assert not hit and hit2 and len(calls) == 3 and 2 in sleeps and 4 in sleeps
    assert first == second and first["requested_model"] == "agent-id"
    assert first["model"] == "exact-returned-id" and first["run_at_utc"]
    assert "fake-secret" not in next(tmp_path.glob("*.json")).read_text()


def test_daily_quota_array_response_blocks_new_requests(tmp_path, monkeypatch):
    import httpx

    from src.extractor import gemini_api

    calls = []

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, *_, **__):
            calls.append(1)
            return httpx.Response(
                429,
                json=[
                    {
                        "error": {
                            "status": "RESOURCE_EXHAUSTED",
                            "details": [
                                {
                                    "violations": [
                                        {"quotaId": "GenerateRequestsPerDay-FreeTier", "quotaValue": "20"}
                                    ]
                                },
                                {"retryDelay": "60000s"},
                            ],
                        }
                    }
                ],
            )

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(gemini_api, "_next_call", 0)
    monkeypatch.setattr(gemini_api.time, "sleep", lambda _: None)
    directory = tmp_path / "responses"
    request = {"model": "daily-quota-fixture", "temperature": 0}
    with pytest.raises(RuntimeError, match="daily quota exhausted"):
        gemini_api.completion(request, "fixture-key", directory)
    with pytest.raises(RuntimeError, match="daily quota exhausted"):
        gemini_api.completion({**request, "messages": []}, "fixture-key", directory)
    assert len(calls) == 1
    assert gemini_api.quota_status(request["model"], directory, "fixture-key", settings.GEMINI_FREE_TIER)


def test_paid_equivalent_guard_also_applies_to_free_keys(tmp_path, monkeypatch):
    import httpx

    from src.extractor import gemini_api
    from src.extractor.response_cache import EvaluationBudget

    calls = []

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, *_, **__):
            calls.append(1)
            return httpx.Response(
                200, json={"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 10}}
            )

    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(gemini_api, "_next_call", 0)
    monkeypatch.setattr(gemini_api.time, "sleep", lambda _: None)
    request = {
        "model": "gemini-3.1-flash-lite",
        "temperature": 0,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": [{"type": "image_url"}]}],
    }
    budget = EvaluationBudget(tmp_path / "budget.json", ceiling=0.1)
    with pytest.raises(RuntimeError, match="budget reached"):
        gemini_api.completion(request, "fixture-key", budget=budget, free_tier=True)
    assert not calls
    budget.ceiling = 2.99
    payload, _ = gemini_api.completion(request, "fixture-key", budget=budget, free_tier=True)
    assert len(calls) == 1
    assert budget.spent == pytest.approx((100 * 0.25 + 10 * 1.5) / 1_000_000)
    assert payload["paid_equivalent_usd"] == pytest.approx(budget.spent)


def test_attempt_summary_counts_failures_and_backoff(tmp_path):
    import json

    from scripts.summarize_api_usage import summarize

    trace = tmp_path / "trace.attempts.json"
    trace.write_text(
        json.dumps(
            {
                "model": "fixture",
                "attempts": [
                    {"http_status": 503, "backoff_seconds": 2},
                    {"http_status": 429, "backoff_seconds": 4},
                    {"http_status": 200, "backoff_seconds": 0},
                ],
            }
        )
    )
    result = summarize([trace])["fixture"]
    assert result["requests"] == 1 and result["http_attempts"] == 3
    assert result["statuses"] == {"503": 1, "429": 1, "200": 1}
    assert result["backoff_seconds"] == 6


def test_missing_headers_force_review_and_schema_failure_keeps_costs():
    import json

    from pydantic import ValidationError

    from src.extractor.gemini_extractor import validated_extraction

    payload = {
        "document_number": None,
        "document_date": None,
        "vendor_name": None,
        "buyer_name": None,
        "currency": "USD",
        "line_items": [],
        "subtotal": None,
        "tax_amount": None,
        "total_amount": 10,
    }
    metadata = {"estimated_cost_usd": 0.01}
    parsed = ParsedArtifact(text="Total 10", evidence=[EvidenceCandidate(page=1, text="Total 10")])
    result = validated_extraction(json.dumps(payload), "fixture", DocumentType.INVOICE, parsed, metadata)
    assert result.document_number == "" and result.vendor_name == ""
    assert "No source evidence was resolved for document_number" in result.review_flags
    assert "No source evidence was resolved for vendor_name" in result.review_flags
    payload["total_amount"] = None
    with pytest.raises(ValidationError) as caught:
        validated_extraction(json.dumps(payload), "fixture", DocumentType.INVOICE, parsed, metadata)
    assert caught.value.provider_metadata == metadata
