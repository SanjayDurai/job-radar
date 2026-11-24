"""Polite HTTP client: per-domain rate limit, clear User-Agent, retries with backoff, robots.txt."""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from radar.robots import RobotsRules

log = logging.getLogger(__name__)

USER_AGENT = "PersonalJobRadar/0.1 (single-user personal job search; checks public job listings once a day)"
# Some sites serve an empty shell to unknown bots; a browser-like Accept helps without pretending to be one.
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
RETRY_STATUS = {429, 500, 502, 503, 504}


class RobotsDisallowed(Exception):
    """robots.txt for this host disallows the URL for our user agent."""


class FetchError(Exception):
    pass


class PoliteClient:
    """One shared client per run. `min_interval` seconds between requests to the same host."""

    def __init__(
        self,
        min_interval: float = 1.2,
        timeout: float = 30.0,
        max_retries: int = 3,
        respect_robots: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.respect_robots = respect_robots
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()
        self._host_interval: dict[str, float] = {}
        self._robots: dict[str, RobotsRules | None] = {}
        self.request_count = 0
        self._client = httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- robots.txt -------------------------------------------------------------------------
    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotsRules | None = None
            try:
                self._wait(parts.netloc)
                r = self._client.get(origin + "/robots.txt", timeout=15)
                self.request_count += 1
                if r.status_code == 200 and "text/html" not in r.headers.get("content-type", ""):
                    parser = RobotsRules(r.text)
                # 4xx / missing / HTML error page => no rules => allowed
            except httpx.HTTPError as e:
                log.debug("robots.txt fetch failed for %s: %s", origin, e)
            self._robots[origin] = parser
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    # --- requests ---------------------------------------------------------------------------
    @property
    def user_agent(self) -> str:
        return USER_AGENT

    def wait_turn(self, url: str) -> None:
        """Respect the per-host delay for requests made outside this client (e.g. a headless browser)."""
        self._wait(urlsplit(url).netloc)

    def set_host_interval(self, host: str, seconds: float) -> None:
        """Slow down for hosts that rate-limit aggressively (configured per company)."""
        self._host_interval[host] = max(seconds, self.min_interval)

    def _wait(self, host: str) -> None:
        """Reserve the next request slot for `host` (thread-safe), then sleep until it."""
        with self._lock:
            now = time.monotonic()
            interval = self._host_interval.get(host, self.min_interval)
            slot = max(now, self._last_hit.get(host, 0.0) + interval)
            self._last_hit[host] = slot
        if slot > now:
            time.sleep(slot - now)

    def request(self, method: str, url: str, *, check_robots: bool = True, **kwargs: Any) -> httpx.Response:
        if check_robots and not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        host = urlsplit(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._wait(host)
            try:
                r = self._client.request(method, url, **kwargs)
                self.request_count += 1
                if r.status_code not in RETRY_STATUS:
                    return r
                last_exc = FetchError(f"HTTP {r.status_code} from {url}")
                retry_after = r.headers.get("retry-after", "")
                wait = float(retry_after) if retry_after.isdigit() else 2**attempt + random.random()
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                wait = 2**attempt + random.random()
            if attempt < self.max_retries:
                time.sleep(min(wait, 30))
        raise FetchError(f"{method} {url} failed after {self.max_retries + 1} attempts: {last_exc}")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        r = self.get(url, **kwargs)
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code} from {url}")
        return r.json()

    def post_json(self, url: str, **kwargs: Any) -> Any:
        r = self.post(url, **kwargs)
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code} from {url}: {r.text[:200]}")
        return r.json()
