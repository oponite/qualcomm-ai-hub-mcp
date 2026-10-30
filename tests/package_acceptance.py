"""Build a wheel/sdist, install into a fresh venv, and exercise installed entry points."""

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def execute(arguments, **kwargs):
    result = subprocess.run(
        arguments, capture_output=True, text=True, check=False, **kwargs
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="qai-mcp-package-") as temporary:
        directory = Path(temporary)
        execute(
            [sys.executable, "-m", "build", "--outdir", str(ROOT / "dist")], cwd=ROOT
        )
        wheel = next((ROOT / "dist").glob("*.whl"))
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        binaries = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        command = binaries / (
            "qualcomm-ai-hub-mcp.exe" if os.name == "nt" else "qualcomm-ai-hub-mcp"
        )
        execute([str(python), "-m", "pip", "install", str(wheel)])
        execute([str(python), "-m", "pip", "check"])
        execute([str(command), "--help"])
        execute([str(python), "-m", "qualcomm_ai_hub_mcp", "--help"])
        acceptance = """
import anyio, sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from qualcomm_ai_hub_mcp.contracts import OPERATIONS
async def check():
    for command, args in [(sys.executable, ['-m','qualcomm_ai_hub_mcp']), (sys.argv[1], [])]:
        async with Client(StdioServerParameters(command=command, args=args)) as connection:
            tools = await connection.list_tools()
            assert {tool.name for tool in tools.tools} == {op.name for op in OPERATIONS}
            result = await connection.call_tool('create_project', {'name':'must-not-create'})
            assert result.is_error
            assert result.structured_content['error']['code'] == 'AUTHORIZATION_REQUIRED'
    print('Installed wheel: both entry points discover all tools and reject unauthorized changes')
anyio.run(check)
"""
        print(
            execute(
                [str(python), "-c", acceptance, str(command)], cwd=directory
            ).strip()
        )
        print(
            "Built:",
            wheel.name,
            "and source distribution; clean pip dependency check passed",
        )
