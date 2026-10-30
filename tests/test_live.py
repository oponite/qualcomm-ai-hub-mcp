"""Optional read-only live check. Never uploads or submits billable jobs."""

import os

import anyio
import pytest
from mcp import Client

from qualcomm_ai_hub_mcp.server import create_server


@pytest.mark.skipif(
    os.environ.get("QAI_HUB_MCP_LIVE") != "1", reason="Opt-in live Qualcomm check"
)
def test_live_device_discovery():
    async def check():
        async with Client(create_server()) as client:
            result = await client.call_tool("get_devices", {})
            assert not result.is_error, result
            assert isinstance(result.structured_content["result"], list)

    anyio.run(check)
