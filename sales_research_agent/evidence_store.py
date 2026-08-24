"""
Evidence store: one JSON file. No database. Every fact used in the brief
must be written here first, with a source URL and timestamp.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class EvidenceStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self._records = []
        self._next_id = 1
        if self.path.exists():
            self._load()

    def _load(self):
        with open(self.path, "r") as f:
            data = json.load(f)
        self._records = data.get("records", [])
        self._next_id = data.get("next_id", len(self._records) + 1)

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(
                {"records": self._records, "next_id": self._next_id},
                f,
                indent=2,
            )

    def add(self, checklist_item: str, url: str, fact: str, company: str, confidence: str = "medium") -> str:
        source_id = f"s{self._next_id}"
        self._next_id += 1
        record = {
            "source_id": source_id,
            "checklist_item": checklist_item,
            "company": company,
            "url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "fact": fact,
            "confidence": confidence,
        }
        self._records.append(record)
        self._save()
        return source_id

    def for_item(self, checklist_item: str):
        return [r for r in self._records if r["checklist_item"] == checklist_item]

    def all(self):
        return list(self._records)

    def get(self, source_id: str):
        for r in self._records:
            if r["source_id"] == source_id:
                return r
        return None