"""The baseline runner: preflight, monitoring, workloads in a fixed order, and a durable record.

The runner attaches to a server that is already running. It never starts, stops, or reconfigures
it. Everything it observes is appended to the run directory as it happens, so an interrupted run
keeps usable data.
"""

import dataclasses
import hashlib
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.request import urlopen

from baseline import api, functional, monitor, phases, schema, stats, vision, workloads
from baseline.lifecycle import LifecycleError, StartedServer
from baseline.rawlog import RunWriter
from baseline.sampler import Sampler
from baseline.schema import ExitCode
from baseline.workloads import Document, Policy, SuiteConfig

CHAT = "/v1/chat/completions"
PROBE_CASE = "context-8k"
CALIBRATION_TOKENS = 1024
VISION_OUTPUT_TOKENS = 512
FUNCTIONAL_OUTPUT_TOKENS = 256


class ServerControl(Protocol):
    """Starts and stops the server a run measures."""

    def preflight(self) -> None: ...

    def start(self) -> StartedServer: ...

    def is_running(self) -> bool: ...

    def stop(self) -> None: ...


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
    gpu_address: str | None = None
    keep_running: bool = False


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
        control: ServerControl | None = None,
    ) -> None:
        self._config = config
        self._writer = writer
        self._sampler = sampler
        self._stop = stop or threading.Event()
        self._clock = clock
        self._opener = opener
        self._progress = progress
        self._cleanup = cleanup
        self._control = control
        self._start_attempted = False
        self._model = config.model or ""
        self._chars_per_token = workloads.INITIAL_CHARS_PER_TOKEN
        self._count_failed = False
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
                "thinking_request": workloads.thinking_request(config.kind, config.request_extra),
                "reasoning_request": workloads.reasoning_request(config.kind, config.request_extra),
            },
            "target": config.target,
            "launch_facts": None,
            "phases": {},
            "workload": {
                "suite": dataclasses.asdict(config.suite),
                "corpus_files": len(config.corpus),
                "corpus_sha256": hashlib.sha256(
                    "".join(f"{d.name}\n{d.text}" for d in config.corpus).encode()
                ).hexdigest(),
                "chars_per_token": workloads.INITIAL_CHARS_PER_TOKEN,
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
                if self._control is not None:
                    self._control.preflight()
                else:
                    self._check_server()
            except (PreflightError, LifecycleError) as failure:
                status, code, error = "failed", ExitCode.PREFLIGHT_FAILED, str(failure)
            else:
                if self._sampler is not None:
                    self._sampler.start()
                    monitoring = True
                self._phases_and_workloads()
        except (KeyboardInterrupt, Interrupted):
            status, code = "interrupted", ExitCode.INTERRUPTED
        except (PreflightError, LifecycleError) as failure:
            status, code, error = "failed", ExitCode.PREFLIGHT_FAILED, str(failure)
        except Exception as failure:  # keep what was recorded and say what broke
            status, code, error = "failed", ExitCode.CHECKS_FAILED, repr(failure)
        finally:
            self._shutdown(monitoring, interrupted=status == "interrupted")
        if code == ExitCode.OK and self._problems:
            code = ExitCode.CHECKS_FAILED
        self._meta["run"] = {"id": self._config.run_id, "status": status}
        if error:
            self._meta["run"]["error"] = error
        if self._problems:
            self._meta["problems"] = self._problems
        self._save_meta()
        return code

    @contextmanager
    def _phase(self, name: str) -> Iterator[dict[str, Any]]:
        """Record a phase's interval and outcome in the meta file, even when it raises."""
        entry: dict[str, Any] = {"start_s": self._clock(), "status": "interrupted"}
        self._meta["phases"][name] = entry
        self._progress(f"Phase: {name}")
        try:
            yield entry
            entry["status"] = "ok"
        except (KeyboardInterrupt, Interrupted):
            raise
        except Exception as failure:
            entry["status"] = "failed"
            entry.setdefault("note", str(failure))
            raise
        finally:
            entry["end_s"] = self._clock()
            self._save_meta()

    def _phases_and_workloads(self) -> None:
        if self._control is not None:
            with self._phase("idle"):
                self._wait(self._config.suite.idle_seconds)
            self._start_server()
        with self._phase("settle") as entry:
            self._settle(entry)
        with self._phase("loaded_idle"):
            self._wait(self._config.suite.loaded_idle_seconds)
        self._workloads()

    def _wait(self, seconds: float) -> None:
        if seconds > 0 and self._stop.wait(seconds):
            raise Interrupted

    def _start_server(self) -> None:
        """Start the server, join its cgroup to the monitoring, and wait until it serves."""
        assert self._control is not None
        suite = self._config.suite
        with self._phase("load") as entry:
            self._start_attempted = True
            started = self._control.start()
            container_meta = dict(started.meta)
            self._meta["launch_facts"] = container_meta.pop("launch_facts", None)
            self._meta["container"] = container_meta
            added, target = monitor.target_sources(started.cgroup, self._config.gpu_address)
            self._meta["target"] = target
            if self._sampler is not None:
                self._sampler.add_sources(added)
            begun = self._clock()
            while True:
                self._check_stop()
                if self._served_models():
                    break
                if self._clock() - begun > suite.load_timeout_s:
                    raise PreflightError(
                        f"The server was not ready within {suite.load_timeout_s:g} s"
                    )
                if not self._control.is_running():
                    raise PreflightError(
                        "The server container stopped while loading; see the server logs"
                    )
                self._stop.wait(suite.ready_poll_s)
            entry["measures"] = {"time_to_ready_s": self._clock() - begun}
            self._choose_model(self._served_models())
        self._save_meta()

    def _settle(self, entry: dict[str, Any]) -> None:
        suite, sampler = self._config.suite, self._sampler
        if sampler is None:
            return
        begun = self._clock()
        while True:
            self._check_stop()
            verdict = phases.settled(
                sampler.recent(suite.settle_seconds + 2 * suite.sample_interval_s),
                window_s=suite.settle_seconds,
                system_cpu_max=suite.settle_system_cpu_percent,
                server_cpu_max=suite.settle_server_cpu_cores,
            )
            if verdict:
                if self._clock() - begun < suite.settle_poll_s:
                    entry["note"] = "Already settled when the server became ready"
                return
            if self._clock() - begun > suite.settle_max_seconds:
                entry["note"] = (
                    f"The machine did not settle within {suite.settle_max_seconds:g} s; "
                    "later phases may include start-up activity"
                )
                return
            self._stop.wait(suite.settle_poll_s)

    def _shutdown(self, monitoring: bool, *, interrupted: bool) -> None:
        """Stop what the runner started, observe the machine afterwards, and end monitoring."""
        control = self._control
        if control is not None and self._start_attempted and not self._config.keep_running:
            entry: dict[str, Any] = {"start_s": self._clock(), "status": "ok"}
            self._meta["phases"]["unload"] = entry
            self._progress("Stopping the server")
            stopped = False
            try:
                control.stop()
                entry["measures"] = {"time_to_stop_s": self._clock() - entry["start_s"]}
                stopped = True
            except LifecycleError as failure:
                entry["status"] = "failed"
                entry["note"] = str(failure)
                self._problems.append(str(failure))
            finally:
                entry["end_s"] = self._clock()
            if stopped and monitoring and not interrupted:
                after: dict[str, Any] = {"start_s": self._clock(), "status": "ok"}
                self._meta["phases"]["after_unload"] = after
                self._stop.wait(self._config.suite.unload_seconds)
                after["end_s"] = self._clock()
        if monitoring and self._sampler is not None:
            self._sampler.stop()
        if self._cleanup is not None:
            self._cleanup()

    def _served_models(self) -> list[str]:
        try:
            data = api.post_json(
                self._config.base_url, "/v1/models", None, timeout=30, opener=self._opener
            )
        except api.ApiError:
            return []
        entries = data.get("data", [])
        return [m["id"] for m in entries if isinstance(m, dict) and "id" in m]

    def _choose_model(self, served: list[str]) -> None:
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

    def _check_server(self) -> None:
        """Attach mode: the server must already be up and serve the expected model."""
        self._progress("Checking the server")
        try:
            data = api.post_json(
                self._config.base_url, "/v1/models", None, timeout=30, opener=self._opener
            )
        except api.ApiError as error:
            raise PreflightError(str(error)) from error
        entries = data.get("data", [])
        self._choose_model([m["id"] for m in entries if isinstance(m, dict) and "id" in m])

    def _workloads(self) -> None:
        self._functional_checks()
        self._warmup()
        self._probe()
        self._sustained()
        self._contexts()
        self._conversation()
        self._reasoning()

    def _payload(
        self,
        messages: list[dict[str, Any]],
        policy: Policy,
        max_tokens: int,
        *,
        stream: bool,
        payload_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = workloads.request_payload(
            self._config.kind,
            self._model,
            messages,
            policy,
            max_tokens=max_tokens,
            extra=self._config.request_extra,
            stream=stream,
            case_extra=payload_extra,
        )
        return payload

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
        self._functional("tools", self._check_tools, requests=2)
        self._functional("vision", self._check_vision)

    def _functional(
        self, check_id: str, body: Callable[[], dict[str, Any]], requests: int = 1
    ) -> None:
        self._check_stop()
        record: dict[str, Any] = {"phase": "functional", "case": check_id, "requests": requests}
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
        first_payload.update(
            tools=functional.TOOLS, tool_choice=functional.forced_tool_choice(self._config.kind)
        )
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
        payload_extra: dict[str, Any] | None = None,
        **extra: Any,
    ) -> api.StreamResult | None:
        self._check_stop()
        payload = self._payload(
            messages,
            workloads.PERFORMANCE,
            max_tokens,
            stream=True,
            payload_extra=payload_extra,
        )
        record: dict[str, Any] = {"phase": phase, "case": case, "run": run, **extra}
        record["max_tokens"] = max_tokens
        record["started_s"] = self._clock()
        result: api.StreamResult | None = None
        error: str | None = None
        try:
            result = self._stream_call(payload)
            if not (result.text or result.tool_calls):
                error = "reasoning without visible output" if result.reasoning else "empty response"
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
            record["first_content_s"] = result.first_content_s
            record["last_output_s"] = result.last_output_s
            record["finish_reason"] = result.finish_reason
            record["visible_chars"] = len(result.text)
            record["reasoning_chars"] = len(result.reasoning)
        self._writer.append_request(record)
        if error:
            self._problems.append(f"{case} run {run}: {error}")
            return None if result is None or not result.text else result
        return result

    def _count_tokens(self, text: str) -> int | None:
        """Count a prompt with the server's tokenizer route, without running the prompt."""
        route = workloads.TOKEN_COUNT_ROUTE.get(self._config.kind)
        if route is None or self._count_failed:
            return None
        body = {
            "model": self._model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": text}],
        }
        count_key = "input_tokens"
        if self._config.kind == "tabbyapi":
            body = {
                "text": body["messages"],
                "template_vars": self._config.request_extra.get("chat_template_kwargs", {}),
            }
            count_key = "length"
        try:
            reply = api.post_json(
                self._config.base_url,
                route,
                body,
                timeout=self._config.suite.request_timeout_s,
                opener=self._opener,
            )
            count = reply[count_key]
            if type(count) is not int or count < 1:
                raise ValueError(f"{count_key} is not a positive integer")
        except (api.ApiError, KeyError, TypeError, ValueError) as error:
            self._count_failed = True
            self._progress(f"Token counting is unavailable ({error}); calibrating from usage")
            self._meta["workload"]["token_counting"] = "calibration from reported usage"
            self._save_meta()
            return None
        self._meta["workload"]["token_counting"] = f"server route {route}"
        return count

    def _prompt_request(
        self, *, phase: str, case: str, run: int, nonce: str, variant: int, tokens: int,
        task: str, max_tokens: int, **extra: Any,
    ) -> api.StreamResult | None:  # fmt: skip
        def build(chars: int) -> workloads.Prompt:
            return workloads.build_prompt(
                self._config.corpus, nonce=nonce, variant=variant, target_chars=chars, task=task
            )

        prompt, counted = workloads.fit_prompt(
            build,
            lambda candidate: self._count_tokens(candidate.text),
            tokens,
            initial_chars=workloads.target_chars(tokens, self._chars_per_token),
        )
        if counted is not None and counted + max_tokens > self._config.context_tokens:
            raise ValueError(
                f"Counted {counted:,} input plus {max_tokens:,} output tokens does not fit "
                f"the {self._config.context_tokens:,}-token context"
            )
        result = self._stream_request(
            phase=phase,
            case=case,
            run=run,
            messages=[{"role": "user", "content": prompt.text}],
            max_tokens=max_tokens,
            requested_input_tokens=tokens,
            counted_input_tokens=counted,
            chars=prompt.chars,
            content_sha256=prompt.content_sha256,
            prompt_sha256=prompt.prompt_sha256,
            **extra,
        )
        if counted is None and result is not None and result.usage and result.usage.prompt_tokens:
            self._chars_per_token = workloads.calibrate(prompt.chars, result.usage.prompt_tokens)
            self._meta["workload"]["chars_per_token"] = round(self._chars_per_token, 4)
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

    def _conversation(self) -> None:
        """Replay a fixed multi-turn coding conversation: cold full prompt, then warm prefixes.

        ``conversation-fresh`` sends the complete history while its prefixes are uncached.
        The reuse ladder then replays the same prefixes in growing order, so reported cached
        token counts and first-output latencies show prefix reuse, or nothing when the server
        reports no cached-token counts.
        """
        turns = workloads.conversation_turns()
        self._progress("conversation-fresh")
        self._stream_request(
            phase="case",
            case="conversation-fresh",
            run=1,
            messages=[dict(m) for m in turns[-1]],
            max_tokens=workloads.CONVERSATION_OUTPUT,
            conversation_messages=len(turns[-1]),
        )
        for index, prefix in enumerate(turns, start=1):
            case = f"conversation-reuse-{index}"
            self._progress(case)
            self._stream_request(
                phase="case",
                case=case,
                run=1,
                messages=[dict(m) for m in prefix],
                max_tokens=workloads.CONVERSATION_OUTPUT,
                conversation_messages=len(prefix),
            )

    def _reasoning(self) -> None:
        """One reasoning request: verified enabling controls where known, else template defaults.

        The visible reply and the reasoning text are recorded separately, so reports can show
        time to first visible output and how much of the reply was reasoning.
        """
        self._progress("reasoning-medium")
        self._stream_request(
            phase="case",
            case="reasoning-medium",
            run=1,
            messages=[{"role": "user", "content": workloads.REASONING_TASK}],
            max_tokens=workloads.REASONING_OUTPUT,
            payload_extra=dict(workloads.THINKING_ON.get(self._config.kind, {})),
            workload="reasoning",
        )

    def _contexts(self) -> None:
        suite = self._config.suite
        plan = workloads.plan_contexts(suite, self._config.context_tokens)
        largest = max(plan, key=lambda item: item.tokens, default=None)
        for index, item in enumerate(plan):
            self._check_stop()
            runs = suite.largest_context_runs if item is largest else 1
            if item.skip is None:
                try:
                    for run in range(1, runs + 1):
                        self._progress(
                            f"{item.label}: run {run} of {runs}" if runs > 1 else item.label
                        )
                        self._prompt_request(
                            phase="case", case=item.label, run=run,
                            nonce=f"{self._config.run_id}-{item.label}-{run}",
                            variant=100 + index + 50 * (run - 1),
                            tokens=item.tokens, task=workloads.REVIEW_TASK,
                            max_tokens=suite.context_output, noise_probe=runs > 1,
                        )  # fmt: skip
                    continue
                except ValueError as error:
                    item = workloads.PlannedContext(item.label, item.tokens, str(error))
            self._writer.append_request(
                {"phase": "case", "case": item.label, "status": "skipped", "note": item.skip}
            )
