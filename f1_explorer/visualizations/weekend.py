import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Final, TypedDict, Mapping

import pandas as pd

import fastf1
import plotly.graph_objects as go
import structlog
# noinspection PyPackageRequirements
from opentelemetry import trace

from f1_explorer import constants
from f1_explorer.visualizations.output import save_plotly

tracer = trace.get_tracer(__name__)

_CACHE_ENV = "F1_WEEKEND_TYRE_CACHE"
_CACHE_SCHEMA = 1



class TyreUse(TypedDict):
    Sessions: list[str]
    Compounds: list[str]


class WeekendEvent(TypedDict):
    year: int
    round: int
    location: str


class TyreAggregate(TypedDict):
    drivers: dict[str, TyreUse]
    order: list[str]
    figure_names: list[str]
    sprint: bool
    event: WeekendEvent
    complete: bool
    inputs: str | None
    session_signatures: dict[str, str]


class CacheFingerprint(TypedDict):
    fingerprint: str
    environment: str
    settings: str
    inputs: str | None
    input_files: list[list[object]] | None

def _session_status(session) -> str:
    status = getattr(session, "session_status", None)
    if status is None:
        status = getattr(session, "session_status_data", None)
    if status is None:
        return ""
    if hasattr(status, "iloc"):
        try:
            status = status.iloc[-1]
        except (IndexError, KeyError):
            return ""
    if hasattr(status, "get"):
        status = status.get("Status", status.get("status", ""))
    return str(status).strip().casefold()


def _session_is_complete(session) -> bool:
    status: pd.DataFrame | None = getattr(session, "session_status", None)
    if status is None:
        status = getattr(session, "session_status_data", None)
    if status is None:
        return False
    try:
        values = list(status["Status"])
    except (KeyError, TypeError, IndexError):
        return _session_status(session) in {"finished", "finalised", "finalized"}
    normalized = [str(value).strip().casefold() for value in values]
    if not normalized:
        return False
    if normalized[-1] in {"finished", "finalised", "finalized"}:
        return True
    if normalized[-1] == "ends":
        non_ends = [value for value in normalized if value != "ends"]
        return bool(non_ends and non_ends[-1] in {"finished", "finalised", "finalized"})
    return False


def _input_snapshot(year: int, race_number: int, current_session=None) -> list[list[object]] | None:
    """Fingerprint the FastF1 cache files for this event; unknown state disables reuse."""
    try:
        cache_root, _ = fastf1.Cache.get_cache_info()
        api_path = getattr(current_session, "api_path", None)
        if not cache_root or not isinstance(api_path, str) or not api_path.startswith("/static/"):
            return None
        cache_root_path = Path(cache_root).resolve()
        session_cache_dir = (cache_root_path / api_path[8:]).resolve()
        session_cache_dir.relative_to(cache_root_path)
        event_cache_dir = session_cache_dir.parent
        if not event_cache_dir.is_dir():
            return None
        relevant: list[list[object]] = []
        for path in sorted(event_cache_dir.rglob("*.ff1pkl")):
            stat = path.stat()
            relevant.append([str(path.relative_to(cache_root_path)), stat.st_size, stat.st_mtime_ns])
        if not relevant:
            return None
        return relevant
    except (OSError, AttributeError, TypeError, ValueError):
        return None


def _input_signature(year: int, race_number: int, current_session=None) -> str | None:
    snapshot = _input_snapshot(year, race_number, current_session)
    if snapshot is None:
        return None
    return hashlib.sha256(json.dumps(snapshot, separators=(",", ":")).encode()).hexdigest()


def _loaded_session_signature(session) -> str:
    records = []
    for driver in session.drivers:
        laps = session.laps.pick_drivers(driver)
        laps = laps[laps.FreshTyre].drop_duplicates(subset=["Stint"], keep="first")
        abbreviation = session.get_driver(driver).Abbreviation
        records.extend((abbreviation, str(lap.Stint), str(lap.Compound)) for lap in laps.itertuples())
    payload = {
        "name": str(session.name),
        "year": int(session.event.year),
        "round": int(session.event.RoundNumber),
        "format": str(session.event.EventFormat),
        "order": list(session.results.Abbreviation),
        "tyres": records,
    }
    if session.name == "Race":
        status: pd.DataFrame | None = getattr(session, "session_status", None)
        payload["status"] = list(status["Status"]) if status is not None else []
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _cache_fingerprint(year: int, race_number: int, current_session=None) -> CacheFingerprint | None:
    try:
        from f1_explorer.analysis_state import build_fingerprint

        repo = Path(__file__).resolve().parents[2]
        fp = build_fingerprint(Path(__file__), repo, Path("config.json"))
        # The active Session changes per child job; only tyre-relevant settings are
        # included here, together with source/dependency and cached input snapshots.
        settings = json.loads(Path("config.json").read_text(encoding="utf-8"))
        for key in ("Session", "Corners", "corners", "Separator", "separator",
                    "Separators", "separators", "Comparison", "comparison"):
            settings.pop(key, None)
        input_files = _input_snapshot(year, race_number, current_session)
        return {"fingerprint": fp.source_hash, "environment": fp.environment_hash,
                "settings": hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest(),
                "inputs": (hashlib.sha256(json.dumps(input_files, separators=(",", ":")).encode()).hexdigest()
                           if input_files is not None else None),
                "input_files": input_files}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _read_cache(path: Path, fingerprint: Mapping[str, object]) -> TyreAggregate | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        aggregate = payload.get("aggregate")
        if (isinstance(payload, dict) and payload.get("schema") == _CACHE_SCHEMA
                and payload.get("fingerprint") == fingerprint and isinstance(aggregate, dict)
                and isinstance(aggregate.get("drivers"), dict)
                and isinstance(aggregate.get("order"), list)
                and isinstance(aggregate.get("figure_names"), list)
                and isinstance(aggregate.get("sprint"), bool)
                and isinstance(aggregate.get("event"), dict)
                and isinstance(aggregate["event"].get("year"), int)
                and isinstance(aggregate["event"].get("round"), int)
                and isinstance(aggregate["event"].get("location"), str)
                and isinstance(aggregate.get("complete"), bool)
                and aggregate.get("complete") is True
                and isinstance(aggregate.get("inputs"), str)
                and isinstance(aggregate.get("session_signatures"), dict)
                and all(isinstance(key, str) and isinstance(value, str)
                        for key, value in aggregate["session_signatures"].items())
                and aggregate["drivers"]
                and all(isinstance(name, str) for name in aggregate["order"] + aggregate["figure_names"])
                and all(isinstance(driver, str) and isinstance(data, dict)
                   and isinstance(data.get("Sessions"), list)
                   and isinstance(data.get("Compounds"), list)
                   and len(data["Sessions"]) == len(data["Compounds"])
                   and all(isinstance(value, str) for value in data["Sessions"] + data["Compounds"])
                   for driver, data in aggregate["drivers"].items())):
                return TyreAggregate(
                    drivers=aggregate["drivers"], order=aggregate["order"],
                    figure_names=aggregate["figure_names"], sprint=aggregate["sprint"],
                    event=aggregate["event"], complete=aggregate["complete"],
                    inputs=aggregate["inputs"], session_signatures=aggregate["session_signatures"],
                )
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
        pass
    return None


def _write_cache(path: Path, fingerprint: Mapping[str, object], aggregate: TyreAggregate) -> None:
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"schema": _CACHE_SCHEMA, "fingerprint": fingerprint,
                       "aggregate": aggregate}, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError):
        pass
    finally:
        try:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        except OSError:
            pass


@tracer.start_as_current_span("weekend.tyre.aggregate")
def aggregate_tyres(year: int, race_number: int, log, current_session=None) -> TyreAggregate | None:
    drivers: dict[str, TyreUse] = {}
    order: list[str] = []
    sprint = False
    event_info: WeekendEvent = {"year": year, "round": race_number, "location": ""}
    race_complete = False
    race_session = None
    session_signatures = {}
    sessions: Final[list[str]] = ['FP1', 'FP2', 'FP3', 'SQ', 'S', 'Q', 'R']
    for session_name in sessions:
        try:
            session = (current_session if current_session is not None and
                       int(current_session.event.year) == int(year) and
                       int(current_session.event.RoundNumber) == int(race_number) and
                       current_session.name == {
                           'FP1': 'Practice 1', 'FP2': 'Practice 2', 'FP3': 'Practice 3',
                           'SQ': 'Sprint Qualifying', 'S': 'Sprint', 'Q': 'Qualifying', 'R': 'Race'
                       }[session_name] else fastf1.get_session(year, race_number, session_name))
        except ValueError:
            continue
        if session is None or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) < session.date:
            continue
        if session is not current_session:
            with tracer.start_as_current_span("weekend.tyre.session_load") as span:
                span.set_attribute("session", session_name)
                span.set_attribute("year", year)
                span.set_attribute("round", race_number)
                session.load(weather=False, messages=False, telemetry=False)
        else:
            with tracer.start_as_current_span("weekend.tyre.session_reuse") as span:
                span.set_attribute("session", session_name)
                span.set_attribute("year", year)
                span.set_attribute("round", race_number)
        event_info = {"year": int(session.event.year), "round": int(session.event.RoundNumber),
                      "location": str(session.event.Location)}
        if session_name == "R":
            race_session = session
            race_complete = _session_is_complete(session)
        order = [d for d in session.results.Abbreviation]
        sprint = session.event.EventFormat == 'sprint_qualifying'
        session_signatures[session_name] = _loaded_session_signature(session)
        with tracer.start_as_current_span("weekend.tyre.session_aggregate") as span:
            span.set_attribute("session", session_name)
            span.set_attribute("year", year)
            span.set_attribute("round", race_number)
            for driver in session.drivers:
                driver_laps = session.laps.pick_drivers(driver)
                laps = driver_laps[driver_laps.FreshTyre].drop_duplicates(subset=['Stint'], keep='first')
                if laps.empty:
                    continue
                abbreviation = session.get_driver(driver).Abbreviation
                data = drivers.setdefault(abbreviation, {'Sessions': [], 'Compounds': []})
                data['Sessions'].extend([session_name for _ in range(len(laps))])
                data['Compounds'].extend(laps["Compound"].tolist())
    if not drivers:
        return None
    figure_names = order + list(set(drivers.keys()) - set(order))
    return {'drivers': drivers, 'order': order, 'figure_names': figure_names,
            'sprint': sprint, 'event': event_info,
            'complete': race_complete,
            'inputs': _input_signature(year, race_number, race_session or current_session),
            'session_signatures': session_signatures}


def _batch_cached_aggregate(year: int, race_number: int, log, current_session=None) -> TyreAggregate | None:
    cache_root = os.environ.get(_CACHE_ENV)
    fingerprint = _cache_fingerprint(year, race_number, current_session) if cache_root else None
    eligible = bool(cache_root and fingerprint is not None and fingerprint.get("inputs") is not None)
    aggregate = None
    if eligible and cache_root is not None and fingerprint is not None:
        with tracer.start_as_current_span("weekend.tyre.cache_lookup") as span:
            span.set_attribute("cache.eligible", True)
            span.set_attribute("year", year)
            span.set_attribute("round", race_number)
            cache_path = Path(cache_root) / f"{year}-{race_number}.json"
            aggregate = _read_cache(cache_path, fingerprint)
            reused = False
            if aggregate is not None:
                current_name = next((name for name, label in {
                    'FP1': 'Practice 1', 'FP2': 'Practice 2', 'FP3': 'Practice 3',
                    'SQ': 'Sprint Qualifying', 'S': 'Sprint', 'Q': 'Qualifying', 'R': 'Race'
                }.items() if current_session is not None and current_session.name == label), None)
                current_matches = (current_session is None or current_name is not None and
                                   aggregate["session_signatures"].get(current_name) ==
                                   _loaded_session_signature(current_session) and
                                   (current_name != "R" or _session_is_complete(current_session)))
                reused = current_matches and aggregate.get("inputs") == fingerprint.get("inputs")
            span.set_attribute("cache.record_found", aggregate is not None)
            span.set_attribute("cache.hit", reused)
            if reused:
                log.info("weekend tyre aggregate cache hit", year=year, round=race_number)
                return aggregate
    aggregate = aggregate_tyres(year, race_number, log, current_session=current_session)
    if aggregate is None:
        return None
    if eligible and cache_root is not None and fingerprint is not None and aggregate.get("complete") is True:
        latest_fingerprint = _cache_fingerprint(year, race_number, current_session)
        if latest_fingerprint is None:
            return aggregate
        stable_fingerprint = _cache_fingerprint(year, race_number, current_session)
        initial_files = {
            tuple(entry) for entry in (fingerprint.get("input_files") or [])
            if isinstance(entry, list) and len(entry) == 3
        }
        latest_files = (latest_fingerprint or {}).get("input_files")
        latest_file_set = {
            tuple(entry) for entry in latest_files or []
            if isinstance(entry, list) and len(entry) == 3
        }
        same_non_input_key = bool(latest_fingerprint and all(
            latest_fingerprint.get(key) == fingerprint.get(key)
            for key in ("fingerprint", "environment", "settings")
        ))
        if (latest_fingerprint is not None and latest_fingerprint == stable_fingerprint
                and same_non_input_key and initial_files <= latest_file_set
                and aggregate.get("inputs") == latest_fingerprint.get("inputs")):
            _write_cache(Path(cache_root) / f"{year}-{race_number}.json", latest_fingerprint, aggregate)
    return aggregate


def make_tyre_figure(aggregate: TyreAggregate):
    drivers = aggregate['drivers']
    order = aggregate['order']
    sprint = aggregate['sprint']
    max_rows = max(len(d['Sessions']) for d in drivers.values())
    names = aggregate['figure_names']
    table_columns = []
    table_colors = []
    for name in names:
        driver_data = drivers.get(name, {'Compounds': [], 'Sessions': []})
        compounds = driver_data['Compounds']
        counts = [f"{compounds.count(compound)}({constants.compound_counts_sprint.get(compound, 0) if sprint else constants.compound_counts.get(compound, 0)})"
                  for compound in constants.compound_color]
        session_list = driver_data['Sessions']
        padding = max_rows - len(session_list)
        table_columns.append(counts + session_list + [""] * padding)
        table_colors.append(list(constants.compound_color.values()) +
                            [constants.compound_color.get(compound, "white") for compound in compounds] +
                            ["white"] * padding)
    with tracer.start_as_current_span("weekend.tyre.figure") as span:
        span.set_attribute("year", aggregate["event"]["year"])
        span.set_attribute("round", aggregate["event"]["round"])
        return go.Figure(data=[go.Table(
            header=go.table.Header(values=names, fill=go.table.header.Fill(color='lightgrey'), align='center'),
            cells=go.table.Cells(values=table_columns, fill=go.table.cells.Fill(color=table_colors), align='center'))])


@tracer.start_as_current_span("plot_tyre")
def plot_tyre(
        year: int,
        race_number: int,
        log: structlog.stdlib.BoundLogger,
        *,
        output_dir: str | Path | None = None,
        current_session=None,
):
    aggregate = _batch_cached_aggregate(year, race_number, log, current_session=current_session)
    if aggregate is None:
        return
    fig = make_tyre_figure(aggregate)

    event = aggregate['event']
    base_dir = Path(output_dir) if output_dir is not None else Path("images") / str(event['year']) / f"{event['round']}_{event['location']}"
    save_plotly(fig, base_dir / "tyres.png", log, width=1920, height=1080)
