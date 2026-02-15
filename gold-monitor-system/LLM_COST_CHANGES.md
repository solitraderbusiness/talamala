# LLM Cost Reduction Changes — 2026-02-15

All changes made to reduce OpenRouter LLM costs (~$70/week → target ~$15-20/week).
If quality degrades, revert each change individually using the instructions below.

---

## Change 1: Reference Scorer → Haiku + Batching + Reduced Frequency

**Files:** `api/analysis/workers/reference_scorer.py`, `api/analysis/workers/main.py`

**What changed:**
- Model switched from `anthropic/claude-sonnet-4` to `anthropic/claude-haiku-4.5`
- Scoring now batches 10 alerts per LLM call (was 1 alert per call)
- System prompt rewritten for batch JSON array output
- Frequency reduced from every 30 minutes to every 6 hours

**Estimated savings:** ~$5-8/day (was the #1 cost driver)

**How to revert `reference_scorer.py`:**
1. Change `MODEL = "anthropic/claude-haiku-4.5"` → `MODEL = "anthropic/claude-sonnet-4"`
2. Remove `BATCH_CHUNK = 10`
3. Revert `SYSTEM_PROMPT` to single-item format (original asked for single JSON object, not array)
4. Replace `_score_batch()` with the old `_score_one()` function that scored alerts individually
5. In `run()`, change the chunk loop back to individual `_score_one()` calls per alert

**How to revert `main.py` frequency:**
- Change `_run_worker("reference_scorer", reference_scorer.run, INTERVAL_6H)`
  back to `_run_worker("reference_scorer", reference_scorer.run, INTERVAL_30M)`

---

## Change 2: Signal Parser → Haiku

**File:** `api/signal_aggregator/config.py`

**What changed:**
- Default model changed from `anthropic/claude-sonnet-4` to `anthropic/claude-haiku-4.5`
- Line: `SIGNAL_PARSE_MODEL: str = os.getenv("SIGNAL_PARSE_MODEL", "anthropic/claude-haiku-4.5")`

**Estimated savings:** ~$1.50-3/day

**How to revert:**
- Change default back to `"anthropic/claude-sonnet-4"` on the `SIGNAL_PARSE_MODEL` line
- Or set env var `SIGNAL_PARSE_MODEL=anthropic/claude-sonnet-4` without code change

---

## Change 3: Chat — max_tokens cap on tool-discovery call

**File:** `api/services/chat/openrouter.py`

**What changed:**
- Added `max_tokens: int = 800` parameter to `chat_completion()` method
- This caps the non-streaming tool-discovery call (previously no limit, model could generate 4096+ tokens)

**Estimated savings:** ~$0.50-1/day

**How to revert:**
- Remove `max_tokens` parameter from `chat_completion()` signature
- Remove `"max_tokens": max_tokens` from the payload dict

---

## Change 4: Chat — Single chunk for no-tool responses

**File:** `api/routers/chat.py`

**What changed:**
- When no tools are called, the response was being fake-streamed in 10-character chunks
- Now yields the complete response as a single chunk (it's already fully generated anyway)

**Estimated savings:** Minimal (reduces server overhead, not LLM cost)

**How to revert:**
- Replace the single-chunk yield block with the old loop:
```python
chunk_size = 10
for i in range(0, len(cleaned_response), chunk_size):
    chunk = cleaned_response[i:i + chunk_size]
    yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
    await asyncio.sleep(0.02)
```

---

## Change 5: Redis cache for chat tool results

**File:** `api/services/chat/tool_executor.py`

**What changed:**
- Added Redis caching (5-minute TTL) for `get_price_data`, `get_sentiment`, and `get_news_summary`
- Cached results avoid redundant DB queries when multiple users ask similar questions

**Estimated savings:** ~$0.50-1/day (reduces DB load, less data in LLM context)

**How to revert:**
- Remove the `_cache_get()`, `_cache_set()` helper functions
- Remove the Redis import and `_get_redis()` function
- Remove the cache-check logic at the top of `_get_price_data`, `_get_sentiment`, `_get_news_summary`
- Remove the cache-set calls at the end of those functions

---

## Change 6: Reduced content sizes for articles and videos

**Files:** `api/articles/config.py`, `api/videos/config.py`

**What changed:**
- `ARTICLE_CONTENT_MAX_CHARS`: 3000 → 2000
- `TRANSCRIPT_MAX_CHARS`: 5000 → 3000

**Estimated savings:** ~$0.30-0.50/day (fewer input tokens per LLM call)

**How to revert:**
- In `api/articles/config.py`: change `ARTICLE_CONTENT_MAX_CHARS: int = 2000` back to `3000`
- In `api/videos/config.py`: change `TRANSCRIPT_MAX_CHARS: int = 3000` back to `5000`

---

## Quick Revert All (env vars, no code changes needed for items 2)

For Change 2 only, you can revert via environment variable without touching code:
```
SIGNAL_PARSE_MODEL=anthropic/claude-sonnet-4
```
Add this to your `.env` file and restart the signal-worker container.
