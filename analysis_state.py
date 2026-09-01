"""Fingerprint and manifest helpers for analysis entrypoints.

The cache key deliberately depends on file contents and the active Python
environment.  Git metadata is retained for diagnostics, but it is not part of
the cache decision so that unrelated commits do not force an analysis rerun.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
from typing import Iterable, Mapping, TypeAlias


SCHEMA_VERSION = 1
MANIFEST_FILENAME = ".analysis-manifest.json"
MISSING_VERSION = "<missing>"
_IDENTITY_KEYS = frozenset({"year", "round", "session", "entrypoint"})

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


def _source_paths(entrypoint: Path, repo_root: Path) -> list[Path]:
    candidates = [
        entrypoint,
        repo_root / "analysis_state.py",
        repo_root / "setup.py",
        repo_root / "constants.py",
    ]
    candidates.extend(repo_root / name for name in ("util.py", "requirements.txt"))
    candidates.extend((repo_root / "visualizations").glob("**/*.py"))

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


def build_fingerprint(entrypoint: Path, repo_root: Path) -> Fingerprint:
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
    return Fingerprint(
        source_files=source_files,
        source_hash=source_hash,
        python_version=python_version,
        dependencies=dependencies,
        environment_hash=environment_hash,
        git_commit=git_commit,
        git_dirty=git_dirty,
    )


def manifest_path(output_dir: str | Path) -> Path:
    """Return the standard success-manifest path for an output directory."""

    return Path(output_dir) / MANIFEST_FILENAME


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
) -> bool:
    """Return whether a previous successful analysis is still reusable."""

    if force:
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
) -> Path:
    """Atomically record a successful analysis and all existing output files."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = manifest_path(directory)

    output_paths = {
        path.resolve()
        for path in directory.rglob("*")
        if path.is_file() and path.resolve() != target.resolve()
    }
    for extra_directory in map(Path, extra_output_dirs):
        if not extra_directory.is_dir():
            continue
        output_paths.update(
            path.resolve()
            for path in extra_directory.rglob("*")
            if path.is_file() and path.name != MANIFEST_FILENAME
        )
    output_paths.update(
        Path(path).resolve() for path in extra_output_paths if Path(path).is_file()
    )
    output_files = sorted(_output_record(path, directory) for path in output_paths)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "identity": _identity_dict(identity),
        "fingerprints": fingerprint.to_dict(),
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
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target
