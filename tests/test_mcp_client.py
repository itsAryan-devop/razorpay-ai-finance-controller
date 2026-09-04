"""Unit tests for the MCP stdio client — subprocess is mocked so these run without the
real razorpay-mcp-server binary or network access (CI-safe, keyless). Verifies the
JSON-RPC handshake, tool listing/calling, and that failures surface loudly rather than
silently returning empty/wrong data."""
import json

import pytest

import mcp_client


class _FakeStdin:
    def __init__(self):
        self.written = []

    def write(self, s):
        self.written.append(s)

    def flush(self):
        pass


class _FakeStdout:
    """Yields canned JSON-RPC response lines in order."""
    def __init__(self, responses):
        self._lines = [json.dumps(r) + "\n" for r in responses]

    def readline(self):
        return self._lines.pop(0) if self._lines else ""


class _FakeProc:
    def __init__(self, responses, stderr_text=""):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(responses)
        self.stderr = type("E", (), {"read": lambda self: stderr_text})()

    def terminate(self):
        pass

    def wait(self, timeout=None):
        pass


def _patch_popen(monkeypatch, tmp_path, responses, stderr_text=""):
    exe = tmp_path / "razorpay-mcp-server.exe"
    exe.write_text("fake")                      # only existence is checked, not content
    monkeypatch.setattr(mcp_client.subprocess, "Popen",
                        lambda *a, **kw: _FakeProc(responses, stderr_text))
    return str(exe)


def test_missing_binary_raises_mcp_unavailable(tmp_path):
    client = mcp_client.RazorpayMcpClient("k", "s", exe_path=str(tmp_path / "nope.exe"))
    with pytest.raises(mcp_client.McpUnavailable):
        with client:
            pass


def test_handshake_and_list_tools(tmp_path, monkeypatch):
    exe = _patch_popen(monkeypatch, tmp_path, responses=[
        {"jsonrpc": "2.0", "id": 1, "result": {}},                       # initialize
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": [
            {"name": "fetch_all_payments"}, {"name": "fetch_settlement_recon_details"}]}},
    ])
    with mcp_client.RazorpayMcpClient("k", "s", exe_path=exe) as client:
        tools = client.list_tools()
    names = [t["name"] for t in tools]
    assert "fetch_settlement_recon_details" in names


def test_call_tool_parses_json_content(tmp_path, monkeypatch):
    payload = {"count": 1, "items": [{"id": "pay_abc", "amount": 100}]}
    exe = _patch_popen(monkeypatch, tmp_path, responses=[
        {"jsonrpc": "2.0", "id": 1, "result": {}},                       # initialize
        {"jsonrpc": "2.0", "id": 2,
         "result": {"content": [{"type": "text", "text": json.dumps(payload)}]}},
    ])
    with mcp_client.RazorpayMcpClient("k", "s", exe_path=exe) as client:
        result = client.call_tool("fetch_all_payments", {"count": 1})
    assert result == payload


def test_mcp_error_response_raises_loudly(tmp_path, monkeypatch):
    exe = _patch_popen(monkeypatch, tmp_path, responses=[
        {"jsonrpc": "2.0", "id": 1, "result": {}},                       # initialize
        {"jsonrpc": "2.0", "id": 2, "error": {"code": -1, "message": "boom"}},
    ])
    with pytest.raises(mcp_client.McpUnavailable):
        with mcp_client.RazorpayMcpClient("k", "s", exe_path=exe) as client:
            client.call_tool("fetch_all_payments", {})


def test_empty_stdout_raises_loudly_with_stderr_context(tmp_path, monkeypatch):
    exe = _patch_popen(monkeypatch, tmp_path,
                       responses=[{"jsonrpc": "2.0", "id": 1, "result": {}}],
                       stderr_text="auth failed: invalid key")
    with mcp_client.RazorpayMcpClient("k", "s", exe_path=exe) as client:
        with pytest.raises(mcp_client.McpUnavailable, match="auth failed"):
            client.call_tool("fetch_all_payments", {})
