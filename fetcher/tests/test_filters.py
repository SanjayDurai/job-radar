import pytest

from radar.filters import check_location, check_title, country_key


@pytest.mark.parametrize(
    "title,ai",
    [
        ("Machine Learning Engineer", True),
        ("AI Engineer - GenAI Platform", True),
        ("Software Engineer II, AI/ML", True),
        ("Applied Scientist", True),
        ("Data Scientist I", True),
        ("LLM Engineer", True),
        ("Member of Technical Staff - Agents", True),
        ("Software Development Engineer I", False),
        ("Software Engineer", False),
        ("MTS 2", False),
    ],
)
def test_titles_accepted(title, ai):
    v = check_title(title)
    assert v.ok, v.reason
    assert v.ai_title is ai


@pytest.mark.parametrize(
    "title",
    [
        "Senior Machine Learning Engineer",
        "Sr. Data Scientist",
        "Staff ML Engineer",
        "Principal Applied Scientist",
        "Lead AI Engineer",
        "Engineering Manager, ML",
        "Machine Learning Intern",
        "Director of AI",
        "AI Solutions Architect",
        "SDE III, Alexa AI",
        "Software Engineer III",
        "AI Sales Specialist",
        "Account Executive",
        "HR Business Partner",
        "Product Designer",
    ],
)
def test_titles_rejected(title):
    assert not check_title(title).ok


def test_optional_senior_in_parentheses_is_allowed():
    assert check_title("(Senior) Machine Learning Engineer").ok
    assert not check_title("Senior Machine Learning Engineer (all genders)").ok


def test_word_boundaries():
    assert check_title("Leadership-free ML Engineer").ok  # 'lead' only as a whole word
    assert check_title("Internal Tools ML Engineer").ok  # 'intern' only as a whole word
    assert not check_title("Email Marketing Associate").ok  # 'ai' inside 'Email' is not AI


def test_country_key():
    assert country_key("UAE") == "uae"
    assert country_key("United Kingdom") == "uk"
    assert country_key("Netherlands") == "netherlands"


@pytest.mark.parametrize(
    "loc,region,country,ok,tag",
    [
        ("Chennai, Tamil Nadu, India", "chennai", "India", True, "chennai"),
        ("Bengaluru, KA, India", "chennai", "India", True, "india_other"),
        ("Remote - India", "india_remote", "India", True, "india_remote"),
        ("Seattle, WA, USA", "india_other", "India", False, "unknown"),
        ("Hyderabad", "india_other", "India", True, "india_other"),
        ("Dubai, United Arab Emirates", "abroad", "UAE", True, "abroad"),
        ("Bengaluru, India", "abroad", "UAE", False, "unknown"),
        ("Amsterdam", "abroad", "Netherlands", True, "abroad"),
        ("London, UK", "abroad", "UK", True, "abroad"),
        ("Toronto, ON, Canada", "abroad", "Canada", True, "abroad"),
        ("San Francisco, CA", "abroad", "Canada", False, "unknown"),  # CA = California, not Canada
        ("Remote", "remote_global", "Global (remote)", True, "remote"),
        ("Remote - US", "remote_global", "Global (remote)", False, "unknown"),
        ("Remote, EMEA", "remote_global", "Global (remote)", True, "remote"),
        ("Remote - India", "remote_global", "Global (remote)", True, "india_remote"),
    ],
)
def test_location_rules(loc, region, country, ok, tag):
    v = check_location(loc, region, country)
    assert v.ok is ok, v.reason
    assert v.region_tag == tag


def test_empty_location_passes():
    assert check_location("", "abroad", "UK").ok
