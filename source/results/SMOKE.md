# Backend comparison

| Backend | Status | Micro F1 | Review rate | p50 (s) | p95 (s) | Est. USD/doc | Paid-equivalent USD/doc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gemini (gemini-3.1-flash-lite) | measured | 0.7647 | 1.0000 | 31.6065 | 32.0457 | 0.0000 | 0.0007 |
| qwen (groq / qwen/qwen3.8-27b) | measured | 0.5294 | 1.0000 | 27.3692 | 50.8340 | 0.0028 | 0.0028 |
| docling_text_llm (gemini-3.1-flash-lite) | measured | 0.5143 | 0.5000 | 36.9825 | 54.8330 | 0.0000 | 0.0004 |

### gemini field results

Held-out completion: 2/2; failed: 0. All selected splits: 5/5 completed.

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| description | 4 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| quantity | 1 | 3 | 0 | 0.2500 | 1.0000 | 0.4000 |
| unit_price | 0 | 4 | 0 | 0.0000 | unknown | 0.0000 |
| line_total | 4 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| subtotal | 1 | 1 | 0 | 0.5000 | 1.0000 | 0.6667 |
| tax_amount | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| total_amount | 2 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |

Development threshold selection: `{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null, "target_review_rate": 0.2, "target_achieved": false, "tie_policy": "strict score < threshold; do not split equal-confidence documents", "curve": [{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 5e-324, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 1.0, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null}]}`.

| Held-out routing | Threshold | Review rate | Error precision | Error recall | Accepted accuracy |
| --- | --- | --- | --- | --- | --- |
| Default | 0.8500 | 1.0000 | 1.0000 | 1.0000 | unknown |
| Dev fit | 0.0000 | 1.0000 | 1.0000 | 1.0000 | unknown |

Held-out field ECE: 0.3810; document ECE: 0.0000. These evaluate heuristic evidence scores, not probabilities.

Requested development review rate 20.0% was unattainable; selected routing reviews 100.0%. Mandatory review flags remain active and equal-score documents stay together.


### qwen field results

Held-out completion: 2/2; failed: 0. All selected splits: 5/5 completed.

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| description | 4 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| quantity | 1 | 3 | 0 | 0.2500 | 1.0000 | 0.4000 |
| unit_price | 0 | 4 | 0 | 0.0000 | unknown | 0.0000 |
| line_total | 3 | 1 | 1 | 0.7500 | 0.7500 | 0.7500 |
| subtotal | 0 | 2 | 1 | 0.0000 | 0.0000 | 0.0000 |
| tax_amount | 0 | 1 | 1 | 0.0000 | 0.0000 | 0.0000 |
| total_amount | 1 | 1 | 1 | 0.5000 | 0.5000 | 0.5000 |

Development threshold selection: `{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null, "target_review_rate": 0.2, "target_achieved": false, "tie_policy": "strict score < threshold; do not split equal-confidence documents", "curve": [{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 5e-324, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 1.0, "review_rate": 1.0, "error_detection_precision": 0.6666666666666666, "error_detection_recall": 1.0, "accepted_document_accuracy": null}]}`.

| Held-out routing | Threshold | Review rate | Error precision | Error recall | Accepted accuracy |
| --- | --- | --- | --- | --- | --- |
| Default | 0.8500 | 1.0000 | 1.0000 | 1.0000 | unknown |
| Dev fit | 0.0000 | 1.0000 | 1.0000 | 1.0000 | unknown |

Held-out field ECE: 0.4286; document ECE: 0.0000. These evaluate heuristic evidence scores, not probabilities.

Requested development review rate 20.0% was unattainable; selected routing reviews 100.0%. Mandatory review flags remain active and equal-score documents stay together.


### docling_text_llm field results

Held-out completion: 2/2; failed: 0. All selected splits: 5/5 completed.

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| description | 4 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 |
| quantity | 1 | 3 | 0 | 0.2500 | 1.0000 | 0.4000 |
| unit_price | 0 | 4 | 0 | 0.0000 | unknown | 0.0000 |
| line_total | 3 | 1 | 1 | 0.7500 | 0.7500 | 0.7500 |
| subtotal | 0 | 2 | 1 | 0.0000 | 0.0000 | 0.0000 |
| tax_amount | 0 | 2 | 1 | 0.0000 | 0.0000 | 0.0000 |
| total_amount | 1 | 1 | 1 | 0.5000 | 0.5000 | 0.5000 |

Development threshold selection: `{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 1.0, "error_detection_recall": 1.0, "accepted_document_accuracy": null, "target_review_rate": 0.2, "target_achieved": false, "tie_policy": "strict score < threshold; do not split equal-confidence documents", "curve": [{"threshold": 0.0, "review_rate": 1.0, "error_detection_precision": 1.0, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 5e-324, "review_rate": 1.0, "error_detection_precision": 1.0, "error_detection_recall": 1.0, "accepted_document_accuracy": null}, {"threshold": 1.0, "review_rate": 1.0, "error_detection_precision": 1.0, "error_detection_recall": 1.0, "accepted_document_accuracy": null}]}`.

| Held-out routing | Threshold | Review rate | Error precision | Error recall | Accepted accuracy |
| --- | --- | --- | --- | --- | --- |
| Default | 0.8500 | 0.5000 | 1.0000 | 0.5000 | 0.0000 |
| Dev fit | 0.0000 | 0.5000 | 1.0000 | 0.5000 | 0.0000 |

Held-out field ECE: 0.4545; document ECE: 0.5000. These evaluate heuristic evidence scores, not probabilities.

Requested development review rate 20.0% was unattainable; selected routing reviews 100.0%. Mandatory review flags remain active and equal-score documents stay together.


List-valued CORD annotations were flattened after model generation. The report records the previous manifest hash and affected cases; predictions and model inputs are unchanged. Diagnoses using old labels are marked stale.

Projected full cost for selected backends: `0.10108800000000003` USD.

Projected full paid-equivalent token cost: `0.194548` USD.

Recorded rate-limit behaviour (cached calls retain original attempts):

```json
{
  "gemini_minimum_interval_seconds": 30.0,
  "max_retries": 5,
  "recorded_http_attempts": 50,
  "recorded_429_responses": 14,
  "recorded_backoff_seconds": 181.0,
  "cache_hits": 28,
  "note": "Cumulative trace history includes failed/aborted smoke attempts and the Pro probe. Direct access diagnostics are excluded; cache reads add no HTTP calls."
}
```

Run scope: **smoke**.
Costs use reported provider usage cost when present, otherwise configured token rates. Gemini costs are estimates, not invoices. Unknown costs remain unknown.
Latency percentiles cover completed documents only: original Docling conversion plus provider call wall time (including throttle/backoff), excluding budget preflight and scoring. Every backend reuses the same actual parse and its recorded duration for each image; first-use model loading is included. Cached provider calls retain their original generation duration.
F1 includes failed documents as false negatives. Field scoring matches normalized multisets per document; it does not prove row association. Absent CORD annotations are scored as empty, so extra predictions are false positives.
CORD has no annotated vendor/document number/currency; these remain required by production review routing but are excluded from extraction F1. This benchmark does not measure invoice/PO mismatch quality.
