# Evidence-First Pipeline Architecture

## Current State
The pipeline currently normalizes inputs, fetches the primary URL, and passes the raw text to the LLM to generate `SignalEvidence`. The LLM is forced to "invent" signals from the raw text rather than evaluating concrete external evidence.

## New Architecture

### 1. Unified Extraction (`backend/core/extraction.py` update)
The extraction phase will precede evidence collection. It will aggressively extract:
- Company Name
- Role Title
- Location
- Posting URL
- Date
- Recruiter Name
(From screenshot OCR or provided text/URL metadata).

### 2. Evidence Bundle Builder (`backend/core/evidence.py`)
We will create a new evidence collection module that systematically gathers:
- **Source 1: Official Careers Page Fetch** (Using the extracted company name to query Serper or similar for the official careers page, then matching the role).
- **Source 2: Domain Search** (Site-specific search on the company domain for the role).
- **Source 3: Open Web Role Search** (Searching the exact title to find duplicates or reposts).
- **Source 4: Recruiter Identity** (Basic lookup or validation of the extracted recruiter name).

### 3. LLM Synthesis (`backend/core/llm_fireworks.py` update)
Instead of asking the LLM to find signals in raw text, the LLM prompt will be rewritten to:
- Take the extracted entities.
- Take the `Evidence Bundle` (results from the searches and fetches).
- Synthesize this concrete evidence into the strict `SignalEvidence` rows (T1/T2/T3).
- The LLM will *weigh* the evidence, not invent it.

### 4. Strict Scoring (`backend/core/scoring.py` update)
- Update thresholds to strictly enforce: No official source = VERIFY or SKIP.
- Remove debug language ("0/100").
- Ensure confidence is strictly tied to evidence strength.

### 5. Report Formatting (`backend/core/report.py` update)
- Ensure the user-facing report explicitly separates: What was checked, What matched, What did not match, Red flags, Sources, and a plain-English recommendation.

## Implementation Steps
1. **Refactor Extraction:** Update `extraction.py` to extract all required fields.
2. **Build Evidence Module:** Implement `evidence.py` to perform the structured searches and fetches.
3. **Update LLM Prompts:** Rewrite `llm_fireworks.py` to process the evidence bundle.
4. **Update Scoring & Report:** Refine `scoring.py` and `report.py` to meet the strict reporting requirements.
5. **Update Orchestrator:** Tie the new flow together in `orchestrator.py`.
6. **Tests & Docs:** Add the required test cases and update documentation.
