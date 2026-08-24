"""
Day 2/3 build, parallelized. Full 8-item checklist, citation-enforced brief,
fail-soft error handling, checklist items run concurrently via
ThreadPoolExecutor so network-bound fetch() calls overlap.

Run:
    python agent.py "Company Name"
"""

import sys
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import CHECKLIST, TOP_N_RESULTS
from tools import search, fetch
from extract import extract_relevant_fact
from evidence_store import EvidenceStore
from brief import compile_brief, render_markdown

MAX_WORKERS = 2  # matches Codespaces' typical 2-core / light multi-thread headroom


def run_item(company: str, item: str, store: EvidenceStore) -> tuple[str, int]:
    query = f"{item} {company}"
    print(f"\n[{item}] starting")

    try:
        results = search(query, max_results=TOP_N_RESULTS + 2)
    except Exception as e:
        print(f"  [{item}] search() raised unexpectedly: {e} — treating as no results")
        results = []

    if not results:
        print(f"  [{item}] no search results — marking 'could not verify'")
        return item, 0

    saved = 0
    for r in results[:TOP_N_RESULTS]:
        try:
            text = fetch(r.url)
        except Exception as e:
            print(f"  [{item}] fetch() raised unexpectedly for {r.url}: {e}")
            continue

        if not text:
            continue

        try:
            fact = extract_relevant_fact(text, item, company)
        except Exception as e:
            print(f"  [{item}] extract_relevant_fact() raised unexpectedly: {e}")
            continue

        if not fact:
            print(f"  [{item}] no relevant fact found in {r.url}")
            continue

        source_id = store.add(item, r.url, fact, confidence="medium")
        print(f"  [{item}] saved {source_id}: {fact[:90]}")
        saved += 1

    return item, saved


def main():
    if len(sys.argv) < 2:
        print('Usage: python agent.py "Company Name"')
        sys.exit(1)

    company = " ".join(sys.argv[1:])
    print(f"Researching: {company}")
    print(f"Checklist ({len(CHECKLIST)} items, {MAX_WORKERS} workers): {CHECKLIST}")

    store = EvidenceStore("evidence.json")
    start = time.time()

    satisfied, unverified = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(run_item, company, item, store): item for item in CHECKLIST}
        for future in as_completed(futures):
            item = futures[future]
            try:
                _, n = future.result()
            except Exception as e:
                print(f"  [main] unexpected error on item {item!r}: {e}")
                n = 0

            if n > 0:
                satisfied.append(item)
            else:
                unverified.append(item)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s. Satisfied: {len(satisfied)}/{len(CHECKLIST)}")
    if unverified:
        print(f"Could not verify: {unverified}")

    brief = compile_brief(company, store)

    with open("brief.json", "w") as f:
        json.dump(brief, f, indent=2)

    md = render_markdown(brief)
    with open("brief.md", "w") as f:
        f.write(md)

    print("\nWrote evidence.json, brief.json, brief.md")


if __name__ == "__main__":
    main()
