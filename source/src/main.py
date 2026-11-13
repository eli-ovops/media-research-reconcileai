from __future__ import annotations

import asyncio
import io
import json
import shutil
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from config import settings
from src.extractor.gemini_extractor import GeminiDocumentExtractor
from src.parser.real_document_parser import parse_document
from src.reconciliation.engine import reconcile_documents
from src.reconciliation.models import DocumentExtraction, DocumentType
from src.storage import JobStore

settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = settings.DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
store = JobStore(settings.DATABASE_PATH)
ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "demo"


@asynccontextmanager
async def lifespan(_: FastAPI):
    resumed_tasks = [asyncio.create_task(_run_jobs([job["job_id"] for job in store.incomplete_jobs()]))]
    yield
    for task in resumed_tasks:
        if not task.done():
            task.cancel()
    if resumed_tasks:
        await asyncio.gather(*resumed_tasks, return_exceptions=True)


app = FastAPI(
    title="ReconcileAI",
    version=settings.VERSION,
    description="Evidence-backed invoice and purchase-order reconciliation.",
    lifespan=lifespan,
)


class ReviewRequest(BaseModel):
    invoice: DocumentExtraction | None = None
    purchase_order: DocumentExtraction | None = None
    note: str = "Reviewer corrected extracted values"


async def _validate_upload(file: UploadFile) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, "Only PDF, PNG, and JPEG documents are supported")
    header = await file.read(8)
    await file.seek(0)
    if not (
        (suffix == ".pdf" and header.startswith(b"%PDF-"))
        or (suffix == ".png" and header == b"\x89PNG\r\n\x1a\n")
        or (suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
    ):
        raise HTTPException(415, "File contents do not match a supported document type")
    return suffix


async def _save_upload(file: UploadFile, target: Path) -> None:
    total = 0
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    with target.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                output.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"Each document must be at most {settings.MAX_UPLOAD_SIZE_MB} MB")
            output.write(chunk)


async def _process_job(job_id: str) -> None:
    job = store.get(job_id)
    if job is None:
        return
    store.update(job_id, status="processing", error=None)
    try:
        if store.estimated_spend_usd() >= settings.MAX_ESTIMATED_COST_USD:
            raise RuntimeError(
                f"Development spend guard reached ${settings.MAX_ESTIMATED_COST_USD:.2f}; "
                "raise MAX_ESTIMATED_COST_USD deliberately to continue"
            )
        invoice_path = Path(job["invoice_path"])
        if not job["purchase_order_path"]:
            parsed = await parse_document(invoice_path)
            if parsed.page_count > settings.MAX_PAGES:
                raise ValueError(f"Documents may contain at most {settings.MAX_PAGES} pages")
            extracted = await GeminiDocumentExtractor().extract(
                invoice_path, job_id, DocumentType.INVOICE, parsed
            )
            store.update(job_id, status="completed", result={"extraction": extracted.model_dump(mode="json")})
            return
        po_path = Path(job["purchase_order_path"])
        invoice_parsed, po_parsed = await asyncio.gather(
            parse_document(invoice_path), parse_document(po_path)
        )
        if invoice_parsed.page_count > settings.MAX_PAGES or po_parsed.page_count > settings.MAX_PAGES:
            raise ValueError(f"Documents may contain at most {settings.MAX_PAGES} pages")
        extractor = GeminiDocumentExtractor()
        invoice, purchase_order = await asyncio.gather(
            extractor.extract(invoice_path, f"{job_id}_invoice", DocumentType.INVOICE, invoice_parsed),
            extractor.extract(po_path, f"{job_id}_po", DocumentType.PURCHASE_ORDER, po_parsed),
        )
        result = reconcile_documents(invoice, purchase_order)
        store.update(job_id, status="completed", result=result.model_dump(mode="json"))
    except Exception as exc:
        store.update(job_id, status="failed", error=str(exc))


async def _run_jobs(job_ids: list[str]) -> None:
    # ponytail: workers are bounded per batch/process; use a durable queue for distributed throughput.
    pending = iter(job_ids)

    async def worker():
        for job_id in pending:
            await _process_job(job_id)

    await asyncio.gather(*(worker() for _ in range(min(settings.BATCH_WORKERS, len(job_ids)))))


@app.post("/api/v1/batches", status_code=202, tags=["Batch extraction"])
async def create_batch(background_tasks: BackgroundTasks, documents: list[UploadFile] = File(...)) -> dict:
    if not 1 <= len(documents) <= settings.MAX_BATCH_DOCUMENTS:
        raise HTTPException(422, f"Upload between 1 and {settings.MAX_BATCH_DOCUMENTS} documents")
    suffixes = [await _validate_upload(document) for document in documents]
    batch_id = f"batch_{uuid4().hex[:12]}"
    directory = UPLOAD_DIR / batch_id
    directory.mkdir(parents=True)
    jobs = []
    try:
        for document, suffix in zip(documents, suffixes):
            job_id = f"job_{uuid4().hex[:12]}"
            path = directory / f"{job_id}{suffix}"
            await _save_upload(document, path)
            jobs.append((job_id, str(path)))
        store.create_batch(batch_id, jobs)
    except Exception:
        shutil.rmtree(directory)
        raise
    background_tasks.add_task(_run_jobs, [job_id for job_id, _ in jobs])
    return {"job_id": batch_id, "batch_id": batch_id, "status": "queued", "total": len(jobs),
            "events_url": f"/api/v1/batches/{batch_id}/events"}


@app.get("/api/v1/batches/{batch_id}", tags=["Batch extraction"])
async def get_batch(batch_id: str) -> dict:
    batch = store.batch(batch_id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    return batch


@app.get("/api/v1/batches/{batch_id}/events", tags=["Batch extraction"])
async def batch_events(batch_id: str, request: Request) -> StreamingResponse:
    if store.batch(batch_id) is None:
        raise HTTPException(404, "Batch not found")

    async def events():
        sequence = 0
        while not await request.is_disconnected():
            batch = store.batch(batch_id)
            summary = {key: value for key, value in batch.items() if key != "jobs"}
            event = "done" if batch["done"] else "progress"
            yield f"id: {sequence}\nevent: {event}\ndata: {json.dumps(summary)}\n\n"
            if batch["done"]:
                return
            sequence += 1
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui() -> HTMLResponse:
    ui_path = Path(__file__).resolve().parent.parent / "ui" / "index.html"
    return HTMLResponse(ui_path.read_text(encoding="utf-8"))


@app.post("/api/v1/jobs", status_code=202, tags=["Reconciliation"])
async def create_job(
    background_tasks: BackgroundTasks,
    invoice: UploadFile = File(...),
    purchase_order: UploadFile = File(...),
) -> dict:
    invoice_suffix = await _validate_upload(invoice)
    po_suffix = await _validate_upload(purchase_order)
    job_id = f"job_{uuid4().hex[:12]}"
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True)
    invoice_path = job_dir / f"invoice{invoice_suffix}"
    po_path = job_dir / f"purchase_order{po_suffix}"
    try:
        await _save_upload(invoice, invoice_path)
        await _save_upload(purchase_order, po_path)
    except Exception:
        shutil.rmtree(job_dir)
        raise
    store.create(job_id, str(invoice_path), str(po_path))
    background_tasks.add_task(_process_job, job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/v1/jobs", tags=["Reconciliation"])
async def list_jobs() -> list[dict]:
    return store.list_recent()


@app.post("/api/v1/sample", status_code=201, tags=["Reconciliation"])
async def create_sample() -> dict:
    """Open a prerecorded fictional case without parsing or a model call."""
    job_id = f"sample_{uuid4().hex[:12]}"
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True)
    invoice_path = job_dir / "invoice.pdf"
    po_path = job_dir / "purchase_order.pdf"
    shutil.copyfile(SAMPLE_DIR / "invoice.pdf", invoice_path)
    shutil.copyfile(SAMPLE_DIR / "purchase_order.pdf", po_path)
    store.create(job_id, str(invoice_path), str(po_path))
    result = json.loads((SAMPLE_DIR / "result.json").read_text(encoding="utf-8"))
    store.update(job_id, status="completed", result=result)
    return {"job_id": job_id, "status": "completed", "mode": "prerecorded_sample"}


@app.get("/api/v1/jobs/{job_id}", tags=["Reconciliation"])
async def get_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    job.pop("invoice_path", None)
    job.pop("purchase_order_path", None)
    return job


@app.get("/api/v1/jobs/{job_id}/documents/{kind}", include_in_schema=False)
async def get_document(job_id: str, kind: str) -> FileResponse:
    job = store.get(job_id)
    if job is None or kind not in {"invoice", "purchase_order"}:
        raise HTTPException(404, "Document not found")
    key = "invoice_path" if kind == "invoice" else "purchase_order_path"
    if not job[key]:
        raise HTTPException(404, "Document not found")
    return FileResponse(job[key], filename=Path(job[key]).name)


@app.get("/api/v1/jobs/{job_id}/documents/{kind}/preview", include_in_schema=False)
async def get_document_preview(
    job_id: str,
    kind: str,
    page: int = Query(default=1, ge=1),
    bbox: str | None = None,
) -> Response:
    job = store.get(job_id)
    if job is None or kind not in {"invoice", "purchase_order"}:
        raise HTTPException(404, "Document not found")
    key = "invoice_path" if kind == "invoice" else "purchase_order_path"
    if not job[key]:
        raise HTTPException(404, "Document not found")
    path = Path(job[key])
    from PIL import Image, ImageDraw

    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(path)
        if page > len(pdf):
            pdf.close()
            raise HTTPException(404, "Page not found")
        pdf_page = pdf[page - 1]
        image = pdf_page.render(scale=1.6).to_pil().convert("RGB")
        pdf_page.close()
        pdf.close()
    else:
        if page != 1:
            raise HTTPException(404, "Page not found")
        image = Image.open(path).convert("RGB")
    if bbox:
        try:
            x0, y0, x1, y1 = [float(value) for value in bbox.split(",")]
            if not all(0 <= value <= 1 for value in (x0, y0, x1, y1)) or x0 > x1 or y0 > y1:
                raise ValueError("Invalid normalized region")
            draw = ImageDraw.Draw(image, "RGBA")
            rect = (x0 * image.width - 5, y0 * image.height - 5, x1 * image.width + 5, y1 * image.height + 5)
            draw.rectangle(rect, fill=(255, 194, 71, 55), outline=(183, 99, 10, 255), width=2)
        except (ValueError, TypeError):
            raise HTTPException(422, "bbox must contain four comma-separated normalized coordinates")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(buffer.getvalue(), media_type="image/png")


@app.put("/api/v1/jobs/{job_id}/review", tags=["Human review"])
async def review_job(job_id: str, review: ReviewRequest) -> dict:
    job = store.get(job_id)
    if job is None or not job["result"] or "invoice" not in job["result"]:
        raise HTTPException(409, "A completed extraction is required before review")
    current = job["result"]
    invoice = review.invoice or DocumentExtraction.model_validate(current["invoice"])
    purchase_order = review.purchase_order or DocumentExtraction.model_validate(current["purchase_order"])
    if invoice.document_type != DocumentType.INVOICE:
        raise HTTPException(422, "invoice must retain document_type=invoice")
    if purchase_order.document_type != DocumentType.PURCHASE_ORDER:
        raise HTTPException(422, "purchase_order must retain document_type=purchase_order")
    result = reconcile_documents(invoice, purchase_order)
    edits = current.get("reviewer_edits", [])
    edits.append({
        "note": review.note,
        "sequence": len(edits) + 1,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "before": {
            "invoice": current["invoice"],
            "purchase_order": current["purchase_order"],
        },
        "after": {
            "invoice": invoice.model_dump(mode="json"),
            "purchase_order": purchase_order.model_dump(mode="json"),
        },
    })
    result.reviewer_edits = edits
    payload = result.model_dump(mode="json")
    store.update(job_id, status="completed", result=payload)
    return payload


@app.get("/api/v1/jobs/{job_id}/export", tags=["Reconciliation"])
async def export_job(job_id: str) -> JSONResponse:
    job = store.get(job_id)
    if job is None or not job["result"]:
        raise HTTPException(404, "Completed result not found")
    return JSONResponse(
        job["result"],
        headers={"Content-Disposition": f'attachment; filename="{job_id}-reconciliation.json"'},
    )


@app.get("/health", tags=["Operations"])
async def health_check() -> dict:
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "model": settings.DEFAULT_VISION_MODEL,
        "gemini_configured": bool(settings.GEMINI_API_KEY),
        "estimated_spend_usd": store.estimated_spend_usd(),
        "spend_guard_usd": settings.MAX_ESTIMATED_COST_USD,
    }
