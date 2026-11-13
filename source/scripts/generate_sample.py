"""Regenerate the fictional, prerecorded sample shown in the workbench."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_benchmark import draw_document  # noqa: E402
from src.reconciliation.engine import reconcile_documents  # noqa: E402
from src.reconciliation.models import (  # noqa: E402
    DocumentExtraction,
    DocumentType,
    EvidenceReference,
    ExtractedLineItem,
)

OUTPUT = ROOT / "demo"


def document(kind: DocumentType, price: float) -> DocumentExtraction:
    name = "invoice" if kind == DocumentType.INVOICE else "purchase_order"
    evidence = EvidenceReference(
        document_id=f"sample_{name}",
        page=1,
        text=f"SKU-42 Network appliance 10 {price:.2f} {price * 10:.2f}",
        bbox=(0.08, 0.21, 0.91, 0.24),
        confidence=1,
    )
    return DocumentExtraction(
        document_id=f"sample_{name}",
        document_type=kind,
        document_number="INV-SAMPLE" if kind == DocumentType.INVOICE else "PO-SAMPLE",
        vendor_name="Kaveri Network Systems",
        buyer_name="Meridian Operations Pvt Ltd",
        currency="INR",
        line_items=[
            ExtractedLineItem(
                sku="SKU-42",
                description="Network appliance",
                quantity=10,
                unit_price=price,
                total_price=price * 10,
                evidence=evidence,
            )
        ],
        subtotal=price * 10,
        total_amount=price * 10,
    )


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    invoice = document(DocumentType.INVOICE, 550)
    po = document(DocumentType.PURCHASE_ORDER, 500)
    for record in (invoice, po):
        name = record.document_type.value
        draw_document(
            OUTPUT / f"{name}.pdf",
            name.replace("_", " ").upper(),
            record.document_number,
            [
                {
                    "sku": item.sku,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                }
                for item in record.line_items
            ],
            layout=3,
        )
        # Use the generated PDF's actual text geometry, not model-proposed boxes.
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(OUTPUT / f"{name}.pdf")
        page = pdf[0]
        textpage = page.get_textpage()
        width, height = page.get_size()
        for field, label in {
            "document_number": record.document_number,
            "vendor_name": f"Vendor: {record.vendor_name}",
            "buyer_name": f"Buyer: {record.buyer_name}",
            "currency": f"Currency: {record.currency}",
            "subtotal": f"Subtotal: {record.subtotal:.2f}",
            "total_amount": f"Total: {record.total_amount:.2f}",
        }.items():
            search = textpage.search(label, match_case=True)
            match = search.get_next()
            assert match, f"Sample field missing from PDF: {field}"
            count = textpage.count_rects(*match)
            rectangles = [textpage.get_rect(index) for index in range(count)]
            left, bottom, right, top = (
                min(r[0] for r in rectangles),
                min(r[1] for r in rectangles),
                max(r[2] for r in rectangles),
                max(r[3] for r in rectangles),
            )
            record.field_evidence[field] = EvidenceReference(
                document_id=record.document_id,
                page=1,
                text=label,
                bbox=(left / width, 1 - top / height, right / width, 1 - bottom / height),
                confidence=1,
            )
            search.close()
        textpage.close()
        page.close()
        pdf.close()
    result = reconcile_documents(invoice, po).model_dump(mode="json")
    for index, discrepancy in enumerate(result["discrepancies"], start=1):
        discrepancy["discrepancy_id"] = f"sample_{index}"
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
