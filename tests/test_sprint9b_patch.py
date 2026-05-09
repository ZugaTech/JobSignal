import pytest
import asyncio
from backend.evidence.company_reviews import (
    _process_reddit,
    _process_x,
    _template_summary,
    ReviewSource
)

def test_reddit_positive_mention_increment():
    # Green flag trigger "great culture" should increment pos count even if sentiment is neutral
    source = ReviewSource(
        platform="Reddit", rating=None, review_count=None, sentiment="neutral",
        snippet="They have a great culture overall.", reliability="medium", post_title="Review"
    )
    res = _process_reddit([source])
    assert res is not None
    assert res["positive_mentions"] == 1
    assert "great culture" in res["green_flags_found"]

def test_x_positive_mention_corroboration():
    # Needs at least 2 occurrences
    source1 = ReviewSource(
        platform="X/Twitter", rating=None, review_count=None, sentiment="neutral",
        snippet="Pays well and good benefits.", reliability="low", post_title=""
    )
    res1 = _process_x([source1])
    assert "pays well" not in res1["green_flags_found"]
    
    source2 = ReviewSource(
        platform="X/Twitter", rating=None, review_count=None, sentiment="positive",
        snippet="I agree it pays well.", reliability="low", post_title=""
    )
    res2 = _process_x([source1, source2])
    assert "pays well" in res2["green_flags_found"]

def test_plain_summary_template_new_format():
    # New pattern: Based on {sources_found} sources, {company_name} has a {overall_sentiment} employer reputation. {top_green_flag if exists, else 'No strong positive signals were found.'}.
    res = _template_summary("Acme", 5, "mostly positive", "Great culture", None)
    assert res == "Based on 5 sources, Acme has a mostly positive employer reputation. Great culture."
    
    # If red exists, it is appended
    res_red = _template_summary("Acme", 5, "mostly negative", None, "High turnover")
    assert res_red == "Based on 5 sources, Acme has a mostly negative employer reputation. No strong positive signals were found. High turnover."
    
    # If nothing exists, it uses the green fallback
    res_none = _template_summary("Acme", 5, "mixed", None, None)
    assert res_none == "Based on 5 sources, Acme has a mixed employer reputation. No strong positive signals were found."

def test_fallback_green_flag():
    # Mostly positive sentiment but no triggers hit
    source = ReviewSource(
        platform="Reddit", rating=None, review_count=None, sentiment="positive",
        snippet="Everything is awesome.", reliability="medium", post_title="Review"
    )
    res = _process_reddit([source])
    assert "Positive employer sentiment found on Reddit" in res["green_flags_found"]
