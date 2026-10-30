import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import anyio
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from qualcomm_ai_hub_mcp.contracts import OPERATIONS

FIXTURE = str(Path(__file__).with_name("stdio_fixture.py"))


def parameters(tmp_path):
    return StdioServerParameters(
        command=sys.executable,
        args=[FIXTURE],
        env={"QAI_MCP_TEST_WORKSPACE": str(tmp_path)},
    )


def test_official_client_subprocess_calls_noise_and_errors(tmp_path):
    async def check():
        async with Client(parameters(tmp_path)) as client:
            assert client.protocol_version == "2026-07-28"
            tools = await client.list_tools()
            assert {t.name for t in tools.tools} == {op.name for op in OPERATIONS}
            result = await client.call_tool("get_devices", {})
            assert (
                result.structured_content["result"][0]["name"] == "Offline Test Device"
            )
            assert not result.is_error
            result = await client.call_tool("get_devices", {"name": "error"})
            assert result.is_error
            assert result.structured_content["error"]["code"] == "INVALID_INPUT"
            assert "secret-test-token" not in result.model_dump_json()
            result = await client.call_tool(
                "submit_inference_job",
                {"model": {"id": "m"}, "device": {"name": "test"}, "confirm": True},
            )
            assert result.structured_content["result"]["job_id"] == "j-fixture"
            result = await client.call_tool(
                "job_wait", {"job_id": "j-fixture", "timeout": 1}
            )
            assert result.is_error
            assert result.structured_content["error"]["code"] == "TIMEOUT"

    anyio.run(check)


def test_status_polling_while_other_call_waits(tmp_path):
    async def check():
        async with Client(parameters(tmp_path)) as client:
            finished = False
            results = []

            async def wait():
                nonlocal finished
                response = await client.call_tool("job_wait", {"job_id": "j-fixture"})
                results.append(response)
                finished = True

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(wait)
                await anyio.sleep(0.05)
                response = await client.call_tool(
                    "job_get_status", {"job_id": "j-fixture"}
                )
                assert not finished
                assert response.structured_content["result"]["running"]
            assert results[0].structured_content["result"]["success"]

    anyio.run(check)


def test_legacy_handshake_and_every_stdout_line_is_protocol(tmp_path):
    env = dict(os.environ, QAI_MCP_TEST_WORKSPACE=str(tmp_path))
    process = subprocess.Popen(
        [sys.executable, FIXTURE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    lines = queue.Queue()

    def read():
        for line in process.stdout:
            lines.put(line)

    thread = threading.Thread(target=read, daemon=True)
    thread.start()

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def receive(identifier):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            message = json.loads(lines.get(timeout=max(0.1, end - time.monotonic())))
            assert message["jsonrpc"] == "2.0"
            if message.get("id") == identifier:
                return message
        raise AssertionError("No MCP response")

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "acceptance", "version": "1"},
                },
            }
        )
        assert receive(1)["result"]["protocolVersion"] == "2025-11-25"
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert len(receive(2)["result"]["tools"]) == len(OPERATIONS)
        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_devices", "arguments": {}},
            }
        )
        result = receive(3)["result"]
        assert result["structuredContent"]["result"][0]["name"] == "Offline Test Device"
        send(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "create_project", "arguments": {"name": "x"}},
            }
        )
        assert receive(4)["result"]["isError"]
        process.stdin.close()
        assert process.wait(timeout=10) == 0
        stderr = process.stderr.read()
        assert "SDK progress" in stderr and "SDK native stdout noise" in stderr
        thread.join(timeout=2)
        while not lines.empty():
            assert json.loads(lines.get_nowait())["jsonrpc"] == "2.0"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
        if not process.stdin.closed:
            process.stdin.close()
