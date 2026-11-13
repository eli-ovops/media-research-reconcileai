from scripts.run_reconciliation_eval import score_items
from src.reconciliation.models import DocumentExtraction, DocumentType, EvidenceReference, ExtractedLineItem


def test_row_score_checks_amount_and_evidence_location():
    document = DocumentExtraction(
        document_type=DocumentType.INVOICE, document_number="INV-1",
        vendor_name="Example", total_amount=5500,
        line_items=[ExtractedLineItem(
            sku="SKU-42", description="Appliance", quantity=10,
            unit_price=550, total_price=5500,
            evidence=EvidenceReference(document_id="invoice", page=1, text="Appliance",
                                       bbox=(0.1, 0.8, 0.5, 0.82)),
        )],
    )
    expected = [{"sku": "SKU-42", "quantity": 10, "unit_price": 500, "total_price": 5000}]
    assert score_items(document, expected, [0.22]) == {
        "expected_rows": 1, "exact_rows": 0, "located_rows": 0,
    }
    document.line_items[0].unit_price = 500
    document.line_items[0].total_price = 5000
    document.line_items[0].evidence.bbox = (0.1, 0.21, 0.5, 0.23)
    assert score_items(document, expected, [0.22]) == {
        "expected_rows": 1, "exact_rows": 1, "located_rows": 1,
    }
