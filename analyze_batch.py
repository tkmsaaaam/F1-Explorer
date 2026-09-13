"""Run multiple F1 session analyzers from a JSON plan.

The analyzers currently read ``config.json`` themselves.  This runner updates
only Year/Round/Session before each subprocess and preserves every other
setting, including separators generated during a previous session.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence


SESSION_ENTRYPOINTS = {
    "FP1": "analyze_practice.py",
    "FP2": "analyze_practice.py",
    "FP3": "analyze_practice.py",
    "Q": "analyze_qualifying.py",
    "SQ": "analyze_qualifying.py",
    "R": "analyze_race.py",
    "S": "analyze_race.py",
}


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    year: int
    round: int
    session: str


def _as_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def parse_plan(payload: Any) -> list[AnalysisJob]:
    """Parse the batch plan and reject ambiguous or unsupported jobs."""
    if isinstance(payload, Mapping):
        for key in ("schedule", "years", "analyses"):
            if key in payload:
                payload = payload[key]
                break
    years = _as_list(payload, field="plan")
    jobs: list[AnalysisJob] = []
    seen: set[AnalysisJob] = set()
    for year_index, year_item in enumerate(years):
        if not isinstance(year_item, Mapping):
            raise ValueError(f"plan[{year_index}] must be an object")
        try:
            year = int(year_item["year"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"plan[{year_index}].year must be an integer") from error
        gps = year_item.get("gp", year_item.get("gps"))
        for gp_index, gp_item in enumerate(_as_list(gps, field=f"plan[{year_index}].gp")):
            if not isinstance(gp_item, Mapping):
                raise ValueError(f"plan[{year_index}].gp[{gp_index}] must be an object")
            raw_round = gp_item.get("number", gp_item.get("round"))
            try:
                round_number = int(raw_round)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"plan[{year_index}].gp[{gp_index}].number must be an integer"
                ) from error
            if round_number < 1:
                raise ValueError("round number must be greater than zero")
            sessions = _as_list(
                gp_item.get("sessions"),
                field=f"plan[{year_index}].gp[{gp_index}].sessions",
            )
            for raw_session in sessions:
                session = str(raw_session).strip().upper()
                if session not in SESSION_ENTRYPOINTS:
                    supported = ", ".join(SESSION_ENTRYPOINTS)
                    raise ValueError(f"unsupported session {raw_session!r}; expected one of {supported}")
                job = AnalysisJob(year, round_number, session)
                if job not in seen:
                    jobs.append(job)
                    seen.add(job)
    if not jobs:
        raise ValueError("plan contains no analysis jobs")
    return jobs


def load_plan(path: str | Path) -> list[AnalysisJob]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"unable to read analysis plan: {path}") from error
    return parse_plan(payload)


def read_config(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"unable to read config: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("config must be a JSON object")
    return payload


def write_config(path: str | Path, config: Mapping[str, Any]) -> None:
    """Atomically replace config while retaining all supplied fields."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(dict(config), file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def update_job_config(path: str | Path, job: AnalysisJob) -> None:
    config = read_config(path)
    config.update({"Year": job.year, "Round": job.round, "Session": job.session})
    write_config(path, config)


def command_for(
    job: AnalysisJob,
    *,
    python: str,
    force: bool = False,
    refresh_separators: bool = False,
) -> list[str]:
    command = [python, SESSION_ENTRYPOINTS[job.session]]
    if force:
        command.append("--force")
    if refresh_separators and job.session in {"FP1", "FP2", "FP3", "Q", "SQ"}:
        command.append("--refresh-separators")
    return command


def run_jobs(
    jobs: Sequence[AnalysisJob],
    *,
    config_path: str | Path,
    repo_root: str | Path,
    python: str = sys.executable,
    force: bool = False,
    refresh_separators: bool = False,
    fail_fast: bool = False,
    dry_run: bool = False,
    keep_last_config: bool = False,
) -> int:
    root = Path(repo_root).resolve()
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = root / config_file
    if dry_run:
        for index, job in enumerate(jobs, start=1):
            command = command_for(
                job,
                python=python,
                force=force,
                refresh_separators=refresh_separators,
            )
            print(
                f"[{index}/{len(jobs)}] {job.year} round {job.round} {job.session}: "
                + " ".join(command),
                flush=True,
            )
        print(f"Dry run: {len(jobs)} job(s).")
        return 0
    original = read_config(config_file)
    original_selection = {key: original.get(key) for key in ("Year", "Round", "Session")}
    failures: list[tuple[AnalysisJob, int]] = []
    try:
        for index, job in enumerate(jobs, start=1):
            command = command_for(
                job,
                python=python,
                force=force,
                refresh_separators=refresh_separators,
            )
            print(
                f"[{index}/{len(jobs)}] {job.year} round {job.round} {job.session}: "
                + " ".join(command),
                flush=True,
            )
            update_job_config(config_file, job)
            result = subprocess.run(command, cwd=root, check=False)
            if result.returncode != 0:
                failures.append((job, result.returncode))
                print(f"  failed with exit code {result.returncode}", file=sys.stderr, flush=True)
                if fail_fast:
                    break
    finally:
        if not keep_last_config:
            # Re-read so separators generated by analyzers are retained.
            latest = read_config(config_file)
            latest.update(original_selection)
            write_config(config_file, latest)

    if failures:
        print(f"Completed with {len(failures)} failed job(s).", file=sys.stderr)
        return 1
    print(f"Completed {len(jobs)} job(s).")
    return 0


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run F1 analyses from a JSON batch plan")
    parser.add_argument("plan", type=Path, help="JSON plan file")
    parser.add_argument("--force", action="store_true", help="pass --force to every analyzer")
    parser.add_argument(
        "--refresh-separators",
        action="store_true",
        help="refresh Practice/Qualifying separators; ignored for Race/Sprint",
    )
    parser.add_argument("--fail-fast", action="store_true", help="stop after the first non-zero exit")
    parser.add_argument("--dry-run", action="store_true", help="show jobs without changing config or running them")
    parser.add_argument(
        "--keep-last-config",
        action="store_true",
        help="leave Year/Round/Session set to the last executed job",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        jobs = load_plan(args.plan)
        return run_jobs(
            jobs,
            config_path=Path("config.json"),
            repo_root=Path(__file__).resolve().parent,
            force=args.force,
            refresh_separators=args.refresh_separators,
            fail_fast=args.fail_fast,
            dry_run=args.dry_run,
            keep_last_config=args.keep_last_config,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
