"""
Trace logger: durable, replayable record of every step in a run — not just
successes (EvidenceStore only stores facts that made it into the brief).
One JSON file per run, thread-safe, appended to live as run_item() executes
so a trace exists even if the run is later killed.
"""
import json
import time
import threading
from datetime import datetime, timezone
from pathlib import Path


class TraceLogger:
    def __init__(self, path: str, company: str):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._start = time.time()
        self._events = []
        self._meta = {
            "company": company,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def log(self, item: str, event_type: str, detail: str = ""):
        """event_type: one of 'start', 'search', 'fetch', 'extract',
        'saved', 'skipped', 'stopped_early'. Kept as a free string rather
        than an enum so new event types don't require a schema change."""
        entry = {
            "t": round(time.time() - self._start, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "item": item,
            "event": event_type,
            "detail": detail,
        }
        with self._lock:
            self._events.append(entry)
            self._save()

    def _save(self):
        with open(self.path, "w") as f:
            json.dump({"meta": self._meta, "events": self._events}, f, indent=2)

    def finalize(self, summary: str):
        self._meta["ended_at"] = datetime.now(timezone.utc).isoformat()
        self._meta["elapsed_s"] = round(time.time() - self._start, 2)
        self._meta["summary"] = summary
        with self._lock:
            self._save()
