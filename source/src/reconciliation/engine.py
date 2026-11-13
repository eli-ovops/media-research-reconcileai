from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher
from uuid import uuid4

from .models import (
    Discrepancy,
    DiscrepancyType,
    DocumentExtraction,
    ExtractedLineItem,
    ReconciliationResult,
    ReconciliationSummary,
)

CENT = Decimal("0.01")


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalized(left), _normalized(right)).ratio()


def _new_discrepancy(kind: DiscrepancyType, **kwargs) -> Discrepancy:
    return Discrepancy(discrepancy_id=f"disc_{uuid4().hex[:10]}", type=kind, **kwargs)


def _match_item(
    invoice_item: ExtractedLineItem,
    candidates: list[tuple[int, ExtractedLineItem]],
) -> tuple[int, ExtractedLineItem, bool] | None:
    if invoice_item.sku:
        exact = [
            pair
            for pair in candidates
            if pair[1].sku and pair[1].sku.lower() == invoice_item.sku.lower()
        ]
        if len(exact) == 1:
            return (*exact[0], False)
    ranked = sorted(
        ((idx, item, _similarity(invoice_item.description, item.description)) for idx, item in candidates),
        key=lambda value: value[2],
        reverse=True,
    )
    if not ranked or ranked[0][2] < 0.55:
        return None
    ambiguous = len(ranked) > 1 and ranked[0][2] - ranked[1][2] < 0.08
    return ranked[0][0], ranked[0][1], ambiguous


def _arithmetic_discrepancies(document: DocumentExtraction, label: str) -> list[Discrepancy]:
    discrepancies: list[Discrepancy] = []
    for item in document.line_items:
        calculated = _money(item.quantity) * _money(item.unit_price)
        if abs(calculated - _money(item.total_price)) > CENT:
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.ARITHMETIC_ERROR,
                severity="critical",
                message=f"{label} line total does not equal quantity × unit price: {item.description}",
                expected=float(calculated),
                actual=item.total_price,
                invoice_evidence=item.evidence if label == "Invoice" else None,
                purchase_order_evidence=item.evidence if label != "Invoice" else None,
            ))
    if document.subtotal is not None:
        calculated_subtotal = sum((_money(item.total_price) for item in document.line_items), Decimal("0"))
        if abs(calculated_subtotal - _money(document.subtotal)) > CENT:
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.ARITHMETIC_ERROR,
                severity="critical",
                message=f"{label} subtotal does not equal the sum of line totals",
                expected=float(calculated_subtotal),
                actual=document.subtotal,
            ))
    return discrepancies


def reconcile_documents(
    invoice: DocumentExtraction,
    purchase_order: DocumentExtraction,
) -> ReconciliationResult:
    discrepancies = _arithmetic_discrepancies(invoice, "Invoice")
    discrepancies.extend(_arithmetic_discrepancies(purchase_order, "Purchase order"))
    matched = 0
    comparable_currency = invoice.currency == purchase_order.currency

    if not comparable_currency:
        discrepancies.append(_new_discrepancy(
            DiscrepancyType.CURRENCY_MISMATCH,
            severity="critical",
            message="Invoice and purchase order use different currencies",
            expected=purchase_order.currency,
            actual=invoice.currency,
            invoice_evidence=invoice.field_evidence.get("currency"),
            purchase_order_evidence=purchase_order.field_evidence.get("currency"),
        ))

    if _normalized(invoice.vendor_name) != _normalized(purchase_order.vendor_name):
        discrepancies.append(_new_discrepancy(
            DiscrepancyType.VENDOR_MISMATCH,
            severity="warning",
            message="Invoice and purchase order name different vendors",
            expected=purchase_order.vendor_name,
            actual=invoice.vendor_name,
            invoice_evidence=invoice.field_evidence.get("vendor_name"),
            purchase_order_evidence=purchase_order.field_evidence.get("vendor_name"),
            requires_review=True,
        ))

    remaining = list(enumerate(purchase_order.line_items))
    for invoice_item in invoice.line_items:
        match = _match_item(invoice_item, remaining)
        if match is None:
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.MISSING_ITEM,
                severity="critical",
                message=f"Invoice item is absent from the purchase order: {invoice_item.description}",
                actual=invoice_item.description,
                financial_impact=float(_money(invoice_item.total_price)),
                invoice_evidence=invoice_item.evidence,
                requires_review=True,
            ))
            continue
        po_index, po_item, ambiguous = match
        remaining = [pair for pair in remaining if pair[0] != po_index]
        matched += 1
        if ambiguous:
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.AMBIGUOUS_MATCH,
                severity="warning",
                message=f"Multiple purchase-order rows may match: {invoice_item.description}",
                invoice_evidence=invoice_item.evidence,
                purchase_order_evidence=po_item.evidence,
                requires_review=True,
            ))
        if _money(invoice_item.quantity) != _money(po_item.quantity):
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.QUANTITY_MISMATCH,
                severity="critical",
                message=f"Quantity differs for {invoice_item.description}",
                expected=po_item.quantity,
                actual=invoice_item.quantity,
                invoice_evidence=invoice_item.evidence,
                purchase_order_evidence=po_item.evidence,
            ))
        if comparable_currency and _money(invoice_item.unit_price) != _money(po_item.unit_price):
            impact = (
                _money(invoice_item.unit_price) - _money(po_item.unit_price)
            ) * _money(invoice_item.quantity)
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.UNIT_PRICE_MISMATCH,
                severity="critical",
                message=f"Unit price differs for {invoice_item.description}",
                expected=po_item.unit_price,
                actual=invoice_item.unit_price,
                financial_impact=float(impact),
                invoice_evidence=invoice_item.evidence,
                purchase_order_evidence=po_item.evidence,
            ))
        if comparable_currency and _money(invoice_item.total_price) != _money(po_item.total_price):
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.LINE_TOTAL_MISMATCH,
                severity="warning",
                message=f"Line total differs for {invoice_item.description}",
                expected=po_item.total_price,
                actual=invoice_item.total_price,
                invoice_evidence=invoice_item.evidence,
                purchase_order_evidence=po_item.evidence,
            ))

    for _, po_item in remaining:
        discrepancies.append(_new_discrepancy(
            DiscrepancyType.MISSING_ITEM,
            severity="warning",
            message=f"Purchase-order item was not invoiced: {po_item.description}",
            expected=po_item.description,
            purchase_order_evidence=po_item.evidence,
        ))

    for document in (invoice, purchase_order):
        for flag in document.review_flags:
            discrepancies.append(_new_discrepancy(
                DiscrepancyType.UNSUPPORTED_FIELD,
                severity="warning",
                message=flag,
                requires_review=True,
            ))

    impact = sum((Decimal(str(item.financial_impact)) for item in discrepancies), Decimal("0"))
    needs_review = any(item.requires_review for item in discrepancies)
    status = "review_required" if needs_review else "discrepancies_found" if discrepancies else "matched"
    return ReconciliationResult(
        invoice=invoice,
        purchase_order=purchase_order,
        discrepancies=discrepancies,
        summary=ReconciliationSummary(
            matched_items=matched,
            invoice_items=len(invoice.line_items),
            purchase_order_items=len(purchase_order.line_items),
            discrepancy_count=len(discrepancies),
            financial_impact=float(impact.quantize(CENT)),
            status=status,
        ),
    )
