"""
Tools: search() and fetch().

BREAK_SEARCH_AFTER env var enables the Day 3 broken-tool demo: set it to a
number N, and search() will start returning [] after the Nth call — no code
changes needed to simulate "the search tool died mid-run".
"""

import os
import re
import time
import random
import requests

from config import FETCH_TIMEOUT

BLOCKED_DOMAINS = {"tracxn.com", "zoominfo.com", "pitchbook.com", "exa.ai", "websets.exa.ai"}


try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    DDGS = None

_search_call_count = 0
_break_after_raw = os.environ.get("BREAK_SEARCH_AFTER")
BREAK_SEARCH_AFTER = int(_break_after_raw) if _break_after_raw else None


class SearchResult:
    def __init__(self, url: str, title: str = "", snippet: str = ""):
        self.url = url
        self.title = title
        self.snippet = snippet

    def __repr__(self):
        return f"SearchResult({self.url!r})"


def search(query: str, max_results: int = 5) -> list[SearchResult]:
    """
    Run a DuckDuckGo search. Returns [] on any failure — network, rate
    limit, library missing, malformed response, or a simulated failure via
    BREAK_SEARCH_AFTER — instead of raising. This is the hook for the
    broken-tool demo: the loop in agent.py never crashes because this
    already fails soft.
    """
    global _search_call_count
    _search_call_count += 1
    time.sleep(random.uniform(0.5, 2.0))  # stagger requests to avoid ddgs rate limiting

    if BREAK_SEARCH_AFTER is not None and _search_call_count > BREAK_SEARCH_AFTER:
        print(f"  [search] SIMULATED FAILURE (BREAK_SEARCH_AFTER={BREAK_SEARCH_AFTER}) — returning no results")
        return []

    if DDGS is None:
        print("  [search] ddgs not installed — skipping search")
        return []

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"  [search] failed for query={query!r}: {e}")
        return []

    results = []
    for r in raw:
        url = r.get("href") or r.get("url") or ""
        if not url:
            continue
        results.append(SearchResult(
            url=url,
            title=r.get("title", ""),
            snippet=r.get("body", ""),
        ))
    return results


def fetch(url: str) -> str | None:
    """Fetch a URL and return cleaned page text, or None on failure."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; SalesResearchAgent/0.3; "
            "+https://example.com/bot)"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [fetch] failed for {url}: {e}")
        return None

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        print(f"  [fetch] skipping non-text content ({content_type}): {url}")
        return None

    text = _extract_text(resp.text)

    if len(text) < 200:
        print(f"  [fetch] extracted text too short (JS-heavy page?): {url}")
        return None

    return text


def _extract_text(html: str) -> str:
    try:
        import trafilatura
        extracted = trafilatura.extract(html)
        if extracted:
            return extracted.strip()
    except ImportError:
        pass

    html = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&amp;|&quot;|&#39;", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


if __name__ == "__main__":
    hits = search("Anthropic funding history")
    for h in hits[:3]:
        print(h)
        time.sleep(0.5)
