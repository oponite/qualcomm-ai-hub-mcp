import json
from datetime import datetime

import numpy as np
import pytest
import qai_hub as hub
from qai_hub import public_api_pb2
from qai_hub.public_rest_api import TensorSpec

from qualcomm_ai_hub_mcp.serialization import encode, io_spec


def test_real_sdk_records_are_explicit_and_never_include_owner():
    client = hub.Client(config=hub.ClientConfig("never-expose-this-token"))
    date = datetime(2026, 1, 1)
    model = hub.Model(
        client,
        "m",
        date,
        hub.SourceModelType.ONNX,
        "model",
        {},
        None,
        False,
        None,
        {},
        {},
    )
    dataset = hub.Dataset(client, "d", date, None, "data", False)
    project = hub.Project(client, "p", "project", "description", date)
    for record in (
        model,
        dataset,
        project,
        hub.Device("Test Device"),
        hub.Framework("QNN"),
    ):
        result = json.dumps(encode(record), allow_nan=False)
        assert "never-expose-this-token" not in result
        assert "owner" not in result and "config" not in result
    assert encode(model)["model_id"] == "m"
    assert encode(dataset)["name"] == "data"
    assert encode(project)["project_name"] == "project"
    with pytest.raises(TypeError):
        encode(client)
    with pytest.raises(TypeError):
        encode(client.config)


def test_job_status_results_metadata_and_graph_specs():
    status = hub.JobStatus(hub.JobStatus.State.SUCCESS)
    assert encode(status)["success"] is True
    result = hub.InferenceJobResult(
        status=status, url=None, artifacts_dir="output", profile={"time": np.int64(3)}
    )
    assert encode(result)["profile"]["time"] == 3
    assert encode({hub.ModelMetadataKey.QNN_SDK_VERSION: "1"}) == {
        "QNN_SDK_VERSION": "1"
    }
    spec = io_spec(
        {None: [TensorSpec(name="x", shape=(1, 2), dtype="float32")], "null": []}
    )
    assert spec["graphs"][0]["name"] is None
    assert spec["graphs"][1]["name"] == "null"
    assert spec["graphs"][0]["tensors"][0]["shape"] == [1, 2]
    json.dumps(spec, allow_nan=False)


def test_real_protobuf_sharing_list_and_unknown_types():
    emails = public_api_pb2.SharedAccess(email=["a@example.invalid"]).email
    assert not isinstance(emails, list)
    assert encode(emails) == ["a@example.invalid"]
    for value in (b"raw", bytearray(b"raw"), object()):
        with pytest.raises(TypeError):
            encode(value)
