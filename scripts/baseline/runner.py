"""The baseline runner: preflight, monitoring, workloads in a fixed order, and a durable record.

The runner attaches to a server that is already running. It never starts, stops, or reconfigures
it. Everything it observes is appended to the run directory as it happens, so an interrupted run
keeps usable data.
"""

import dataclasses
import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from baseline import api, functional, schema, stats, vision, workloads
from baseline.rawlog import RunWriter
from baseline.sampler import Sampler
from baseline.schema import ExitCode
from baseline.workloads import Document, Policy, SuiteConfig

CHAT = "/v1/chat/completions"
PROBE_CASE = "context-8k"
CALIBRATION_TOKENS = 1024
VISION_OUTPUT_TOKENS = 512
FUNCTIONAL_OUTPUT_TOKENS = 256


class PreflightError(Exception):
    """The server cannot be used; the message says why."""


class Interrupted(Exception):
    """The runner was asked to stop between requests."""


@dataclass(frozen=True)
class RunConfig:
    """Everything one run needs; the command line builds it, tests build it directly."""

    recipe: str
    kind: str
    base_url: str
    model: str | None
    context_tokens: int
    corpus: list[Document]
    run_id: str
    expectations: vision.Expectations
    image: Path
    image_is_default: bool
    suite: SuiteConfig = field(default_factory=SuiteConfig)
    request_extra: dict[str, Any] = field(default_factory=dict)
    target: dict[str, Any] = field(default_factory=dict)
    meta_extra: dict[str, Any] = field(default_factory=dict)


def converged(rates: list[float | None], tolerance: float) -> bool:
    """Whether the last two decode rates agree within ``tolerance`` of the larger one."""
    if len(rates) < 2:
        return False
    earlier, latest = rates[-2], rates[-1]
    if earlier is None or latest is None or max(earlier, latest) <= 0:
        return False
    return abs(earlier - latest) / max(earlier, latest) <= tolerance


def _describe(policy: Policy) -> dict[str, float | int]:
    return policy.fields()


class Runner:
    """Run the suite against one server and record it to ``writer``."""

    def __init__(
        self,
        config: RunConfig,
        writer: RunWriter,
        sampler: Sampler | None = None,
        *,
        stop: threading.Event | None = None,
        clock: Callable[[], float] = time.monotonic,
        opener: Callable[..., Any] = urlopen,
        progress: Callable[[str], None] = lambda message: None,
        cleanup: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._writer = writer
        self._sampler = sampler
        self._stop = stop or threading.Event()
        self._clock = clock
        self._opener = opener
        self._progress = progress
        self._cleanup = cleanup
        self._model = config.model or ""
        self._chars_per_token = workloads.INITIAL_CHARS_PER_TOKEN
        self._calibrated = False
        self._problems: list[str] = []
        self._meta: dict[str, Any] = self._initial_meta()

    def _initial_meta(self) -> dict[str, Any]:
        config = self._config
        meta: dict[str, Any] = {
            "schema_version": schema.SCHEMA_VERSION,
            "suite_version": schema.SUITE_VERSION,
            "recipe": config.recipe,
            "run": {"id": config.run_id, "status": "interrupted"},
            "server": {
                "kind": config.kind,
                "model": config.model or "unknown",
                "context_tokens": config.context_tokens,
            },
            "policy": {
                "performance": _describe(workloads.PERFORMANCE),
                "functional": _describe(workloads.FUNCTIONAL),
                "request_extra": config.request_extra,
                "thinking_disabled_by_default": workloads.thinking_configured(config.kind),
            },
            "target": config.target,
            "workload": {
                "suite": dataclasses.asdict(config.suite),
                "corpus_files": len(config.corpus),
                "corpus_sha256": hashlib.sha256(
                    "".join(f"{d.name}\n{d.text}" for d in config.corpus).encode()
                ).hexdigest(),
                "chars_per_token": workloads.INITIAL_CHARS_PER_TOKEN,
                "chars_per_token_source": "initial",
            },
        }
        for key, value in config.meta_extra.items():
            existing = meta.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                value = {**existing, **value}
            meta[key] = value
        return meta

    def _save_meta(self) -> None:
        self._writer.write_meta(self._meta)

    def _check_stop(self) -> None:
        if self._stop.is_set():
            raise Interrupted

    def run(self) -> ExitCode:
        """Run the suite; returns the process exit status and leaves the run directory complete."""
        self._save_meta()
        status, code, error = "complete", ExitCode.OK, None
        monitoring = False
        try:
            try:
                self._preflight()
            except PreflightError as failure:
                status, code, error = "failed", ExitCode.PREFLIGHT_FAILED, str(failure)
            else:
                if self._sampler is not None:
                    self._sampler.start()
                    monitoring = True
                self._workloads()
        except (KeyboardInterrupt, Interrupted):
            status, code = "interrupted", ExitCode.INTERRUPTED
        except Exception as failure:  # keep what was recorded and say what broke
            status, code, error = "failed", ExitCode.CHECKS_FAILED, repr(failure)
        finally:
            self._finish(monitoring)
        if code == ExitCode.OK and self._problems:
            code = ExitCode.CHECKS_FAILED
        self._meta["run"] = {"id": self._config.run_id, "status": status}
        if error:
            self._meta["run"]["error"] = error
        if self._problems:
            self._meta["problems"] = self._problems
        self._save_meta()
        return code

    def _finish(self, monitoring: bool) -> None:
        if monitoring and self._sampler is not None:
            self._sampler.stop()
        if self._cleanup is not None:
            self._cleanup()

    def _preflight(self) -> None:
        self._progress("Checking the server")
        try:
            data = api.post_json(
                self._config.base_url, "/v1/models", None, timeout=30, opener=self._opener
            )
        except api.ApiError as error:
            raise PreflightError(str(error)) from error
        entries = data.get("data", [])
        served = [m["id"] for m in entries if isinstance(m, dict) and "id" in m]
        if self._config.model is None:
            if len(served) != 1:
                listing = ", ".join(served) or "none"
                raise PreflightError(
                    f"{len(served)} models are served ({listing}); choose with --model"
                )
            self._model = served[0]
        else:
            try:
                api.require_model(served, self._config.model)
            except api.ApiError as error:
                raise PreflightError(str(error)) from error
        self._meta["server"]["model"] = self._model
        self._save_meta()

    def _workloads(self) -> None:
        self._idle()
        self._functional_checks()
        self._warmup()
        self._probe()
        self._sustained()
        self._contexts()

    def _idle(self) -> None:
        seconds = self._config.suite.idle_seconds
        if seconds <= 0:
            return
        self._progress("Recording the idle reference")
        start = self._clock()
        if self._stop.wait(seconds):
            raise Interrupted
        self._meta["idle"] = {"start_s": start, "end_s": self._clock()}
        self._save_meta()

    def _payload(
        self,
        messages: list[dict[str, Any]],
        policy: Policy,
        max_tokens: int,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        return workloads.request_payload(
            self._config.kind,
            self._model,
            messages,
            policy,
            max_tokens=max_tokens,
            extra=self._config.request_extra,
            stream=stream,
        )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        return api.post_json(
            self._config.base_url,
            CHAT,
            payload,
            timeout=self._config.suite.request_timeout_s,
            opener=self._opener,
        )

    def _stream_call(self, payload: dict[str, Any]) -> api.StreamResult:
        timeout = self._config.suite.request_timeout_s
        return api.stream_chat(
            self._config.base_url,
            CHAT,
            payload,
            timeout=timeout,
            clock=self._clock,
            opener=self._opener,
            deadline_s=timeout,
        )

    def _functional_checks(self) -> None:
        self._progress("Running functional checks")
        self._functional("text", self._check_text)
        self._functional("tools", self._check_tools)
        self._functional("vision", self._check_vision)

    def _functional(self, check_id: str, body: Callable[[], dict[str, Any]]) -> None:
        self._check_stop()
        record: dict[str, Any] = {"phase": "functional", "case": check_id}
        record["started_s"] = self._clock()
        try:
            entry = body()
        except KeyboardInterrupt:
            entry = {"id": check_id, "status": "skipped", "detail": "interrupted"}
            record.update(ended_s=self._clock(), status="interrupted", functional=entry)
            self._writer.append_request(record)
            raise
        except (api.ApiError, ValueError, OSError, KeyError, IndexError, TypeError) as error:
            entry = {"id": check_id, "status": "fail", "detail": str(error)}
        record["ended_s"] = self._clock()
        record["status"] = "ok" if entry["status"] in ("pass", "skipped") else "failed"
        record["functional"] = entry
        self._writer.append_request(record)
        if entry["status"] not in ("pass", "skipped"):
            self._problems.append(f"functional check {check_id}: {entry['status']}")

    def _check_text(self) -> dict[str, Any]:
        messages = [{"role": "user", "content": functional.TEXT_PROMPT}]
        payload = self._payload(
            messages, workloads.FUNCTIONAL, FUNCTIONAL_OUTPUT_TOKENS, stream=True
        )
        result = self._stream_call(payload)
        if not result.text.strip():
            raise ValueError("The streamed answer was empty")
        return {"id": "text", "status": "pass", "detail": f"{len(result.text)} characters"}

    def _check_tools(self) -> dict[str, Any]:
        prompt = functional.TOOL_PROMPT
        first_payload = self._payload(
            [{"role": "user", "content": prompt}],
            workloads.FUNCTIONAL,
            FUNCTIONAL_OUTPUT_TOKENS,
            stream=False,
        )
        first_payload.update(tools=functional.TOOLS, tool_choice=functional.TOOL_CHOICE)
        message = self._post(first_payload)["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        functional.check_tool_call(calls)
        second_payload = self._payload(
            functional.tool_followup(prompt, calls),
            workloads.FUNCTIONAL,
            FUNCTIONAL_OUTPUT_TOKENS,
            stream=False,
        )
        second_payload.update(tools=functional.TOOLS, tool_choice="none")
        answer = self._post(second_payload)["choices"][0]["message"].get("content") or ""
        if not functional.reports_temperature(answer):
            raise ValueError(f"The answer did not report the supplied temperature: {answer[:200]}")
        return {"id": "tools", "status": "pass", "detail": "forced call and fixed result handled"}

    def _check_vision(self) -> dict[str, Any]:
        expectations = self._config.expectations
        raw = self._config.image.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        content = functional.image_content(vision.build_prompt(expectations), raw)
        payload = self._payload(
            [{"role": "user", "content": content}],
            workloads.FUNCTIONAL,
            VISION_OUTPUT_TOKENS,
            stream=False,
        )
        answer = self._post(payload)["choices"][0]["message"].get("content") or ""
        if not self._config.image_is_default:
            return {
                "id": "vision",
                "status": "skipped",
                "detail": "Custom image; review the answer manually",
                "image_sha256": digest,
                "answer": answer,
            }
        if digest != expectations.image_sha256:
            raise ValueError("The vision image does not match the expectations file")
        score = vision.score_answer(expectations, answer)
        return {**score.to_result(expectations), "status": score.status}

    def _stream_request(
        self,
        *,
        phase: str,
        case: str,
        run: int,
        messages: list[dict[str, Any]],
        max_tokens: int,
        **extra: Any,
    ) -> api.StreamResult | None:
        self._check_stop()
        payload = self._payload(messages, workloads.PERFORMANCE, max_tokens, stream=True)
        record: dict[str, Any] = {"phase": phase, "case": case, "run": run, **extra}
        record["max_tokens"] = max_tokens
        record["started_s"] = self._clock()
        result: api.StreamResult | None = None
        error: str | None = None
        try:
            result = self._stream_call(payload)
            if not (result.text or result.tool_calls):
                error = "empty response"
        except api.StreamInterrupted as failure:
            result, error = failure.partial, str(failure)
        except api.ApiError as failure:
            error = str(failure)
        except KeyboardInterrupt:
            record.update(ended_s=self._clock(), status="interrupted", error="interrupted")
            self._writer.append_request(record)
            raise
        record["ended_s"] = self._clock()
        record["status"] = "failed" if error else "ok"
        record["error"] = error
        if result is not None:
            record["usage"] = dataclasses.asdict(result.usage) if result.usage else None
            record["first_output_s"] = result.first_output_s
            record["last_output_s"] = result.last_output_s
            record["finish_reason"] = result.finish_reason
        self._writer.append_request(record)
        if error:
            self._problems.append(f"{case} run {run}: {error}")
            return None if result is None or not result.text else result
        return result

    def _prompt_request(
        self, *, phase: str, case: str, run: int, nonce: str, variant: int, tokens: int,
        task: str, max_tokens: int, **extra: Any,
    ) -> api.StreamResult | None:  # fmt: skip
        prompt = workloads.build_prompt(
            self._config.corpus,
            nonce=nonce,
            variant=variant,
            target_chars=workloads.target_chars(tokens, self._chars_per_token),
            task=task,
        )
        result = self._stream_request(
            phase=phase,
            case=case,
            run=run,
            messages=[{"role": "user", "content": prompt.text}],
            max_tokens=max_tokens,
            requested_input_tokens=tokens,
            chars=prompt.chars,
            content_sha256=prompt.content_sha256,
            prompt_sha256=prompt.prompt_sha256,
            **extra,
        )
        if result is not None and not self._calibrated and result.usage:
            used = result.usage.prompt_tokens
            if used:
                self._chars_per_token = workloads.calibrate(prompt.chars, used)
                self._calibrated = True
                self._meta["workload"]["chars_per_token"] = round(self._chars_per_token, 4)
                self._meta["workload"]["chars_per_token_source"] = "usage"
                self._save_meta()
        return result

    def _warmup(self) -> None:
        suite = self._config.suite
        self._progress("Warming up the server")
        rates: list[float | None] = []
        for index in range(suite.warmup_max):
            nonce = f"{self._config.run_id}-warmup-{index}"
            if index == 0:
                result = self._prompt_request(
                    phase="warmup", case="warmup", run=1, nonce=nonce, variant=900,
                    tokens=CALIBRATION_TOKENS, task=workloads.REVIEW_TASK,
                    max_tokens=suite.warmup_output,
                )  # fmt: skip
            else:
                prompt = workloads.WARMUP_PROMPTS[index % len(workloads.WARMUP_PROMPTS)]
                result = self._stream_request(
                    phase="warmup",
                    case="warmup",
                    run=index + 1,
                    messages=[{"role": "user", "content": f"Request {nonce}.\n\n{prompt}"}],
                    max_tokens=suite.warmup_output,
                )
            rates.append(
                stats.client_decode_rate(
                    result.usage.completion_tokens if result and result.usage else None,
                    result.first_output_s if result else None,
                    result.last_output_s if result else None,
                )
            )
            if converged(rates, suite.warmup_tolerance):
                break
        self._meta["warmup"] = {"converged": converged(rates, suite.warmup_tolerance)}
        self._save_meta()

    def _probe(self) -> None:
        suite = self._config.suite
        for index in range(suite.noise_runs):
            self._progress(f"{PROBE_CASE}: run {index + 1} of {suite.noise_runs}")
            self._prompt_request(
                phase="case", case=PROBE_CASE, run=index + 1,
                nonce=f"{self._config.run_id}-8k-{index}", variant=index,
                tokens=suite.probe_tokens, task=workloads.REVIEW_TASK,
                max_tokens=suite.probe_output, noise_probe=True,
            )  # fmt: skip

    def _sustained(self) -> None:
        suite = self._config.suite
        for case, task in workloads.SUSTAINED_TASKS:
            self._progress(case)
            self._stream_request(
                phase="case",
                case=case,
                run=1,
                messages=[
                    {"role": "user", "content": f"Request {self._config.run_id}-{case}.\n\n{task}"}
                ],
                max_tokens=suite.sustained_output,
                min_output_tokens=suite.min_sustained_output,
            )

    def _contexts(self) -> None:
        suite = self._config.suite
        plan = workloads.plan_contexts(suite, self._config.context_tokens)
        for index, item in enumerate(plan):
            self._check_stop()
            if item.skip is None:
                self._progress(item.label)
                try:
                    self._prompt_request(
                        phase="case", case=item.label, run=1,
                        nonce=f"{self._config.run_id}-{item.label}", variant=100 + index,
                        tokens=item.tokens, task=workloads.REVIEW_TASK,
                        max_tokens=suite.context_output,
                    )  # fmt: skip
                    continue
                except ValueError as error:
                    item = workloads.PlannedContext(item.label, item.tokens, str(error))
            self._writer.append_request(
                {"phase": "case", "case": item.label, "status": "skipped", "note": item.skip}
            )
