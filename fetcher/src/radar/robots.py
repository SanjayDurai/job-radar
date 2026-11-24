"""robots.txt matching per RFC 9309 (the rules Google and Bing follow).

Python's urllib.robotparser applies the *first* matching rule, so a file like
    Disallow: /
    Allow: /api/pcsx
blocks /api/pcsx there, while RFC 9309 says the *longest* (most specific) match wins
and ties go to Allow. Many career sites rely on that, so we implement it properly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
    return re.compile("^" + regex + ("$" if anchored else ""))


class RobotsRules:
    def __init__(self, text: str) -> None:
        self.groups: list[_Group] = []
        current: _Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = _Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
            elif key in ("allow", "disallow") and current is not None:
                last_was_agent = False
                if value or key == "allow":  # empty Disallow = allow everything
                    current.rules.append((key == "allow", value))
            else:
                last_was_agent = False

    def _rules_for(self, user_agent: str) -> list[tuple[bool, str]]:
        token = re.split(r"[/\s]", user_agent.strip(), maxsplit=1)[0].lower()
        specific = [g for g in self.groups if any(a != "*" and a in token for a in g.agents)]
        chosen = specific or [g for g in self.groups if "*" in g.agents]
        return [r for g in chosen for r in g.rules]

    def can_fetch(self, user_agent: str, url: str) -> bool:
        parts = urlsplit(url)
        path = unquote(parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best_len, allowed = -1, True
        for allow, pattern in self._rules_for(user_agent):
            if not pattern:
                continue
            if _pattern_to_regex(pattern).match(path):
                length = len(pattern)
                if length > best_len or (length == best_len and allow):
                    best_len, allowed = length, allow
        return allowed
