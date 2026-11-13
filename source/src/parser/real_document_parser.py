from __future__ import annotations

import asyncio
import re
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel, Field

_converter = None
_converter_lock = threading.Lock()


class EvidenceCandidate(BaseModel):
    page: int
    text: str
    bbox: tuple[float, float, float, float] | None = None


class ParsedArtifact(BaseModel):
    text: str
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    page_count: int = 0


def _normalize_bbox(prov: object, page_size: object | None) -> tuple[float, float, float, float] | None:
    bbox = getattr(prov, "bbox", None)
    if bbox is None:
        return None
    values = [getattr(bbox, name, None) for name in ("l", "t", "r", "b")]
    if any(value is None for value in values):
        return None
    width = float(getattr(page_size, "width", 1) or 1)
    height = float(getattr(page_size, "height", 1) or 1)
    left, top, right, bottom = (float(value) for value in values)
    origin = str(getattr(bbox, "coord_origin", "")).upper()
    if "BOTTOMLEFT" in origin:
        top, bottom = height - top, height - bottom
    normalized = (left / width, top / height, right / width, bottom / height)
    return tuple(round(max(0.0, min(1.0, value)), 6) for value in normalized)


def _parse_sync(path: Path) -> ParsedArtifact:
    global _converter
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise RuntimeError("Docling is required for document parsing; install project dependencies") from exc

    # Docling's model pipeline is expensive and is not documented as thread-safe.
    # ponytail: one parser lock bounds laptop memory; use process workers when parsing throughput matters.
    with _converter_lock:
        if _converter is None:
            _converter = DocumentConverter()
        result = _converter.convert(path)
    document = result.document
    text = document.export_to_markdown()
    evidence: list[EvidenceCandidate] = []
    pages = getattr(document, "pages", {})
    items = list(getattr(document, "texts", [])) + list(getattr(document, "tables", []))
    for item in items:
        item_text = getattr(item, "text", None)
        if not item_text and hasattr(item, "export_to_markdown"):
            item_text = item.export_to_markdown(doc=document)
        if not item_text:
            continue
        provenance = list(getattr(item, "prov", []) or [])
        if provenance:
            for prov in provenance:
                evidence.append(EvidenceCandidate(
                    page=int(getattr(prov, "page_no", 1)),
                    text=str(item_text),
                    bbox=_normalize_bbox(
                        prov,
                        getattr(pages.get(int(getattr(prov, "page_no", 1))), "size", None),
                    ),
                ))
        else:
            evidence.append(EvidenceCandidate(page=1, text=str(item_text)))
    return ParsedArtifact(text=text, evidence=evidence, page_count=len(pages) or 1)


async def parse_document(path: Path) -> ParsedArtifact:
    return await asyncio.to_thread(_parse_sync, path)


def evidence_score(value: str, candidate: str) -> float:
    raw_value = str(value).strip()
    try:
        numeric = Decimal(raw_value.replace(",", ""))
        if numeric == numeric.to_integral():
            raw_value = str(numeric.quantize(Decimal("1")))
    except InvalidOperation:
        pass
    clean_value = " ".join(re.findall(r"[a-z0-9]+", raw_value.lower()))
    clean_candidate = " ".join(re.findall(r"[a-z0-9]+", candidate.lower()))
    if not clean_value:
        return 0.0
    if clean_value in clean_candidate:
        return 1.0
    wanted = set(clean_value.split())
    actual = set(clean_candidate.split())
    return len(wanted & actual) / len(wanted)
