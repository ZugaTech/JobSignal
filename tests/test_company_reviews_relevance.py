"""Reputation SERP rows must reference the employer and real platforms."""

from backend.evidence.company_reviews import (
    _parse_serper_item,
    is_company_relevant,
    is_relevant_negative_hit,
)


def test_x_query_news_about_twitter_rejected_for_unrelated_employer():
    item = {
        "title": "Twitter employees speak out after layoffs — NBC News",
        "snippet": "Twitter employees are speaking out on social media after layoffs, and some filed a class action lawsuit.",
        "link": "https://www.nbcnews.com/tech/twitter-layoffs-story",
    }
    assert _parse_serper_item(item, "x_layoffs", "sofatutor GmbH") is None


def test_glassdoor_row_kept_when_company_token_in_url():
    item = {
        "title": "Test Company Glassdoor Reviews",
        "snippet": "Rating: 4.5 - 100 reviews. Great place to work at Test Company.",
        "link": "https://www.glassdoor.com/Reviews/Test-Company-Reviews-E123.htm",
    }
    src = _parse_serper_item(item, "reviews_aggregate", "Test Company")
    assert src is not None
    assert src.platform == "Glassdoor"


def test_real_x_post_kept_when_domain_and_snippet_match():
    item = {
        "title": "sofatutor layoffs rumor?",
        "snippet": "Anyone know if sofatutor is hiring again after last year's cuts?",
        "link": "https://x.com/someuser/status/1234567890",
    }
    src = _parse_serper_item(item, "x_layoffs", "sofatutor")
    assert src is not None
    assert src.platform == "X/Twitter"


def test_is_company_relevant_filters_absent_company_name():
    result = {
        "title": "Recruiting scam alert",
        "snippet": "Job seekers should avoid generic recruiter scams this season.",
    }
    assert is_company_relevant(result, "Deloitte") is False


def test_is_relevant_negative_hit_requires_company_proximity():
    near = "Deloitte announced layoffs in one regional division during restructuring."
    far = "Deloitte hiring update. " + ("x" * 220) + " layoffs were discussed in the broader tech market."
    assert is_relevant_negative_hit(near, "layoffs", "Deloitte") is True
    assert is_relevant_negative_hit(far, "layoffs", "Deloitte") is False
