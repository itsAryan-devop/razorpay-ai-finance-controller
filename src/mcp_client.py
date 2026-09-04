"""
mcp_client.py — a minimal MCP (Model Context Protocol) stdio client for talking to the
official `razorpay-mcp-server` binary as a subprocess.

Not a general-purpose MCP SDK — just enough of the protocol (initialize handshake,
tools/list, tools/call over newline-delimited JSON-RPC on stdin/stdout) to let
sources.py's RazorpaySettlementsSource call real Razorpay tools. Deliberately small:
the alternative (pulling in a full MCP client SDK dependency) is not warranted for one
call site.

The binary itself is NOT committed to the repo (fetched from the official
razorpay/razorpay-mcp-server GitHub releases, checksum-verified, ~3MB) — see
tools/README.md for how to fetch it. RAZORPAY_MCP_SERVER_PATH overrides the default
local path if you place it elsewhere.
"""
import json
import os
import subprocess

DEFAULT_EXE = os.path.join(os.path.dirname(__file__), "..", "tools",
                           "razorpay-mcp-server", "razorpay-mcp-server.exe")
EXE_PATH = os.getenv("RAZORPAY_MCP_SERVER_PATH", DEFAULT_EXE)


class McpUnavailable(RuntimeError):
    """The MCP server binary is missing, or the handshake/tool call failed."""


class RazorpayMcpClient:
    """A short-lived stdio session with the razorpay-mcp-server binary. Use as a
    context manager so the subprocess is always terminated. Always launched with
    --read-only: this client is for reading reconciliation data, never for mutating
    real (even test-mode) Razorpay state."""

    def __init__(self, key_id: str, key_secret: str, exe_path: str = None,
                read_only: bool = True, timeout: float = 15.0):
        # Resolved at call time (not bound as a def-time default) so overriding the
        # module-level EXE_PATH — e.g. via monkeypatch in tests — actually takes effect.
        self.exe_path = exe_path if exe_path is not None else EXE_PATH
        self.key_id, self.key_secret = key_id, key_secret
        self.read_only = read_only
        self.timeout = timeout
        self._proc = None
        self._next_id = 1

    def __enter__(self):
        if not os.path.exists(self.exe_path):
            raise McpUnavailable(
                f"razorpay-mcp-server binary not found at {self.exe_path}. "
                "See tools/README.md to fetch it.")
        env = dict(os.environ, RAZORPAY_KEY_ID=self.key_id,
                  RAZORPAY_KEY_SECRET=self.key_secret)
        args = [self.exe_path, "stdio"] + (["--read-only"] if self.read_only else [])
        try:
            self._proc = subprocess.Popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env, text=True, bufsize=1)
        except OSError as e:
            raise McpUnavailable(f"failed to launch razorpay-mcp-server: {e!r}") from e
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "recon-controller", "version": "0.1"},
        })
        self._notify("notifications/initialized")
        return self

    def __exit__(self, *exc):
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _send(self, msg: dict):
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    def _notify(self, method: str, params: dict = None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _rpc(self, method: str, params: dict) -> dict:
        msg_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        line = self._proc.stdout.readline()
        if not line.strip():
            err = self._proc.stderr.read()
            raise McpUnavailable(f"empty response from MCP server; stderr: {err[-500:]}")
        resp = json.loads(line)
        if "error" in resp:
            raise McpUnavailable(f"MCP error calling {method}: {resp['error']}")
        return resp.get("result", {})

    def list_tools(self) -> list[dict]:
        return self._rpc("tools/list", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Calls a tool and parses its JSON text content. Raises McpUnavailable on any
        transport/protocol failure; raises ValueError if the tool itself reports a
        validation error (e.g. a missing required argument) — the caller should not
        silently swallow either."""
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        text = content[0].get("text", "") if content else ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ValueError(f"tool {name} did not return JSON: {text[:300]}")
