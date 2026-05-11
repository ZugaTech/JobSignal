# JobSignal: Day 4 Engineering & Debugging Log

A log of real-world "war stories" from today's push to move from a demo engine to a production-ready workflow tool.

## 1. The "Ghost Signals" Bug (Async Loop Nesting)
- **Symptom**: Pasting different job links resulted in the exact same "Insufficient Data" report every time.
- **The Bug**: Inside the FastAPI backend, an event loop is already running. Our evidence collection was trying to call `asyncio.run()`, which is illegal in a running loop. Instead of crashing, it was silently catching the error and returning an empty signal set `{}`.
- **The Fix**: Wrapped the evidence collection in a `ThreadPoolExecutor`. By running the async search queries in a worker thread, they get a fresh event loop that doesn't clash with the main ASGI loop.
- **Lesson**: Don't trust a `try/except` block that might be hiding a critical architectural clash.

## 2. The "Honest Uncertainty" Parsing Issue
- **Symptom**: LLM-derived signals were intermittently failing with `LLM_MALFORMED`.
- **The Bug**: Smaller models often add helpful preambles like "Here is your JSON:" or closing remarks. Standard `json.loads()` crashes on this extra text.
- **The Fix**: Implemented a "greedy JSON extractor" in `llm_fireworks.py` that scans for the first `{` and the last `}`.
- **Lesson**: Post-processing AI output requires more than just a parser; it needs a robust extractor.

## 3. The "Key Confusion" Adapter Shift
- **Symptom**: Search API returning `401 Unauthorized` even with a fresh key.
- **The Bug**: The system was built for SerpApi (GET + params), but the user provided a Serper.dev key (POST + headers).
- **The Fix**: Pivoted the entire search adapter layer. Built a native Serper provider that handles POST requests and `X-API-KEY` headers. Renamed internal functions globally to reflect the move to Serper.
- **Lesson**: API standardizations (like SERP) aren't always standard. Check the headers first.

## 4. The "Batch Mode" Scoping Crash
- **Symptom**: "ReferenceError: file is not defined" in the browser console.
- **The Bug**: During the Sprint 8 UI expansion (Batch Mode), duplicated function definitions in `app.js` caused variable scoping to break. The `file` object (screenshot) wasn't being passed correctly to the unified `runFlow`.
- **The Fix**: Performed a full "clean-room" rewrite of `app.js`, ensuring a single source of truth for the verification flow and strict input handling.
- **Lesson**: UI state grows exponentially. Keep the core logic isolated from the tab-switching logic.

## 5. Extension Scraper Handshake
- **Symptom**: One-click verification from the browser extension wasn't populating the report.
- **The Bug**: The extension didn't have a way to quickly verify if a URL was a valid job posting before triggering the heavy backend flow.
- **The Fix**: Implemented a lightweight `/v1/classify-url` endpoint that uses regex pattern matching to "warm up" the extension's logic before the deep-dive analysis starts.
- **Lesson**: Build small, cheap endpoints to support the heavy, expensive ones.
