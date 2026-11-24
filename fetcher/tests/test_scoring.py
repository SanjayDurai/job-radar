from __future__ import annotations

import json

import pytest

from radar.scoring.llm import LLMScorer, LLMUnavailable, content_hash, validate
from radar.scoring.rules import (
    CompanyInput,
    JobInput,
    detect_visa,
    final_score,
    parse_years,
    salary_to_lpa,
    score_rules,
)
from radar.settings import profile, scoring

# --- years parsing ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,years",
    [
        ("3+ years of experience in Python", 3),
        ("We need 2-4 years of relevant experience", 2),
        ("Minimum 3 years of hands-on experience", 3),
        ("at least two years of professional experience", 2),
        ("Basic: 1+ years of experience. Preferred: 5+ years of experience", 1),
        ("Software Engineer | Bangalore | 7 + to 10 years", 7),
        ("Data Scientist (10-15yrs)exp", 10),
        ("5 plus years in industry", 5),
        ("4 years of experience with ML systems", 4),
    ],
)
def test_parse_years(text, years):
    assert parse_years(text) == years


@pytest.mark.parametrize(
    "text",
    [
        "Founded 20 years ago, we are a leader",
        "Over the past 15 years we have grown",
        "a 3 year warranty on all devices",
        "No experience requirement mentioned here",
        "",
        None,
    ],
)
def test_parse_years_ignores_non_experience(text):
    assert parse_years(text) is None


def test_plain_years_need_experience_context():
    assert parse_years("Our 10 years in fintech") is None
    assert parse_years("You have 2 years of experience building APIs") == 2


# --- visa ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,signal",
    [
        ("Visa sponsorship is available for this role.", "sponsored"),
        ("We offer relocation support to Amsterdam.", "sponsored"),
        ("Bangkok-based, Relocation Provided", "sponsored"),
        ("We are unable to offer sponsorship for this position.", "right_to_work_required"),
        ("You must have the right to work in the UK.", "right_to_work_required"),
        ("We do not sponsor visas.", "right_to_work_required"),
        ("Candidates must be eligible to work without sponsorship.", "right_to_work_required"),
        ("Great team and free lunch.", "unknown"),
    ],
)
def test_detect_visa(text, signal):
    assert detect_visa(text) == signal


# --- salary -------------------------------------------------------------------------------------------

FX = {"INR": 1, "USD": 88, "AED": 24, "EUR": 102}


def test_salary_to_lpa():
    assert salary_to_lpa(2_000_000, 3_000_000, "INR", "year", FX) == 30.0
    assert salary_to_lpa(25000, 35000, "AED", "month", FX) == 100.8  # 35000*12*24 / 1e5
    assert salary_to_lpa(50, None, "USD", "hour", FX) == 91.5  # 50*2080*88 / 1e5
    assert salary_to_lpa(None, None, "INR", "year", FX) is None
    assert salary_to_lpa(100, 200, "XYZ", "year", FX) is None


# --- full rule score ----------------------------------------------------------------------------------

CFG = scoring()
PROFILE = profile()


def rules(title, desc="", loc="Chennai, India", region="chennai", country="India", priority=2, **salary):
    return score_rules(
        JobInput(title=title, description=desc, location_text=loc, **salary),
        CompanyInput(region=region, country=country, priority=priority),
        CFG,
        PROFILE,
        my_years=1.3,
    )


def labels(res):
    return " | ".join(r["label"] for r in res.reasons)


def test_strong_chennai_ai_job_scores_high_with_reasons():
    r = rules("Machine Learning Engineer I", "Build LLM agents in Python on AWS Lambda. 1+ years of experience.")
    assert not r.excluded
    assert r.score >= 85
    assert r.region_tag == "chennai" and r.years_required == 1
    for expected in ("AI/ML role in the title", "skills match", "fits", "in Chennai"):
        assert expected in labels(r)


def test_ai_title_beats_generic_title():
    ai = rules("AI Engineer", "Python")
    generic = rules("Software Engineer", "Python")
    assert ai.score > generic.score


def test_generic_title_gets_credit_for_ai_description():
    plain = rules("Software Engineer", "Build web APIs in Java.")
    ai_work = rules("Software Engineer", "Machine learning platform. Work with LLMs and generative models, deep learning, NLP.")
    assert ai_work.score > plain.score
    assert "description is AI/ML work" in labels(ai_work)


def test_years_score_relative_to_my_experience():
    one = rules("Data Scientist", "1+ years of experience")
    three = rules("Data Scientist", "3+ years of experience")
    four = rules("Data Scientist", "4+ years of experience")
    assert one.score > three.score > four.score
    assert "a stretch" in labels(three)


def test_five_plus_years_is_excluded():
    r = rules("Data Scientist", "5+ years of experience required")
    assert r.excluded and "5+" in r.exclude_reason


def test_title_years_override_description():
    r = rules("Software Engineer (5+ yrs)", "1+ years of experience")
    assert r.excluded


def test_citizenship_restriction_excluded():
    r = rules("AI Engineer", "This role is open to UAE Nationals only.", loc="Dubai, UAE", region="abroad", country="UAE")
    assert r.excluded and "uae national" in r.exclude_reason


def test_senior_title_excluded_at_scoring_time():
    assert rules("Senior Data Scientist").excluded
    assert rules("Forward Deployed Engineer V, GenAI").excluded


def test_abroad_visa_signals():
    base = dict(loc="Amsterdam, Netherlands", region="abroad", country="Netherlands")
    sponsored = rules("ML Engineer", "Visa sponsorship is available.", **base)
    neutral = rules("ML Engineer", "Nice team.", **base)
    rtw = rules("ML Engineer", "You must have the right to work in the Netherlands.", **base)
    assert sponsored.score > neutral.score > rtw.score
    assert sponsored.visa_signal == "sponsored" and rtw.visa_signal == "right_to_work_required"


def test_visa_ignored_for_india_roles():
    a = rules("ML Engineer", "Visa sponsorship is available.")
    b = rules("ML Engineer", "Nice team.")
    assert a.score == b.score


def test_unknown_location_gets_partial_points():
    r = rules("ML Engineer", "", loc="")
    assert "location not stated" in labels(r) and r.region_tag == "unknown"


def test_phd_required_penalty():
    assert rules("Software Engineer, PhD, Early Career").score < rules("Software Engineer, Early Career").score


def test_below_pay_bar_flag_and_final_penalty():
    low = rules("ML Engineer", "", loc="Bengaluru, India", region="india_other",
                salary_min=800000, salary_max=1200000, salary_currency="INR", salary_period="year")  # fmt: skip
    ok = rules("ML Engineer", "", loc="Bengaluru, India", region="india_other",
               salary_min=2000000, salary_max=2600000, salary_currency="INR", salary_period="year")  # fmt: skip
    assert low.below_pay_bar and low.salary_lpa == 12.0
    assert not ok.below_pay_bar
    low_final, extra = final_score(low, None, 2, CFG)
    ok_final, _ = final_score(ok, None, 2, CFG)
    assert low_final < ok_final * 0.5
    assert any("below pay bar" in e["label"] for e in extra)


def test_chennai_floor_is_lower_than_other_city():
    # ₹16 LPA: fine for a Chennai job (floor 15), below the bar in another city (floor 20)
    chennai = rules("ML Engineer", "", salary_min=1600000, salary_currency="INR", salary_period="year")
    blr = rules("ML Engineer", "", loc="Bengaluru, India", region="india_other",
                salary_min=1600000, salary_currency="INR", salary_period="year")  # fmt: skip
    assert not chennai.below_pay_bar and blr.below_pay_bar


def test_final_blend_and_priority_boost():
    r = rules("ML Engineer", "Python")
    rule_only, _ = final_score(r, None, 3, CFG)
    assert rule_only == r.score
    p1, extra = final_score(r, None, 1, CFG)
    assert p1 == min(100, r.score + CFG["priority_boost"][1])
    blended, extra = final_score(r, 90, 3, CFG)
    b = CFG["final_blend"]
    assert blended == round(b["rule_weight"] * r.score + b["llm_weight"] * 90)
    assert any("blend" in e["label"] for e in extra)


# --- LLM layer (no network) ---------------------------------------------------------------------------


def test_validate_normalises_llm_json():
    raw = json.dumps({"score": 81.6, "fit_summary": "Good GenAI fit.", "why_match": "Python + LLMs",
                      "gaps": ["a", "b", "c", "d"], "seniority_ok": True, "visa_sponsorship": "YES",
                      "est_years_required": "2"})  # fmt: skip
    d = validate(raw)
    assert d["score"] == 82 and d["why_match"] == ["Python + LLMs"] and len(d["gaps"]) == 3
    assert d["visa_sponsorship"] == "yes" and d["est_years_required"] == 2.0


@pytest.mark.parametrize("raw", ["not json", "[1,2]", '{"score": 140}', '{"fit_summary": "no score"}'])
def test_validate_rejects_bad_output(raw):
    with pytest.raises((ValueError, KeyError)):
        validate(raw)


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        assert kwargs["response_format"] == {"type": "json_object"}
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply

        class Msg:
            content = reply

        class Choice:
            message = Msg()

        class Resp:
            choices = [Choice()]

        return Resp()


class FakeClient:
    def __init__(self, replies):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(replies)


GOOD = json.dumps({"score": 77, "fit_summary": "x", "why_match": [], "gaps": [], "seniority_ok": True,
                   "visa_sponsorship": "unknown", "est_years_required": None})  # fmt: skip


def make_scorer(replies, max_calls=5):
    cfg = {**CFG, "llm": {**CFG["llm"], "max_calls_per_run": max_calls, "min_seconds_between_calls": 0}}
    s = LLMScorer(cfg, PROFILE, client=FakeClient(replies))
    return s


def test_llm_scorer_respects_call_cap(monkeypatch):
    monkeypatch.delenv("LLM_MAX_CALLS_PER_RUN", raising=False)
    s = make_scorer([GOOD, GOOD, GOOD], max_calls=2)
    kw = dict(company="Acme", country="India", title="ML Engineer", location="Chennai", description="d")
    assert s.score(**kw).score == 77
    assert s.score(**kw).score == 77
    with pytest.raises(LLMUnavailable):
        s.score(**kw)


def test_llm_daily_limit_stops_the_run(monkeypatch):
    monkeypatch.delenv("LLM_MAX_CALLS_PER_RUN", raising=False)

    class RateLimitError(Exception):
        pass

    s = make_scorer([RateLimitError("Rate limit reached ... tokens per day (TPD): Limit 100000")])
    with pytest.raises(LLMUnavailable):
        s.score(company="A", country="I", title="t", location="l", description="d")
    assert not s.available and "daily" in s.stopped_reason


def test_content_hash_changes_with_description():
    assert content_hash("m", "t", "a") != content_hash("m", "t", "b")
    assert content_hash("m", "t", "a") == content_hash("m", "t", "a")
