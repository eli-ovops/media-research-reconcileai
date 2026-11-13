# Architecture decisions

## Why a workflow instead of an agent

Invoice reconciliation has known stages and objective checks. A fixed workflow makes failures observable and keeps the model away from the final financial decision. Gemini performs schema-guided perception; deterministic code owns item matching, decimal arithmetic, discrepancies, and review history.

## Trust boundaries

- Uploaded files are untrusted. Their printed instructions are explicitly treated as content.
- The API key stays in the backend environment and is never returned to the browser.
- Model output is parsed through Pydantic before reconciliation.
- High-value fields and rows require locally resolved source evidence. Missing support or evidence below `CONFIDENCE_THRESHOLD` creates a review flag. This score is a text-match heuristic; calibration requires held-out predictions.
- SQLite preserves job status, results, errors, provider usage, and reviewer changes across restarts.
- The configured development spend guard checks accumulated estimated Gemini cost before starting new inference.

## Failure behavior

Provider errors, invalid structured output, document limits, and parser errors move the job to `failed` with a visible message. There is no silent fallback to sample data. On restart, queued/processing jobs resume through bounded in-process workers. Completed jobs are retained. Batch uploads are validated before workers start, failed uploads are cleaned up, and SSE exposes persisted progress snapshots. One Uvicorn process is supported; distributed execution needs a durable queue with job claiming.

## Evaluation and public demo

CORD images and label manifests are pinned separately. Gemini vision, Groq Qwen and Docling-text-only Gemini share the typed extraction schema and evidence resolver. Expected labels never enter extraction prompts; they are supplied only to the diagnostic judge after scoring. Public benchmark raw responses are cached for offline rescoring; production uploads do not use this cache. Cost reservations persist before requests to preserve the evaluation budget on timeouts or interruption.

The Gradio demo is a separate sample-only entrypoint prepared for Spaces with no extraction code or credentials. An explicit deployment allowlist contains only fixed fictional PDFs, precomputed JSON, the UI and its minimal dependencies.

## Matching policy

Rows match by case-insensitive SKU when available. Otherwise, normalized description similarity must be at least `0.55`; close competing candidates create an ambiguous-match review item. Money uses `Decimal` rounded to cents. Currency mismatches stop meaningful price comparison and remain critical findings.

Extraction and diagnostic judging use gemini-3.1-flash-lite through the OpenAI-compatible HTTP transport. A process-wide throttle and bounded exponential retries apply to HTTP 429 and transient 503; transport timeouts propagate. The diagnostic judge sees labels after scoring and cannot change field F1. Same-model preference and shared reasoning errors limit its diagnoses; selected failures are also visually reviewed. Groq retries respect Retry-After, and its VLM adapter sends all pages of PDFs up to three pages, rejecting longer documents before inference.
