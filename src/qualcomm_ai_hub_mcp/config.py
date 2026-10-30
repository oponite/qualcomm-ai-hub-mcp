"""Official authentication and local file trust boundary."""

import os
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

import h5py
import qai_hub as hub
from qai_hub import api_utils

from .errors import ConnectorError

PROTECTED = {
    ".qai_hub",
    ".ssh",
    ".aws",
    ".azure",
    ".docker",
    ".git",
    ".git-credentials",
    ".gnupg",
    ".kube",
    ".netrc",
    ".npmrc",
    ".pgpass",
    ".pypirc",
}


def credential_paths(profile=None):
    return {
        Path(api_utils.get_config_path(profile)).expanduser().resolve(),
        Path(api_utils.get_config_path()).expanduser().resolve(),
    }


def client(profile=None):
    token = os.environ.get("QAI_HUB_API_TOKEN")
    if token is not None and profile:
        raise ConnectorError(
            "CONFIGURATION",
            "Select a token environment variable or a named profile, not both.",
        )
    if token is not None and not token.strip():
        raise ConnectorError("AUTHENTICATION", "QAI_HUB_API_TOKEN is empty.")
    try:
        result = hub.Client(
            config=hub.ClientConfig(token) if token else None, profile=profile
        )
        # Force only local configuration loading. No network call is needed for discovery.
        result.set_verbose(False)
        if not result.config.api_token:
            raise ConnectorError(
                "AUTHENTICATION", "The Qualcomm SDK configuration has no API token."
            )
    except (OSError, hub.UserError) as exc:
        raise ConnectorError(
            "AUTHENTICATION",
            "Configure an API token with qai-hub configure, QAIHUB_CLIENT_INI, or QAI_HUB_API_TOKEN.",
        ) from exc
    return result


def _protected(candidate, forbidden):
    # Windows ignores trailing dots/spaces and opens NTFS streams as "name:stream".
    names = [p.lower().split(":")[0].rstrip(" .") for p in candidate.parts]
    return candidate in forbidden or any(
        n in PROTECTED or n == ".env" or n.startswith(".env.") for n in names
    )


def path(value, root, output=False, *, forbidden=(), directory=False):
    root = Path(root).resolve()
    raw = Path(value).expanduser()
    raw = root / raw
    candidate = raw.resolve()
    forbidden = set(forbidden) | credential_paths()
    if (
        not candidate.is_relative_to(root)
        or _protected(raw, forbidden)
        or _protected(candidate, forbidden)
    ):
        raise ConnectorError(
            "UNSAFE_PATH",
            "Path is outside the workspace or names protected configuration.",
        )
    if output:
        if candidate.exists() or raw.is_symlink():
            raise FileExistsError("Refusing overwrite")
    elif candidate.is_dir() and directory:
        if candidate == root:
            raise ConnectorError(
                "UNSAFE_PATH", "Choose a directory inside the workspace, not its root."
            )
        for parent, dirs, files in os.walk(candidate, followlinks=False):
            for name in dirs + files:
                child = Path(parent) / name
                if child.is_symlink():
                    raise ConnectorError(
                        "UNSAFE_PATH", "Model directories must not contain symlinks."
                    )
                resolved = child.resolve()
                if not resolved.is_relative_to(root) or _protected(resolved, forbidden):
                    raise ConnectorError(
                        "UNSAFE_PATH", "Model directory contains protected files."
                    )
    elif not candidate.is_file():
        raise ConnectorError(
            "UNSAFE_PATH", "Expected an existing regular file inside the workspace."
        )
    return str(candidate)


def safe_name(value):
    """Require a portable basename, including on hosts where backslash is ordinary."""
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)
    }
    if (
        not value
        or value in (".", "..")
        or value.endswith((" ", "."))
        or any(ord(c) < 32 or c in '/\\:*?"<>|' for c in value)
        or PurePosixPath(value).name != value
        or PureWindowsPath(value).name != value
        or value.split(".")[0].upper() in reserved
    ):
        raise ConnectorError("UNSAFE_PATH", "Unsafe server-provided artifact filename.")
    return value


def validate_model_archive(filename):
    if not filename.lower().endswith(".zip"):
        return
    try:
        archive = zipfile.ZipFile(filename)
    except zipfile.BadZipFile as exc:
        raise ConnectorError("INVALID_INPUT", "Model file is not a valid zip.") from exc
    with archive:
        for item in archive.infolist():
            name = item.filename.rstrip("/")
            parts = PurePosixPath(name).parts
            if (
                not parts
                or item.filename.startswith("/")
                or stat.S_ISLNK(item.external_attr >> 16)
            ):
                raise ConnectorError("UNSAFE_PATH", "Unsafe model archive entry.")
            for part in parts:
                safe_name(part)
                if _protected(Path(part), set()):
                    raise ConnectorError(
                        "UNSAFE_PATH", "Model archive contains protected files."
                    )


def validate_hdf5(filename, max_bytes=None):
    """Reject HDF5 links/storage that would make the SDK read another local file."""
    total, seen = 0, set()
    try:
        data = h5py.File(filename, "r")
    except OSError as exc:
        raise ConnectorError(
            "INVALID_INPUT", "Dataset file is not valid HDF5."
        ) from exc
    with data:

        def visit(group):
            nonlocal total
            address = h5py.h5o.get_info(group.id).addr
            if address in seen:
                return
            seen.add(address)
            for name in group:
                link = group.get(name, getlink=True)
                if isinstance(link, (h5py.ExternalLink, h5py.SoftLink)):
                    raise ConnectorError(
                        "UNSAFE_PATH",
                        "HDF5 files must be self-contained, without external or soft links.",
                    )
                obj = group[name]
                if isinstance(obj, h5py.Group):
                    visit(obj)
                elif isinstance(obj, h5py.Dataset):
                    if obj.is_virtual or obj.external or obj.dtype.hasobject:
                        raise ConnectorError(
                            "UNSAFE_PATH",
                            "HDF5 external storage, virtual datasets, and object arrays are unsupported.",
                        )
                    total += obj.size * obj.dtype.itemsize
                    if max_bytes is not None and total > max_bytes:
                        raise ConnectorError(
                            "RESULT_TOO_LARGE",
                            "Dataset exceeds the inline limit; download it to a file.",
                        )

        visit(data)
