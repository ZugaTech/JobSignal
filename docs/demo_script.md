# JobSignal — Demo Script

**Goal:** Demonstrate the "Accuracy-First" verification pipeline, from screenshot ingestion to similar-job recommendations, with a focus on **honesty** and **explainability**.

---

## 1) Setup (Pre-Demo)
1. **Reset State:** Refresh the browser at `http://localhost:8080`.
2. **Configuration:** Ensure `.env` has `ENABLE_JOB_FETCH=1` and `RECOMMENDATIONS_ENABLED=1`.
3. **Environment:** If using fixtures for a offline demo, set `NODE_ENV=development`.

---

## 2) The "Safe Match" Path (URL + Trust)
**Narrative:** *"Imagine you found a job on a social media post. It looks legit, but you want to be sure. You paste the URL into JobSignal."*

1. **Input:** Paste a known official URL (e.g., `https://careers.google.com/...`).
2. **Action:** Click **Verify**.
3. **Observation:**
   - Watch the **Pipeline Timeline** move from `Normalize` → `Fetch` → `Evidence` → `Score`.
   - Result shows **APPLY (High Confidence)**.
   - Expand the **Signals** table to show `fetch_ok` and `domain_align` (T1 evidence).
   - Show the **Verdict Card** highlights.

---

## 3) The "Uncertain" Path (Blurry Screenshot)
**Narrative:** *"Sometimes you only have a screenshot from a friend. Let's see how JobSignal handles low-quality input."*

1. **Input:** Upload a blurry or cropped screenshot.
2. **Action:** Click **Verify**.
3. **Observation:**
   - The UI shows an **Insufficient Data** warning.
   - Message: *"Screenshot doesn’t contain enough readable job details—please paste the job URL (preferred) or paste the full job text."*
   - **Key Point:** *"We don't guess. If the OCR isn't confident, we tell the user to provide more context."*

---

## 4) The "Multimodal" Path (Clear Screenshot)
**Narrative:** *"Now, let's try a clear screenshot of a LinkedIn posting."*

1. **Input:** Upload a high-resolution screenshot of a job posting.
2. **Action:** Click **Verify**.
3. **Observation:**
   - Ingestion note shows **Extraction Confidence: High**.
   - Pipeline Timeline shows the extraction steps.
   - Result shows **VERIFY** (Medium Confidence) because we have the text but haven't cross-checked the live URL yet.
   - Explain the **Uncertainty Strip**: *"We're not fully confident yet—confirm on the employer's official careers page."*

---

## 5) The "Honest Recommendations" Path
**Narrative:** *"While you're here, JobSignal can help you find similar, already-verified jobs."*

1. **Action:** Scroll down to the **Similar Jobs** section.
2. **Observation:**
   - Show the **High** and **Medium** confidence badges on the cards.
   - Explain that each recommendation has been through the **same verification pipeline** before appearing here.
   - *"We aren't just a job board; we only recommend what we can verify."*

---

## 6) Conclusion
**Narrative:** *"JobSignal isn't about giving you a green light every time. It's about giving you the evidence to make a safe decision. No fabricated data, no false certainties. Just honest verification."*
