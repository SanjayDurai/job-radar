from radar.robots import RobotsRules

UA = "PersonalJobRadar/0.1 (personal job search)"

EIGHTFOLD = """
User-agent: *
Disallow: /
Allow: /$
Allow: /careers
Allow: /api/pcsx
"""


def test_longest_match_wins_over_order():
    r = RobotsRules(EIGHTFOLD)
    assert r.can_fetch(UA, "https://x.com/api/pcsx/search?domain=a.com")
    assert r.can_fetch(UA, "https://x.com/careers/job/1")
    assert r.can_fetch(UA, "https://x.com/")
    assert not r.can_fetch(UA, "https://x.com/internal/admin")


def test_wildcards_and_query_strings():
    r = RobotsRules("User-agent: *\nAllow: /\nDisallow: /search-and-apply/?keyword=\nDisallow: /*/externaljobs/*qtvc=\n")
    assert r.can_fetch(UA, "https://x.com/search-and-apply/")
    assert not r.can_fetch(UA, "https://x.com/search-and-apply/?keyword=ml")
    assert not r.can_fetch(UA, "https://x.com/en_US/externaljobs/foo?qtvc=1")
    assert r.can_fetch(UA, "https://x.com/en_US/externaljobs/foo")


def test_specific_agent_group_overrides_star():
    r = RobotsRules("User-agent: LinkedInBot\nAllow: /v1/companies/\n\nUser-agent: *\nDisallow: /\n")
    assert not r.can_fetch(UA, "https://api.x.com/v1/companies/acme/postings")
    assert r.can_fetch("LinkedInBot/1.0", "https://api.x.com/v1/companies/acme/postings")


def test_empty_disallow_allows_all_and_tie_goes_to_allow():
    assert RobotsRules("User-agent: *\nDisallow:\n").can_fetch(UA, "https://x.com/anything")
    assert RobotsRules("User-agent: *\nDisallow: /a\nAllow: /a\n").can_fetch(UA, "https://x.com/a")


def test_dollar_anchor():
    r = RobotsRules("User-agent: *\nDisallow: /\nAllow: /$\n")
    assert r.can_fetch(UA, "https://x.com/")
    assert not r.can_fetch(UA, "https://x.com/page")
