from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DocumentType(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"


class EvidenceReference(BaseModel):
    document_id: str
    page: int = Field(ge=1)
    text: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ExtractedLineItem(BaseModel):
    line_id: str | None = None
    sku: str | None = None
    description: str
    quantity: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    total_price: float = Field(ge=0)
    evidence: EvidenceReference | None = None


class DocumentExtraction(BaseModel):
    document_id: str = ""
    document_type: DocumentType
    document_number: str
    document_date: str | None = None
    vendor_name: str
    buyer_name: str | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    subtotal: float | None = Field(default=None, ge=0)
    tax_amount: float | None = Field(default=None, ge=0)
    total_amount: float = Field(ge=0)
    field_evidence: dict[str, EvidenceReference] = Field(default_factory=dict)
    review_flags: list[str] = Field(default_factory=list)
    provider_metadata: dict[str, str | int | float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_currency(self) -> "DocumentExtraction":
        self.currency = self.currency.upper()
        return self


class DiscrepancyType(str, Enum):
    MISSING_ITEM = "missing_item"
    AMBIGUOUS_MATCH = "ambiguous_match"
    QUANTITY_MISMATCH = "quantity_mismatch"
    UNIT_PRICE_MISMATCH = "unit_price_mismatch"
    LINE_TOTAL_MISMATCH = "line_total_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    VENDOR_MISMATCH = "vendor_mismatch"
    ARITHMETIC_ERROR = "arithmetic_error"
    UNSUPPORTED_FIELD = "unsupported_field"


class Discrepancy(BaseModel):
    discrepancy_id: str
    type: DiscrepancyType
    severity: Literal["info", "warning", "critical"]
    message: str
    expected: str | float | None = None
    actual: str | float | None = None
    financial_impact: float = 0.0
    invoice_evidence: EvidenceReference | None = None
    purchase_order_evidence: EvidenceReference | None = None
    requires_review: bool = False


class ReconciliationSummary(BaseModel):
    matched_items: int
    invoice_items: int
    purchase_order_items: int
    discrepancy_count: int
    financial_impact: float
    status: Literal["matched", "discrepancies_found", "review_required"]


class ReconciliationResult(BaseModel):
    invoice: DocumentExtraction
    purchase_order: DocumentExtraction
    discrepancies: list[Discrepancy]
    summary: ReconciliationSummary
    reviewer_edits: list[dict] = Field(default_factory=list)
