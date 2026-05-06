# JobSignal — Final scope freeze (Sprint 4)

**Effective:** 2026-05-04 (working freeze for hackathon / pilot). Changes after this require an explicit **version bump** and **ADR**.

## Will ship (in scope)

- Applicant-side **verification recommendation** for a **single job fingerprint** (URL and/or pasted description).
- **Rule-first** scoring with **VERIFY-first** behavior under weak evidence (`docs/decision_logic.md`).
- **Explainable signals** and **warnings**; **no false certainty** in UI copy requirements (`docs/frontend_flow.md`).
- **Global shared cache** for identical **public** normalized inputs with **TTL** (10–30 days, default 14) and **versioned keys** (`docs/cache_design.md`).
- **Multi-tenant-safe** separation: tenant metadata **not** in shared cache payload (`docs/security.md`).
- **Minimal static UI** for demo (`frontend/`) and **pytest** coverage for core logic.
- **Hardened inputs**, **env validation (strict mode)**, **health payloads**, and **prompt-injection risk assessment** utilities.

## Will not ship (out of scope)

- A **job board**, mass **crawler**, or employer **public blacklist / defamation** surface.
- Legal claims of fraud/scam without human/legal process.
- Full managed cloud IaC in-repo (documented checklists only).
- Full production API server implementation in this repository (readiness docs and health **contracts** are in scope; vendor-specific wiring remains integration work).

## Success criteria (honesty)

- The product can **always** explain why **VERIFY** was returned.
- **APPLY** cannot trigger without passing documented gates (Sprint 3 scorer + Sprint 4 input gates).

## Related documents

- `scope.md`, `JOBSIGNAL-MASTER-PLAN.md`, `PROGRESS-LOG.md`

## Change log

| Date | Change | Why |
|------|--------|-----|
| Sprint 4 | Frozen scope statement | Sprint 4 deliverable. |
| 2026-05-06 | Optional screenshot input + vision extraction (see `docs/scope_addendum_2026-05-06.md`) | Sprint 5 / vNext multimodal plan |
