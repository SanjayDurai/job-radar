"""Layer 2 (optional): LLM fit score via Groq's free tier.

Off unless GROQ_API_KEY is set (and LLM_PROVIDER isn't "none"). Only jobs that pass the rules
are sent, at most `max_calls_per_run` per run, and each result is cached by a content hash so a
job is never scored twice. If Groq's daily free limit is reached, the rest of the run simply
keeps rule-only scores and continues next time.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from radar.profile import experience_years

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You assess how well a job posting fits one specific candidate. Be strict and realistic.

Candidate:
- {experience} years of experience (first job), current role: {current_role}
- Skills: {skills}
- Wants: AI/ML engineering, GenAI/LLM, agentic AI, applied science, data science, Python/automation roles
- Fits roles asking 0-3 years (a "2-4 years" or "3+" ask is a stretch but possible). Senior/Staff/Lead/Manager roles do not fit.
- Based in Chennai, India. Open to other Indian cities and to moving abroad with visa sponsorship.

Scoring guide for "score" (0-100):
90+ near-perfect (AI/ML/GenAI role, junior-mid level, strong skill overlap); 70-89 strong; 50-69 possible;
30-49 weak (wrong focus or a stretch on seniority); below 30 poor fit.

Reply with only a JSON object with exactly these keys:
{{"score": int 0-100,
  "fit_summary": one sentence (max 25 words),
  "why_match": up to 3 short bullet strings,
  "gaps": up to 3 short bullet strings,
  "seniority_ok": true/false,
  "visa_sponsorship": "yes" | "no" | "unknown",
  "est_years_required": number or null}}"""

USER_TEMPLATE = """Company: {company} ({country})
Title: {title}
Location: {location}

Description:
{description}"""


class LLMUnavailable(Exception):
    """Daily limit hit or the provider is down: stop calling the LLM for the rest of this run."""


@dataclass
class LLMResult:
    score: int
    data: dict[str, Any]
    model: str


def content_hash(model: str, title: str, description: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}|{model}|{title}|{description}".encode()).hexdigest()


def validate(raw: str) -> dict[str, Any]:
    """Parse and normalise the model's JSON. Raises ValueError if it can't be trusted."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    score = int(round(float(data["score"])))
    if not 0 <= score <= 100:
        raise ValueError(f"score out of range: {score}")

    def str_list(key: str) -> list[str]:
        val = data.get(key) or []
        val = [val] if isinstance(val, str) else val
        return [str(x).strip()[:160] for x in val if str(x).strip()][:3]

    visa = str(data.get("visa_sponsorship", "unknown")).lower()
    years = data.get("est_years_required")
    try:
        years = None if years in (None, "", "null") else float(years)
    except (TypeError, ValueError):
        years = None
    return {
        "score": score,
        "fit_summary": str(data.get("fit_summary", "")).strip()[:220],
        "why_match": str_list("why_match"),
        "gaps": str_list("gaps"),
        "seniority_ok": bool(data.get("seniority_ok", False)),
        "visa_sponsorship": visa if visa in ("yes", "no", "unknown") else "unknown",
        "est_years_required": years,
    }


class LLMScorer:
    def __init__(self, cfg: dict[str, Any], profile: dict[str, Any], client: Any | None = None) -> None:
        llm = cfg.get("llm", {})
        self.provider = os.environ.get("LLM_PROVIDER", llm.get("provider", "groq")).strip().lower()
        self.model = os.environ.get("LLM_MODEL", llm.get("model", "openai/gpt-oss-120b"))
        self.reasoning_effort = llm.get("reasoning_effort")
        self.max_calls = int(os.environ.get("LLM_MAX_CALLS_PER_RUN", llm.get("max_calls_per_run", 40)))
        self.min_rule_score = int(llm.get("min_rule_score", 35))
        self.max_chars = int(llm.get("max_description_chars", 6000))
        self.min_gap = float(llm.get("min_seconds_between_calls", 2.5))
        self.calls = 0
        self.stopped_reason: str | None = None
        self._last_call = 0.0
        self._system = SYSTEM_PROMPT.format(
            experience=experience_years(),
            current_role=profile.get("current_role", ""),
            skills=", ".join(profile.get("skills", [])),
        )
        self._client = client
        if self._client is None and self.enabled_by_config:
            from groq import Groq

            # max_retries: the SDK waits out a per-minute 429 (honouring retry-after) before giving up
            self._client = Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=3, timeout=60)

    @property
    def enabled_by_config(self) -> bool:
        return self.provider == "groq" and bool(os.environ.get("GROQ_API_KEY", "").strip())

    @property
    def available(self) -> bool:
        return self._client is not None and self.stopped_reason is None and self.calls < self.max_calls

    def score(self, *, company: str, country: str, title: str, location: str, description: str) -> LLMResult:
        if not self.available:
            raise LLMUnavailable(self.stopped_reason or "LLM disabled or call cap reached")
        wait = self.min_gap - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        user = USER_TEMPLATE.format(company=company, country=country, title=title, location=location or "not stated",
                                    description=(description or "")[: self.max_chars])  # fmt: skip
        self._last_call = time.monotonic()
        self.calls += 1
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": self._system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_completion_tokens": 1500,  # reasoning models spend some tokens thinking before the JSON
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort and "gpt-oss" in self.model:
            kwargs["reasoning_effort"] = self.reasoning_effort
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # groq.RateLimitError / APIStatusError / APIConnectionError
            msg = str(e)
            if type(e).__name__ == "RateLimitError" and (
                "per day" in msg.lower() or "tpd" in msg.lower() or "rpd" in msg.lower()
            ):
                self.stopped_reason = "Groq daily free limit reached; remaining jobs keep rule scores until the next run"
                raise LLMUnavailable(self.stopped_reason) from e
            if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError", "NotFoundError"):
                self.stopped_reason = f"Groq rejected the request ({type(e).__name__}): check GROQ_API_KEY / model"
                raise LLMUnavailable(self.stopped_reason) from e
            raise
        content = resp.choices[0].message.content or ""
        data = validate(content)
        return LLMResult(score=data["score"], data=data, model=self.model)
