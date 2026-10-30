"""Explicit Core API surface and its JSON equivalents (qai-hub 0.57.0)."""

import base64
import binascii
import inspect
import math
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Literal

import numpy as np
import qai_hub as hub
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

# Keep bulk tensors in HDF5 files; inline data must fit a normal tool exchange.
MAX_INLINE_BYTES = 16 * 1024 * 1024
DTYPES = (
    "float16",
    "float32",
    "float64",
    "bool",
    "int8",
    "int16",
    "int32",
    "int64",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
)


# The SDK joins IDs into request URLs unescaped: "//host" would send the API token there.
REMOTE_ID = r"^[A-Za-z0-9_-]+$"
RemoteId = Annotated[str, Field(min_length=1, pattern=REMOTE_ID)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(Input):
    id: RemoteId = Field(description="Existing Qualcomm model or dataset ID.")


class FileReference(Input):
    path: str = Field(
        min_length=1,
        description="Existing file or model directory inside the server workspace.",
    )


class DeviceSpec(Input):
    name: str = Field(default="", description="Device name or SDK name query.")
    os: str = Field(default="", description="Operating-system version query.")
    attributes: str | list[str] = Field(
        default_factory=list,
        description="SDK device attributes, e.g. chipset:qualcomm-snapdragon-8gen3.",
    )


class Tensor(Input):
    dtype: str = Field(
        description="NumPy numeric dtype, including explicit byte order when needed."
    )
    shape: list[Annotated[StrictInt, Field(ge=0)]]
    base64: str = Field(
        max_length=((MAX_INLINE_BYTES + 2) // 3) * 4,
        description="Base64 of C-order tensor bytes; no pickle or object arrays.",
    )

    @model_validator(mode="after")
    def valid_tensor(self):
        try:
            dtype = np.dtype(self.dtype)
            if (
                dtype.name not in DTYPES
                or dtype.fields
                or dtype.subdtype
                or dtype.hasobject
            ):
                raise ValueError("Unsupported numeric dtype")
            if len(self.shape) > 32:
                raise ValueError("Tensor rank exceeds 32")
            size = math.prod(self.shape) * dtype.itemsize
            if size > MAX_INLINE_BYTES:
                raise ValueError("Inline tensor exceeds 16 MiB; use an HDF5 file")
            raw = base64.b64decode(self.base64, validate=True)
            if len(raw) != size:
                raise ValueError("Tensor byte count does not match dtype and shape")
        except (TypeError, binascii.Error) as exc:
            raise ValueError("Invalid tensor encoding") from exc
        return self

    def array(self):
        return (
            np.frombuffer(
                base64.b64decode(self.base64, validate=True), dtype=np.dtype(self.dtype)
            )
            .reshape(self.shape)
            .copy()
        )


class Feature(Input):
    name: str = Field(min_length=1)
    samples: list[Tensor] = Field(min_length=1)


class InlineDataset(Input):
    features: list[Feature] = Field(
        min_length=1,
        description="Ordered features: order is part of the SDK dataset schema.",
    )

    @model_validator(mode="after")
    def valid_features(self):
        if len({f.name for f in self.features}) != len(self.features):
            raise ValueError("Feature names must be unique")
        if len({len(f.samples) for f in self.features}) != 1:
            raise ValueError("Each feature must have the same number of samples")
        if (
            sum(
                math.prod(t.shape) * np.dtype(t.dtype).itemsize
                for f in self.features
                for t in f.samples
            )
            > MAX_INLINE_BYTES
        ):
            raise ValueError("Inline dataset exceeds 16 MiB; use an HDF5 file")
        return self

    def entries(self):
        return {f.name: [t.array() for t in f.samples] for f in self.features}


Shape = tuple[StrictInt, ...]
InputSpecs = dict[str, Shape | tuple[Shape, str]]
ModelRef = Reference | FileReference
DatasetRef = Reference | FileReference | InlineDataset
JobType = Literal[tuple(hub.JobType.__members__)]
State = Literal[tuple(hub.JobStatus.State.__members__)]
ArtifactType = Literal[tuple(hub.JobArtifactType.__members__)]
QuantizeDtype = Literal[tuple(hub.QuantizeDtype.__members__)]

CLIENT_METHODS = (
    "get_devices",
    "get_device_attributes",
    "get_frameworks",
    "upload_model",
    "get_model",
    "get_models",
    "submit_compile_job",
    "submit_quantize_job",
    "submit_profile_job",
    "submit_inference_job",
    "submit_link_job",
    "submit_compile_and_profile_jobs",
    "submit_compile_and_link_jobs",
    "get_job",
    "get_job_summaries",
    "set_verbose",
    "upload_dataset",
    "get_dataset",
    "get_datasets",
    "get_project",
    "create_project",
    "get_projects",
)
OBJECT_METHODS = {
    "model": (
        hub.Model,
        (
            "download",
            "get_sharing",
            "modify_sharing",
            "disable_sharing",
            "wait",
            "get_producer",
        ),
    ),
    "dataset": (
        hub.Dataset,
        (
            "download",
            "get_expiration_status",
            "is_expired",
            "get_sharing",
            "modify_sharing",
            "disable_sharing",
        ),
    ),
    "job": (
        hub.Job,
        (
            "get_available_artifacts",
            "wait",
            "get_status",
            "set_name",
            "download_results",
            "get_sharing",
            "modify_sharing",
            "disable_sharing",
            "download_artifacts_for_type",
            "download_job_logs",
        ),
    ),
    "compilejob": (
        hub.CompileJob,
        ("get_target_model", "get_target_shapes", "download_target_model"),
    ),
    "quantizejob": (hub.QuantizeJob, ("get_target_model", "download_target_model")),
    "linkjob": (hub.LinkJob, ("get_target_model", "download_target_model")),
    "inferencejob": (
        hub.InferenceJob,
        ("get_output_dataset", "download_output_data", "download_profile"),
    ),
}


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    cls: type
    kind: str | None = None
    property_read: bool = False

    @property
    def sensitive(self):
        return self.method.startswith(
            ("submit_", "upload_", "create_")
        ) or self.method in ("modify_sharing", "disable_sharing", "set_name")

    @property
    def sdk_method(self):
        member = getattr(self.cls, self.method)
        return member.fget if self.property_read else member

    @property
    def parameters(self):
        return [
            p
            for p in inspect.signature(self.sdk_method).parameters.values()
            if p.name != "self"
        ]


OPERATIONS = tuple(
    [Operation(n, n, hub.Client) for n in CLIENT_METHODS]
    + [
        Operation(f"{prefix}_{n}", n, cls, "job" if prefix.endswith("job") else prefix)
        for prefix, (cls, names) in OBJECT_METHODS.items()
        for n in names
    ]
    + [
        Operation(f"model_get_{n}", n, hub.Model, "model", True)
        for n in ("metadata", "input_spec", "output_spec")
    ]
)


def parameter_type(op, parameter):
    name = parameter.name
    if name == "device":
        return DeviceSpec | list[DeviceSpec]
    if name in ("model", "models"):
        if op.method == "upload_model":
            return FileReference
        return (
            ModelRef | list[ModelRef | None] | None
            if name == "models"
            else ModelRef | None
        )
    if name in ("data", "inputs", "calibration_data"):
        if op.method == "upload_dataset":
            return FileReference | InlineDataset
        if name == "calibration_data" and op.method == "submit_quantize_job":
            return DatasetRef
        return DatasetRef | None
    if name == "input_specs":
        return (
            InputSpecs | list[InputSpecs | None] | None
            if op.method == "submit_compile_and_link_jobs"
            else InputSpecs | None
        )
    types = {
        "model_id": RemoteId,
        "dataset_id": RemoteId,
        "job_id": RemoteId,
        "project_id": RemoteId,
        "attributes": str | list[str] | None,
        "weights_dtype": QuantizeDtype,
        "activations_dtype": QuantizeDtype,
        "type": JobType | None,
        "job_type": JobType | None,
        "state": State | list[State] | None,
        "artifact_type": ArtifactType,
        "add_emails": list[str] | None,
        "delete_emails": list[str] | None,
        "graph_names": list[str] | None,
        "compile_options": str | list[str],
        "project": RemoteId | None,
    }
    if name in types:
        return types[name]
    annotation = inspect.signature(op.sdk_method).parameters[name].annotation
    scalar = {
        "str": str,
        "bool": StrictBool,
        "int": StrictInt,
        "str | None": str | None,
        "int | None": StrictInt | None,
    }
    if annotation not in scalar:
        raise TypeError(
            f"Missing JSON parameter contract: {op.name}.{name}: {annotation}"
        )
    return scalar[annotation]


def tool_signature(op):
    params = []
    if op.kind:
        params.append(
            inspect.Parameter(
                f"{op.kind}_id",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[
                    RemoteId,
                    Field(description=f"Existing Qualcomm {op.kind} ID."),
                ],
            )
        )
    for p in op.parameters:
        default = p.default.name if isinstance(p.default, Enum) else p.default
        annotation = Annotated[
            parameter_type(op, p),
            Field(
                description=f"Qualcomm SDK {p.name}; see tool documentation for semantics."
            ),
        ]
        params.append(
            p.replace(
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=annotation,
                default=default,
            )
        )
    if op.sensitive:
        params.append(
            inspect.Parameter(
                "confirm",
                inspect.Parameter.KEYWORD_ONLY,
                default=False,
                annotation=Annotated[
                    StrictBool,
                    Field(
                        description="Explicit authorization for this remote change or potentially billable submission. Human approval must be enforced by the client."
                    ),
                ],
            )
        )
    return inspect.Signature(params, return_annotation=dict[str, object])
