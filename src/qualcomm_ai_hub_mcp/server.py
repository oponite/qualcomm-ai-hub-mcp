"""MCP transport. Qualcomm SDK work stays off the event loop."""

import argparse
import inspect
from pathlib import Path

import anyio
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from . import __version__
from .adapter import Adapter
from .contracts import OPERATIONS, tool_signature
from .downloads import DOWNLOAD_METHODS
from .errors import ConnectorError, error_result


def create_server(workspace=None, profile=None, sdk=None):
    root = Path(workspace or Path.cwd()).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Workspace must be an existing directory")
    adapter = Adapter(root, profile, sdk)
    server = MCPServer(
        "Qualcomm AI Hub",
        version=__version__,
        instructions="Sensitive tools require confirm=true. Ask the user before authorizing uploads, submissions, or sharing changes. Local paths are restricted to the configured workspace.",
    )

    def register(op):
        async def invoke(**arguments):
            if op.sensitive and arguments.get("confirm") is not True:
                return error_result(
                    ConnectorError(
                        "AUTHORIZATION_REQUIRED",
                        "Explicit confirm=true is required before this operation.",
                    )
                )
            try:
                # Abandoning frees the worker slot, so cancelled waits cannot block polling.
                result = await anyio.to_thread.run_sync(
                    lambda: adapter.invoke(op, arguments),
                    abandon_on_cancel=True,
                )
                return {"result": result}
            except Exception as exc:  # noqa: BLE001 - tool boundary; classify() sanitizes
                return error_result(exc, sensitive=op.sensitive)

        invoke.__signature__ = tool_signature(op)
        invoke.__annotations__ = {
            p.name: p.annotation for p in invoke.__signature__.parameters.values()
        } | {"return": dict[str, object]}
        invoke.__name__ = op.name
        description = inspect.getdoc(op.sdk_method) or f"Read Qualcomm {op.method}."
        if op.method == "download_target_model":
            description += (
                "\nMCP returns a saved file path, never a Python model object."
            )
            if any(
                p.name == "filename" and p.default is not p.empty for p in op.parameters
            ):
                description += " If filename is omitted, the artifact is saved under workspace/artifacts/<unique-id>/."
        if any(
            p.name in ("model", "models", "data", "inputs", "calibration_data")
            for p in op.parameters
        ):
            description += "\nMCP uses explicit {id: ...} or {path: ...} references. Inline datasets use ordered features with dtype/shape/base64 tensor samples; see the input schema."
        if op.sensitive:
            description += "\nRequires explicit confirm=true before any remote change. The client must obtain human approval."
        server.add_tool(
            invoke,
            name=op.name,
            description=description,
            structured_output=True,
            annotations=ToolAnnotations(
                read_only_hint=not (
                    op.sensitive
                    or op.method in DOWNLOAD_METHODS
                    or op.method == "set_verbose"
                ),
                destructive_hint=op.method
                in ("disable_sharing", "modify_sharing", "set_name"),
                idempotent_hint=not (op.sensitive or op.method in DOWNLOAD_METHODS),
                open_world_hint=True,
            ),
        )

    for op in OPERATIONS:
        register(op)
    return server


def main():
    parser = argparse.ArgumentParser(description="Qualcomm AI Hub MCP server (stdio).")
    parser.add_argument(
        "--workspace",
        help="Allowed local data directory; defaults to the startup directory.",
    )
    parser.add_argument(
        "--profile", help="Official Qualcomm SDK configuration profile."
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    create_server(args.workspace, args.profile).run(transport="stdio")
