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
FIT_TOLERANCE = 0.03
FIT_ROUNDS = 8

# Verified field names; other servers need their own settings supplied with --request-extra.
THINKING_OFF: dict[str, dict[str, Any]] = {"strata": {"reasoning_effort": "none"}}
TOKEN_LIMIT_FIELD = {"strata": "max_completion_tokens"}
# Servers with a tokenizer route that counts a prompt without running it.
TOKEN_COUNT_ROUTE = {"strata": "/v1/messages/count_tokens"}

REVIEW_TASK = (
    "Summarize what each file above is responsible for, then list three potential bugs or "
    "design problems, citing the file names."
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


def thinking_configured(kind: str) -> bool:
    """Whether a verified way of disabling thinking is known for this server kind."""
    return kind in THINKING_OFF


def request_payload(
    kind: str,
    model: str,
    messages: list[dict[str, Any]],
    policy: Policy,
    *,
    max_tokens: int,
    extra: dict[str, Any],
    stream: bool,
) -> dict[str, Any]:
    """Build a chat-completions body; ``extra`` overrides any default field."""
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
    sustained_output: int = 2048
    min_sustained_output: int = 512
    warmup_max: int = 4
    warmup_tolerance: float = 0.10
    warmup_output: int = 64
    idle_seconds: float = 5.0
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
