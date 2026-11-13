# Resume bullets

Numeric sources: `real_comparison.json` and `verification.json`. Field F1 uses frozen CORD annotations; fixture checks use a stub extractor.

- Evaluated Gemini 3.1 Flash-Lite, Qwen3.8-27B (Groq), and Docling OCR + Gemini 3.1 Flash-Lite on 40 public CORD receipts, achieving 76.0%, 66.0%, 56.9% field F1 respectively on 20 held-out receipts; normalized predictions enable offline scoring and confidence calibration.
- Built invoice/PO reconciliation with deterministic controls verified against 50 labeled synthetic pairs across 4 scenarios.
- Added persistent batch processing with SSE progress, verified using a 6-document stub fixture, and a no-key PDF review demo highlighting 2 precomputed mismatches.
