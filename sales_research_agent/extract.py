"""
One LLM call: given raw page text + the checklist item it's meant to answer,
pull out a single short factual sentence, or return None if the page has
nothing relevant.

- Streams tokens to stdout for visual feedback instead of a silent wait
- Bounds num_predict/num_ctx so the model can't over-generate
- Serializes requests through a semaphore (Ollama is CPU-bound and
  effectively single-threaded anyway — this prevents timeouts from queued
  concurrent calls)
- Cleans model output robustly regardless of which scaffolding the model
  echoes back ("Answer:", "Fact:", "Company: X\nFact: Y", etc.)
"""
import os
import re
import json
import threading
import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
SKIP_LLM = os.environ.get("SKIP_LLM") == "1"

_OLLAMA_LOCK = threading.Semaphore(1)  # only 1 concurrent Ollama request

EXTRACT_PROMPT = """Read the page text below. Find any fact about "{checklist_item}" for the company {company}.

Example:
Page text: "Acme raised a $20M Series A led by Sequoia in 2023."
Checklist item: funding history
Answer: Acme raised a $20M Series A led by Sequoia in 2023.

Example:
Page text: "Our office has a rooftop garden and free lunch."
Checklist item: funding history
Answer: NONE

Now do the real one.
Page text:
{page_text}

Checklist item: {checklist_item}
Company: {company}
Write ONE sentence stating the fact, using real numbers/names from the page text if present.
If the page text truly has nothing about "{checklist_item}", write exactly: NONE
Answer:"""


def _heuristic_extract(page_text: str, checklist_item: str) -> str | None:
    """No-model stand-in for SKIP_LLM=1: first sentence mentioning a
    checklist keyword. Not accurate — just exercises the rest of the
    pipeline while the model is bypassed."""
    keywords = [w.lower() for w in re.split(r"[ /()]+", checklist_item) if len(w) > 3]
    sentences = re.split(r"(?<=[.!?])\s+", page_text)
    for s in sentences:
        if any(k in s.lower() for k in keywords):
            return s.strip()[:300]
    return None


def _clean_model_output(raw: str) -> str:
    """
    Models inconsistently echo prompt scaffolding before the real answer
    (seen: "Answer: ...", "Company: X\\nFact: ...", etc). Strip any leading
    "Label: " lines and join what's left into one line.
    """
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    if not lines:
        return raw.strip()
    content_lines = []
    for line in lines:
        m = re.match(r"^([A-Za-z ]{2,20}):\s*(.*)$", line)
        if m and len(m.group(1).split()) <= 3:
            remainder = m.group(2).strip()
            if remainder:
                content_lines.append(remainder)
        else:
            content_lines.append(line)
    return " ".join(content_lines).strip()


def extract_relevant_fact(page_text: str, checklist_item: str, company: str) -> str | None:
    if not page_text or not page_text.strip():
        return None

    if SKIP_LLM:
        return _heuristic_extract(page_text, checklist_item)

    truncated = page_text[:6000]
    prompt = EXTRACT_PROMPT.format(
        checklist_item=checklist_item,
        company=company,
        page_text=truncated,
    )

    try:
        with _OLLAMA_LOCK:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "num_predict": 120,
                        "num_ctx": 4096,
                        "temperature": 0.1,
                    },
                },
                timeout=180,
                stream=True,
            )
            resp.raise_for_status()

            chunks = []
            for line in resp.iter_lines():
                if not line:
                    continue
                piece = json.loads(line)
                token = piece.get("response", "")
                if token:
                    print(token, end="", flush=True)
                    chunks.append(token)
                if piece.get("done"):
                    break
            print()
            raw = "".join(chunks).strip()
    except Exception as e:
        print(f"  [extract failed] {e}")
        return None

    text = _clean_model_output(raw)

    if not text or text.upper().startswith("NONE"):
        return None
    return text
