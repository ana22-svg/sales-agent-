"""
Run-level budget: caps total steps, wall-clock time, and (for future paid
API use) estimated dollar cost. Thread-safe since run_item() executes
concurrently across ThreadPoolExecutor workers.

A "step" = one search(), fetch(), or extract_relevant_fact() call — the
three tool calls that actually cost time/tokens/money per checklist item.

On local Ollama, cost is always $0 (COST_PER_1K_TOKENS defaults to 0), but
the ceiling stays in place so swapping to a paid API later doesn't require
new plumbing.
"""
import os
import time
import threading


class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class Budget:
    def __init__(
        self,
        max_steps: int = 40,
        max_seconds: float = 180,
        max_cost_usd: float = 1.0,
        cost_per_1k_tokens: float = 0.0,  # 0 for local Ollama; set >0 for a paid API
    ):
        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self.max_cost_usd = max_cost_usd
        self.cost_per_1k_tokens = cost_per_1k_tokens

        self._lock = threading.Lock()
        self._start = time.time()
        self._steps = 0
        self._tokens = 0
        self._cost = 0.0

    def check(self):
        """Raise BudgetExceeded if any ceiling has been hit. Call this
        before starting new work — not just after — so items queued but
        not yet started bail immediately."""
        elapsed = time.time() - self._start
        with self._lock:
            steps, cost = self._steps, self._cost
        if elapsed > self.max_seconds:
            raise BudgetExceeded(f"wall-clock limit hit ({elapsed:.0f}s > {self.max_seconds}s)")
        if steps >= self.max_steps:
            raise BudgetExceeded(f"step limit hit ({steps} >= {self.max_steps})")
        if cost >= self.max_cost_usd:
            raise BudgetExceeded(f"cost limit hit (${cost:.4f} >= ${self.max_cost_usd})")

    def record_step(self):
        with self._lock:
            self._steps += 1

    def record_tokens(self, n: int):
        with self._lock:
            self._tokens += n
            self._cost += (n / 1000) * self.cost_per_1k_tokens

    def summary(self) -> str:
        elapsed = time.time() - self._start
        with self._lock:
            return (
                f"steps={self._steps}/{self.max_steps}  "
                f"time={elapsed:.0f}s/{self.max_seconds:.0f}s  "
                f"tokens={self._tokens}  cost=${self._cost:.4f}/{self.max_cost_usd}"
            )
