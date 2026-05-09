"""Regression: job URLs with long query strings must not false-positive as SQL injection."""

from backend.core.url_preflight import validate_url_format

LINKEDIN_TRACKING_URL = (
    "https://www.linkedin.com/jobs/view/4403231467/?alternateChannel=search"
    "&eBP=CwEAAAGeDKwlcovpRhg5UV0oxAY598QzeeJRFeKffNub0NmCI-l6vIwrKgdkEt8G1XIjSM2-ocXvgm20SwOEQVuvjABVS7N_Cpeq07i0q9jN9H3EewC1So7qLkSpgNKYIYmDFqRZg5BCb2BrrumZUvwOYowNEKwoQpMz9n1EF7egomXVFNOIQ4qVeicE7dN4iQp-Hzntvy6z6Jc1-UCs1wlpP7pP6L1DxbetuH-vTXNt--WsUg8u6_srJ4Wh9cjdz4tn74oFCS7wAldmDN_KPc0_8zEbCUDyo7UOFR3elIuDTSJ_ob6hTaKbcUiskKMsph4D76XpO4yDc-0YbblIXyLOb69k2w2U482tp4vOKJN3LfxPYL0obQCtCcsAYe0YPQom5Gl40Qfa1TSMwcgLMFlshzV7OIR5EmdCefkzofJpC9flT2YJ_GoBi7649yeYNabP3Oo9w4go5roWA9H9Toz4m3KX1uUj5EAtTw6EH1c"
    "&refId=a1A41ji5xBcWFA%2FOExOERg%3D%3D&trackingId=u%2Bl0xxE709oGIxTBv7XOMA%3D%3D"
)


def test_linkedin_job_url_with_tracking_query_not_rejected():
    assert validate_url_format(LINKEDIN_TRACKING_URL) is None


def test_plain_https_job_path_accepted():
    assert validate_url_format("https://www.linkedin.com/jobs/view/12345/") is None


def test_union_select_in_path_still_rejected():
    bad = "https://evil.example/hack/union%20select%201"
    assert validate_url_format(bad) is not None


def test_double_hyphen_only_in_query_does_not_reject():
    assert validate_url_format("https://jobs.example.com/posting?token=ab--cd") is None
