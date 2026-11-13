from src.extractor.gemini_extractor import attach_evidence
from src.parser.real_document_parser import ParsedArtifact
from src.reconciliation.engine import reconcile_documents
from src.reconciliation.models import (
    DiscrepancyType,
    DocumentExtraction,
    DocumentType,
    EvidenceReference,
    ExtractedLineItem,
)


def document(kind: DocumentType, *, quantity: float = 10, price: float = 500) -> DocumentExtraction:
    evidence = EvidenceReference(
        document_id=kind.value,
        page=1,
        text=f"SKU-42 Network appliance {quantity} {price}",
        bbox=(0.1, 0.2, 0.9, 0.3),
        confidence=1,
    )
    return DocumentExtraction(
        document_id=kind.value,
        document_type=kind,
        document_number="INV-1" if kind == DocumentType.INVOICE else "PO-1",
        vendor_name="Example Systems",
        buyer_name="Example Buyer",
        currency="INR",
        line_items=[ExtractedLineItem(
            sku="SKU-42",
            description="Network appliance",
            quantity=quantity,
            unit_price=price,
            total_price=quantity * price,
            evidence=evidence,
        )],
        subtotal=quantity * price,
        total_amount=quantity * price,
    )


def test_matching_documents_have_no_discrepancies():
    result = reconcile_documents(
        document(DocumentType.INVOICE),
        document(DocumentType.PURCHASE_ORDER),
    )
    assert result.summary.status == "matched"
    assert result.summary.matched_items == 1
    assert result.discrepancies == []


def test_overcharge_is_detected_with_financial_impact_and_evidence():
    invoice = document(DocumentType.INVOICE, price=550)
    po = document(DocumentType.PURCHASE_ORDER, price=500)
    result = reconcile_documents(invoice, po)

    price_issue = next(d for d in result.discrepancies if d.type == DiscrepancyType.UNIT_PRICE_MISMATCH)
    assert price_issue.expected == 500
    assert price_issue.actual == 550
    assert price_issue.financial_impact == 500
    assert price_issue.invoice_evidence is not None
    assert price_issue.purchase_order_evidence is not None


def test_missing_and_ambiguous_items_require_review():
    invoice = document(DocumentType.INVOICE)
    invoice.line_items[0].sku = None
    invoice.line_items[0].description = "Unrelated consulting service"
    result = reconcile_documents(invoice, document(DocumentType.PURCHASE_ORDER))

    assert result.summary.status == "review_required"
    assert any(d.type == DiscrepancyType.MISSING_ITEM and d.requires_review for d in result.discrepancies)


def test_missing_source_evidence_requires_review():
    invoice = attach_evidence(
        document(DocumentType.INVOICE),
        ParsedArtifact(text="", page_count=1, evidence=[]),
    )

    result = reconcile_documents(invoice, document(DocumentType.PURCHASE_ORDER))

    assert result.summary.status == "review_required"
    assert any("No source evidence" in flag for flag in invoice.review_flags)
    assert any(
        d.type == DiscrepancyType.UNSUPPORTED_FIELD and d.requires_review
        for d in result.discrepancies
    )


def test_document_arithmetic_error_is_reported():
    invoice = document(DocumentType.INVOICE)
    invoice.line_items[0].total_price = 4999
    result = reconcile_documents(invoice, document(DocumentType.PURCHASE_ORDER))
    assert any(d.type == DiscrepancyType.ARITHMETIC_ERROR for d in result.discrepancies)


def test_currency_mismatch_does_not_compare_incomparable_prices():
    invoice = document(DocumentType.INVOICE, price=550)
    po = document(DocumentType.PURCHASE_ORDER, price=500)
    invoice.currency = "USD"
    po.currency = "INR"
    result = reconcile_documents(invoice, po)
    types = {d.type for d in result.discrepancies}
    assert DiscrepancyType.CURRENCY_MISMATCH in types
    assert DiscrepancyType.UNIT_PRICE_MISMATCH not in types
