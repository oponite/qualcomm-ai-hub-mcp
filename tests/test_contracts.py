import inspect
import json
from unittest.mock import MagicMock

import anyio
import numpy as np
import pytest
import qai_hub as hub
from mcp import Client
from pydantic import ValidationError

from qualcomm_ai_hub_mcp.contracts import (
    CLIENT_METHODS,
    OBJECT_METHODS,
    OPERATIONS,
    InlineDataset,
    Tensor,
)
from qualcomm_ai_hub_mcp.serialization import encode
from qualcomm_ai_hub_mcp.server import create_server


def run(call):
    return anyio.run(call)


def sample(op, name, tmp_path):
    if name in ("model", "models"):
        if op.method == "upload_model":
            (tmp_path / "model.onnx").write_bytes(b"model")
            return {"path": "model.onnx"}
        return {"id": "model-id"}
    if name in ("data", "inputs", "calibration_data"):
        if op.method == "upload_dataset":
            return {
                "features": [
                    {
                        "name": "x",
                        "samples": [{"dtype": "int8", "shape": [1], "base64": "AQ=="}],
                    }
                ]
            }
        return {"id": "dataset-id"}
    return {
        "device": {"name": "Test Device"},
        "name": "test",
        "description": "description",
        "attributes": ["os:android"],
        "os": "",
        "model_id": "m",
        "dataset_id": "d",
        "job_id": "j",
        "project_id": "p",
        "project": "p",
        "options": "--target_runtime onnx",
        "compile_options": "--target_runtime onnx",
        "profile_options": "",
        "link_options": "",
        "input_specs": {"x": [[1, 2], "float32"]},
        "graph_names": ["graph"],
        "single_compile": True,
        "retry": False,
        "profile": True,
        "embed_in_onnx": False,
        "weights_dtype": "INT8",
        "activations_dtype": "INT16",
        "verbose": False,
        "offset": 1,
        "limit": 2,
        "creator": "creator",
        "state": ["SUCCESS"],
        "type": "INFERENCE",
        "job_type": "INFERENCE",
        "query": "test",
        "job_name": "renamed",
        "filename": "output.bin",
        "artifacts_dir": "results",
        "output_dir": "logs",
        "timeout": 3,
        "artifact_type": "DEVICE_LOG",
        "add_emails": ["user@example.com"],
        "delete_emails": [],
    }[name]


@pytest.mark.parametrize("op", OPERATIONS, ids=lambda op: op.name)
def test_each_operation_forwards_typed_parameters(op, tmp_path, monkeypatch):
    from qualcomm_ai_hub_mcp.downloads import DOWNLOAD_METHODS, Downloads

    download = MagicMock(return_value=None)
    monkeypatch.setattr(Downloads, "invoke", download)
    sdk = MagicMock(spec=hub.Client)
    model, dataset = MagicMock(spec=hub.Model), MagicMock(spec=hub.Dataset)
    sdk.get_model.return_value, sdk.get_dataset.return_value = model, dataset
    target = sdk
    if op.kind:
        target = MagicMock(spec=op.cls)
        getattr(sdk, f"get_{op.kind}").return_value = target
    arguments = {p.name: sample(op, p.name, tmp_path) for p in op.parameters}
    if op.kind:
        arguments[op.kind + "_id"] = "object-id"
    if op.sensitive:
        arguments["confirm"] = True
    if op.property_read:
        setattr(target, op.method, {})
    else:
        getattr(target, op.method).return_value = None

    async def check():
        async with Client(create_server(tmp_path, sdk=sdk)) as client:
            result = await client.call_tool(op.name, arguments)
            assert not result.is_error, result
            json.dumps(result.structured_content, allow_nan=False)

    run(check)
    if op.kind and op.method in DOWNLOAD_METHODS:
        download.assert_called_once()
        assert download.call_args.args[0] == op
        assert download.call_args.args[1] is target
        assert set(download.call_args.args[2]) == {p.name for p in op.parameters}
    elif not op.property_read:
        called = getattr(target, op.method)
        called.assert_called_once()
        kwargs = called.call_args.kwargs
        assert set(kwargs) == {p.name for p in op.parameters}
        if "weights_dtype" in kwargs:
            assert kwargs["weights_dtype"] is hub.QuantizeDtype.INT8
        if "state" in kwargs:
            assert kwargs["state"] == [hub.JobStatus.State.SUCCESS]
        if "device" in kwargs:
            assert kwargs["device"].name == "Test Device"
        if "input_specs" in kwargs:
            assert kwargs["input_specs"] == {"x": ((1, 2), "float32")}
        if "data" in kwargs:
            assert kwargs["data"]["x"][0].dtype == np.int8


def test_registry_matches_sdk_surface():
    assert set(CLIENT_METHODS) == set(hub.hub.__all__) - {"set_session_token"}
    assert len({op.name for op in OPERATIONS}) == len(OPERATIONS)
    for prefix, (cls, expected) in OBJECT_METHODS.items():
        actual = {
            name
            for name, method in inspect.getmembers(cls, inspect.isfunction)
            if not name.startswith("_")
        }
        inherited = (
            set()
            if prefix in ("model", "dataset", "job")
            else set(OBJECT_METHODS["job"][1])
        )
        assert actual - inherited == set(expected)


def test_all_schemas_and_defaults(tmp_path):
    async def check():
        async with Client(create_server(tmp_path)) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert set(tools) == {op.name for op in OPERATIONS}
            for op in OPERATIONS:
                tool = tools[op.name]
                assert tool.description and tool.output_schema
                props = tool.input_schema["properties"]
                for p in op.parameters:
                    assert (
                        props[p.name].get("type")
                        or props[p.name].get("anyOf")
                        or props[p.name].get("$ref")
                    )
                    if p.default is not inspect.Parameter.empty:
                        expected = (
                            p.default.name if hasattr(p.default, "name") else p.default
                        )
                        assert props[p.name].get("default") == expected

    run(check)


def test_tensor_roundtrip_and_feature_order():
    array = np.array([np.nan, np.inf, -np.inf, 1.5], dtype=">f4")
    tensor = Tensor(**encode(array))
    np.testing.assert_array_equal(tensor.array(), array)
    huge = np.array([2**63 + 1], dtype=np.uint64)
    np.testing.assert_array_equal(Tensor(**encode(huge)).array(), huge)
    features = InlineDataset(
        features=[{"name": n, "samples": [encode(huge)]} for n in ["z", "a"]]
    )
    assert list(features.entries()) == ["z", "a"]
    assert json.loads(json.dumps(encode(array), allow_nan=False))["shape"] == [4]


@pytest.mark.parametrize(
    "value",
    [
        {"dtype": "object", "shape": [1], "base64": "AQ=="},
        {"dtype": "int8", "shape": [-1], "base64": ""},
        {"dtype": "float32", "shape": [1], "base64": "AQ=="},
        {"dtype": "int8", "shape": [1], "base64": "invalid!"},
    ],
)
def test_invalid_tensors(value):
    with pytest.raises(ValidationError):
        Tensor(**value)


def test_coverage_document_matches_registry():
    from pathlib import Path

    document = (
        Path(__file__).resolve().parents[1] / "docs/API_COVERAGE.md"
    ).read_text()
    documented = {
        line.split("`")[1] for line in document.splitlines() if line.startswith("| `")
    }
    assert documented == {op.name for op in OPERATIONS}
