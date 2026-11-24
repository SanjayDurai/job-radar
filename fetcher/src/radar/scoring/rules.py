"""Layer 1: rule-based score (free, always on). Every point added or removed becomes a visible reason."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from radar.filters import AI_TITLE, check_location, check_title
from radar.profile import experience_years

# --- years of experience ----------------------------------------------------------------------------

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_N = r"(\d{1,2}(?:\.\d)?|one|two|three|four|five|six|seven|eight|nine|ten)"
_YRS = r"(?:years?|yrs?)"
_EXP_CONTEXT = re.compile(r"experience|exp\b|industry|professional|working|hands[- ]on|relevant|track record", re.I)
_NOT_EXPERIENCE = re.compile(r"^\W*(old|ago|of age|warranty|history|anniversary|in business|running)", re.I)
_YEAR_PATTERNS = [
    # "2-4 years", "3 to 5 yrs", "7 + to 10 years"
    (re.compile(_N + r"\s*(?:\+|plus)?\s*(?:-|–|—|to)\s*" + _N + r"\s*\+?\s*" + _YRS, re.I), False),
    # "minimum 3 years", "at least 2 years"
    (re.compile(r"(?:minimum|min\.?|at least)\s*(?:of\s*)?" + _N + r"\s*\+?\s*" + _YRS, re.I), False),
    # "3+ years", "5 plus years"
    (re.compile(_N + r"\s*(?:\+|plus)\s*" + _YRS, re.I), False),
    # "3 years of experience" (needs an experience word close by)
    (re.compile(_N + r"\s*" + _YRS, re.I), True),
]


def _to_num(s: str) -> float:
    return float(_NUM_WORDS.get(s.lower(), s))


def parse_years(text: str | None) -> float | None:
    """Smallest 'years of experience' the text asks for, or None.

    Postings often list a required minimum and a higher 'preferred' number; the minimum is what
    decides whether it's worth applying. Numbers about company age ("20 years old") are ignored.
    """
    if not text:
        return None
    found: list[float] = []
    taken: list[tuple[int, int]] = []
    for pattern, needs_context in _YEAR_PATTERNS:
        for m in pattern.finditer(text):
            if any(s <= m.start() < e for s, e in taken):
                continue  # already matched by a more specific pattern
            after = text[m.end() : m.end() + 80]
            before = text[max(0, m.start() - 60) : m.start()]
            if _NOT_EXPERIENCE.match(after) or re.search(r"(over the (past|last)|founded|for over|since)\s*$", before, re.I):
                continue
            if needs_context and not _EXP_CONTEXT.search(after[:60] + before[-25:]):
                continue
            low = _to_num(m.group(1))
            if 0 <= low <= 20:
                found.append(low)
                taken.append((m.start(), m.end()))
    return min(found) if found else None


# --- visa / relocation ------------------------------------------------------------------------------

_VISA_NEGATIVE = re.compile(
    r"(?:no|not|unable to|cannot|can't|won't|will not|do not|don't|does not|doesn't)\s+"
    r"(?:provide\s+|offer\s+)?(?:visa\s+)?sponsor"
    r"|without\s+(?:the\s+need\s+for\s+)?(?:visa\s+|employer\s+)?sponsorship|sponsorship\s+is\s+not\s+(?:available|offered)"
    r"|must\s+(?:already\s+)?(?:have|hold|possess)\s+(?:the\s+|a\s+)?(?:full\s+|existing\s+|valid\s+)?(?:right|authori[sz]ation|permit)\s+to\s+work"
    r"|existing\s+right\s+to\s+work|not\s+able\s+to\s+sponsor|unable\s+to\s+offer\s+sponsorship",
    re.I,
)
_VISA_POSITIVE = re.compile(
    r"visa\s+sponsorship(?:\s+is)?\s+(?:available|provided|offered|possible)|we\s+(?:will\s+|can\s+|do\s+)?sponsor"
    r"|sponsorship\s+(?:is\s+)?available|relocation\s+(?:support|assistance|package|bonus|allowance|provided)"
    r"|(?:we\s+)?(?:offer|provide)s?\s+relocation|help(?:ing)?\s+you\s+relocate|visa\s+support|work\s+permit\s+support"
    r"|relocation\s+to\s+\w+\s+(?:is\s+)?(?:provided|supported)|\(relocation provided\)",
    re.I,
)


def detect_visa(text: str) -> str:
    if _VISA_NEGATIVE.search(text):
        return "right_to_work_required"
    if _VISA_POSITIVE.search(text):
        return "sponsored"
    return "unknown"


# --- salary -----------------------------------------------------------------------------------------

_HOURS_PER_YEAR = 2080


def salary_to_lpa(
    smin: float | Decimal | None, smax: float | Decimal | None, currency: str | None, period: str | None,
    fx: dict[str, float],
) -> float | None:  # fmt: skip
    """Posted salary -> ₹ lakh per annum (uses the top of the range: it's what you could negotiate to)."""
    amount = smax or smin
    if not amount or not currency or currency.upper() not in fx:
        return None
    yearly = float(amount) * {"hour": _HOURS_PER_YEAR, "month": 12}.get(period or "year", 1)
    return round(yearly * fx[currency.upper()] / 100_000, 1)


# --- scoring ----------------------------------------------------------------------------------------

ENTRY_LEVEL = re.compile(
    r"\b(i|ii|1|2|associate|junior|jr\.?|entry|early career|new grad|graduate|level [12]|l[34]"
    r"|sde ?(?:i|ii|1|2)|mts ?[12]|e[34])\b",
    re.I,
)
PHD_REQUIRED = re.compile(r"\bph\.?d\b(?!\s*(?:is\s+)?(?:a\s+)?(?:plus|preferred|nice|bonus))", re.I)
AI_DESC = re.compile(r"machine learning|\bllms?\b|gen ?ai|generative|deep learning|\bnlp\b|agentic|ai models?|data scien", re.I)


@dataclass
class JobInput:
    title: str
    description: str | None
    location_text: str
    is_remote: bool = False
    salary_min: float | Decimal | None = None
    salary_max: float | Decimal | None = None
    salary_currency: str | None = None
    salary_period: str | None = None


@dataclass
class CompanyInput:
    region: str
    country: str
    priority: int


@dataclass
class RuleResult:
    score: int
    reasons: list[dict[str, Any]] = field(default_factory=list)  # [{"label": str, "points": int}]
    region_tag: str = "unknown"
    years_required: float | None = None
    visa_signal: str = "unknown"
    salary_lpa: float | None = None
    below_pay_bar: bool = False
    excluded: bool = False
    exclude_reason: str | None = None


def score_rules(
    job: JobInput, company: CompanyInput, cfg: dict[str, Any], profile: dict[str, Any], my_years: float | None = None
) -> RuleResult:
    pts = cfg["rule_points"]
    my_years = experience_years(career_start=profile["career_start"]) if my_years is None else my_years
    desc = job.description or ""
    text = f"{job.title}\n{desc}"
    reasons: list[dict[str, Any]] = []
    score = 0

    def add(label: str, points: int) -> None:
        nonlocal score
        score += points
        reasons.append({"label": label, "points": points})

    res = RuleResult(score=0)

    # Exclusions that no score can save. The title check re-runs here so that editing the
    # exclusion keywords in profile.yaml also applies to jobs stored earlier.
    tv = check_title(job.title)
    if not tv.ok:
        res.excluded, res.exclude_reason = True, tv.reason
    for phrase in profile.get("citizenship_restrictions", []):
        if res.excluded:
            break
        if re.search(rf"\b{re.escape(phrase)}(?:s|es)?\b", text, re.I):  # "UAE National(s)", "US citizen(s)"
            res.excluded, res.exclude_reason = True, f"restricted to citizens/nationals ('{phrase}')"
            break

    # Title
    ai_title = bool(AI_TITLE.search(job.title))
    if ai_title:
        add("AI/ML role in the title", pts["title_ai"])
    else:
        add("software engineering title", pts["title_generic"])
        if len(AI_DESC.findall(desc)) >= 3:
            add("description is AI/ML work", pts["generic_with_ai_description"])
    if ENTRY_LEVEL.search(job.title):
        add("entry/mid level in title", pts["entry_level_hint"])

    # Skills
    skill_pts, hits = 0, []
    for pattern, p in cfg.get("skill_terms", {}).items():
        m = re.search(pattern, desc, re.I)
        if m:
            skill_pts += p
            hits.append(m.group(0).strip().lower())
    if skill_pts:
        add(f"skills match: {', '.join(dict.fromkeys(hits))}", min(skill_pts, pts["skills_max"]))

    # Experience: years in the title (e.g. "(5+ yrs)") win over the description
    years = parse_years(job.title)
    years = years if years is not None else parse_years(desc)
    res.years_required = years
    if years is None:
        add("years of experience not stated", pts["years_unknown"])
    elif years >= cfg.get("exclude_if_years_at_least", 5):
        if not res.excluded:
            res.excluded, res.exclude_reason = True, f"asks {years:g}+ years of experience"
    else:
        gap = years - my_years
        points = next((row["points"] for row in pts["years_fit"] if gap <= row["max_gap"]), 0)
        verdict = "fits" if gap <= 0.5 else "a stretch" if gap <= 2 else "a big stretch"
        add(f"asks {years:g}+ years, you have {my_years:g} ({verdict})", points)

    # Location
    if job.location_text.strip():
        lv = check_location(job.location_text, company.region, company.country, job.is_remote)
        res.region_tag = lv.region_tag
        add(f"location: {lv.reason}", pts["location_match"] if lv.ok else 0)
        if company.region == "chennai" and lv.region_tag == "chennai":
            add("in Chennai", pts["chennai_bonus"])
    else:
        add("location not stated", pts["location_unknown"])

    # Visa / relocation (matters for abroad roles)
    res.visa_signal = detect_visa(text)
    if company.region == "abroad" or res.region_tag == "abroad":
        if res.visa_signal == "sponsored":
            add("mentions visa sponsorship / relocation", pts["visa_sponsorship"])
        elif res.visa_signal == "right_to_work_required":
            add("requires existing right to work", pts["right_to_work_required"])

    if PHD_REQUIRED.search(job.title) or re.search(r"ph\.?d\.?\s+(?:is\s+)?required|must\s+have\s+a\s+ph\.?d", desc, re.I):
        add("PhD required", pts["phd_required"])

    # Pay: only when the posting shows a salary
    res.salary_lpa = salary_to_lpa(job.salary_min, job.salary_max, job.salary_currency, job.salary_period, cfg["fx_to_inr"])
    if res.salary_lpa is not None:
        floors = profile["pay_floor_lpa"]
        tag = res.region_tag if res.region_tag in floors else ("india_remote" if res.region_tag == "remote" else company.region)
        floor = floors.get(tag, floors.get(company.region, 0))
        if res.salary_lpa < floor:
            res.below_pay_bar = True
            reasons.append({"label": f"posted pay ≈ ₹{res.salary_lpa:g} LPA, below your ₹{floor} LPA bar", "points": 0})
        else:
            reasons.append({"label": f"posted pay ≈ ₹{res.salary_lpa:g} LPA (meets ₹{floor} LPA bar)", "points": 0})

    res.score = max(0, min(100, score))
    res.reasons = reasons
    return res


def final_score(rule: RuleResult, llm_score: int | None, priority: int, cfg: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Blend rule + LLM, add the priority boost, apply the pay-bar penalty. Returns (score, extra reasons)."""
    extra: list[dict[str, Any]] = []
    if llm_score is None:
        score = float(rule.score)
    else:
        b = cfg["final_blend"]
        score = b["rule_weight"] * rule.score + b["llm_weight"] * llm_score
        extra.append(
            {"label": f"blend: {b['rule_weight']:g}×rules {rule.score} + {b['llm_weight']:g}×LLM {llm_score}", "points": 0}
        )
    boost = int(cfg.get("priority_boost", {}).get(priority, 0))
    if boost:
        score += boost
        extra.append({"label": f"P{priority} company", "points": boost})
    if rule.below_pay_bar:
        mult = cfg.get("below_pay_bar_multiplier", 0.4)
        extra.append({"label": f"below pay bar (×{mult})", "points": int(score * mult - score)})
        score *= mult
    return max(0, min(100, round(score))), extra
