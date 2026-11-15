"""Request policy, deterministic prompt construction, and case planning for the baseline suite."""

import hashlib
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIN_DOCUMENT_CHARS = 2_000
MAX_DOCUMENT_CHARS = 200_000
MIN_CHARS_PER_TOKEN, MAX_CHARS_PER_TOKEN = 1.5, 8.0
INITIAL_CHARS_PER_TOKEN = 3.0
LENGTH_MARGIN = 0.97
VARIANT_STRIDE = 7
FIT_TOLERANCE = 0.01
FIT_ROUNDS = 8

# Verified field names; other servers need their own settings supplied with --request-extra.
THINKING_OFF: dict[str, dict[str, Any]] = {"strata": {"reasoning_effort": "none"}}
# Verified enabling control for the reasoning case; other servers keep template defaults.
THINKING_ON: dict[str, dict[str, Any]] = {"strata": {"reasoning_effort": "high"}}
TOKEN_LIMIT_FIELD = {"strata": "max_completion_tokens"}
# Servers with a tokenizer route that counts a prompt without running it.
TOKEN_COUNT_ROUTE = {"strata": "/v1/messages/count_tokens", "tabbyapi": "/v1/token/encode"}

REVIEW_TASK = (
    "Summarize what each file above is responsible for, then list three potential bugs or "
    "design problems, citing the file names."
)
REASONING_OUTPUT = 1536
REASONING_TASK = (
    "A snail starts at the bottom of a 30 m wall. Each day it climbs 3 m up and each night it "
    "slips 2 m back down. How many days does it take to reach the top? Think carefully about "
    "the last day, then answer with the number of days and one sentence of justification."
)
SUSTAINED_TASKS = (
    (
        "sustained-lru-cache",
        "Write a Python module implementing a thread-safe LRU cache with TTL expiry, type hints, "
        "and docstrings, plus a pytest file covering eviction, expiry, and concurrent access.",
    ),
    (
        "sustained-tokenizer",
        "Write a Python command-line tool that tokenizes a source file into identifiers, numbers, "
        "strings, and operators, with a streaming API, error recovery, and tests.",
    ),
    (
        "sustained-event-store",
        "Design and implement a small event-sourcing library in Python with an append-only "
        "store, snapshots, projections, and optimistic concurrency, with tests.",
    ),
)
WARMUP_PROMPTS = (
    "Write a Python function that parses ISO 8601 dates.",
    "Write a Python function that merges overlapping intervals.",
    "Write a Python function that validates balanced brackets.",
    "Write a Python function that flattens nested lists.",
)

# Conversation-reuse case: a fixed multi-turn coding session with tool results, embedded so
# every run replays identical prefixes. Each cumulative prefix is one request; the model
# continues after the file dump, after the failing test run, and after the applied patch.
CONVERSATION_OUTPUT = 256

_CONVERSATION_TASK = (
    "worker.py has a race: after an entry's TTL expires, two concurrent get() calls can both "
    "start a load, and the slower loader's stale value overwrites the fresher one, "
    "occasionally resurrecting deleted keys. test_worker.py::test_stale_refresh_race fails "
    "once in a while. Read the file, run the test, patch worker.py, and re-run the test. "
    "When the tests pass, summarize the fix in a few sentences."
)
_CONVERSATION_SOURCE = '''\
"""Background-revalidating metadata cache."""
import threading
import time


class RevalidatingCache:
    def __init__(self, loader, ttl=30.0):
        self._loader = loader
        self._ttl = ttl
        self._data = {}            # key -> (value, expires_at)
        self._lock = threading.Lock()

    def get(self, key):
        entry = self._data.get(key)
        if entry and entry[1] > time.monotonic():
            return entry[0]
        value = self._loader(key)
        self._store(key, value)
        return value

    def invalidate(self, key):
        with self._lock:
            self._data.pop(key, None)

    def _store(self, key, value):
        with self._lock:
            self._data[key] = (value, time.monotonic() + self._ttl)

    def refresh(self, key):
        self._store(key, self._loader(key))

    def snapshot(self):
        now = time.monotonic()
        with self._lock:
            return {k: v for k, (v, exp) in self._data.items() if exp > now}
'''
_CONVERSATION_TESTS = """\
$ pytest test_worker.py -q -p no:randomly -k stale_refresh --count=200
...F...
=================================== FAILURES ===================================
___________________________ test_stale_refresh_race ____________________________

    def test_stale_refresh_race():
        slow = threading.Barrier(2)
        def loader(key):
            slow.wait(timeout=2)
            return "stale-v2" if loader.calls == 0 else "fresh-v1"
        cache = RevalidatingCache(loader, ttl=0.05)
        cache._data["k"] = ("v1", time.monotonic() + 1)
        time.sleep(0.06)                     # expire the entry
        threads = [threading.Thread(target=cache.get, args=("k",)) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
>       assert cache.snapshot()["k"] == "fresh-v1"
E       AssertionError: assert 'stale-v2' == 'fresh-v1'

1 failed, 5 passed (flaky: failed 38/200 runs)
"""
_CONVERSATION_PATCH = """\
--- a/worker.py
+++ b/worker.py
@@ -8,6 +8,7 @@ class RevalidatingCache:
         self._lock = threading.Lock()
+        self._loading = {}                 # key -> threading.Event
@@ -14,8 +15,20 @@ class RevalidatingCache:
     def get(self, key):
-        entry = self._data.get(key)
-        if entry and entry[1] > time.monotonic():
-            return entry[0]
-        value = self._loader(key)
-        self._store(key, value)
-        return value
+        now = time.monotonic()
+        with self._lock:
+            entry = self._data.get(key)
+            if entry and entry[1] > now:
+                return entry[0]
+            waiter = self._loading.get(key)
+            if waiter is not None:
+                fresh = waiter
+            else:
+                fresh = threading.Event()
+                self._loading[key] = fresh
+        ...

$ pytest test_worker.py -q -p no:randomly --count=200
120 passed in 41.8s (0 flakes)"""


def conversation_turns() -> list[list[dict[str, Any]]]:
    """Cumulative message prefixes of the fixed coding conversation, shortest first.

    The assistant messages carry realistic analyses and ``tool_calls``; the ``tool`` results
    carry the file source, the flaky pytest report, and the applied patch with a clean rerun.
    """
    turns: list[list[dict[str, Any]]] = []
    history: list[dict[str, Any]] = [{"role": "user", "content": _CONVERSATION_TASK}]

    def add(message: dict[str, Any]) -> None:
        history.append(message)
        if message["role"] == "tool":
            turns.append([dict(m) for m in history])

    add(
        {
            "role": "assistant",
            "content": "I will read worker.py first.",
            "tool_calls": [
                {
                    "id": "call_read_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "worker.py"}'},
                }
            ],
        }
    )
    add({"role": "tool", "tool_call_id": "call_read_1", "content": _CONVERSATION_SOURCE})
    add(
        {
            "role": "assistant",
            "content": (
                "get() checks expiry, then loads and stores without coordinating concurrent "
                "misses: both callers pass the expiry check, both call the loader, and the "
                "slower _store wins. I will reproduce it with the existing flaky test."
            ),
            "tool_calls": [
                {
                    "id": "call_tests_1",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": '{"command": "pytest test_worker.py -q --count=200"}',
                    },
                }
            ],
        }
    )
    add({"role": "tool", "tool_call_id": "call_tests_1", "content": _CONVERSATION_TESTS})
    add(
        {
            "role": "assistant",
            "content": (
                "Confirmed: one load must own the refresh and the loser must return the "
                "winner's value. Applying a per-key in-flight guard to worker.py."
            ),
            "tool_calls": [
                {
                    "id": "call_edit_1",
                    "type": "function",
                    "function": {
                        "name": "edit_file",
                        "arguments": '{"path": "worker.py", "patch": "<in-flight guard>"}',
                    },
                }
            ],
        }
    )
    add({"role": "tool", "tool_call_id": "call_edit_1", "content": _CONVERSATION_PATCH})
    return turns


@dataclass(frozen=True)
class Policy:
    """Sampling settings recorded with every baseline."""

    temperature: float
    top_k: int
    top_p: float
    min_p: float
    repetition_penalty: float
    presence_penalty: float

    def fields(self) -> dict[str, float | int]:
        return {
            "temperature": self.temperature,
            "top_k": self.top_k,
            "top_p": self.top_p,
            "min_p": self.min_p,
            "repetition_penalty": self.repetition_penalty,
            "presence_penalty": self.presence_penalty,
        }


PERFORMANCE = Policy(1.0, 20, 0.95, 0.0, 1.0, 0.0)
FUNCTIONAL = Policy(0.0, 20, 0.95, 0.0, 1.0, 0.0)


def thinking_request(kind: str, extra: dict[str, Any]) -> dict[str, Any]:
    """Record explicit thinking controls after overrides; an empty mapping means unspecified.

    These are request fields, not confirmation of server-side behavior. Template kwargs
    are retained intact because their interpretation belongs to the server's template.
    """
    return _thinking_fields({**THINKING_OFF.get(kind, {}), **extra})


def reasoning_request(kind: str, extra: dict[str, Any]) -> dict[str, Any]:
    """Record the thinking controls used by the reasoning case, after user overrides."""
    return _thinking_fields({**THINKING_ON.get(kind, {}), **extra})


_THINKING_KEYS = (
    "reasoning_effort",
    "enable_thinking",
    "thinking",
    "chat_template_kwargs",
    "reasoning_budget_tokens",
)


def _thinking_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: fields[key] for key in _THINKING_KEYS if key in fields}


def request_payload(
    kind: str,
    model: str,
    messages: list[dict[str, Any]],
    policy: Policy,
    *,
    max_tokens: int,
    extra: dict[str, Any],
    stream: bool,
    case_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a chat-completions body.

    ``case_extra`` applies per-workload defaults (for example thinking on) above runtime
    defaults; ``extra`` still overrides any field.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        TOKEN_LIMIT_FIELD.get(kind, "max_tokens"): max_tokens,
        **policy.fields(),
        **THINKING_OFF.get(kind, {}),
    }
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    payload.update(case_extra or {})
    payload.update(extra)
    return payload


@dataclass(frozen=True)
class SuiteConfig:
    """Sizes and counts of the workload suite; tests use a small one."""

    probe_tokens: int = 8192
    noise_runs: int = 5
    probe_output: int = 1024
    contexts: tuple[tuple[str, int], ...] = (
        ("context-32k", 32768),
        ("context-64k", 65536),
        ("context-120k", 120000),
    )
    context_output: int = 1024
    largest_context_runs: int = 2
    sustained_output: int = 2048
    min_sustained_output: int = 512
    warmup_max: int = 4
    warmup_tolerance: float = 0.10
    warmup_output: int = 64
    idle_seconds: float = 30.0
    load_timeout_s: float = 1800.0
    ready_poll_s: float = 2.0
    settle_seconds: float = 10.0
    settle_max_seconds: float = 120.0
    settle_poll_s: float = 1.0
    settle_system_cpu_percent: float = 15.0
    settle_server_cpu_cores: float = 0.25
    loaded_idle_seconds: float = 10.0
    unload_seconds: float = 10.0
    sample_interval_s: float = 0.5
    request_timeout_s: float = 3600.0


@dataclass(frozen=True)
class Document:
    name: str
    text: str


def default_corpus_directory() -> Path:
    """The running interpreter's standard library, which is PSF-licensed source text."""
    return Path(sysconfig.get_paths()["stdlib"])


def load_corpus(directory: Path) -> list[Document]:
    """Top-level Python files of a directory in sorted order, excluding tiny and huge ones.

    Raises:
        ValueError: the directory has no usable files.
    """
    documents = []
    for path in sorted(directory.glob("*.py")):
        text = path.read_text(errors="replace")
        if MIN_DOCUMENT_CHARS <= len(text) <= MAX_DOCUMENT_CHARS:
            documents.append(Document(path.name, text))
    if not documents:
        raise ValueError(f"The corpus directory {directory} has no usable Python files")
    return documents


@dataclass(frozen=True)
class Prompt:
    text: str
    chars: int
    content_sha256: str
    prompt_sha256: str


def build_prompt(
    corpus: list[Document], *, nonce: str, variant: int, target_chars: int, task: str
) -> Prompt:
    """Assemble a prompt of exactly ``target_chars`` characters: nonce, file content, then the task.

    The nonce leads the prompt so no earlier prompt shares a prefix with it. ``variant`` rotates
    the starting file so repeated requests carry different content. ``content_sha256`` excludes
    the nonce and is stable across runs.

    Raises:
        ValueError: the corpus is smaller than the requested length.
    """
    tail = f"\n\n{task}"
    header = f"Request {nonce}.\n\n"
    body_chars = target_chars - len(header) - len(tail)
    if body_chars <= 0:
        raise ValueError("The requested prompt length is shorter than its header and task")
    start = (variant * VARIANT_STRIDE) % len(corpus)
    body = ""
    for offset in range(len(corpus)):
        document = corpus[(start + offset) % len(corpus)]
        body += f"### File: {document.name}\n{document.text}\n\n"
        if len(body) >= body_chars:
            break
    else:
        raise ValueError("The corpus is smaller than the requested prompt length")
    text = f"{header}{body[:body_chars]}{tail}"
    content = hashlib.sha256((body[:body_chars] + tail).encode()).hexdigest()
    return Prompt(text, len(text), content, hashlib.sha256(text.encode()).hexdigest())


def fit_prompt(
    build: Callable[[int], Prompt],
    count: Callable[[Prompt], int | None],
    target_tokens: int,
    *,
    initial_chars: int,
) -> tuple[Prompt, int | None]:
    """Resize a prompt until its counted tokens land just under ``target_tokens``.

    Characters per token vary with content, so a ratio measured on one prompt does not carry over.
    Returns the prompt and its counted tokens, or the first prompt and ``None`` when ``count``
    cannot count. If no round lands under the target, the last prompt is returned and the caller
    must check its count.

    Raises:
        ValueError: ``build`` cannot make a prompt of the requested size.
    """
    chars = initial_chars
    best: tuple[Prompt, int] | None = None
    last: tuple[Prompt, int] | None = None
    for _ in range(FIT_ROUNDS):
        prompt = build(chars)
        tokens = count(prompt)
        if tokens is None:
            return prompt, None
        last = (prompt, tokens)
        if tokens <= target_tokens:
            if best is None or tokens > best[1]:
                best = (prompt, tokens)
            if tokens >= target_tokens * (1 - FIT_TOLERANCE):
                return prompt, tokens
        chars = max(1, int(chars * target_tokens * (1 - FIT_TOLERANCE / 2) / max(tokens, 1)))
    if best is not None:
        return best
    assert last is not None
    return last


def calibrate(prompt_chars: int, prompt_tokens: int) -> float:
    """Characters per token observed on one request, clamped to a sane range."""
    return min(MAX_CHARS_PER_TOKEN, max(MIN_CHARS_PER_TOKEN, prompt_chars / prompt_tokens))


def target_chars(tokens: int, chars_per_token: float) -> int:
    """Characters of content to request for a token target, kept slightly under it."""
    return int(tokens * chars_per_token * LENGTH_MARGIN)


@dataclass(frozen=True)
class PlannedContext:
    label: str
    tokens: int
    skip: str | None


def plan_contexts(config: SuiteConfig, context_tokens: int) -> list[PlannedContext]:
    """Mark the context cases whose input plus output cannot fit the server's context."""
    plan = []
    for label, tokens in config.contexts:
        skip = None
        if tokens + config.context_output > context_tokens:
            skip = (
                f"Input {tokens:,} plus output {config.context_output:,} tokens does not fit "
                f"the {context_tokens:,}-token context"
            )
        plan.append(PlannedContext(label, tokens, skip))
    return plan
