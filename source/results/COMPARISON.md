# Backend comparison

| Backend | Status | Micro F1 | Review rate | p50 (s) | p95 (s) | Est. USD/doc | Paid-equivalent USD/doc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gemini (gemini-3.1-flash-lite) | measured | 0.7603 | 1.0000 | 16.6019 | 32.0007 | 0.0000 | 0.0007 |
| qwen (groq / qwen/qwen3.8-27b) | measured | 0.6596 | 1.0000 | 27.2018 | 50.8340 | 0.0027 | 0.0027 |
| docling_text_llm (gemini-3.1-flash-lite) | measured | 0.5692 | 0.8500 | 20.3335 | 36.9825 | 0.0000 | 0.0004 |

### gemini field results

Held-out completion: 20/20; failed: 0. All selected splits: 40/40 completed.

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| description | 38 | 10 | 3 | 0.7917 | 0.9268 | 0.8539 |
| quantity | 35 | 13 | 0 | 0.7292 | 1.0000 | 0.8434 |
| unit_price | 8 | 40 | 0 | 0.1667 | 1.0000 | 0.2857 |
| line_total | 38 | 10 | 1 | 0.7917 | 0.9744 | 0.8736 |
| subtotal | 13 | 7 | 2 | 0.6500 | 0.8667 | 0.7429 |
| tax_amount | 7 | 9 | 1 | 0.4375 | 0.8750 | 0.5833 |
| total_amount | 18 | 2 | 1 | 0.9000 | 0.9474 | 0.9231 |

Development threshold selection: `{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.8, "error_detection_recall": 1.0, "accepted_document_accuracy": null, "target_review_rate": 0.2, "target_achieved": false, "tie_policy": "strict score < threshold; do not split equal-confidence documents", "curve": [{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.8, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 5e-324, "review_rate": 1.0, "error_detection_precision": 0.8, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 1.0, "review_rate": 1.0, "error_detection_precision": 0.8, "error_detection_recall": 1.0, "accepted_document_accuracy": null}]}`.

| Held-out routing | Threshold | Review rate | Error precision | Error recall | Accepted accuracy |
| --- | --- | --- | --- | --- | --- |
| Default | 0.8500 | 1.0000 | 0.9500 | 1.0000 | unknown |
| Dev fit | 0.0000 | 1.0000 | 0.9500 | 1.0000 | unknown |

Held-out field ECE: 0.4896; document ECE: 0.0500. These evaluate heuristic evidence scores, not probabilities.

Requested development review rate 20.0% was unattainable; selected routing reviews 100.0%. Mandatory review flags remain active and equal-score documents stay together.


### qwen field results

Held-out completion: 19/20; failed: 1. All selected splits: 38/40 completed.

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| description | 27 | 15 | 14 | 0.6429 | 0.6585 | 0.6506 |
| quantity | 29 | 13 | 6 | 0.6905 | 0.8286 | 0.7532 |
| unit_price | 8 | 34 | 0 | 0.1905 | 1.0000 | 0.3200 |
| line_total | 30 | 12 | 9 | 0.7143 | 0.7692 | 0.7407 |
| subtotal | 10 | 9 | 5 | 0.5263 | 0.6667 | 0.5882 |
| tax_amount | 6 | 2 | 2 | 0.7500 | 0.7500 | 0.7500 |
| total_amount | 15 | 4 | 4 | 0.7895 | 0.7895 | 0.7895 |

Development threshold selection: `{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.85, "error_detection_recall": 1.0, "accepted_document_accuracy": null, "target_review_rate": 0.2, "target_achieved": false, "tie_policy": "strict score < threshold; do not split equal-confidence documents", "curve": [{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.85, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 5e-324, "review_rate": 1.0, "error_detection_precision": 0.85, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 1.0, "review_rate": 1.0, "error_detection_precision": 0.85, "error_detection_recall": 1.0, "accepted_document_accuracy": null}]}`.

| Held-out routing | Threshold | Review rate | Error precision | Error recall | Accepted accuracy |
| --- | --- | --- | --- | --- | --- |
| Default | 0.8500 | 1.0000 | 0.9000 | 1.0000 | unknown |
| Dev fit | 0.0000 | 1.0000 | 0.9000 | 1.0000 | unknown |

Held-out field ECE: 0.4926; document ECE: 0.1000. These evaluate heuristic evidence scores, not probabilities.

Requested development review rate 20.0% was unattainable; selected routing reviews 100.0%. Mandatory review flags remain active and equal-score documents stay together.


### docling_text_llm field results

Held-out completion: 20/20; failed: 0. All selected splits: 40/40 completed.

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| description | 22 | 18 | 19 | 0.5500 | 0.5366 | 0.5432 |
| quantity | 28 | 12 | 7 | 0.7000 | 0.8000 | 0.7467 |
| unit_price | 4 | 36 | 4 | 0.1000 | 0.5000 | 0.1667 |
| line_total | 30 | 10 | 9 | 0.7500 | 0.7692 | 0.7595 |
| subtotal | 8 | 11 | 7 | 0.4211 | 0.5333 | 0.4706 |
| tax_amount | 4 | 15 | 4 | 0.2105 | 0.5000 | 0.2963 |
| total_amount | 13 | 7 | 6 | 0.6500 | 0.6842 | 0.6667 |

Development threshold selection: `{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.9, "error_detection_recall": 1.0, "accepted_document_accuracy": null, "target_review_rate": 0.2, "target_achieved": false, "tie_policy": "strict score < threshold; do not split equal-confidence documents", "curve": [{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.9, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 5e-324, "review_rate": 1.0, "error_detection_precision": 0.9, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 1.0, "review_rate": 1.0, "error_detection_precision": 0.9, "error_detection_recall": 1.0, "accepted_document_accuracy": null}]}`.

| Held-out routing | Threshold | Review rate | Error precision | Error recall | Accepted accuracy |
| --- | --- | --- | --- | --- | --- |
| Default | 0.8500 | 0.8500 | 1.0000 | 0.8500 | 0.0000 |
| Dev fit | 0.0000 | 0.8500 | 1.0000 | 0.8500 | 0.0000 |

Held-out field ECE: 0.4725; document ECE: 0.1500. These evaluate heuristic evidence scores, not probabilities.

Requested development review rate 20.0% was unattainable; selected routing reviews 100.0%. Mandatory review flags remain active and equal-score documents stay together.


List-valued CORD annotations were flattened after model generation. The report records the previous manifest hash and affected cases; predictions and model inputs are unchanged. Diagnoses using old labels are marked stale.

Recorded rate-limit behaviour (cached calls retain original attempts):

```json
{
  "gemini_minimum_interval_seconds": 15.0,
  "max_retries": 5,
  "recorded_http_attempts": 263,
  "recorded_429_responses": 46,
  "recorded_backoff_seconds": 818.0,
  "cache_hits": 46,
  "note": "Cumulative trace history includes failed/aborted smoke attempts and the Pro probe. Direct access diagnostics are excluded; cache reads add no HTTP calls."
}
```

Run scope: **full**.
Costs use reported provider usage cost when present, otherwise configured token rates. Gemini costs are estimates, not invoices. Unknown costs remain unknown.
Latency percentiles cover completed documents only: original Docling conversion plus provider call wall time (including throttle/backoff), excluding budget preflight and scoring. Every backend reuses the same actual parse and its recorded duration for each image; first-use model loading is included. Cached provider calls retain their original generation duration.
F1 includes failed documents as false negatives. Field scoring matches normalized multisets per document; it does not prove row association. Absent CORD annotations are scored as empty, so extra predictions are false positives.
CORD has no annotated vendor/document number/currency; these remain required by production review routing but are excluded from extraction F1. This benchmark does not measure invoice/PO mismatch quality.
