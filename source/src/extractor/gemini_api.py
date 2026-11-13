"""Gemini OpenAI-compatible transport, shared by extraction and diagnostic judging."""

import hashlib
import json
import threading
import time
from datetime import UTC, datetime, timedelta

import httpx

from config import settings
from src.extractor.response_cache import cache_path, save_response

_lock = threading.Lock()
_next_call = 0.0


def quota_file(model, directory, api_key, free_tier):
    return (
        cache_path(
            directory.parent,
            {
                "quota_model": model,
                "endpoint": settings.GEMINI_BASE_URL,
                "credential_hash": hashlib.sha256(api_key.encode()).hexdigest(),
                "free_tier": free_tier,
            },
        )
        if directory
        else None
    )


def quota_status(model, directory, api_key, free_tier):
    path = quota_file(model, directory, api_key, free_tier)
    if path and path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if datetime.fromisoformat(record["retry_not_before_utc"]) > datetime.now(UTC):
            return record
    return None


def completion(request, api_key, cache_dir=None, budget=None, *, free_tier=None):
    global _next_call
    endpoint = settings.GEMINI_BASE_URL.rstrip("/")
    free_tier = settings.GEMINI_FREE_TIER if free_tier is None else free_tier
    cached = cache_path(cache_dir, {"endpoint": endpoint, "free_tier": free_tier, **request})
    if cached and cached.exists():
        return json.loads(cached.read_text(encoding="utf-8")), True
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for live extraction")
    blocked = quota_status(request["model"], cache_dir, api_key, free_tier)
    if blocked:
        raise RuntimeError(f"Gemini daily quota exhausted; retry after {blocked['retry_not_before_utc']}")
    # Bound paid-equivalent spend even for a key declared free; project billing can differ.
    rates = {
        "gemini-3.1-flash-lite": (0.25, 1.50),
        "gemini-2.5-flash": (0.30, 2.50),
        "gemini-2.5-flash-lite": (0.10, 0.40),
        "gemini-3.8-flash": (0.75, 3.75),
        "gemini-3.1-pro-preview": (2.0, 12.0),
    }.get(request["model"])
    maximum = 0.0
    if budget:
        if rates is None:
            raise RuntimeError("Verified model-specific rates required for a budgeted Gemini call")
        text_bytes = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        input_bound = 1_048_576 if "image_url" in json.dumps(request) else text_bytes
        input_rate, output_rate = rates
        if request["model"] == "gemini-3.1-pro-preview" and input_bound > 200_000:
            input_rate, output_rate = 4.0, 18.0
        rates = (input_rate, output_rate)
        maximum = (input_bound * input_rate + request["max_tokens"] * output_rate) / 1_000_000
        budget.reserve(maximum)
    started = time.perf_counter()
    attempts = []
    trace_path = cached.with_suffix(".attempts.json") if cached else None
    prior_attempts = (
        json.loads(trace_path.read_text(encoding="utf-8"))["attempts"]
        if trace_path and trace_path.exists()
        else []
    )
    with httpx.Client(timeout=settings.GEMINI_TIMEOUT_MS / 1000) as client:
        for attempt in range(settings.GEMINI_MAX_RETRIES + 1):
            # ponytail: process-wide throttle; use a shared limiter for multiple server processes.
            with _lock:
                time.sleep(max(0, _next_call - time.monotonic()))
                _next_call = time.monotonic() + settings.GEMINI_MIN_INTERVAL_SECONDS
            response = client.post(
                endpoint + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=request,
            )
            event = {
                "attempt": attempt + 1,
                "http_status": response.status_code,
                "at_utc": datetime.now(UTC).isoformat(),
                "backoff_seconds": 0,
            }
            if response.is_error:
                try:
                    body = response.json()
                    body = body[0] if isinstance(body, list) and body else body
                    error = body.get("error", {})
                    event["provider_status"] = error.get("status")
                    event["quota_limits"] = [
                        {k: violation[k] for k in ("quotaId", "quotaMetric", "quotaValue") if k in violation}
                        for detail in error.get("details", [])
                        for violation in detail.get("violations", [])
                    ]
                    message = str(error.get("message", "")).lower()
                    event["zero_quota"] = "limit: 0" in message or "limit:0" in message
                    event["daily_quota"] = "perday" in message or "per_day" in message
                    event["daily_quota"] |= any(
                        "PerDay" in q.get("quotaId", "") for q in event["quota_limits"]
                    )
                    hints = [
                        float(d["retryDelay"].removesuffix("s"))
                        for d in error.get("details", [])
                        if isinstance(d.get("retryDelay"), str) and d["retryDelay"].endswith("s")
                    ]
                    if event["daily_quota"] and hints:
                        until = datetime.now(UTC) + timedelta(seconds=max(hints))
                        save_response(
                            quota_file(request["model"], cache_dir, api_key, free_tier),
                            {
                                "model": request["model"],
                                "quota_limits": event["quota_limits"],
                                "run_at_utc": event["at_utc"],
                                "retry_not_before_utc": until.isoformat(),
                            },
                        )
                        event["retry_not_before_utc"] = until.isoformat()
                except (ValueError, AttributeError, TypeError):
                    pass
            attempts.append(event)
            if event.get("retry_not_before_utc"):
                save_response(trace_path, {"model": request["model"], "attempts": prior_attempts + attempts})
                raise RuntimeError(
                    f"Gemini daily quota exhausted; retry after {event['retry_not_before_utc']}"
                )
            if response.status_code in (429, 503) and attempt < settings.GEMINI_MAX_RETRIES:
                delay = min(60, 2 ** (attempt + 1))
                try:
                    delay = max(delay, min(60, float(response.headers.get("retry-after", 0))))
                except ValueError:
                    pass
                event["backoff_seconds"] = delay
                print(
                    f"{request['model']}: HTTP {response.status_code}; "
                    f"retry {attempt + 1}/{settings.GEMINI_MAX_RETRIES} after {delay:g}s",
                    flush=True,
                )
                if cached:
                    save_response(
                        cached.with_suffix(".attempts.json"),
                        {"model": request["model"], "attempts": prior_attempts + attempts},
                    )
                time.sleep(delay)
                continue
            if cached:
                save_response(
                    cached.with_suffix(".attempts.json"),
                    {"model": request["model"], "attempts": prior_attempts + attempts},
                )
            if response.is_error:
                # Avoid provider bodies or request headers leaking credentials into logs/results.
                raise RuntimeError(f"Gemini HTTP {response.status_code}; response body omitted")
            raw = response.json()
            payload = {key: raw.get(key) for key in ("id", "model", "choices", "usage")}
            payload.update(
                run_at_utc=datetime.now(UTC).isoformat(),
                latency_seconds=time.perf_counter() - started,
                requested_model=request["model"],
                temperature=request["temperature"],
                endpoint=endpoint,
                free_tier=free_tier,
                attempts=attempts,
            )
            usage = payload.get("usage") or {}
            if rates and "prompt_tokens" in usage and "completion_tokens" in usage:
                payload["paid_equivalent_usd"] = (
                    usage["prompt_tokens"] * rates[0] + usage["completion_tokens"] * rates[1]
                ) / 1_000_000
                payload["rates_usd_per_million_tokens"] = {"input": rates[0], "output": rates[1]}
            save_response(cached, payload)
            if budget:
                budget.settle(maximum, payload.get("paid_equivalent_usd"))
            return payload, False
    raise RuntimeError("Gemini retry limit exceeded")
