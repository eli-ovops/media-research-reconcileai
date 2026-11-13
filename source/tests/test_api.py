import asyncio
import threading
from io import BytesIO

from fastapi.testclient import TestClient

import src.main as main
from src.parser.real_document_parser import ParsedArtifact
from src.reconciliation.engine import reconcile_documents
from src.reconciliation.models import DocumentExtraction, DocumentType, ExtractedLineItem
from src.storage import JobStore


def extraction(kind: DocumentType) -> DocumentExtraction:
    return DocumentExtraction(
        document_id=kind.value,
        document_type=kind,
        document_number="INV-1" if kind == DocumentType.INVOICE else "PO-1",
        vendor_name="Acme",
        currency="USD",
        line_items=[ExtractedLineItem(
            sku="A-1",
            description="Widget",
            quantity=1,
            unit_price=10,
            total_price=10,
        )],
        subtotal=10,
        total_amount=10,
    )


def test_health_and_ui(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", JobStore(tmp_path / "api.db"))
    client = TestClient(main.app)

    assert client.get("/health").json()["service"] == "ReconcileAI"
    assert "Find the mismatch" in client.get("/").text


def test_upload_rejects_unsupported_files(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", JobStore(tmp_path / "api.db"))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    client = TestClient(main.app)
    response = client.post(
        "/api/v1/jobs",
        files={
            "invoice": ("invoice.txt", BytesIO(b"invoice"), "text/plain"),
            "purchase_order": ("po.pdf", BytesIO(b"pdf"), "application/pdf"),
        },
    )
    assert response.status_code == 415


def test_upload_rejects_malformed_document(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", JobStore(tmp_path / "api.db"))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    response = TestClient(main.app).post(
        "/api/v1/jobs",
        files={
            "invoice": ("invoice.pdf", BytesIO(b"not a PDF"), "application/pdf"),
            "purchase_order": ("po.pdf", BytesIO(b"%PDF-1.7"), "application/pdf"),
        },
    )
    assert response.status_code == 415
    assert not (tmp_path / "uploads").exists()


def test_oversized_second_upload_removes_first_document(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", JobStore(tmp_path / "api.db"))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main.settings, "MAX_UPLOAD_SIZE_MB", 0.00001)
    response = TestClient(main.app).post(
        "/api/v1/jobs",
        files={
            "invoice": ("invoice.pdf", BytesIO(b"%PDF-1.7"), "application/pdf"),
            "purchase_order": ("po.pdf", BytesIO(b"%PDF-1.7 too large"), "application/pdf"),
        },
    )
    assert response.status_code == 413
    assert not list((tmp_path / "uploads").iterdir())


def test_prerecorded_sample_opens_without_model_and_can_export(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", JobStore(tmp_path / "api.db"))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    client = TestClient(main.app)
    response = client.post("/api/v1/sample")

    assert response.status_code == 201
    assert response.json()["mode"] == "prerecorded_sample"
    job_id = response.json()["job_id"]
    result = client.get(f"/api/v1/jobs/{job_id}").json()["result"]
    assert {item["type"] for item in result["discrepancies"]} == {
        "unit_price_mismatch", "line_total_mismatch",
    }
    assert client.get(f"/api/v1/jobs/{job_id}/documents/invoice/preview").status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}/export").status_code == 200


def test_review_reruns_controls_and_records_audit(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "api.db")
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)
    initial = reconcile_documents(
        extraction(DocumentType.INVOICE),
        extraction(DocumentType.PURCHASE_ORDER),
    )
    store.create("job-review", "invoice.pdf", "po.pdf")
    store.update("job-review", status="completed", result=initial.model_dump(mode="json"))

    invoice = initial.invoice.model_dump(mode="json")
    invoice["line_items"][0]["unit_price"] = 12
    invoice["line_items"][0]["total_price"] = 12
    invoice["subtotal"] = 12
    invoice["total_amount"] = 12
    response = client.put(
        "/api/v1/jobs/job-review/review",
        json={"invoice": invoice, "note": "Corrected invoice row"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["discrepancy_count"] == 2
    audit = payload["reviewer_edits"][0]
    assert audit["note"] == "Corrected invoice row"
    assert audit["sequence"] == 1
    assert audit["before"]["invoice"]["line_items"][0]["unit_price"] == 10
    assert audit["after"]["invoice"]["line_items"][0]["unit_price"] == 12


def test_lifespan_resumes_incomplete_job(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "api.db")
    store.create("job-restart", "invoice.pdf", "po.pdf")
    store.update("job-restart", status="processing")
    resumed = threading.Event()

    async def process(job_id):
        store.update(job_id, status="completed")
        resumed.set()

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "_process_job", process)

    with TestClient(main.app):
        assert resumed.wait(timeout=2)

    assert store.get("job-restart")["status"] == "completed"


def test_provider_timeout_is_persisted_as_job_failure(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "api.db")
    store.create("job-timeout", "invoice.pdf", "po.pdf")

    async def parse(_):
        return ParsedArtifact(text="", page_count=1, evidence=[])

    class TimeoutExtractor:
        async def extract(self, *_):
            raise TimeoutError("provider request timed out")

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "parse_document", parse)
    monkeypatch.setattr(main, "GeminiDocumentExtractor", TimeoutExtractor)

    asyncio.run(main._process_job("job-timeout"))

    job = store.get("job-timeout")
    assert job["status"] == "failed"
    assert "provider request timed out" in job["error"]
