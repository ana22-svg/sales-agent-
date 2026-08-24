import os
"""
Day 3 critic pass: second LLM call that reads the draft brief and evidence
store, flagging any claim that doesn't map back to a valid, matching
source_id. Run AFTER agent.py has produced brief.json + evidence.json:

    python critic.py "Acme Corp"

Writes critic_report.json and appends a "Critic Review" section to brief.md.
This is a redundant check on top of brief.py's structural enforcement
(every sentence in the brief already carries a source_id when it's built) —
useful as a safety net if brief.py logic ever changes, or a source_id gets
mismatched.
"""

import sys
import json
import requests

from config import OLLAMA_MODEL, OLLAMA_URL, EXTRACT_TIMEOUT, EVIDENCE_STORE_PATH, BRIEF_JSON_PATH, BRIEF_MD_PATH
from evidence_store import EvidenceStore

CRITIC_PROMPT = """You are a fact-checking critic. Below is a research brief and the evidence
records it was built from. For EACH claim in the brief that carries a
[source_id] tag, check whether that source_id exists in the evidence list
AND whether the evidence record's fact actually supports the claim text.

ONLY include a claim in "flagged" if there is a genuine problem: the source_id does not exist, OR the evidence fact does NOT support the claim. Do NOT include claims that are correctly supported - only report real mismatches.

Evidence records (source_id: fact):
{evidence_lines}

Brief claims to check:
{claim_lines}

Respond ONLY with valid JSON, no preamble, in this exact shape:
{{
  "flagged": [
    {{"claim": "...", "source_id": "...", "reason": "..."}}
  ]
}}

If nothing is flagged, respond with {{"flagged": []}}.
"""


def _collect_claims(brief: dict) -> list[dict]:
    claims = []
    if brief.get("snapshot"):
        claims.append({"text": brief["snapshot"], "source_id": brief.get("snapshot_source")})
    for s in brief.get("signals", []):
        claims.append({"text": s["text"], "source_id": s["source_id"]})
    for h in brief.get("hypotheses", []):
        claims.append({"text": h["text"], "source_id": h["source_id"]})
    return claims


def critic_review(brief: dict, store: EvidenceStore) -> dict:
    claims = _collect_claims(brief)
    if not claims:
        return {"flagged": [], "note": "no claims to check"}

    evidence_lines = "\n".join(f"{r['source_id']}: {r['fact']}" for r in store.all())
    claim_lines = "\n".join(f"- {c['text']} [{c.get('source_id')}]" for c in claims)
    prompt = CRITIC_PROMPT.format(evidence_lines=evidence_lines, claim_lines=claim_lines)

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=EXTRACT_TIMEOUT,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        result = json.loads(answer)
    except Exception as e:
        print(f"  [critic] LLM call or parse failed: {e}")
        # Fail soft — a broken critic pass should never block the brief itself
        return {"flagged": [], "note": f"critic pass failed: {e}"}

    # Structural cross-check regardless of what the LLM said: any claim
    # pointing at a source_id that doesn't exist in the store is an
    # automatic flag.
    valid_ids = {r["source_id"] for r in store.all()}
    for c in claims:
        sid = c.get("source_id")
        if sid and sid not in valid_ids:
            result.setdefault("flagged", []).append({
                "claim": c["text"], "source_id": sid,
                "reason": "source_id not found in evidence store (structural check)"
            })

    return result


def main():
    if not os.path.exists(BRIEF_JSON_PATH):
        print(f"[critic] No brief found at {BRIEF_JSON_PATH} - agent run likely didn't complete. Skipping critic pass.")
        return

    if len(sys.argv) < 2:
        print('Usage: python critic.py "Company Name"')
        sys.exit(1)

    company = " ".join(sys.argv[1:])

    with open(BRIEF_JSON_PATH) as f:
        brief = json.load(f)
    store = EvidenceStore(EVIDENCE_STORE_PATH)

    print(f"Running critic pass on brief for {company}...")
    report = critic_review(brief, store)

    with open("critic_report.json", "w") as f:
        json.dump(report, f, indent=2)

    flagged = report.get("flagged", [])
    print(f"Critic flagged {len(flagged)} claim(s)")
    for f_ in flagged:
        print(f"  - {f_['claim'][:80]} [{f_['source_id']}]: {f_['reason']}")

    with open(BRIEF_MD_PATH, "a") as f:
        f.write("\n## Critic Review\n")
        if flagged:
            for f_ in flagged:
                f.write(f"- \u26a0\ufe0f **{f_['claim']}** [{f_['source_id']}] — {f_['reason']}\n")
        else:
            f.write("_No unsupported claims found._\n")

    print("Wrote critic_report.json, appended Critic Review to brief.md")


if __name__ == "__main__":
    main()
