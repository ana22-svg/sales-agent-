"""
Reads a trace.json produced by TraceLogger and reprints a past run
step-by-step, without re-hitting the network or Ollama.
"""
import json
import sys
import time


def replay(path: str, speed: float = 0.0):
    with open(path) as f:
        data = json.load(f)

    meta = data["meta"]
    print(f"=== Replaying run for {meta.get('company')} ===")
    print(f"started_at: {meta.get('started_at')}")
    if "ended_at" in meta:
        print(f"ended_at:   {meta['ended_at']}  (elapsed {meta.get('elapsed_s')}s)")
    if "summary" in meta:
        print(f"summary:    {meta['summary']}")
    print()

    for e in data["events"]:
        line = f"[t={e['t']:>6.2f}s] [{e['item']}] {e['event']}"
        if e.get("detail"):
            line += f" — {e['detail']}"
        print(line)
        if speed > 0:
            time.sleep(speed)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python replay.py <trace.json> [speed_seconds_between_lines]")
        sys.exit(1)
    speed = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    replay(sys.argv[1], speed)
