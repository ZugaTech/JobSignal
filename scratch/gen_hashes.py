import hashlib
import unicodedata
import re
from typing import Optional

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def normalize_job_url(s: str) -> str:
    # Minimal canonicalization for hash generation
    s = s.strip()
    return _sha256_hex(s.encode("utf-8"))

def normalize_job_text(raw: str) -> str:
    nfkc = unicodedata.normalize("NFKC", raw)
    full_bytes = nfkc.encode("utf-8")
    return _sha256_hex(full_bytes)

# Case 1: Google Software Engineer
u1 = "https://www.google.com/about/careers/applications/jobs/results/12345-software-engineer"
t1 = "Software Engineer at Google. Experience with Python and distributed systems."
print(f"Google URL Hash: {normalize_job_url(u1)}")
print(f"Google Text Hash: {normalize_job_text(t1)}")

# Case 2: Suspect Remote Role
u2 = "https://bit.ly/suspect-job-123"
t2 = "Urgent hire! Work from home. $5000/week. No experience needed. Telegram @scammy."
print(f"Suspect URL Hash: {normalize_job_url(u2)}")
print(f"Suspect Text Hash: {normalize_job_text(t2)}")

# Case 3: LinkedIn Post
u3 = "https://www.linkedin.com/jobs/view/999888777/"
t3 = "Senior Product Manager at Acme Corp. Join our dynamic team."
print(f"Acme URL Hash: {normalize_job_url(u3)}")
print(f"Acme Text Hash: {normalize_job_text(t3)}")
