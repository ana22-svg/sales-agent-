"""
Planner: given a company name, ask the LLM to generate a research checklist
dynamically instead of using the fixed CHECKLIST constant. Falls back to
CHECKLIST on any failure (bad JSON, empty response, Ollama down) so a
planner failure degrades to Phase-1 behavior rather than killing the run.
"""
import os
import re
import json
import requests

from config import CHECKLIST, OLLAMA_URL, OLLAMA_MODEL

SKIP_LLM = os.environ.get("SKIP_LLM") == "1"

PLANNER_PROMPT = """You are planning pre-call sales research for a company.

Given the company name below, write a checklist of 5 to 8 short research
items — the kinds of things a sales rep would want to know before a call.
Each item should be a short phrase (3-6 words), similar in style to these
examples: "funding history / financials", "headcount trend", "tech stack
signals", "recent news / announcements".

Company: {company}

Respond with ONLY a JSON array of strings, nothing else. Example format:
["company snapshot (size, industry, HQ)", "funding history / financials", "headcount trend"]

JSON array:"""


def _parse_checklist_json(raw: str) -> list[str] | None:
    """Extract a JSON array of strings from the model's raw output. Models
    sometimes wrap the array in markdown fences or add a leading sentence,
    so pull out the first [...] block rather than requiring a clean parse."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return None
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list) or not items:
        return None
    items = [str(i).strip() for i in items if str(i).strip()]
    if len(items) < 3:
        return None
    return items


def generate_checklist(company: str) -> list[str]:
    """Generate a research checklist for `company` via the LLM. Returns the
    hardcoded CHECKLIST on any failure, so callers never need their own
    fallback logic."""
    if SKIP_LLM:
        print("  [planner] SKIP_LLM=1 — using default CHECKLIST")
        return CHECKLIST

    prompt = PLANNER_PROMPT.format(company=company)

    for attempt in range(1, 4):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 300,
                        "num_ctx": 2048,
                        "temperature": 0.3,
                    },
                },
                timeout=60,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            items = _parse_checklist_json(raw)
            if items:
                print(f"  [planner] generated {len(items)}-item checklist for {company!r}")
                return items
            print(f"  [planner] attempt {attempt} produced unparseable output — retrying")
        except Exception as e:
            print(f"  [planner] attempt {attempt} failed: {e}")
        if attempt < 3:
            import time
            time.sleep(2 ** (attempt - 1))

    print(f"  [planner] all attempts failed — falling back to default CHECKLIST")
    return CHECKLIST
