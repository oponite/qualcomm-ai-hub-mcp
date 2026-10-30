import threading

import anyio
import pytest
import qai_hub as hub
from mcp import Client

from qualcomm_ai_hub_mcp import __version__
from qualcomm_ai_hub_mcp.config import path
from qualcomm_ai_hub_mcp.contracts import REMOTE_ID
from qualcomm_ai_hub_mcp.errors import ConnectorError
from qualcomm_ai_hub_mcp.server import create_server, main


class SDK:
    def get_devices(self, **kwargs):
        return []

    def create_project(self, **kwargs):
        raise AssertionError("Must not reach SDK without confirmation")


def test_protocol():
    async def check():
        async with Client(create_server(sdk=SDK())) as client:
            tools = await client.list_tools()
            assert len(tools.tools) >= 50
            result = await client.call_tool("get_devices", {})
            assert result.structured_content == {"result": []}
            result = await client.call_tool("create_project", {"name": "test"})
            assert result.is_error

    anyio.run(check)


def test_path(tmp_path):
    with pytest.raises(ConnectorError):
        path("../escape", tmp_path)
    f = tmp_path / "file"
    f.write_text("x")
    with pytest.raises(FileExistsError):
        path(str(f), tmp_path, output=True)


def test_nullable_and_defaults():
    class QuantizeSDK(SDK):
        def get_model(self, model_id):
            return model_id

        def get_dataset(self, dataset_id):
            return dataset_id

        def submit_quantize_job(self, **kwargs):
            import qai_hub as hub

            assert kwargs["weights_dtype"] is hub.QuantizeDtype.INT8
            assert kwargs["activations_dtype"] is hub.QuantizeDtype.INT8
            assert kwargs["name"] is None

    async def check():
        async with Client(create_server(sdk=QuantizeSDK())) as client:
            result = await client.call_tool(
                "submit_quantize_job",
                {
                    "model": {"id": "m"},
                    "calibration_data": {"id": "d"},
                    "name": None,
                    "confirm": True,
                },
            )
            assert not result.is_error
            result = await client.call_tool(
                "create_project", {"name": "x", "confirm": "true"}
            )
            assert result.is_error

    anyio.run(check)


@pytest.mark.parametrize(
    "bad", ["//evil.example/x", "../../users", "a/b", "a?b", "a#b", "a b", "a\n"]
)
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_job", lambda bad: {"job_id": bad}),
        ("get_model", lambda bad: {"model_id": bad}),
        ("get_dataset", lambda bad: {"dataset_id": bad}),
        ("get_project", lambda bad: {"project_id": bad}),
        ("job_get_status", lambda bad: {"job_id": bad}),
        ("model_download", lambda bad: {"model_id": bad, "filename": "out"}),
        (
            "submit_profile_job",
            lambda bad: {
                "model": {"id": bad},
                "device": {"name": "d"},
                "confirm": True,
            },
        ),
        (
            "submit_inference_job",
            lambda bad: {
                "model": {"id": "m"},
                "device": {"name": "d"},
                "project": bad,
                "confirm": True,
            },
        ),
    ],
)
def test_url_unsafe_ids_never_reach_sdk(tool, arguments, bad):
    class Refuse:
        def __getattr__(self, name):
            raise AssertionError(f"SDK reached: {name}")

    async def check():
        async with Client(create_server(sdk=Refuse())) as client:
            result = await client.call_tool(tool, arguments(bad))
            assert result.is_error
            assert "SDK reached" not in str(result.content)

    anyio.run(check)


def test_every_url_bound_input_has_the_id_pattern():
    async def check():
        async with Client(create_server(sdk=SDK())) as client:
            tools = (await client.list_tools()).tools
        constrained = 0
        for tool in tools:
            for name, schema in tool.input_schema["properties"].items():
                if name.endswith("_id") or name == "project":
                    options = schema.get("anyOf", [schema])
                    strings = [o for o in options if o.get("type") == "string"]
                    assert strings, (tool.name, name)
                    assert all(o.get("pattern") == REMOTE_ID for o in strings)
                    constrained += 1
        assert constrained >= 40

    anyio.run(check)


def test_tool_annotations_match_behavior():
    async def check():
        async with Client(create_server(sdk=SDK())) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
        for name in ("model_download", "job_download_results", "dataset_download"):
            assert not tools[name].annotations.read_only_hint
            assert not tools[name].annotations.idempotent_hint
        assert tools["get_devices"].annotations.read_only_hint
        assert tools["get_devices"].annotations.idempotent_hint
        assert not tools["submit_compile_job"].annotations.idempotent_hint
        assert tools["job_set_name"].annotations.destructive_hint

    anyio.run(check)


def test_target_model_filename_description_matches_schema():
    async def check():
        async with Client(create_server(sdk=SDK())) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
        compiled = tools["compilejob_download_target_model"]
        assert "filename" in compiled.input_schema["required"]
        assert "If filename is omitted" not in compiled.description
        assert (
            "If filename is omitted"
            in tools["linkjob_download_target_model"].description
        )

    anyio.run(check)


def test_cancelled_waits_do_not_block_polling():
    release = threading.Event()

    class Job(hub.CompileJob):
        def __init__(self):
            pass

        def wait(self, timeout=None):
            release.wait(30)
            return hub.JobStatus(hub.JobStatus.State.SUCCESS)

        def get_status(self):
            return hub.JobStatus(hub.JobStatus.State.SUCCESS)

    class WaitSDK(SDK):
        def get_job(self, job_id):
            return Job()

    async def waiter(client):
        with anyio.move_on_after(0.2):
            await client.call_tool("job_wait", {"job_id": "j"})

    async def check():
        try:
            async with Client(create_server(sdk=WaitSDK())) as client:
                async with anyio.create_task_group() as group:
                    for _ in range(45):
                        group.start_soon(waiter, client)
                with anyio.fail_after(5):
                    result = await client.call_tool("job_get_status", {"job_id": "j"})
                assert not result.is_error
        finally:
            release.set()

    anyio.run(check)


def test_version_flag(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["qualcomm-ai-hub-mcp", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_stdio_discovery(tmp_path):
    import sys

    from mcp.client.stdio import StdioServerParameters

    async def check():
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "qualcomm_ai_hub_mcp", "--workspace", str(tmp_path)],
            )
        ) as client:
            tools = await client.list_tools()
            assert any(t.name == "submit_compile_job" for t in tools.tools)
            result = await client.call_tool("create_project", {"name": "x"})
            assert result.is_error

    anyio.run(check)
