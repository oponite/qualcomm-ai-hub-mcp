"""Conversion between typed MCP arguments and the official SDK."""

import threading

import qai_hub as hub

from .config import (
    client,
    credential_paths,
    path,
    validate_hdf5,
    validate_model_archive,
)
from .contracts import DeviceSpec, FileReference, InlineDataset, Reference
from .downloads import DOWNLOAD_METHODS, Downloads
from .errors import ConnectorError
from .serialization import dataset_entries, encode, io_spec


class Adapter:
    def __init__(self, root, profile=None, sdk=None):
        self.root, self.profile, self._client = root, profile, sdk
        self._lock = threading.Lock()
        self.forbidden = credential_paths(profile)

    @property
    def client(self):
        with self._lock:
            if self._client is None:
                self._client = client(self.profile)
            return self._client

    def convert(self, key, value):
        if value is None:
            return None
        if isinstance(value, Reference):
            return getattr(
                self.client,
                "get_model" if key in ("model", "models") else "get_dataset",
            )(value.id)
        if isinstance(value, FileReference):
            filename = path(
                value.path,
                self.root,
                forbidden=self.forbidden,
                directory=key in ("model", "models"),
            )
            if key in ("model", "models"):
                validate_model_archive(filename)
            else:
                validate_hdf5(filename)
            return filename
        if isinstance(value, InlineDataset):
            return value.entries()
        if isinstance(value, DeviceSpec):
            return hub.Device(**value.model_dump())
        if isinstance(value, list) and key in ("device", "models"):
            return [self.convert(key, v) for v in value]
        enum = {
            "weights_dtype": hub.QuantizeDtype,
            "activations_dtype": hub.QuantizeDtype,
            "type": hub.JobType,
            "job_type": hub.JobType,
            "artifact_type": hub.JobArtifactType,
            "state": hub.JobStatus.State,
        }.get(key)
        if enum:
            return [enum[v] for v in value] if isinstance(value, list) else enum[value]
        if key in ("filename", "output_dir", "artifacts_dir"):
            return path(value, self.root, output=True, forbidden=self.forbidden)
        return value

    def invoke(self, op, arguments):
        arguments = dict(arguments)
        arguments.pop("confirm", None)
        target = self.client
        if op.kind:
            target = getattr(target, f"get_{op.kind}")(arguments.pop(f"{op.kind}_id"))
            if not isinstance(target, op.cls):
                raise ConnectorError(
                    "UNSUPPORTED_OPERATION",
                    "This operation does not support the supplied job type.",
                )
        args = {k: self.convert(k, v) for k, v in arguments.items()}
        if op.method in DOWNLOAD_METHODS and op.kind:
            value = Downloads(self.root, self.client, self.forbidden).invoke(
                op, target, args
            )
        else:
            value = (
                getattr(target, op.method)
                if op.property_read
                else getattr(target, op.method)(**args)
            )
        if op.property_read and op.method in ("input_spec", "output_spec"):
            return io_spec(value)
        if (
            op.method in ("download", "download_output_data")
            and isinstance(value, dict)
            and op.kind in ("dataset", "job")
        ):
            return dataset_entries(value)
        return encode(value)
