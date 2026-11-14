"""An in-process OpenAI-compatible server for runner tests."""

import json
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

VISION_ANSWER = {
    "application": "amdgpu_top",
    "gpu_model": "AMD Radeon RX 9070 XT",
    "application_version": "v0.11.5",
    "architecture": "GFX1201",
    "device_vram": "15,737 / 16,304 MiB",
    "device_gtt": "116 / 30,328 MiB",
    "process_name": "strata-host",
    "process_vram": "15,419 M",
    "panel_headings": ["GRBM", "Memory Usage", "Activity", "fdinfo", "Sensors", "GPU Metrics"],
}


class FakeServer:
    """Serves models, streamed completions, forced tool calls, and image answers.

    Behavior switches are plain attributes the test sets before or during a run.
    """

    def __init__(
        self,
        model: str = "test-model",
        *,
        output_tokens: int = 24,
        token_delay_s: float = 0.002,
        chars_per_token: float = 4.0,
    ) -> None:
        self.model = model
        self.models = [model]
        self.output_tokens = output_tokens
        self.token_delay_s = token_delay_s
        self.chars_per_token = chars_per_token
        self.behave: Callable[[dict[str, Any]], str | None] = lambda payload: None
        self.release = threading.Event()
        self.vision_answer: dict[str, Any] = dict(VISION_ANSWER)
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> "FakeServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.release.set()
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> "FakeServer":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def _json(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path == "/v1/models":
                    self._json(200, {"data": [{"id": name} for name in outer.models]})
                else:
                    self._json(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                outer.requests.append(payload)
                behavior = outer.behave(payload)
                if behavior == "hang":
                    outer.release.wait(30)
                    return
                if behavior == "fail":
                    self._json(500, {"error": {"message": "injected failure"}})
                    return
                self._chat(payload, truncate=behavior == "truncate")

            def _chat(self, payload: dict[str, Any], truncate: bool = False) -> None:
                messages = payload["messages"]
                chars = sum(len(str(m.get("content") or "")) for m in messages)
                prompt_tokens = max(1, int(chars / outer.chars_per_token))
                last = messages[-1]
                if "tools" in payload:
                    self._tools(payload, last, prompt_tokens)
                elif isinstance(last.get("content"), list):
                    answer = json.dumps(outer.vision_answer)
                    self._json(200, self._completion(answer, prompt_tokens))
                else:
                    self._stream(payload, prompt_tokens, truncate)

            def _completion(self, content: str, prompt_tokens: int) -> dict[str, Any]:
                return {
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 8},
                }

            def _tools(self, payload: dict[str, Any], last: dict[str, Any], tokens: int) -> None:
                if last.get("role") == "tool":
                    self._json(200, self._completion("It is 17 degrees in Belgrade.", tokens))
                    return
                call = {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_temperature", "arguments": '{"city": "Belgrade"}'},
                }
                message = {"role": "assistant", "content": None, "tool_calls": [call]}
                self._json(200, {"choices": [{"message": message, "finish_reason": "tool_calls"}]})

            def _event(self, body: dict[str, Any]) -> None:
                self.wfile.write(b"data: " + json.dumps(body).encode() + b"\n\n")
                self.wfile.flush()

            def _stream(self, payload: dict[str, Any], prompt_tokens: int, truncate: bool) -> None:
                limit = payload.get("max_completion_tokens") or payload.get("max_tokens") or 10**6
                count = min(limit, outer.output_tokens)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self._event({"choices": [{"delta": {"role": "assistant"}}]})
                for index in range(count):
                    time.sleep(outer.token_delay_s)
                    self._event({"choices": [{"delta": {"content": f"tok{index} "}}]})
                    if truncate and index == 1:
                        return
                reason = "length" if count == limit else "stop"
                self._event({"choices": [{"delta": {}, "finish_reason": reason}]})
                usage = {"prompt_tokens": prompt_tokens, "completion_tokens": count}
                self._event({"choices": [], "usage": usage})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        return Handler
