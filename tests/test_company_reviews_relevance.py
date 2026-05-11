"""Reputation SERP rows must reference the employer and real platforms."""

from backend.evidence.company_reviews import (
    _parse_serper_item,
    count_relevant_negative_hits,
    is_company_relevant,
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


def test_count_relevant_negative_hits_skips_results_without_company_name():
    results = [
        {
            "title": "Deloitte review roundup",
            "snippet": "Deloitte layoffs were discussed by former employees.",
        },
        {
            "title": "Generic scam alert",
            "snippet": "Job seekers warned about recruiter scam messages.",
        },
    ]
    assert count_relevant_negative_hits(results, ["layoffs", "scam"], "Deloitte") == 1
