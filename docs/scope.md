# JobSignal — Scope (Sprint 1)

## 1. Product definition (one paragraph)

JobSignal helps applicants decide whether to invest time in a job posting by **verifying** it with **multiple explainable signals** (official-site alignment, bounded page fetch, search corroboration, duplication and staleness hints). It returns **`APPLY`**, **`VERIFY`**, or **`SKIP`** with **confidence**, **reasons**, and explicit **warnings** when evidence is thin—prioritizing **accuracy** and **honest uncertainty** over persuasive AI output.

## 2. In scope (MVP)

- Paste **job URL** and/or **job description**; receive structured **verdict** + **signals** + **cache** metadata.
- **Normalization** pipeline versioned and testable.
- **Global shared cache** for identical **public** normalized fingerprints; **TTL** 10–30 days (default 14).
- **Multi-tenant ready:** tenant id for limits/audit; **no** tenant-private fields in shared cache.
- **Source validation** via bounded fetch + hosted **search API** adapter (provider TBD at implementation).
- **Rule-first** scoring; optional LLM for structuring only (see `trust_model.md`).

## 3. Out of scope (explicit)

- Operating a **job board** or accepting employer job posts as product core.
- **Mass crawling** of the web beyond single-job fetch + search API usage.
- A **public blacklist** or defamation-style employer reputation product.
- Legal certainty claims (“this is a scam”) without human/legal review processes (not in MVP).
- Deep OSINT / invasive recruiter tracing beyond public snippet corroboration.

## 4. MVP acceptance themes (for later sprints)

- User always sees **why** VERIFY or low confidence.
- System **never** implies certainty the data does not support.
- **Deployment:** single API + external cache is enough for demo and small pilot.

## 5. Frozen scope statement (working — finalize in Sprint 4)

**Will do:** applicant-side verification recommendation for one job fingerprint using explainable signals, shared TTL cache for public inputs, tenant-safe separation, VERIFY-first under weak evidence.

**Will not do:** job hosting at scale, crawler platform, or public employer shaming lists.

## Related documents

- `architecture.md`, `trust_model.md`, `JOBSIGNAL-MASTER-PLAN.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 1 | Added `docs/scope.md` | Explicit in/out for hackathon scope control. |
