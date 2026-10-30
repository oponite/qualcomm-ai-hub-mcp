import json
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anyio
import h5py
import numpy as np
import pytest
import qai_hub as hub
from mcp import Client
from qai_hub.public_rest_api import APIException

from qualcomm_ai_hub_mcp.config import (
    client,
    path,
    safe_name,
    validate_hdf5,
    validate_model_archive,
)
from qualcomm_ai_hub_mcp.contracts import OPERATIONS
from qualcomm_ai_hub_mcp.downloads import Downloads
from qualcomm_ai_hub_mcp.errors import ConnectorError, error_result
from qualcomm_ai_hub_mcp.server import create_server


def test_auth_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("QAI_HUB_API_TOKEN", raising=False)
    monkeypatch.setenv("QAIHUB_CLIENT_INI", str(tmp_path / "missing.ini"))
    with pytest.raises(ConnectorError) as error:
        client()
    assert error.value.code == "AUTHENTICATION"
    monkeypatch.setenv("QAI_HUB_API_TOKEN", "secret-test-token")
    sdk = client()
    assert sdk.config.api_token == "secret-test-token"
    assert sdk.verbose is False
    with pytest.raises(ConnectorError) as error:
        client("profile")
    assert error.value.code == "CONFIGURATION"


def test_ini_and_profiles(monkeypatch, tmp_path):
    from qai_hub import api_utils

    monkeypatch.delenv("QAI_HUB_API_TOKEN", raising=False)
    content = "[api]\napi_url=https://example.invalid\nweb_url=https://example.invalid\napi_token=test-token\n"
    config = tmp_path / "custom.conf"
    config.write_text(content)
    monkeypatch.setenv("QAIHUB_CLIENT_INI", str(config))
    assert client().config.api_token == "test-token"
    monkeypatch.setattr(api_utils, "_CONFIG_DIR", str(tmp_path))
    (tmp_path / "named.ini").write_text(content)
    assert client("named").config.api_token == "test-token"
    with pytest.raises(ConnectorError):
        path(str(config), tmp_path)


@pytest.mark.parametrize(
    "op", [o for o in OPERATIONS if o.sensitive], ids=lambda o: o.name
)
@pytest.mark.parametrize("confirmation", [False, None, "true", 1])
def test_sensitive_calls_never_touch_sdk_without_boolean_authorization(
    op, confirmation, tmp_path
):
    from test_contracts import sample

    sdk = MagicMock(spec=hub.Client)
    arguments = {p.name: sample(op, p.name, tmp_path) for p in op.parameters}
    if op.kind:
        arguments[op.kind + "_id"] = "object"
    arguments["confirm"] = confirmation

    async def check():
        async with Client(create_server(tmp_path, sdk=sdk)) as connection:
            result = await connection.call_tool(op.name, arguments)
            assert result.is_error

    anyio.run(check)
    assert sdk.mock_calls == []


def test_missing_credentials_are_a_structured_tool_error(monkeypatch, tmp_path):
    monkeypatch.delenv("QAI_HUB_API_TOKEN", raising=False)
    monkeypatch.setenv("QAIHUB_CLIENT_INI", str(tmp_path / "missing.ini"))

    async def check():
        async with Client(create_server(tmp_path)) as connection:
            assert (await connection.list_tools()).tools
            result = await connection.call_tool("get_devices", {})
            assert result.is_error
            assert result.structured_content["error"]["code"] == "AUTHENTICATION"

    anyio.run(check)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AUTHENTICATION"),
        (403, "PERMISSION_DENIED"),
        (404, "NOT_FOUND"),
        (429, "RATE_LIMITED"),
        (503, "SERVICE_UNAVAILABLE"),
        (400, "INVALID_INPUT"),
    ],
)
def test_sdk_suppressed_causes_are_classified_without_exposing_secrets(status, code):
    try:
        try:
            raise APIException(
                "secret-test-token and https://signed.invalid/?secret=token",
                status_code=status,
            )
        except APIException:
            raise hub.UserError("secret-test-token") from None
    except hub.UserError as exc:
        result = error_result(exc)
    assert result.structured_content["error"]["code"] == code
    assert "secret-test-token" not in result.model_dump_json()
    assert "signed.invalid" not in result.model_dump_json()


def test_submission_timeout_is_not_automatically_retryable():
    result = error_result(TimeoutError("secret"), sensitive=True)
    assert result.is_error
    assert result.structured_content["error"]["retryable"] is False
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "name",
    [
        "../x",
        "/absolute",
        "C:\\escape",
        "..\\escape",
        "NUL",
        "CON.txt",
        "x:y",
        "x/../y",
        "x\n",
        "x.",
        "x ",
    ],
)
def test_unsafe_remote_names(name):
    with pytest.raises(ConnectorError):
        safe_name(name)


def test_paths_and_directory_symlinks(tmp_path):
    for name in [".env", ".env.production", ".ssh/id_rsa"]:
        with pytest.raises(ConnectorError):
            path(name, tmp_path, output=True)
    with pytest.raises(ConnectorError):
        path("../outside", tmp_path, output=True)
    directory = tmp_path / "model.onnx"
    directory.mkdir()
    (directory / "weights").write_bytes(b"x")
    assert path("model.onnx", tmp_path, directory=True) == str(directory)
    try:
        (directory / "escape").symlink_to(tmp_path.parent, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires host privileges")
    with pytest.raises(ConnectorError):
        path("model.onnx", tmp_path, directory=True)


def test_archive_paths(tmp_path):
    archive = tmp_path / "model.zip"
    with zipfile.ZipFile(archive, "w") as data:
        data.writestr("model.onnx/../../.env", b"secret")
    with pytest.raises(ConnectorError):
        validate_model_archive(str(archive))


def test_hdf5_external_files_are_rejected(tmp_path):
    source = tmp_path / "data.h5"
    with h5py.File(source, "w") as data:
        data["data"] = h5py.ExternalLink("/outside/secret.h5", "/data")
    with pytest.raises(ConnectorError):
        validate_hdf5(source)


@pytest.fixture
def downloads(monkeypatch, tmp_path):
    from qualcomm_ai_hub_mcp import downloads as module

    sdk = MagicMock(spec=hub.Client)
    sdk.config = hub.ClientConfig("test-token")
    instance = Downloads(tmp_path, sdk)

    def transfer(url, filename, destination, verbose):
        Path(destination).write_bytes(b"artifact")
        return str(destination)

    monkeypatch.setattr(module.api_utils, "download_file", transfer)
    monkeypatch.setattr(
        module.api,
        "get_model_download_url",
        lambda *a: SimpleNamespace(
            filename="model.onnx", url="https://example.invalid/model"
        ),
    )
    monkeypatch.setattr(
        module.api,
        "download_job_artifacts_info",
        lambda *a: (
            SimpleNamespace(
                artifacts=[
                    SimpleNamespace(
                        filename="device.log", url="https://example.invalid/log"
                    )
                ]
            )
            if a[2] == hub.JobArtifactType.DEVICE_LOG.value
            else SimpleNamespace(artifacts=[])
        ),
    )
    return instance


def operation(name):
    return next(op for op in OPERATIONS if op.name == name)


def test_model_download_and_suffix_overwrite(downloads, tmp_path):
    target = MagicMock(spec=hub.Model)
    target.model_id = "m"
    target.wait.return_value = True
    result = downloads.invoke(
        operation("model_download"),
        target,
        {"filename": str(tmp_path / "output"), "timeout": 2},
    )
    assert result == str(tmp_path / "output.onnx")
    assert Path(result).read_bytes() == b"artifact"
    with pytest.raises(FileExistsError):
        downloads.invoke(
            operation("model_download"), target, {"filename": str(tmp_path / "output")}
        )
    assert Path(result).read_bytes() == b"artifact"
    target.download.assert_not_called()


def test_remote_traversal_rejected_before_transfer(downloads, monkeypatch, tmp_path):
    from qualcomm_ai_hub_mcp import downloads as module

    transfer = MagicMock()
    monkeypatch.setattr(module.api_utils, "download_file", transfer)
    monkeypatch.setattr(
        module.api,
        "get_model_download_url",
        lambda *a: SimpleNamespace(
            filename="../escape.onnx", url="https://example.invalid/model"
        ),
    )
    target = MagicMock(spec=hub.Model)
    target.model_id = "m"
    with pytest.raises(ConnectorError):
        downloads.invoke(
            operation("model_download"), target, {"filename": str(tmp_path / "output")}
        )
    transfer.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_profile_filename_never_uses_remote_job_name(downloads, tmp_path):
    target = MagicMock(spec=hub.InferenceJob)
    target.name = "../../escape"
    target.download_profile.return_value = {"execution_summary": {"time": 5}}
    result = downloads.invoke(
        operation("inferencejob_download_profile"),
        target,
        {"filename": str(tmp_path / "profile")},
    )
    assert json.loads(Path(result).read_text()) == {"execution_summary": {"time": 5}}
    assert target.download_profile.call_args.args == ()


@pytest.mark.parametrize(
    "cls", [hub.CompileJob, hub.QuantizeJob, hub.LinkJob, hub.InferenceJob]
)
def test_result_bundles_use_only_guarded_transfers(downloads, cls, tmp_path):
    target = MagicMock(spec=cls)
    target.job_id, target.url = "j", "https://example.invalid/jobs/j"
    target.wait.return_value = hub.JobStatus(hub.JobStatus.State.SUCCESS)
    target.get_available_artifacts.return_value = [hub.JobArtifactType.DEVICE_LOG]
    if cls is hub.InferenceJob:
        target.get_output_dataset.return_value = None
        target.download_profile.return_value = {"execution_summary": {"time": 5}}
    else:
        model = MagicMock(spec=hub.Model)
        model.model_id = "m"
        target.get_target_model.return_value = model
    result = downloads.invoke(
        operation("job_download_results"),
        target,
        {"artifacts_dir": str(tmp_path / "results")},
    )
    assert result.status.success
    assert (tmp_path / "results/logs/device.log").read_bytes() == b"artifact"
    if cls is hub.InferenceJob:
        assert (tmp_path / "results/profile.json").is_file()
    else:
        assert (tmp_path / "results/model/model.onnx").is_file()
    target.download_results.assert_not_called()


def test_dataset_inline_and_file_roundtrip(downloads, tmp_path):
    dataset = hub.Dataset(
        downloads.client,
        "d",
        datetime.now(),
        None,
        "data",
        False,
        data={
            "z": [np.array([1, 2], dtype=np.int64)],
            "a": [np.array([3, 4], dtype=np.int64)],
        },
    )
    result = downloads.invoke(operation("dataset_download"), dataset, {})
    assert list(result) == ["z", "a"]
    output = downloads.invoke(
        operation("dataset_download"), dataset, {"filename": str(tmp_path / "output")}
    )
    assert output.endswith(".h5")
    validate_hdf5(output)
    with pytest.raises(FileExistsError):
        downloads.invoke(
            operation("dataset_download"),
            dataset,
            {"filename": str(tmp_path / "output")},
        )


def test_failed_transfer_does_not_publish(downloads, monkeypatch, tmp_path):
    from qualcomm_ai_hub_mcp import downloads as module

    def fail(*args):
        Path(args[2]).write_bytes(b"partial")
        raise TimeoutError("signed-secret-url")

    monkeypatch.setattr(module.api_utils, "download_file", fail)
    target = MagicMock(spec=hub.Model)
    target.model_id = "m"
    with pytest.raises(TimeoutError):
        downloads.invoke(
            operation("model_download"), target, {"filename": str(tmp_path / "out")}
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "cls,name",
    [
        (hub.CompileJob, "compilejob_download_target_model"),
        (hub.QuantizeJob, "quantizejob_download_target_model"),
        (hub.LinkJob, "linkjob_download_target_model"),
    ],
)
def test_target_model_downloads_have_file_equivalents(downloads, cls, name, tmp_path):
    target = MagicMock(spec=cls)
    model = MagicMock(spec=hub.Model)
    model.model_id = "model"
    model.wait.return_value = True
    target.get_target_model.return_value = model
    args = {"filename": str(tmp_path / "compiled")} if cls is hub.CompileJob else {}
    result = downloads.invoke(operation(name), target, args)
    assert Path(result).is_relative_to(tmp_path)
    assert Path(result).read_bytes() == b"artifact"
    if cls is not hub.CompileJob:
        assert (tmp_path / "artifacts").is_dir()
    target.download_target_model.assert_not_called()


def test_remote_hdf5_download_and_output_data(downloads, monkeypatch, tmp_path):
    from qai_hub.util.dataset_entries_converters import dataset_entries_to_h5

    from qualcomm_ai_hub_mcp import downloads as module

    monkeypatch.setattr(
        module.api,
        "download_dataset_info",
        lambda *a: SimpleNamespace(
            filename="data.h5", url="https://example.invalid/data"
        ),
    )

    def transfer(url, filename, destination, verbose):
        with h5py.File(destination, "w") as data:
            dataset_entries_to_h5({"x": [np.array([1, 2], dtype=np.int64)]}, data)
        return str(destination)

    monkeypatch.setattr(module.api_utils, "download_file", transfer)
    dataset = hub.Dataset(downloads.client, "d", datetime.now(), None, "remote", False)
    target = MagicMock(spec=hub.InferenceJob)
    target.get_output_dataset.return_value = dataset
    result = downloads.invoke(
        operation("inferencejob_download_output_data"), target, {}
    )
    np.testing.assert_array_equal(result["x"][0], [1, 2])
    result = downloads.invoke(
        operation("inferencejob_download_output_data"),
        target,
        {"filename": str(tmp_path / "outputs")},
    )
    assert result == str(tmp_path / "outputs.h5")
    validate_hdf5(result)


def test_duplicate_artifacts_rejected_before_any_transfer(
    downloads, monkeypatch, tmp_path
):
    from qualcomm_ai_hub_mcp import downloads as module

    item = SimpleNamespace(filename="same.log", url="https://example.invalid/log")
    monkeypatch.setattr(
        module.api,
        "download_job_artifacts_info",
        lambda *a: SimpleNamespace(artifacts=[item, item]),
    )
    transfer = MagicMock()
    monkeypatch.setattr(module.api_utils, "download_file", transfer)
    target = MagicMock(spec=hub.Job)
    target.job_id = "j"
    target.get_available_artifacts.return_value = [hub.JobArtifactType.DEVICE_LOG]
    with pytest.raises(ConnectorError):
        downloads.invoke(
            operation("job_download_artifacts_for_type"),
            target,
            {
                "output_dir": str(tmp_path / "logs"),
                "artifact_type": hub.JobArtifactType.DEVICE_LOG,
            },
        )
    transfer.assert_not_called()
    assert not (tmp_path / "logs").exists()


@pytest.mark.parametrize(
    "name",
    [
        ".env::$DATA",
        ".env ",
        ".ENV.",
        ".ssh./key",
        ".gnupg/key",
        ".kube/config",
        ".docker/config.json",
        ".git-credentials",
        ".pgpass",
    ],
)
def test_protected_name_variants(tmp_path, name):
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("secret")
    with pytest.raises(ConnectorError) as error:
        path(name, tmp_path)
    assert error.value.code == "UNSAFE_PATH"


def test_workspace_root_cannot_be_uploaded_as_a_model(tmp_path):
    (tmp_path / "private.txt").write_text("x")
    with pytest.raises(ConnectorError) as error:
        path(".", tmp_path, directory=True)
    assert error.value.code == "UNSAFE_PATH"
    (tmp_path / "model").mkdir()
    assert path("model", tmp_path, directory=True) == str(tmp_path.resolve() / "model")


def test_corrupt_inputs_report_invalid_input(tmp_path):
    archive = tmp_path / "model.zip"
    archive.write_bytes(b"not a zip")
    data = tmp_path / "data.h5"
    data.write_bytes(b"not hdf5")
    for check, target in ((validate_model_archive, archive), (validate_hdf5, data)):
        with pytest.raises(ConnectorError) as error:
            check(str(target))
        assert error.value.code == "INVALID_INPUT"
