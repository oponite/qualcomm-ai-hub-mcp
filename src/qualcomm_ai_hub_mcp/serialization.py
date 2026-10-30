"""JSON encoders for known SDK results; never traverse a client or its config."""

import base64
import math
from collections.abc import Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum

import numpy as np
import qai_hub as hub
from qai_hub.public_rest_api import TensorSpec

from .contracts import MAX_INLINE_BYTES


def dataset_entries(value):
    return {
        "features": [
            {"name": name, "samples": [encode(t) for t in samples]}
            for name, samples in value.items()
        ]
    }


def io_spec(value):
    return {
        "graphs": [
            {"name": name, "tensors": [encode(t) for t in tensors]}
            for name, tensors in value.items()
        ]
    }


def encode(value):
    if isinstance(value, Enum):
        return value.name
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return (
                "NaN"
                if math.isnan(value)
                else ("Infinity" if value > 0 else "-Infinity")
            )
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.generic):
        return encode(value.item())
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject or value.nbytes > MAX_INLINE_BYTES:
            raise ValueError(
                "Tensor cannot be returned inline; download to HDF5 instead"
            )
        return {
            "dtype": value.dtype.str,
            "shape": list(value.shape),
            "base64": base64.b64encode(value.tobytes(order="C")).decode("ascii"),
        }
    if isinstance(value, TensorSpec):
        return {k: encode(getattr(value, k)) for k in ("name", "shape", "dtype")}
    # SDK repeated protobuf fields are annotated as lists but are not list instances.
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {str(encode(k)): encode(v) for k, v in value.items()}
    if isinstance(value, hub.JobStatus):
        return {
            k: encode(getattr(value, k))
            for k in (
                "state",
                "message",
                "code",
                "symbol",
                "success",
                "failure",
                "finished",
                "running",
                "pending",
            )
        }
    if isinstance(value, hub.Model):
        names = (
            "model_id",
            "date",
            "model_type",
            "name",
            "file_size",
            "num_parameters",
            "url",
        )
    elif isinstance(value, hub.Dataset):
        names = ("dataset_id", "name", "creation_time", "expiration_time")
    elif isinstance(value, hub.Project):
        names = ("project_id", "project_name", "project_description", "creation_time")
    elif isinstance(value, hub.Job):
        names = (
            "job_id",
            "name",
            "date",
            "hub_version",
            "options",
            "project_id",
            "job_type",
            "url",
        )
        names += tuple(
            k
            for k in (
                "device",
                "compatible_devices",
                "model",
                "models",
                "shapes",
                "calibration_dataset",
                "weights_dtype",
                "activations_dtype",
                "inputs",
                "profiling",
            )
            if hasattr(value, k)
        )
    elif isinstance(value, (hub.Device, hub.Framework, hub.JobSummary, hub.JobResult)):
        names = (
            tuple(f.name for f in fields(value))
            if is_dataclass(value)
            else ("name", "shape", "dtype")
        )
    else:
        raise TypeError(f"Unsupported SDK result type: {type(value).__name__}")
    return {k: encode(getattr(value, k)) for k in names}
