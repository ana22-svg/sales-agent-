from evidence_store import EvidenceStore

SNAPSHOT_ITEM = "company snapshot (size, industry, HQ)"


def _sentences_for(store: EvidenceStore, item: str, company: str) -> list[dict]:
    return [r for r in store.for_item(item) if r.get("fact") and r.get("company") == company]


def compile_brief(company: str, store: EvidenceStore, checklist: list[str]) -> dict:
    unverified_items = []

    snapshot_records = _sentences_for(store, SNAPSHOT_ITEM, company)
    snapshot = snapshot_records[0]["fact"] if snapshot_records else None
    if not snapshot:
        unverified_items.append(SNAPSHOT_ITEM)

    signals = []
    for item in checklist:
        if item == SNAPSHOT_ITEM:
            continue
        records = _sentences_for(store, item, company)
        if not records:
            unverified_items.append(item)
            continue
        for r in records:
            signals.append({"text": r["fact"], "source_id": r["source_id"], "item": item})

    stakeholders = [
        s for s in signals
        if s["item"] == "org changes (leadership moves, hiring surges)"
    ]

    hypotheses = _infer_pain_points(signals)
    opener = _infer_opener(company, signals, hypotheses)

    company_records = [r for r in store.all() if r.get("company") == company]
    sources = [
        {"source_id": r["source_id"], "url": r["url"], "retrieved_at": r["retrieved_at"]}
        for r in sorted(company_records, key=lambda r: int(r["source_id"].lstrip("s")))
    ]

    return {
        "company": company,
        "snapshot": snapshot,
        "snapshot_source": snapshot_records[0]["source_id"] if snapshot_records else None,
        "signals": signals,
        "stakeholders": stakeholders,
        "hypotheses": hypotheses,
        "suggested_opener": opener,
        "sources": sources,
        "unverified_items": unverified_items,
    }


def _infer_pain_points(signals: list[dict]) -> list[dict]:
    hypotheses = []
    keywords = ["hiring", "layoff", "restructur", "departure", "resign", "surge", "scaling"]
    for s in signals:
        if any(k in s["text"].lower() for k in keywords):
            hypotheses.append({
                "text": f"Possible pain point inferred from: {s['text']}",
                "source_id": s["source_id"],
            })
    return hypotheses


def _infer_opener(company: str, signals: list[dict], hypotheses: list[dict]) -> str:
    if hypotheses:
        basis = hypotheses[0]
        return (
            f"Reference this in the open: \"{basis['text']}\" "
            f"[{basis['source_id']}] — ask how it's affecting their priorities this quarter."
        )
    if signals:
        basis = signals[0]
        return f"Open with: \"{basis['text']}\" [{basis['source_id']}] and ask what changed since."
    return f"No strong signal found yet for {company} — open with a discovery question instead of a hook."


def render_markdown(brief: dict) -> str:
    lines = [f"# Sales Research Brief — {brief['company']}", ""]

    lines.append("## Snapshot")
    if brief["snapshot"]:
        lines.append(f"{brief['snapshot']} [{brief['snapshot_source']}]")
    else:
        lines.append("_Could not verify — no source found for company snapshot._")
    lines.append("")

    lines.append("## Signals")
    if brief["signals"]:
        for s in brief["signals"]:
            lines.append(f"- **{s['item']}**: {s['text']} [{s['source_id']}]")
    else:
        lines.append("_No signals verified._")
    lines.append("")

    lines.append("## Stakeholders / Org Changes")
    if brief["stakeholders"]:
        for s in brief["stakeholders"]:
            lines.append(f"- {s['text']} [{s['source_id']}]")
    else:
        lines.append("_No org-change signals found._")
    lines.append("")

    lines.append("## Likely Pain Points (inferred)")
    if brief["hypotheses"]:
        for h in brief["hypotheses"]:
            lines.append(f"- {h['text']} [{h['source_id']}]")
    else:
        lines.append("_No strong pain-point signal inferred from current evidence._")
    lines.append("")

    lines.append("## Suggested Opener")
    lines.append(brief["suggested_opener"])
    lines.append("")

    if brief["unverified_items"]:
        lines.append("## Could Not Verify")
        for item in brief["unverified_items"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## Sources")
    for src in brief["sources"]:
        lines.append(f"- `{src['source_id']}` [{src['url']}]({src['url']}) — retrieved {src['retrieved_at']}")
    lines.append("")

    return "\n".join(lines)
