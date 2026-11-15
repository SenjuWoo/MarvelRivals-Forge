"""Minimal MCP stdio client for fmodel-mcp (FModel.Mcp.exe --config <json>).

Protocol (verified against v1.2.0): newline-delimited JSON-RPC 2.0. `initialize` (protocolVersion 2025-11-25),
then `notifications/initialized`, then `tools/call`; tool results arrive in `result.structuredContent`.
Close every game session before closing stdin: closing early cancels running exports.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path

from . import __version__
from .util import ForgeError, redact

PROTOCOL = "2025-11-25"
TERMINAL = ("completed", "completed_with_errors", "cancelled", "failed")


class McpClient:
    def __init__(self, argv: list[str], cwd: str | None = None, timeout: float = 120):
        self.timeout = timeout
        self.proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, bufsize=0)
        self._id = 0
        self._q: queue.Queue = queue.Queue()
        self._stderr: list[str] = []
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self):
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except ValueError:
                self._stderr.append("stdout(non-json): " + line[:200])
        self._q.put(None)

    def _read_err(self):
        for raw in iter(self.proc.stderr.readline, b""):
            self._stderr.append(raw.decode("utf-8", errors="replace").rstrip()[:300])
            del self._stderr[:-50]

    def _send(self, obj: dict) -> None:
        try:
            self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except OSError as e:
            raise ForgeError("MCP_PIPE_CLOSED", f"fmodel-mcp exited: {self.stderr_tail()}", "run mrforge doctor") from e

    def stderr_tail(self) -> str:
        return redact(" | ".join(self._stderr[-5:]))

    def request(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        deadline = time.time() + (timeout or self.timeout)
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise ForgeError("MCP_TIMEOUT", f"{method} got no answer in {timeout or self.timeout}s", self.stderr_tail())
            try:
                msg = self._q.get(timeout=left)
            except queue.Empty:
                continue
            if msg is None:
                raise ForgeError("MCP_EXITED", f"fmodel-mcp exited during {method}: {self.stderr_tail()}",
                                 "check the generated config (inputRoots, oodleLibrary)")
            if msg.get("id") != rid:
                continue  # notifications / logs
            if "error" in msg:
                raise ForgeError("MCP_ERROR", f"{method}: {redact(json.dumps(msg['error'])[:400])}")
            return msg.get("result", {})

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self) -> dict:
        r = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                        "clientInfo": {"name": "mrforge", "version": __version__}})
        self.notify("notifications/initialized")
        return r

    def call(self, tool: str, args: dict, timeout: float | None = None) -> dict:
        r = self.request("tools/call", {"name": tool, "arguments": args}, timeout)
        if r.get("isError"):
            text = " ".join(c.get("text", "") for c in r.get("content", []) if isinstance(c, dict))
            raise ForgeError("MCP_TOOL_ERROR", f"{tool}: {redact(text)[:500]}")
        sc = r.get("structuredContent")
        if sc is None:
            text = "".join(c.get("text", "") for c in r.get("content", []) if isinstance(c, dict))
            try:
                sc = json.loads(text)
            except ValueError:
                sc = {"text": text}
        return sc

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def wait_job(c: McpClient, session: str, job: str, limit: float = 900) -> dict:
    t = time.time()
    while time.time() - t < limit:
        st = c.call("fmodel_job_status", {"sessionId": session, "jobId": job})
        if st.get("state") in TERMINAL:
            return st
        time.sleep(1.0)
    raise ForgeError("EXPORT_TIMEOUT", f"export job {job} still running after {limit}s")


def write_config(path: Path, input_roots: list[Path], output_root: Path, oodle: Path | None) -> Path:
    cfg = {"inputRoots": [str(Path(p).resolve()) for p in input_roots], "outputRoot": str(Path(output_root).resolve())}
    if oodle:
        cfg["oodleLibrary"] = str(Path(oodle).resolve())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path
