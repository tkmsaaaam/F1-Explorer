"""Fingerprint and manifest helpers for analysis entrypoints.

The cache key deliberately depends on file contents and the active Python
environment.  Git metadata is retained for diagnostics, but it is not part of
the cache decision so that unrelated commits do not force an analysis rerun.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
from collections.abc import Mapping as RuntimeMapping
from typing import Iterable, Mapping, TypeAlias

import fastf1
import math
import numpy as np
import pandas as pd


# Version 4 adds a loaded-session input fingerprint to successful manifests.
SCHEMA_VERSION = 4
MANIFEST_FILENAME = ".analysis-manifest.json"
MISSING_VERSION = "<missing>"
_IDENTITY_KEYS = frozenset({"year", "round", "session", "entrypoint"})
SESSION_INPUT_ALGORITHM = "fastf1-session-input-v1"
SESSION_INPUT_COMPONENTS = (
    "event", "results", "laps", "weather_data", "session_status",
    "track_status", "car_data", "pos_data", "race_control_messages",
)
_REQUIRED_INPUT_COLUMNS = {
    "results": {"Position"}, "laps": {"LapNumber"}, "weather_data": {"Time"},
    "session_status": {"Status"}, "track_status": {"Time", "Status"},
    "race_control_messages": {"Time", "Message"},
    "car_data": {"Time"}, "pos_data": {"Time"},
}

JsonScalar: TypeAlias = str | int | float | bool | None
AnalysisIdentity: TypeAlias = Mapping[str, JsonScalar]


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """A snapshot of analysis source files and its execution environment."""

    source_files: Mapping[str, str]
    source_hash: str
    python_version: str
    dependencies: Mapping[str, str]
    environment_hash: str
    git_commit: str | None
    git_dirty: bool | None
    configuration_hash: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON representation used by manifests."""

        return {
            "source": {
                "hash": self.source_hash,
                "files": dict(sorted(self.source_files.items())),
            },
            "environment": {
                "hash": self.environment_hash,
                "python_version": self.python_version,
                "dependencies": dict(sorted(self.dependencies.items())),
            },
            "git": {
                "commit": self.git_commit,
                "dirty": self.git_dirty,
            },
            "configuration": {
                "hash": self.configuration_hash,
            },
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(encoded)


def _normalise_input_value(value: object) -> object:
    """Turn FastF1 and pandas values into deterministic JSON with explicit nulls."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.DataFrame):
        return {
            "kind": "dataframe", "columns": [_normalise_input_value(v) for v in value.columns],
            "index": [_normalise_input_value(v) for v in value.index],
            "rows": [[_normalise_input_value(v) for v in row] for row in value.itertuples(index=False, name=None)],
        }
    if isinstance(value, pd.Series):
        return {"kind": "series", "name": _normalise_input_value(value.name),
                "index": [_normalise_input_value(v) for v in value.index],
                "values": [_normalise_input_value(v) for v in value.array]}
    if isinstance(value, pd.Index):
        return {"kind": "index", "values": [_normalise_input_value(v) for v in value]}
    if isinstance(value, RuntimeMapping):
        return {str(k): _normalise_input_value(value[k]) for k in sorted(value, key=lambda item: str(item))}
    if isinstance(value, np.ndarray):
        return [_normalise_input_value(v) for v in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_normalise_input_value(v) for v in value]
    if isinstance(value, np.generic):
        return _normalise_input_value(value.item())
    if isinstance(value, (pd.Timestamp, datetime)):
        return {"datetime": value.isoformat()}
    if isinstance(value, pd.Timedelta):
        return {"timedelta_ns": int(value.value)}
    if isinstance(value, timedelta):
        total_seconds = value.days * 86_400 + value.seconds
        return {"timedelta_ns": total_seconds * 1_000_000_000 + value.microseconds * 1_000}
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            return {"float": "+inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "isoformat"):
        return {"datetime": value.isoformat()}
    raise TypeError(f"unsupported session input value: {type(value).__name__}")


def session_input_fingerprint(session: object, *, include_messages: bool) -> dict[str, object] | None:
    """Hash raw loaded session inputs; failures conservatively disable reuse."""
    components = [name for name in SESSION_INPUT_COMPONENTS
                  if include_messages or name != "race_control_messages"]
    inputs: dict[str, object] = {}
    values: dict[str, object] = {}
    try:
        event = getattr(session, "event")
        if event is None:
            return None
        values["event"] = event
        if ((isinstance(event, RuntimeMapping) and not event)
                or (isinstance(event, pd.Series) and event.empty)):
            return None
        inputs["event"] = _normalise_input_value(event)
        for name in components[1:]:
            # Every selected property must be present; an unavailable value is
            # not equivalent to an empty input. FastF1 may raise DataNotLoadedError.
            value = getattr(session, name)
            values[name] = value
            if value is None:
                return None
            if name in ("car_data", "pos_data") and isinstance(value, RuntimeMapping):
                if any(not isinstance(frame, pd.DataFrame) for frame in value.values()):
                    return None
                required_columns = _REQUIRED_INPUT_COLUMNS[name]
                if any(not required_columns.issubset(set(map(str, frame.columns)))
                       for frame in value.values()):
                    return None
                value = {str(k): value[k] for k in sorted(value, key=lambda item: str(item))}
            elif name in ("car_data", "pos_data"):
                return None
            elif not isinstance(value, pd.DataFrame):
                return None
            required_columns = _REQUIRED_INPUT_COLUMNS.get(name, set())
            if (isinstance(value, pd.DataFrame)
                    and not required_columns.issubset(set(map(str, value.columns)))):
                return None
            inputs[name] = _normalise_input_value(value)
        digest = _canonical_hash(inputs)
        columns = {}
        for name in components:
            value = values[name]
            columns[name] = {
                str(key): [str(column) for column in item.columns]
                for key, item in value.items()
            } if name in ("car_data", "pos_data") else (
                [str(key) for key in value.index] if name == "event" and isinstance(value, pd.Series) else (
                [str(key) for key in value] if name == "event" and isinstance(value, RuntimeMapping) else (
                [str(column) for column in value.columns] if isinstance(value, pd.DataFrame) else None
                ))
            )
    except Exception:
        # FastF1 DataNotLoadedError and unusual third-party scalar types mean
        # the loaded input cannot be compared safely, so disable reuse.
        return None
    return {"algorithm": SESSION_INPUT_ALGORITHM, "hash": digest,
            "components": components, "columns": columns,
            "fastf1_version": getattr(fastf1, "__version__", MISSING_VERSION)}


def session_is_finished(session: object) -> bool:
    try:
        status = getattr(session, "session_status", None)
    except Exception:
        return False
    if not isinstance(status, pd.DataFrame) or status.empty or "Status" not in status:
        return False
    final_status = status["Status"].iloc[-1]
    return isinstance(final_status, str) and final_status.casefold() == "finished"


def _source_paths(entrypoint: Path, repo_root: Path) -> list[Path]:
    candidates = [entrypoint, repo_root / "requirements.txt"]
    candidates.extend((repo_root / "f1_explorer").glob("**/*.py"))
    candidates.extend((repo_root / "templates").glob("**/*.html"))

    unique: dict[str, Path] = {}
    for candidate in candidates:
        path = candidate.resolve()
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(repo_root).as_posix()
        except ValueError as error:
            raise ValueError(f"source file is outside repo root: {path}") from error
        unique[relative] = path
    return [unique[name] for name in sorted(unique)]


def _requirement_names(requirements_path: Path) -> list[str]:
    if not requirements_path.is_file():
        return []

    names: set[str] = set()
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line or line.startswith(("-", "http://", "https://", "git+")):
            continue
        match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if match:
            names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return sorted(names)


def _dependency_versions(requirements_path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _requirement_names(requirements_path):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = MISSING_VERSION
    return versions


def _git_metadata(repo_root: Path) -> tuple[str | None, bool | None]:
    try:
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None, None
    return commit_result.stdout.strip(), bool(status_result.stdout.strip())


def build_fingerprint(entrypoint: Path, repo_root: Path, config_path: Path | None = None) -> Fingerprint:
    """Build a content and environment fingerprint for an analysis script."""

    root = repo_root.resolve()
    entrypoint_path = entrypoint if entrypoint.is_absolute() else root / entrypoint
    source_files: dict[str, str] = {}
    for path in _source_paths(entrypoint_path.resolve(), root):
        relative = path.relative_to(root).as_posix()
        source_files[relative] = _sha256(path.read_bytes())

    source_hash = _canonical_hash(source_files)
    python_version = platform.python_version()
    dependencies = _dependency_versions(root / "requirements.txt")
    environment_hash = _canonical_hash(
        {"python_version": python_version, "dependencies": dependencies}
    )
    git_commit, git_dirty = _git_metadata(root)
    configuration_hash: str | None = None
    if config_path is not None:
        path = config_path if config_path.is_absolute() else root / config_path
        try:
            # Hash parsed JSON rather than formatting so atomic rewrites and
            # harmless whitespace changes do not create different cache keys.
            configuration_hash = _canonical_hash(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError):
            configuration_hash = MISSING_VERSION
    return Fingerprint(
        source_files=source_files,
        source_hash=source_hash,
        python_version=python_version,
        dependencies=dependencies,
        environment_hash=environment_hash,
        git_commit=git_commit,
        git_dirty=git_dirty,
        configuration_hash=configuration_hash,
    )


def manifest_path(output_dir: str | Path) -> Path:
    """Return the standard success-manifest path for an output directory."""

    return Path(output_dir) / MANIFEST_FILENAME


def invalidate_success_manifest(output_dir: str | Path) -> None:
    """Remove the prior success marker before starting a regeneration."""

    try:
        manifest_path(output_dir).unlink()
    except FileNotFoundError:
        pass


def _identity_dict(identity: AnalysisIdentity) -> dict[str, JsonScalar]:
    normalized = dict(identity)
    if set(normalized) != _IDENTITY_KEYS:
        missing = sorted(_IDENTITY_KEYS - set(normalized))
        extra = sorted(set(normalized) - _IDENTITY_KEYS)
        raise ValueError(f"invalid identity keys; missing={missing}, extra={extra}")
    return normalized


def _recorded_outputs_exist(manifest_file: Path, output_files: object) -> bool:
    if not isinstance(output_files, list) or not output_files:
        return False
    for recorded in output_files:
        if not isinstance(recorded, str) or not recorded:
            return False
        path = Path(recorded)
        if not path.is_absolute():
            path = manifest_file.parent / path
        if not path.is_file():
            return False
    return True


def should_skip(
    manifest_file: str | Path,
    fingerprint: Fingerprint,
    expected_identity: AnalysisIdentity,
    force: bool = False,
    session_input: Mapping[str, object] | None = None,
    complete: bool = True,
) -> bool:
    """Return whether a previous successful analysis is still reusable."""

    if force or not complete or session_input is None:
        return False
    path = Path(manifest_file)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        identity = _identity_dict(expected_identity)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        return False

    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return False
    if payload.get("identity") != identity:
        return False
    fingerprints = payload.get("fingerprints")
    if not isinstance(fingerprints, dict):
        return False
    source = fingerprints.get("source")
    environment = fingerprints.get("environment")
    if not isinstance(source, dict) or not isinstance(environment, dict):
        return False
    if source.get("hash") != fingerprint.source_hash:
        return False
    if environment.get("hash") != fingerprint.environment_hash:
        return False
    inputs = fingerprints.get("session_input")
    if not isinstance(inputs, dict) or inputs != dict(session_input):
        return False
    if fingerprint.configuration_hash is not None:
        configuration = fingerprints.get("configuration")
        if not isinstance(configuration, dict) or configuration.get("hash") != fingerprint.configuration_hash:
            return False
    return _recorded_outputs_exist(path, payload.get("output_files"))


def _output_record(path: Path, output_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(output_dir.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def write_success_manifest(
    output_dir: str | Path,
    fingerprint: Fingerprint,
    identity: AnalysisIdentity,
    extra_output_paths: Iterable[str | Path] = (),
    extra_output_dirs: Iterable[str | Path] = (),
    exclude_extra_suffixes: tuple[str, ...] = (),
    required_output_paths: Iterable[str | Path] = (),
    session_input: Mapping[str, object] | None = None,
) -> Path:
    """Atomically record explicitly listed outputs from a successful analysis."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = manifest_path(directory)

    if tuple(extra_output_dirs) or exclude_extra_suffixes:
        raise ValueError("recursive output discovery is unsupported; pass explicit output paths")
    required_paths = {Path(path).resolve() for path in required_output_paths}
    output_paths = {Path(path).resolve() for path in extra_output_paths}
    if not required_paths or not output_paths:
        raise ValueError("at least one required output path must be declared")
    if session_input is None:
        raise ValueError("session input fingerprint is required")
    missing = sorted(str(path) for path in required_paths if not path.is_file())
    if missing:
        raise FileNotFoundError(f"required analysis outputs are missing: {missing}")
    unlisted_required = sorted(str(path) for path in required_paths if path not in output_paths)
    if unlisted_required:
        raise ValueError(f"required outputs were not produced in this run: {unlisted_required}")
    missing_listed = sorted(str(path) for path in output_paths if not path.is_file())
    if missing_listed:
        raise FileNotFoundError(f"analysis outputs are missing: {missing_listed}")
    output_paths.discard(target.resolve())
    output_files = sorted(_output_record(path, directory) for path in output_paths)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "identity": _identity_dict(identity),
        "fingerprints": {**fingerprint.to_dict(), "session_input": dict(session_input)},
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "output_files": output_files,
    }

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(Path(temporary.name), target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target
