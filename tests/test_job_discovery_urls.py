"""Job discovery URL gate — organic candidates must look like real postings."""

from backend.core.job_discovery_urls import is_job_posting_discovery_candidate


def test_accepts_linkedin_job_view():
    assert is_job_posting_discovery_candidate("https://www.linkedin.com/jobs/view/340395")


def test_rejects_linkedin_company_page():
    assert not is_job_posting_discovery_candidate("https://www.linkedin.com/company/deloitte/")


def test_rejects_linkedin_pulse():
    assert not is_job_posting_discovery_candidate("https://www.linkedin.com/pulse/some-article")


def test_rejects_linkedin_jobs_search():
    assert not is_job_posting_discovery_candidate("https://www.linkedin.com/jobs/search?keywords=engineer")


def test_rejects_indeed_company():
    assert not is_job_posting_discovery_candidate("https://www.indeed.com/cmp/Acme-Corp")


def test_accepts_greenhouse_job():
    assert is_job_posting_discovery_candidate("https://boards.greenhouse.io/acme/jobs/123")


def test_accepts_lever_job():
    assert is_job_posting_discovery_candidate("https://jobs.lever.co/acme/uuid-here")


def test_accepts_myworkday_job():
    assert is_job_posting_discovery_candidate(
        "https://acme.wd103.myworkdayjobs.com/en-US/job/engineer_jr/JR123",
    )
