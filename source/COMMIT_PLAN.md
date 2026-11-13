# Proposed ReconcileAI commit

Approved by the user for a single clean commit and push. Two unpublished local commits will be replaced with one clean commit on the existing remote base, removing cache files from unpublished history. Local cache files stay on disk.

Excluded: `.env`, public dataset images (`evals/cord/`), raw provider responses and attempt sidecars (`results/raw/`), parsed OCR caches (`results/parsed/`). Normalized field predictions and measured metadata remain in result summaries for offline metric reruns. Reliability PNGs are generated result plots, not dataset images.

The existing fictional demo PDFs are unchanged. `demo/result.json` updates their precomputed field geometry. Spaces deployment remains pending HF_TOKEN.

Validation: 39 passing tests; all 50 frozen synthetic control cases pass; corrected manifest applied to every backend; normalized summaries rescore without raw responses. Secret-value scan passed.

Approved changed/new files: 53 plus this review record. The CI workflow also installs demo dependencies required by the new UI checks.

## Source, configuration and checks

- `.github/workflows/ci.yml`

- `.env.example`
- `.gitattributes`
- `.gitignore`
- `config.py`
- `demo_app.py`
- `requirements-demo.txt`
- `requirements-eval.txt`
- `requirements.txt`
- `scripts/deploy_space.py`
- `scripts/generate_benchmark.py`
- `scripts/generate_sample.py`
- `scripts/prepare_cord.py`
- `scripts/run_real_eval.py`
- `scripts/summarize_api_usage.py`
- `scripts/verify_results.py`
- `src/extractor/gemini_api.py`
- `src/extractor/gemini_extractor.py`
- `src/extractor/open_vlm.py`
- `src/extractor/response_cache.py`
- `src/main.py`
- `src/parser/real_document_parser.py`
- `src/storage.py`
- `tests/test_real_eval_and_batch.py`
- `tests/test_real_extraction_support.py`

## Manifests and derived result summaries

- `results/budget.json`
- `results/cord_manifest.json`
- `results/cord_manifest_before_list_fix.json`
- `results/dataset_inventory.json`
- `results/error_review.json`
- `results/ingestion.json`
- `results/judge_fallback.json`
- `results/model_access.json`
- `results/model_selection.json`
- `results/provider_catalog.json`
- `results/rate_limiting.json`
- `results/real_comparison.json`
- `results/reliability_docling_text_llm_document.png`
- `results/reliability_docling_text_llm_field.png`
- `results/reliability_gemini_document.png`
- `results/reliability_gemini_field.png`
- `results/reliability_qwen_document.png`
- `results/reliability_qwen_field.png`
- `results/smoke_comparison.json`
- `results/verification.json`

## Documentation and fictional sample fixture

- `ERROR_ANALYSIS.md`
- `README.md`
- `demo/result.json`
- `docs/architecture.md`
- `evals/README.md`
- `results/COMPARISON.md`
- `results/README.md`
- `results/RESUME_BULLETS.md`
- `results/SMOKE.md`

## Repository-only removals

- Previously tracked `results/raw/**` and `results/parsed/**` (removed from the index; local files preserved).
