"""Guard SDK transfers before writes, using its signed-URL APIs and transfer helper.

No archive extraction or Python model deserialization is performed here.
"""

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import h5py
import qai_hub as hub
from qai_hub import api_utils, s3_transfer
from qai_hub import public_rest_api as api
from qai_hub.util.dataset_entries_converters import h5_to_dataset_entries

from .config import path, safe_name, validate_hdf5
from .contracts import MAX_INLINE_BYTES
from .errors import ConnectorError
from .serialization import encode

DOWNLOAD_METHODS = {
    "download",
    "download_target_model",
    "download_output_data",
    "download_profile",
    "download_results",
    "download_artifacts_for_type",
    "download_job_logs",
}


class Downloads:
    def __init__(self, root, client, forbidden=()):
        self.root, self.client, self.forbidden = root, client, forbidden

    def destination(self, value):
        return Path(path(value, self.root, output=True, forbidden=self.forbidden))

    def transfer(self, info, filename, destination):
        safe_name(filename)
        if hasattr(info, "credentials") and info.HasField("credentials"):
            result = s3_transfer.download_file(
                info.credentials, filename, str(destination), False
            )
        else:
            url = urlparse(info.url)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
            ):
                raise ConnectorError(
                    "UNSAFE_URL",
                    "Artifact download requires an HTTPS URL without embedded credentials.",
                )
            result = api_utils.download_file(
                info.url, filename, str(destination), False
            )
        if Path(result).resolve() != destination.resolve() or not destination.is_file():
            raise ConnectorError(
                "UNSAFE_PATH", "SDK transfer returned an unexpected output path."
            )
        return destination

    def publish(self, source, destination):
        self.destination(str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents overwrites, including SDK-added extensions.
        created = False
        try:
            with destination.open("xb") as output:
                created = True
                with source.open("rb") as data:
                    shutil.copyfileobj(data, output)
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
        return str(destination)

    def file(self, info, requested, stage):
        name = safe_name(info.filename)
        suffix = "".join(Path(name).suffixes)
        destination = self.destination(requested)
        if suffix and not str(destination).endswith(suffix):
            destination = self.destination(str(destination) + suffix)
        source = stage / name
        self.transfer(info, name, source)
        return self.publish(source, destination)

    def model(self, model, filename, stage, timeout=None):
        if not model.wait(timeout):
            return None
        info = api.get_model_download_url(self.client.config, model.model_id)
        if filename is None:
            filename = str(
                self.root / "artifacts" / uuid.uuid4().hex / safe_name(info.filename)
            )
        return self.file(info, filename, stage)

    def dataset_source(self, dataset, stage, max_bytes=None):
        if dataset.is_expired():
            raise ConnectorError("EXPIRED", "The Qualcomm dataset has expired.")
        if dataset._data is not None:
            source = Path(dataset.download(str(stage / "dataset.h5")))
        else:
            info = api.download_dataset_info(self.client.config, dataset.dataset_id)
            name = safe_name(info.filename)
            source = self.transfer(info, name, stage / name)
        validate_hdf5(source, max_bytes)
        return source

    def dataset(self, dataset, filename, stage):
        if filename is None and dataset._data is not None:
            value = dataset._data
            if (
                sum(t.nbytes for tensors in value.values() for t in tensors)
                > MAX_INLINE_BYTES
            ):
                raise ConnectorError(
                    "RESULT_TOO_LARGE",
                    "Dataset exceeds the inline limit; download it to a file.",
                )
            return value
        source = self.dataset_source(
            dataset, stage, MAX_INLINE_BYTES if filename is None else None
        )
        if filename is not None:
            suffix = "".join(source.suffixes)
            destination = str(filename)
            if suffix and not destination.endswith(suffix):
                destination += suffix
            return self.publish(source, self.destination(destination))
        with h5py.File(source, "r") as data:
            return h5_to_dataset_entries(data)

    def artifacts(self, job, artifact_types, stage):
        available = job.get_available_artifacts()
        infos = []
        for kind in artifact_types:
            if kind in available:
                infos.extend(
                    api.download_job_artifacts_info(
                        self.client.config, job.job_id, kind.value
                    ).artifacts
                )
        names = [safe_name(info.filename) for info in infos]
        if len(set(names)) != len(names):
            raise ConnectorError(
                "UNSAFE_PATH",
                "Artifact filenames are duplicated; refusing to overwrite.",
            )
        return [
            self.transfer(info, name, stage / name)
            for info, name in zip(infos, names, strict=True)
        ]

    def publish_directory(self, stage, requested):
        destination = self.destination(requested)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(mode=0o700, exist_ok=False)
        try:
            for source in stage.iterdir():
                self.publish(source, destination / safe_name(source.name))
        except BaseException:
            shutil.rmtree(destination)
            raise
        return destination

    def invoke(self, op, target, args):
        # Private staging is bounded to a single call and is always removed.
        with tempfile.TemporaryDirectory(prefix="qai-mcp-") as temporary:
            stage = Path(temporary)
            method = op.method
            if method == "download":
                if op.kind == "model":
                    return self.model(
                        target, args["filename"], stage, args.get("timeout")
                    )
                return self.dataset(target, args.get("filename"), stage)
            if method == "download_target_model":
                model = target.get_target_model()
                return (
                    None
                    if model is None
                    else self.model(model, args.get("filename"), stage)
                )
            if method == "download_output_data":
                dataset = target.get_output_dataset()
                return (
                    None
                    if dataset is None
                    else self.dataset(dataset, args.get("filename"), stage)
                )
            if method == "download_profile":
                profile = target.download_profile()
                if not profile or args.get("filename") is None:
                    return profile
                destination = str(args["filename"])
                if not destination.endswith(".json"):
                    destination += ".json"
                source = stage / "profile.json"
                source.write_text(
                    json.dumps(encode(profile), allow_nan=False), encoding="utf-8"
                )
                return self.publish(source, self.destination(destination))
            log_types = [hub.JobArtifactType.DEVICE_LOG, hub.JobArtifactType.HUB_LOG]
            if method in ("download_artifacts_for_type", "download_job_logs"):
                types = (
                    [args["artifact_type"]]
                    if method == "download_artifacts_for_type"
                    else log_types
                )
                sources = self.artifacts(target, types, stage)
                if not sources:
                    return []
                destination = self.publish_directory(stage, args["output_dir"])
                return [str(destination / s.name) for s in sources]
            if method != "download_results":
                raise ValueError("Unsupported download operation")
            status = target.wait()
            logs_stage = stage / "logs"
            logs_stage.mkdir()
            self.artifacts(target, log_types, logs_stage)
            profile = None
            if status.success:
                # Subdirectories keep independently named SDK outputs from colliding with logs.
                if isinstance(target, hub.InferenceJob):
                    dataset = target.get_output_dataset()
                    if dataset is not None:
                        data_stage = stage / "dataset"
                        data_stage.mkdir()
                        self.dataset_source(dataset, data_stage)
                    profile = target.download_profile()
                    if profile:
                        (stage / "profile.json").write_text(
                            json.dumps(encode(profile), allow_nan=False),
                            encoding="utf-8",
                        )
                else:
                    model = target.get_target_model()
                    if model is not None:
                        model_stage = stage / "model"
                        model_stage.mkdir()
                        info = api.get_model_download_url(
                            self.client.config, model.model_id
                        )
                        name = safe_name(info.filename)
                        self.transfer(info, name, model_stage / name)
            # Result bundles can contain the fixed model/dataset subdirectories.
            destination = self.destination(args["artifacts_dir"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.mkdir(mode=0o700, exist_ok=False)
            try:
                for source in stage.iterdir():
                    if source.is_dir():
                        shutil.copytree(source, destination / source.name)
                    else:
                        self.publish(source, destination / source.name)
            except BaseException:
                shutil.rmtree(destination)
                raise
            result_type = {
                hub.CompileJob: hub.CompileJobResult,
                hub.QuantizeJob: hub.QuantizeJobResult,
                hub.LinkJob: hub.LinkJobResult,
                hub.InferenceJob: hub.InferenceJobResult,
            }
            for cls, result_cls in result_type.items():
                if isinstance(target, cls):
                    kwargs = {
                        "status": status,
                        "url": None if cls is hub.InferenceJob else target.url,
                        "artifacts_dir": str(destination),
                    }
                    if cls is hub.InferenceJob:
                        kwargs["profile"] = profile or None
                    return result_cls(**kwargs)
            raise ValueError("Unsupported job result type")
