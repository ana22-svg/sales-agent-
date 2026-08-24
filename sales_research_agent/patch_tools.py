import re

with open("tools.py") as f:
    src = f.read()

# 1. Add FetchResult right after SearchResult's class definition
old_searchresult_end = '''    def __repr__(self):
        return f"SearchResult({self.url!r})"'''

new_searchresult_end = old_searchresult_end + '''


class FetchResult:
    def __init__(self, url: str, text: str | None, success: bool, error: str | None = None):
        self.url = url
        self.text = text
        self.success = success
        self.error = error

    def __repr__(self):
        return f"FetchResult({self.url!r}, success={self.success})"'''

assert old_searchresult_end in src, "SearchResult block not found — check whitespace"
src = src.replace(old_searchresult_end, new_searchresult_end)

# 2. Wrap search()'s DDGS call with real retry + backoff
old_search_try = '''    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"  [search] failed for query={query!r}: {e}")
        return []'''

new_search_try = '''    raw = None
    for attempt in range(1, 4):
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
            break
        except Exception as e:
            if attempt == 3:
                print(f"  [search] failed for query={query!r} after 3 attempts: {e}")
                return []
            delay = 2 ** (attempt - 1)
            print(f"  [search] attempt {attempt} failed ({e}); retrying in {delay}s")
            time.sleep(delay)'''

assert old_search_try in src, "search() try block not found — check whitespace"
src = src.replace(old_search_try, new_search_try)

# 3. Make fetch() retry the request AND return FetchResult instead of str|None
old_fetch_sig = '''def fetch(url: str) -> str | None:
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

    return text'''

new_fetch_sig = '''def fetch(url: str) -> FetchResult:
    """Fetch a URL and return a FetchResult (text populated on success)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; SalesResearchAgent/0.3; "
            "+https://example.com/bot)"
        )
    }
    resp = None
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
            resp.raise_for_status()
            break
        except Exception as e:
            if attempt == 3:
                print(f"  [fetch] failed for {url} after 3 attempts: {e}")
                return FetchResult(url=url, text=None, success=False, error=str(e))
            delay = 2 ** (attempt - 1)
            print(f"  [fetch] attempt {attempt} failed ({e}); retrying in {delay}s")
            time.sleep(delay)

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        print(f"  [fetch] skipping non-text content ({content_type}): {url}")
        return FetchResult(url=url, text=None, success=False, error=f"non-text content-type: {content_type}")

    text = _extract_text(resp.text)

    if len(text) < 200:
        print(f"  [fetch] extracted text too short (JS-heavy page?): {url}")
        return FetchResult(url=url, text=None, success=False, error="extracted text too short")

    return FetchResult(url=url, text=text, success=True)'''

assert old_fetch_sig in src, "fetch() block not found — check whitespace"
src = src.replace(old_fetch_sig, new_fetch_sig)

with open("tools.py", "w") as f:
    f.write(src)

print("Patched tools.py: FetchResult added, retry wired inline in both search() and fetch(), fetch() now returns FetchResult.")
