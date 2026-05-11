"""Reputation SERP rows must reference the employer and real platforms (no query-key misclassification)."""

from backend.evidence.company_reviews import _parse_serper_item


def test_x_query_news_about_twitter_rejected_for_unrelated_employer():
    item = {
        "title": "Twitter employees speak out after layoffs — NBC News",
        "snippet": "Twitter employees are speaking out on social media after layoffs, and some filed a class action lawsuit.",
        "link": "https://www.nbcnews.com/tech/twitter-layoffs-story",
    }
    assert _parse_serper_item(item, "x_layoffs", "sofatutor GmbH") is None


def test_glassdoor_row_kept_when_company_token_in_url():
    item = {
        "title": "Glassdoor Reviews",
        "snippet": "Rating: 4.5 - 100 reviews. Great place to work.",
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
