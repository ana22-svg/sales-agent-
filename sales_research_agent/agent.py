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

from config import TOP_N_RESULTS
from planner import generate_checklist
from tools import search, fetch
from extract import extract_relevant_fact
from evidence_store import EvidenceStore
from brief import compile_brief, render_markdown
from budget import Budget, BudgetExceeded
from trace import TraceLogger
import os

MAX_WORKERS = 2  # matches Codespaces' typical 2-core / light multi-thread headroom


def run_item(company: str, item: str, store: EvidenceStore, budget: Budget, trace: TraceLogger) -> tuple[str, int]:
    try:
        budget.check()
    except BudgetExceeded as e:
        print(f"\n[{item}] skipped — {e.reason}")
        trace.log(item, "skipped", e.reason)
        return item, 0

    query = f"{item} {company}"
    print(f"\n[{item}] starting")
    trace.log(item, "start", query)
    try:
        budget.record_step()
        results = search(query, max_results=TOP_N_RESULTS + 2)
        trace.log(item, "search", f"{len(results)} results")
    except Exception as e:
        print(f"  [{item}] search() raised unexpectedly: {e} — treating as no results")
        trace.log(item, "search_error", str(e))
        results = []
    if not results:
        print(f"  [{item}] no search results — marking 'could not verify'")
        trace.log(item, "no_results", "")
        return item, 0
    saved = 0
    for r in results[:TOP_N_RESULTS]:
        try:
            budget.check()
        except BudgetExceeded as e:
            print(f"  [{item}] stopping early — {e.reason}")
            trace.log(item, "stopped_early", e.reason)
            break
        try:
            budget.record_step()
            result = fetch(r.url)
            trace.log(item, "fetch", f"{r.url} success={result.success}")
        except Exception as e:
            print(f"  [{item}] fetch() raised unexpectedly for {r.url}: {e}")
            trace.log(item, "fetch_error", f"{r.url}: {e}")
            continue
        if not result.success:
            continue
        text = result.text
        try:
            budget.check()
            budget.record_step()
            fact = extract_relevant_fact(text, item, company)
            trace.log(item, "extract", f"{r.url} -> {'fact' if fact else 'NONE'}")
        except BudgetExceeded as e:
            print(f"  [{item}] stopping early — {e.reason}")
            trace.log(item, "stopped_early", e.reason)
            break
        except Exception as e:
            print(f"  [{item}] extract_relevant_fact() raised unexpectedly: {e}")
            trace.log(item, "extract_error", f"{r.url}: {e}")
            continue
        if not fact:
            print(f"  [{item}] no relevant fact found in {r.url}")
            continue
        source_id = store.add(item, r.url, fact, company, confidence="medium")
        print(f"  [{item}] saved {source_id}: {fact[:90]}")
        trace.log(item, "saved", f"{source_id}: {fact[:90]}")
        saved += 1
    return item, saved


def main():
    if len(sys.argv) < 2:
        print('Usage: python agent.py "Company Name"')
        sys.exit(1)

    company = " ".join(sys.argv[1:])
    print(f"Researching: {company}")
    CHECKLIST = generate_checklist(company)
    print(f"Checklist ({len(CHECKLIST)} items, {MAX_WORKERS} workers): {CHECKLIST}")
    budget = Budget(
        max_steps=int(os.environ.get("MAX_STEPS", 40)),
        max_seconds=float(os.environ.get("MAX_SECONDS", 180)),
        max_cost_usd=float(os.environ.get("MAX_COST_USD", 1.0)),
    )

    store = EvidenceStore("evidence.json")
    trace = TraceLogger("trace.json", company)
    start = time.time()

    satisfied, unverified = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(run_item, company, item, store, budget, trace): item for item in CHECKLIST}
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
    print(f"Budget: {budget.summary()}")
    if unverified:
        print(f"Could not verify: {unverified}")
    trace.finalize(f"satisfied={len(satisfied)}/{len(CHECKLIST)} elapsed={elapsed:.0f}s budget={budget.summary()}")

    brief = compile_brief(company, store, CHECKLIST)

    with open("brief.json", "w") as f:
        json.dump(brief, f, indent=2)

    md = render_markdown(brief)
    with open("brief.md", "w") as f:
        f.write(md)

    print("\nWrote evidence.json, brief.json, brief.md")


if __name__ == "__main__":
    main()
