"""Cheap pre-filter on title + location, run before fetching full descriptions.

It is deliberately a little permissive; Phase-3 scoring (rules + optional LLM) does the fine sorting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from radar.settings import profile

# --- title ------------------------------------------------------------------------------------------

AI_TITLE = re.compile(
    r"\b(ai|a\.i\.|ml|genai|gen ai|llms?|nlp|mlops|llmops|aiml|ai/ml|ml/ai)\b"
    r"|machine learning|deep learning|artificial intelligence|generative|agentic|\bagents?\b|data scien"
    r"|applied scien|research scien|computer vision|python|prompt engineer|conversational|intelligent automation"
    r"|ai automation|rag\b",
    re.I,
)
GENERIC_SWE_TITLE = re.compile(
    r"software (development |dev )?engineer|software developer|\bsde\b|\bswe\b|member of technical staff|\bmts\b"
    r"|backend engineer|back-end engineer|automation engineer|engineer i\b|engineer ii\b|engineer 1\b|engineer 2\b"
    r"|associate engineer|graduate engineer|product engineer|platform engineer",
    re.I,
)
TOO_SENIOR_LEVEL = re.compile(
    r"\b(iii|iv|vi|engineer [3-9]|scientist [3-9]|sde ?[3-9]|l[5-9]|e[5-9]|ic[4-9]|mts ?[3-9]|level [4-9])\b"
    r"|\b(engineer|scientist|developer|analyst)\s+v\b",  # "Engineer V" = senior level at Google & others
    re.I,
)
ALLOWED_PHRASES = re.compile(
    r"member of (the )?technical staff"  # contains "staff" but is an entry level at many firms
    r"|\((senior|sr\.?)\)",  # "(Senior) Engineer" = junior or senior, common in German job ads
    re.I,
)


@lru_cache
def _exclusion_re() -> re.Pattern[str]:
    p = profile()
    words = [*p.get("exclude_title_keywords", []), *p.get("exclude_functions", [])]
    alts = "|".join(re.escape(w.strip().rstrip(".")) + (r"\.?" if w.strip().endswith(".") else "") for w in words if w.strip())
    return re.compile(rf"\b({alts})\b", re.I)


@dataclass
class TitleVerdict:
    ok: bool
    reason: str
    ai_title: bool = False  # True: AI/ML in the title; False: generic SWE title (scored lower later)


def check_title(title: str) -> TitleVerdict:
    t = ALLOWED_PHRASES.sub(" ", title)
    m = _exclusion_re().search(t)
    if m:
        return TitleVerdict(False, f"excluded keyword '{m.group(0)}' in title")
    m = TOO_SENIOR_LEVEL.search(t)
    if m:
        return TitleVerdict(False, f"too-senior level '{m.group(0)}' in title")
    if AI_TITLE.search(title):
        return TitleVerdict(True, "AI/ML title", ai_title=True)
    if GENERIC_SWE_TITLE.search(title):
        return TitleVerdict(True, "software engineering title", ai_title=False)
    return TitleVerdict(False, "title doesn't match target roles")


# --- location ---------------------------------------------------------------------------------------

COUNTRY_TERMS: dict[str, list[str]] = {
    "india": ["india", "ind", "bengaluru", "bangalore", "chennai", "hyderabad", "pune", "mumbai", "gurugram", "gurgaon",
              "noida", "delhi", "new delhi", "kolkata", "ahmedabad", "kochi", "coimbatore", "trivandrum",
              "thiruvananthapuram", "jaipur", "mysore", "mysuru", "chandigarh", "indore", "karnataka", "tamil nadu",
              "telangana", "maharashtra", "haryana"],
    "uae": ["united arab emirates", "uae", "u.a.e", "dubai", "abu dhabi", "sharjah", "are"],
    "singapore": ["singapore", "sgp"],
    "thailand": ["thailand", "bangkok", "tha"],
    "netherlands": ["netherlands", "the netherlands", "holland", "amsterdam", "eindhoven", "veldhoven", "rotterdam",
                    "utrecht", "the hague", "delft", "nld"],
    "germany": ["germany", "deutschland", "berlin", "munich", "münchen", "muenchen", "hamburg", "frankfurt", "cologne",
                "köln", "aachen", "erlangen", "nuremberg", "nürnberg", "stuttgart", "deu"],
    "uk": ["united kingdom", "uk", "u.k.", "england", "scotland", "london", "manchester", "cambridge", "edinburgh",
           "bristol", "hatfield", "leeds", "gbr", "great britain"],
    "ireland": ["ireland", "dublin", "cork", "irl"],
    "canada": ["canada", "toronto", "vancouver", "montreal", "montréal", "ottawa", "waterloo", "calgary", "can"],
    "australia": ["australia", "sydney", "melbourne", "brisbane", "perth", "aus"],
    "japan": ["japan", "tokyo", "osaka", "fukuoka", "jpn"],
}  # fmt: skip
REMOTE_RE = re.compile(r"\bremote\b|work from home|\bwfh\b|anywhere|distributed", re.I)
REMOTE_INDIA_FRIENDLY = re.compile(r"india|apac|asia|emea|worldwide|global|anywhere|international", re.I)
REMOTE_RESTRICTED = re.compile(
    r"\b(us|usa|united states|americas|north america|canada|uk|united kingdom|europe|eu|latam|brazil|mexico)\b(?!.*india)",
    re.I,
)


def country_key(sheet_country: str) -> str | None:
    s = sheet_country.lower()
    for key in COUNTRY_TERMS:
        if key in s or (key == "uk" and "kingdom" in s) or (key == "uae" and "emirates" in s):
            return key
    return None


@lru_cache
def _country_re(key: str) -> re.Pattern[str]:
    terms = sorted(COUNTRY_TERMS[key], key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(t) for t in terms) + r")(?![\w])", re.I)


def mentions_country(text: str, key: str) -> bool:
    return bool(_country_re(key).search(text))


OTHER_PLACES = re.compile(
    r"\b(united states|usa|u\.s\.|china|taiwan|korea|hong kong|israel|poland|spain|france|italy|portugal|mexico|brazil|"
    r"argentina|egypt|pakistan|turkey|vietnam|philippines|malaysia|indonesia|san francisco|new york|seattle|austin|"
    r"san diego|boston|chicago|los angeles|wilton|phoenix|toronto)\b",
    re.I,
)


def mentions_any_place(text: str) -> bool:
    return bool(OTHER_PLACES.search(text)) or any(mentions_country(text, k) for k in COUNTRY_TERMS)


@dataclass
class LocationVerdict:
    ok: bool
    reason: str
    region_tag: str  # chennai | india_other | india_remote | abroad | remote | unknown


def check_location(location_text: str, company_region: str, company_country: str, is_remote: bool = False) -> LocationVerdict:
    """Does this posting's location fit the company's Region rule from the sheet?"""
    text = (location_text or "").strip()
    remote = is_remote or bool(REMOTE_RE.search(text))
    if not text:
        return LocationVerdict(True, "no location given", "unknown")

    if company_region in ("chennai", "india_other", "india_remote"):
        if re.search(r"\bchennai\b", text, re.I):
            return LocationVerdict(True, "Chennai", "chennai")
        if mentions_country(text, "india"):
            if remote:
                return LocationVerdict(True, "remote in India", "india_remote")
            return LocationVerdict(True, "India (other city)", "india_other")
        if remote and REMOTE_INDIA_FRIENDLY.search(text):
            return LocationVerdict(True, "remote (APAC/global)", "remote")
        return LocationVerdict(False, f"not in India: {text[:80]}", "unknown")

    if company_region == "abroad":
        key = country_key(company_country)
        if key and mentions_country(text, key):
            return LocationVerdict(True, f"in {company_country}", "abroad")
        return LocationVerdict(False, f"not in {company_country}: {text[:80]}", "unknown")

    # remote_global: a remote company; must be workable from India
    if mentions_country(text, "india"):
        return LocationVerdict(True, "India / remote-India", "india_remote" if remote else "india_other")
    if remote and not REMOTE_RESTRICTED.search(text):
        return LocationVerdict(True, "remote (no country restriction)", "remote")
    if remote and REMOTE_INDIA_FRIENDLY.search(text):
        return LocationVerdict(True, "remote (APAC/global)", "remote")
    return LocationVerdict(False, f"remote not open to India: {text[:80]}", "unknown")
