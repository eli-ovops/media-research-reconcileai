"""Pin and prepare CORD receipt images and labels without exposing labels to extractors."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = "naver-clova-ix/cord-v2"
REVISION = "7f0115a4b758a71d6473b8d085751692da2fef98"
FILES = {
    "development": (
        "validation-00000-of-00001-cc3c5779fe22e8ca.parquet",
        "0d0f6dac11fdcc549de2746aa9f53136a3bc22a2a1aff2b0b847f7622ad60c15",
    ),
    "held_out": (
        "test-00000-of-00001-9c204eb3f4e11791.parquet",
        "51c65f1788faff392abe2a0b55b023eb23e9be551c509138eaa3a832514224e7",
    ),
}
FIELDS = {
    "menu.nm": "description",
    "menu.cnt": "quantity",
    "menu.unitprice": "unit_price",
    "menu.price": "line_total",
    "sub_total.subtotal_price": "subtotal",
    "sub_total.tax_price": "tax_amount",
    "total.total_price": "total_amount",
}


def cord_labels(ground_truth: dict) -> dict:
    expected = {field: [] for field in FIELDS.values()}
    for category, field in FIELDS.items():
        section, key = category.split(".")
        records = ground_truth["gt_parse"].get(section, [])
        if isinstance(records, dict):
            records = [records]
        expected[field] = [
            value
            for record in records
            if key in record
            for value in (record[key] if isinstance(record[key], list) else [record[key]])
        ]
    return expected


def main(limit: int) -> None:
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    cases = []
    for split, (filename, checksum) in FILES.items():
        parquet = Path(hf_hub_download(DATASET, f"data/{filename}", repo_type="dataset", revision=REVISION))
        with parquet.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                raise RuntimeError(f"Dataset checksum mismatch: {filename}")
        table = pq.read_table(parquet)
        for index, row in enumerate(table.slice(0, limit).to_pylist()):
            case_id = f"cord_{split}_{index:03d}"
            ground_truth = json.loads(row["ground_truth"])
            image_bytes = row["image"]["bytes"]
            image = ROOT / "evals" / "cord" / split / f"{case_id}.png"
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(image_bytes)
            expected = cord_labels(ground_truth)
            cases.append(
                {
                    "case_id": case_id,
                    "split": split,
                    "image": image.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(image_bytes).hexdigest(),
                    "expected": expected,
                }
            )
    manifest = {
        "dataset": DATASET,
        "revision": REVISION,
        "license": "CC-BY-4.0",
        "attribution": "Park et al., CORD: A Consolidated Receipt Dataset for Post-OCR Parsing (2019)",
        "source": "https://github.com/clovaai/cord",
        "selection": "first N rows per official split",
        "limit_per_split": limit,
        "fields": FIELDS,
        "cases": cases,
    }
    output = ROOT / "results" / "cord_manifest.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    inventory = {
        "receipts": len(cases),
        "field_types": len(FIELDS),
        "revision": REVISION,
        "manifest_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "splits": {
            split: {
                "documents": sum(c["split"] == split for c in cases),
                "annotated_values": {
                    field: sum(len(c["expected"][field]) for c in cases if c["split"] == split)
                    for field in FIELDS.values()
                },
            }
            for split in FILES
        },
        "model_quality_measured": False,
        "rerun": f"python scripts/prepare_cord.py --limit {limit}",
    }
    (ROOT / "results/dataset_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", newline="\n")
    print(f"Prepared {len(cases)} receipts; frozen labels: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    main(args.limit)
