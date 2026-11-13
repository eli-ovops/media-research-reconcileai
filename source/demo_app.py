"""Sample-only Space: fixed fictional PDFs and precomputed results, no provider code or keys."""

from __future__ import annotations

import json
from pathlib import Path

import pypdfium2 as pdfium
from PIL import ImageDraw

ROOT = Path(__file__).resolve().parent
SAMPLE = json.loads((ROOT / "demo" / "result.json").read_text(encoding="utf-8"))


def sources() -> dict:
    choices = {
        "Invoice: whole page": ("invoice", None),
        "Purchase order: whole page": ("purchase_order", None),
    }
    for kind in ("invoice", "purchase_order"):
        document = SAMPLE[kind]
        for name, evidence in document["field_evidence"].items():
            choices[f"{kind}: {name}"] = (kind, evidence)
        for index, item in enumerate(document["line_items"], 1):
            if item.get("evidence"):
                choices[f"{kind}: row {index} — {item['description']}"] = (kind, item["evidence"])
    for index, discrepancy in enumerate(SAMPLE["discrepancies"], 1):
        kind = "invoice" if discrepancy.get("invoice_evidence") else "purchase_order"
        choices[f"Finding {index}: {discrepancy['message']}"] = (kind, discrepancy.get(f"{kind}_evidence"))
    return choices


def preview(choice: str):
    kind, evidence = sources()[choice]
    pdf = pdfium.PdfDocument(ROOT / "demo" / f"{kind}.pdf")
    page = pdf[(evidence or {}).get("page", 1) - 1]
    image = page.render(scale=1.6).to_pil().convert("RGB")
    page.close()
    pdf.close()
    bbox = (evidence or {}).get("bbox")
    if bbox:
        ImageDraw.Draw(image, "RGBA").rectangle(
            (
                bbox[0] * image.width - 5,
                bbox[1] * image.height - 5,
                bbox[2] * image.width + 5,
                bbox[3] * image.height + 5,
            ),
            fill=(255, 194, 71, 55),
            outline=(183, 99, 10, 255),
            width=2,
        )
    return image


def build_demo():
    import gradio as gr

    fields = [
        [kind, field, str(value)]
        for kind in ("invoice", "purchase_order")
        for field, value in SAMPLE[kind].items()
        if field in {"document_number", "vendor_name", "currency", "subtotal", "total_amount"}
    ]
    for kind in ("invoice", "purchase_order"):
        for index, item in enumerate(SAMPLE[kind]["line_items"], 1):
            fields.extend(
                [
                    [kind, f"row {index}: {field}", str(item[field])]
                    for field in ("description", "quantity", "unit_price", "total_price")
                ]
            )
    findings = [
        [d["type"], d["message"], str(d["expected"]), str(d["actual"])] for d in SAMPLE["discrepancies"]
    ]
    with gr.Blocks(title="ReconcileAI sample review") as demo:
        gr.Markdown(
            "# ReconcileAI\nFictional sample PDFs and precomputed extraction. "
            "No uploads, API keys or live model calls. Select a field or finding to highlight its source."
        )
        with gr.Row():
            with gr.Column():
                choice = gr.Dropdown(
                    list(sources()), value="Invoice: whole page", label="Field or flagged mismatch"
                )
                image = gr.Image(
                    value=preview("Invoice: whole page"),
                    label="PDF source and bounding box",
                    interactive=False,
                )
                gr.File(
                    value=[str(ROOT / "demo/invoice.pdf"), str(ROOT / "demo/purchase_order.pdf")],
                    label="Download original sample PDFs",
                    interactive=False,
                )
            with gr.Column():
                gr.Dataframe(
                    value=fields,
                    headers=["Document", "Field", "Extracted value"],
                    label="Extracted fields",
                    interactive=False,
                )
                gr.Dataframe(
                    value=findings,
                    headers=["Mismatch", "Finding", "Expected", "Actual"],
                    label="Flagged mismatches",
                    interactive=False,
                )
                gr.JSON(value=SAMPLE, label="Precomputed result and source evidence")
        choice.change(preview, inputs=choice, outputs=image)
    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="0.0.0.0", server_port=7860)
