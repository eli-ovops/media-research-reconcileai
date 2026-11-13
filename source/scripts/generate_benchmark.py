"""Generate a versioned 50-case synthetic invoice/PO reconciliation benchmark."""

from __future__ import annotations

import json
import random
from pathlib import Path

from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "evals" / "generated"


def draw_document(path: Path, title: str, number: str, items: list[dict], layout: int) -> None:
    page_size = A4 if layout % 2 else letter
    canvas = Canvas(str(path), pagesize=page_size, invariant=1)
    width, height = page_size
    left = 46 if layout < 3 else 75
    canvas.setFont("Helvetica-Bold", 19)
    canvas.drawString(left, height - 60, title)
    canvas.setFont("Helvetica", 10)
    canvas.drawRightString(width - left, height - 60, number)
    canvas.drawString(left, height - 86, "Vendor: Kaveri Network Systems")
    canvas.drawString(left, height - 102, "Buyer: Meridian Operations Pvt Ltd")
    canvas.drawString(left, height - 118, "Currency: INR")
    y = height - (168 if layout % 2 else 190)
    headers = ("SKU", "Description", "Qty", "Unit price", "Line total")
    x_positions = (left, left + 70, width - 225, width - 155, width - 78)
    canvas.setFont("Helvetica-Bold", 9)
    for x, header in zip(x_positions, headers):
        canvas.drawString(x, y, header)
    y -= 20
    canvas.setFont("Helvetica", 9)
    for item in items:
        values = (
            item["sku"],
            item["description"],
            str(item["quantity"]),
            f'{item["unit_price"]:.2f}',
            f'{item["total_price"]:.2f}',
        )
        for x, value in zip(x_positions, values):
            canvas.drawString(x, y, value)
        y -= 19
    total = sum(item["total_price"] for item in items)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawRightString(width - left, y - 15, f"Subtotal: {total:.2f}")
    canvas.drawRightString(width - left, y - 32, f"Total: {total:.2f}")
    canvas.save()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260919)
    manifest = {"name": "reconcile-ai-benchmark", "version": "1.1.0", "seed": 20260919, "cases": []}
    scenarios = ("clean", "unit_price_mismatch", "quantity_mismatch", "missing_item")
    for index in range(50):
        split = "development" if index < 20 else "held_out"
        layout = index % 3 if split == "development" else 3 + (index % 3)
        scenario = scenarios[index % len(scenarios)]
        base_price = rng.choice((250.0, 500.0, 1250.0))
        po_items = [{
            "sku": "SKU-42",
            "description": "Network appliance",
            "quantity": 10,
            "unit_price": base_price,
            "total_price": 10 * base_price,
        }]
        invoice_items = [dict(po_items[0])]
        expected: list[str] = []
        if scenario == "unit_price_mismatch":
            invoice_items[0]["unit_price"] += 50
            invoice_items[0]["total_price"] = invoice_items[0]["quantity"] * invoice_items[0]["unit_price"]
            expected.extend(["unit_price_mismatch", "line_total_mismatch"])
        elif scenario == "quantity_mismatch":
            invoice_items[0]["quantity"] = 12
            invoice_items[0]["total_price"] = 12 * base_price
            expected.extend(["quantity_mismatch", "line_total_mismatch"])
        elif scenario == "missing_item":
            invoice_items.append({
                "sku": "SVC-9",
                "description": "Expedited handling",
                "quantity": 1,
                "unit_price": 900.0,
                "total_price": 900.0,
            })
            expected.append("missing_item")
        case_id = f"case_{index + 1:03d}"
        case_dir = OUTPUT / case_id
        case_dir.mkdir(exist_ok=True)
        draw_document(case_dir / "invoice.pdf", "TAX INVOICE", f"INV-{index + 1:04d}", invoice_items, layout)
        draw_document(
            case_dir / "purchase_order.pdf",
            "PURCHASE ORDER",
            f"PO-{index + 1:04d}",
            po_items,
            layout,
        )
        manifest["cases"].append({
            "case_id": case_id,
            "split": split,
            "layout_family": layout,
            "scenario": scenario,
            "invoice": f"{case_id}/invoice.pdf",
            "purchase_order": f"{case_id}/purchase_order.pdf",
            "expected_discrepancies": expected,
            "invoice_items": invoice_items,
            "purchase_order_items": po_items,
            "row_top_fractions": [
                round(((168 if layout % 2 else 190) + 20 + row * 19) / (A4[1] if layout % 2 else letter[1]), 5)
                for row in range(len(invoice_items))
            ],
        })
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    print(f"Generated {len(manifest['cases'])} labeled pairs at {OUTPUT}")


if __name__ == "__main__":
    main()
