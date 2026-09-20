"""Automatic mini-segment separator estimation.

The F1 live timing archive is an intentionally small, defensive integration
point.  The archive is not an API supported by FastF1 and has changed shape
several times, so this module accepts both the current archive index shape and
the older, flatter variants.  Estimation is kept independent from report
rendering which makes it possible to test with recorded/mocked streams.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


DEFAULT_ARCHIVE_URL = "https://livetiming.formula1.com"
ARCHIVE_TIMEOUT_SECONDS = 15
_TIMING_DATA_NAME = "TimingData.jsonStream"
_SESSION_NAMES = {
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
    "Q": "Qualifying",
    "SQ": "Sprint Qualifying",
    "Practice 1": "Practice 1",
    "Practice 2": "Practice 2",
    "Practice 3": "Practice 3",
    "Qualifying": "Qualifying",
    "Sprint Qualifying": "Sprint Qualifying",
}


class SeparatorEstimationError(RuntimeError):
    """Raised when an archive or its data cannot produce reliable boundaries."""


SEPARATOR_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SeparatorBoundary:
    """One automatic boundary and its Live Timing identity."""

    distance: float
    sector: int
    segment: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "distance": round(float(self.distance), 1),
            "sector": int(self.sector),
            "segment": int(self.segment),
        }


@dataclass(frozen=True, slots=True)
class SeparatorResolution:
    """The separators selected for a report and how they were obtained."""

    separators: list[float]
    source: str
    pending_save: bool = False
    boundaries: list[SeparatorBoundary] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LiveTimingLapWindow:
    """One internally consistent lap on the Live Timing clock."""

    driver: str
    lap: int
    start: float
    end: float
    reported_lap_time: float

    def percent_at(self, timestamp: float) -> float:
        return (timestamp - self.start) / (self.end - self.start) * 100.0


def _session_name(session: Any) -> str:
    name = getattr(session, "name", "")
    return _SESSION_NAMES.get(str(name), str(name))


def _location(session: Any) -> str:
    event = getattr(session, "event", None)
    if event is None:
        return ""
    for key in ("Location", "location"):
        try:
            value = event[key]
        except (KeyError, TypeError, IndexError):
            value = getattr(event, key, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(getattr(event, "EventName", "")).strip()


def _year(session: Any) -> int:
    event = getattr(session, "event", None)
    value = getattr(event, "year", None)
    if value is None:
        try:
            value = event["year"]
        except (KeyError, TypeError, IndexError):
            value = getattr(session, "year", None)
    return int(value)


def _join_url(base: str, path: str) -> str:
    path = str(path).strip()
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/static/"):
        path = "/static" + path
    return base.rstrip("/") + path


def _normalise_path(path: str) -> str:
    path = str(path).strip()
    if path.endswith("/"):
        return path
    return path + "/"


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _path_value(item: Mapping[str, Any]) -> str | None:
    for key in ("Path", "path", "Url", "URL", "url"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _find_session_path(index: Any, session: Any) -> str | None:
    wanted = _session_name(session).casefold()
    event_name = str(getattr(getattr(session, "event", None), "EventName", "")).casefold()
    location = _location(session).casefold()
    # Some season indexes put the session names in a sibling list and the
    # path on the meeting object.  Match the meeting before its session.
    for meeting in _walk_dicts(index):
        meeting_text = " ".join(
            str(meeting.get(key, "")) for key in ("Name", "EventName", "Location")
        ).casefold()
        if (location and location not in meeting_text) and (not event_name or event_name not in meeting_text):
            continue
        sessions = meeting.get("Sessions", meeting.get("sessions"))
        if not isinstance(sessions, list):
            continue
        for item in sessions:
            if not isinstance(item, dict):
                continue
            name = str(item.get("Name", item.get("name", ""))).casefold()
            if name == wanted or name.replace(" ", "_") == wanted:
                return _path_value(item) or _path_value(meeting)

    # Fall back to a flat index, where each session itself has a name/path and
    # there is no meeting context to disambiguate.
    for item in _walk_dicts(index):
        name = str(item.get("Name", item.get("name", item.get("SessionName", "")))).casefold()
        if name not in {wanted, wanted.replace(" ", "_")}:
            continue
        path = _path_value(item)
        if path:
            return path
    return None


def _find_timing_path(index: Any) -> str | None:
    for item in _walk_dicts(index):
        for key, value in item.items():
            if isinstance(value, str) and _TIMING_DATA_NAME.casefold() in value.casefold():
                return value
            if isinstance(key, str) and _TIMING_DATA_NAME.casefold() in key.casefold():
                return value if isinstance(value, str) else key
    if isinstance(index, list):
        for value in index:
            if isinstance(value, str) and _TIMING_DATA_NAME.casefold() in value.casefold():
                return value
    return None


class StaticArchiveClient:
    """Fetch and cache static archive pages with bounded HTTP timeouts."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_ARCHIVE_URL,
        mirror_base_url: str | None = "https://livetiming-mirror.fastf1.dev",
        cache_dir: str | Path | None = None,
        timeout: float = ARCHIVE_TIMEOUT_SECONDS,
        http_get: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mirror_base_url = mirror_base_url.rstrip("/") if mirror_base_url else None
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.timeout = timeout
        self.http_get = http_get
        self._memory: dict[str, bytes] = {}

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.bin"

    def _get_bytes(self, url: str) -> bytes:
        if url in self._memory:
            return self._memory[url]
        cache_path = self._cache_path(url)
        if cache_path is not None and cache_path.is_file():
            data = cache_path.read_bytes()
            self._memory[url] = data
            return data

        getter = self.http_get
        if getter is None:
            import requests

            getter = requests.get
        try:
            response = getter(url, timeout=self.timeout)
        except Exception as error:
            if self.mirror_base_url and self.base_url != self.mirror_base_url and url.startswith(self.base_url):
                mirror_url = self.mirror_base_url + url[len(self.base_url):]
                response = getter(mirror_url, timeout=self.timeout)
            else:
                raise SeparatorEstimationError(f"archive request failed: {url}") from error
        status = getattr(response, "status_code", 200)
        if status >= 400:
            if self.mirror_base_url and self.base_url != self.mirror_base_url and url.startswith(self.base_url):
                mirror_url = self.mirror_base_url + url[len(self.base_url):]
                response = getter(mirror_url, timeout=self.timeout)
                status = getattr(response, "status_code", 200)
            if status >= 400:
                raise SeparatorEstimationError(f"archive returned HTTP {status}: {url}")
        data = getattr(response, "content", None)
        if data is None:
            text = getattr(response, "text", "")
            data = str(text).encode("utf-8")
        if isinstance(data, str):
            data = data.encode("utf-8")
        data = bytes(data)
        self._memory[url] = data
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=cache_path.parent, delete=False) as file:
                    temporary = Path(file.name)
                    file.write(data)
                    file.flush()
                temporary.replace(cache_path)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        return data

    def _json(self, url: str) -> Any:
        try:
            return json.loads(self._get_bytes(url).decode("utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SeparatorEstimationError(f"invalid archive JSON: {url}") from error

    def timing_data(self, session: Any) -> list[Any]:
        """Resolve year index -> session path -> session index -> stream."""
        year = _year(session)
        season_url = _join_url(self.base_url, f"/{year}/Index.json")
        season_index = self._json(season_url)
        session_path = _find_session_path(season_index, session)
        if session_path is None:
            # FastF1's path is a useful compatibility fallback for indexes that
            # omit old meetings, while still using the static archive stream.
            session_path = getattr(session, "api_path", None)
        if not session_path:
            raise SeparatorEstimationError("session path is missing from archive index")
        session_path = _normalise_path(session_path)
        session_index_url = _join_url(self.base_url, session_path + "Index.json")
        session_index = self._json(session_index_url)
        timing_path = _find_timing_path(session_index)
        if timing_path is None:
            timing_path = _normalise_path(session_path) + _TIMING_DATA_NAME
        elif not timing_path.startswith(("/", "http://", "https://")) and not timing_path.startswith(session_path):
            timing_path = session_path + timing_path
        stream_url = _join_url(self.base_url, timing_path)
        raw = self._get_bytes(stream_url).decode("utf-8-sig")
        return parse_json_stream(raw)


def _time_seconds(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, pd.Timedelta):
        return value.total_seconds()
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.:](\d{1,6}))?", text)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        fraction = float(f"0.{(match.group(4) or '0')[:6]}")
        return hours * 3600 + minutes * 60 + seconds + fraction
    try:
        return pd.to_timedelta(text).total_seconds()
    except (ValueError, TypeError):
        return None


def parse_json_stream(raw: str | bytes | Sequence[Any]) -> list[Any]:
    """Parse a TimingData jsonStream without requiring a live connection."""
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    stripped = str(raw).lstrip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            pass
    result: list[Any] = []
    for line in str(raw).replace("\r\n", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        # jsonStream records start with a fixed-width HH:MM:SS:fff timestamp.
        timestamp = line[:12]
        payload = line[12:]
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            try:
                parsed = json.loads(line)
                timestamp = None
            except json.JSONDecodeError:
                continue
        result.append([timestamp, parsed] if timestamp is not None else parsed)
    return result


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _evaluated(segment: Any) -> bool:
    if not isinstance(segment, Mapping):
        return False
    evaluated = _first(segment, "Evaluated", "evaluated", "IsEvaluated", "isEvaluated")
    if evaluated is not None:
        return bool(evaluated) and evaluated not in {"0", "false", "False"}
    status = _first(segment, "Status", "status", "Color", "color")
    value = _first(segment, "Value", "value")
    if status is None and value is None:
        return False
    if isinstance(status, str) and status.strip().casefold() in {"", "0", "none", "null", "notstarted", "pending"}:
        return False
    if status in (0, False):
        return False
    return value is not None or status is not None


def _driver_lap(line: Mapping[str, Any], driver: str, previous: int | None) -> int | None:
    raw = _first(line, "LapNumber", "lapNumber", "Lap", "lap", "CurrentLap", "currentLap", "NumberOfLaps")
    if isinstance(raw, Mapping):
        raw = _first(raw, "Value", "value")
    try:
        lap = int(raw)
        return lap if lap > 0 else previous
    except (TypeError, ValueError):
        return previous


def _records(raw: Sequence[Any]) -> list[tuple[float, str, Mapping[str, Any]]]:
    result: list[tuple[float, str, Mapping[str, Any]]] = []
    current_lap: dict[str, int | None] = {}
    for record in raw:
        timestamp: Any = None
        payload: Any = record
        if isinstance(record, (list, tuple)) and len(record) >= 2:
            timestamp, payload = record[0], record[1]
        if not isinstance(payload, Mapping):
            continue
        event_time = _time_seconds(_first(payload, "SessionTime", "sessionTime", "Time", "time"))
        if event_time is None:
            event_time = _time_seconds(timestamp)
        lines = payload.get("Lines", payload.get("lines"))
        if lines is None and _first(payload, "DriverNumber", "driverNumber") is not None:
            lines = {str(_first(payload, "DriverNumber", "driverNumber")): payload}
        if lines is None:
            lines = payload
        if not isinstance(lines, Mapping):
            continue
        for driver_key, line in lines.items():
            if not isinstance(line, Mapping):
                continue
            line_time = event_time
            if line_time is None:
                line_time = _time_seconds(_first(line, "SessionTime", "sessionTime", "Time", "time"))
            if line_time is None:
                continue
            driver = str(_first(line, "DriverNumber", "driverNumber") or driver_key)
            # A flat event shape is useful for fixtures and for archive
            # mirrors which flatten the current sector update.
            if not isinstance(_first(line, "Sectors", "sectors"), Mapping):
                sector = _first(line, "SectorIndex", "sectorIndex", "Sector", "sector")
                segment = _first(line, "SegmentIndex", "segmentIndex", "Segment", "segment")
                if sector is not None and segment is not None:
                    line = dict(line)
                    line["Sectors"] = {str(sector): {"Segments": {str(segment): line}}}
            current_lap[driver] = _driver_lap(line, driver, current_lap.get(driver))
            result.append((line_time, driver, line))
    return result


def _integer_value(value: Any) -> int | None:
    if isinstance(value, Mapping):
        value = _first(value, "Value", "value")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _reported_lap_time(line: Mapping[str, Any]) -> float | None:
    value = _first(line, "LastLapTime", "lastLapTime", "LapTime", "lapTime")
    if isinstance(value, Mapping):
        value = _first(value, "Value", "value")
    seconds = _time_seconds(value)
    if seconds is None or not math.isfinite(seconds) or seconds <= 0:
        return None
    return seconds


def _updated_timestamp(value: Mapping[str, Any], fallback: float) -> float | None:
    """Return a field's update time, falling back to its stream timestamp."""
    for key in (
        "Updated", "updated", "UpdatedAt", "updatedAt", "Timestamp", "timestamp",
        "SessionTime", "sessionTime", "Time", "time",
    ):
        candidate = value.get(key)
        if isinstance(candidate, Mapping):
            candidate = _first(candidate, "Value", "value")
        timestamp = _time_seconds(candidate)
        if timestamp is not None and math.isfinite(timestamp):
            return timestamp
    return fallback if math.isfinite(fallback) else None


def _sector_completion_timestamp(
    line: Mapping[str, Any], sector_index: str, record_timestamp: float
) -> float | None:
    """Extract an explicit TimingData sector completion update, if present.

    TimingData has used both a sector object under ``Sectors`` and
    ``SectorNTime`` fields over time.  A completed/evaluated sector value is
    deliberately distinct from the mini-segment objects below it: the latter
    are only used as the fallback boundary.
    """
    candidates: list[Mapping[str, Any]] = []
    sectors = _first(line, "Sectors", "sectors")
    if isinstance(sectors, Mapping):
        sector = sectors.get(sector_index)
        if sector is None:
            sector = sectors.get(str(sector_index))
        if sector is None:
            try:
                sector = sectors.get(int(sector_index))
            except (TypeError, ValueError):
                pass
        if isinstance(sector, Mapping):
            candidates.append(sector)

    try:
        number = int(sector_index) + 1
    except (TypeError, ValueError):
        number = None
    if number is not None:
        for name in (f"Sector{number}Time", f"Sector{number}"):
            field = line.get(name)
            if isinstance(field, Mapping):
                candidates.append(field)
            elif field is not None:
                candidates.append({"Value": field})
        session_field = line.get(f"Sector{number}SessionTime")
        if isinstance(session_field, Mapping):
            candidates.append(session_field)
        elif session_field is not None:
            candidates.append({"Value": session_field, "Updated": session_field})

    for candidate in candidates:
        status = _first(candidate, "Status", "status", "Color", "color")
        completed = _first(
            candidate, "Completed", "completed", "Complete", "complete",
            "IsComplete", "isComplete", "Finished", "finished",
        )
        value = _first(candidate, "Value", "value", "SectorTime", "sectorTime")
        if isinstance(value, Mapping):
            status = status if status is not None else _first(value, "Status", "status", "Color", "color")
            completed = completed if completed is not None else _first(
                value, "Completed", "completed", "Complete", "complete",
                "IsComplete", "isComplete", "Finished", "finished",
            )
            value = _first(value, "Value", "value", "SectorTime", "sectorTime")
        # A status-bearing value is the common archive shape.  Explicit
        # boolean completion fields cover mirrors which omit Status.
        status_done = status is not None and _evaluated({"Status": status, "Value": value})
        boolean_done = completed is True or str(completed).strip().casefold() in {
            "1", "true", "yes", "complete", "completed", "finished",
        }
        has_value = value is not None and not isinstance(value, Mapping)
        parsed_value = _time_seconds(value) if has_value else None
        if not (
            status_done
            or boolean_done
            or (status is None and parsed_value is not None and parsed_value > 0)
        ):
            continue
        return _updated_timestamp(candidate, record_timestamp)
    return None


def build_live_timing_lap_windows(
    timing_records: Sequence[Any],
    *,
    relative_tolerance: float = 0.05,
    absolute_tolerance: float = 2.0,
) -> tuple[list[LiveTimingLapWindow], dict[str, int]]:
    """Build and validate lap windows solely on the Live Timing clock.

    Consecutive ``NumberOfLaps`` transitions delimit a lap.  Their elapsed
    time must agree with ``LastLapTime`` within the supplied tolerance.  For
    the first observable lap, where no previous transition exists, the
    reported lap time is used to establish its start.
    """
    grouped: dict[str, list[tuple[float, Mapping[str, Any]]]] = {}
    for timestamp, driver, line in _records(timing_records):
        grouped.setdefault(driver, []).append((timestamp, line))

    diagnostics = {
        "lap_completions": 0,
        "consistent_laps": 0,
        "duration_mismatch": 0,
        "missing_lap_time": 0,
    }
    windows: list[LiveTimingLapWindow] = []
    for driver, entries in grouped.items():
        current_count: int | None = None
        completions: dict[int, float] = {}
        lap_times: dict[int, float] = {}
        for timestamp, line in sorted(entries, key=lambda item: item[0]):
            count = _integer_value(_first(line, "NumberOfLaps", "numberOfLaps"))
            if count is not None:
                if current_count is None or count > current_count:
                    current_count = count
                    if count > 0:
                        completions.setdefault(count, timestamp)
                elif count == current_count:
                    current_count = count
            reported = _reported_lap_time(line)
            if reported is not None and current_count is not None and current_count > 0:
                lap_times.setdefault(current_count, reported)

        for count, timestamp in sorted(completions.items()):
            diagnostics["lap_completions"] += 1
            reported = lap_times.get(count)
            if reported is None:
                diagnostics["missing_lap_time"] += 1
                continue
            previous_completion = completions.get(count - 1)
            if previous_completion is None:
                start = timestamp - reported
            else:
                start = previous_completion
                observed = timestamp - start
                tolerance = max(absolute_tolerance, reported * relative_tolerance)
                if abs(observed - reported) > tolerance:
                    diagnostics["duration_mismatch"] += 1
                    continue
            if timestamp > start:
                windows.append(LiveTimingLapWindow(driver, count, start, timestamp, reported))
                diagnostics["consistent_laps"] += 1
    return windows, diagnostics


def _window_for(
    windows: Mapping[str, Sequence[LiveTimingLapWindow]],
    driver: str,
    timestamp: float,
) -> LiveTimingLapWindow | None:
    for window in windows.get(driver, ()):
        # Archive messages can arrive a few milliseconds around the boundary.
        if window.start - 0.05 <= timestamp <= window.end + 0.05:
            return window
    return None


def _lookup_distance(
    lookup: Any,
    driver: str,
    lap: int,
    timestamp: float,
    record: Mapping[str, Any],
    *,
    lap_percent: float | None = None,
    sector_index: str | None = None,
    sector_percent: float | None = None,
) -> float | None:
    entry: Any = None
    if isinstance(lookup, Mapping):
        entry = lookup.get((driver, lap))
        if entry is None:
            entry = lookup.get((str(driver), int(lap)))

    direct = _first(record, "Distance", "distance")
    if direct is not None:
        try:
            result = float(direct)
        except (TypeError, ValueError):
            result = None
        if result is not None and math.isfinite(result):
            if sector_percent is not None and sector_index is not None and isinstance(entry, Mapping):
                ranges = entry.get("SectorDistanceRange", entry.get("sector_distance_range"))
                bounds = ranges.get(str(sector_index)) if isinstance(ranges, Mapping) else None
                if isinstance(bounds, Sequence) and len(bounds) >= 2:
                    try:
                        low, high = float(bounds[0]), float(bounds[1])
                    except (TypeError, ValueError):
                        return None
                    if not math.isfinite(low) or not math.isfinite(high) or high < low:
                        return None
                    result = float(np.clip(result, low, high))
            return result
    if lookup is None:
        return None
    if callable(lookup):
        value = lookup(
            driver,
            lap,
            sector_percent if sector_percent is not None else (
                lap_percent if lap_percent is not None else timestamp
            ),
        )
    elif isinstance(lookup, Mapping):
        value = entry
        if callable(value):
            value = value(
                sector_percent if sector_percent is not None else (
                    lap_percent if lap_percent is not None else timestamp
                )
            )
        elif isinstance(value, Mapping):
            if sector_percent is not None and sector_index is not None:
                sector_times = value.get("SectorTimePercent", value.get("sector_time_percent"))
                times = sector_times.get(str(sector_index)) if isinstance(sector_times, Mapping) else None
                # A sector-local key must never silently fall back to lap
                # percent: that would let S1 pace move an S2/S3 boundary.
                if times is None:
                    return None
            elif lap_percent is not None:
                times = value.get("LapTimePercent", value.get("lap_time_percent"))
            else:
                times = value.get("SessionTime", value.get("time"))
            distances = value.get("Distance", value.get("distance"))
            if times is not None and distances is not None:
                target = (
                    sector_percent if sector_percent is not None
                    else lap_percent if lap_percent is not None
                    else timestamp
                )
                try:
                    points = [float(item) for item in times] if (
                        lap_percent is not None or sector_percent is not None
                    ) else [_time_seconds(item) for item in times]
                    values = [float(item) for item in distances]
                except (TypeError, ValueError):
                    return None
                if any(item is None or not math.isfinite(item) for item in points + values):
                    return None
                if len(points) != len(values) or len(points) < 2:
                    return None
                if any(current <= previous for previous, current in zip(points, points[1:])):
                    return None
                if any(current < previous for previous, current in zip(values, values[1:])):
                    return None
                if sector_percent is not None and sector_index is not None:
                    target = float(np.clip(target, 0.0, 100.0))
                    ranges = value.get("SectorDistanceRange", value.get("sector_distance_range"))
                    bounds = ranges.get(str(sector_index)) if isinstance(ranges, Mapping) else None
                    if isinstance(bounds, Sequence) and len(bounds) >= 2:
                        try:
                            low, high = float(bounds[0]), float(bounds[1])
                        except (TypeError, ValueError):
                            return None
                    else:
                        low, high = float(np.interp(0.0, points, values)), float(np.interp(100.0, points, values))
                    if not math.isfinite(low) or not math.isfinite(high) or high < low:
                        return None
                    value = float(np.clip(np.interp(target, points, values), low, high))
                else:
                    value = np.interp(target, points, values)
            else:
                return None
    else:
        value = None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def estimate_separator_distances(
    timing_records: Sequence[Any],
    distance_lookup: Any = None,
    *,
    track_length: float | None = None,
    min_samples: int = 3,
    affected_intervals: Iterable[tuple[float, float]] = (),
    diagnostics: dict[str, int] | None = None,
    structured_boundaries: list[SeparatorBoundary] | None = None,
) -> list[float]:
    """Estimate boundaries using the median distance per sector and segment.

    A segment contributes only on its first transition from unevaluated to
    evaluated.  A boundary is retained when it has observations from at least
    ``min_samples`` driver/lap samples, or from that many distinct drivers.
    """
    transition_events: dict[
        tuple[str, int, str, str],
        tuple[float, str, int, Mapping[str, Any], float | None],
    ] = {}
    states: dict[tuple[str, int, str, str], bool] = {}
    order: list[tuple[str, str]] = []
    laps_by_driver: dict[str, int | None] = {}
    intervals = list(affected_intervals)
    live_windows, lap_diagnostics = build_live_timing_lap_windows(timing_records)
    windows_by_driver: dict[str, list[LiveTimingLapWindow]] = {}
    for window in live_windows:
        windows_by_driver.setdefault(window.driver, []).append(window)
    normalized = bool(live_windows)
    lap_progress: dict[tuple[str, int], list[tuple[float, tuple[str, str]]]] = {}
    sector_states: dict[tuple[str, int, str], bool] = {}
    explicit_sector_ends: dict[tuple[str, int, int], float] = {}

    for timestamp, driver, line in sorted(_records(timing_records), key=lambda item: item[0]):
        lap_percent: float | None = None
        window = _window_for(windows_by_driver, driver, timestamp) if normalized else None
        if window is not None:
            lap = window.lap
            lap_percent = window.percent_at(timestamp)
            if lap_percent < 0 or lap_percent > 100:
                continue
        elif normalized:
            continue
        else:
            lap = _driver_lap(line, driver, laps_by_driver.get(driver))
        laps_by_driver[driver] = lap
        if lap is None or any(start <= timestamp <= end for start, end in intervals):
            continue
        sectors = _first(line, "Sectors", "sectors")
        sector_items: list[tuple[str, Any]] = []
        if isinstance(sectors, Mapping):
            sector_items.extend((str(index), sector) for index, sector in sectors.items())
        # Some archive mirrors expose the completed sector time as a line
        # field and omit the Sectors object in that update.
        for sector_number in range(3):
            if any(name in line for name in (
                f"Sector{sector_number + 1}Time",
                f"Sector{sector_number + 1}",
                f"Sector{sector_number + 1}SessionTime",
            )):
                if str(sector_number) not in {index for index, _ in sector_items}:
                    sector_items.append((str(sector_number), None))
        for sector_index, sector in sector_items:
            explicit_timestamp = _sector_completion_timestamp(line, sector_index, timestamp)
            try:
                sector_number = int(sector_index)
            except (TypeError, ValueError):
                sector_number = None
            if explicit_timestamp is not None and sector_number is not None:
                state_key = (driver, lap, sector_index)
                if not sector_states.get(state_key, False):
                    explicit_sector_ends[(driver, lap, sector_number)] = explicit_timestamp
                sector_states[state_key] = True
            elif sector_number is not None:
                sector_states.setdefault((driver, lap, sector_index), False)
            if not isinstance(sector, Mapping):
                continue
            segments = _first(sector, "Segments", "segments")
            if not isinstance(segments, Mapping):
                continue
            for segment_index, segment in segments.items():
                key = (driver, lap, str(sector_index), str(segment_index))
                now = _evaluated(segment)
                previous = states.get(key)
                states[key] = previous or now
                # Require an observed unevaluated state.  Full snapshots that
                # are already coloured are not segment-completion events.
                if not now or previous is not False:
                    continue
                pair = (str(sector_index), str(segment_index))
                if pair not in order:
                    order.append(pair)
                if lap_percent is not None:
                    lap_progress.setdefault((driver, lap), []).append((lap_percent, pair))
                transition_events[key] = (timestamp, driver, lap, segment, lap_percent)

    def logical_pair(pair: tuple[str, str]) -> tuple[int, int]:
        try:
            return int(pair[0]), int(pair[1])
        except ValueError:
            return 0, 0

    invalid_laps: set[tuple[str, int]] = set()
    for driver_lap, progress in lap_progress.items():
        logical = [logical_pair(pair) for _, pair in progress]
        percentages = [percent for percent, _ in progress]
        if any(current <= previous for previous, current in zip(logical, logical[1:])):
            invalid_laps.add(driver_lap)
        elif any(current <= previous for previous, current in zip(percentages, percentages[1:])):
            invalid_laps.add(driver_lap)
    if invalid_laps:
        transition_events = {
            key: value for key, value in transition_events.items()
            if (key[0], key[1]) not in invalid_laps
        }

    # Live Timing and telemetry clocks are unrelated.  Map each mini-sector
    # within its own sector so pace differences in S1 do not shift every
    # boundary in S2 and S3.  An explicit sector completion is authoritative;
    # only a sector without one uses its final mini-segment transition.
    fallback_sector_ends: dict[tuple[str, int, int], float] = {}
    window_map = {(window.driver, window.lap): window for window in live_windows}
    for (driver, lap, sector, _), event in transition_events.items():
        try:
            sector_number = int(sector)
        except ValueError:
            continue
        key = (driver, lap, sector_number)
        fallback_sector_ends[key] = max(fallback_sector_ends.get(key, -math.inf), event[0])
    explicit_sector_ends = {
        key: timestamp for key, timestamp in explicit_sector_ends.items()
        if (key[0], key[1]) not in invalid_laps
    }
    sector_ends = dict(fallback_sector_ends)
    sector_ends.update(explicit_sector_ends)

    transitions: dict[tuple[str, int, str, str], tuple[float, str, int, Mapping[str, Any]]] = {}
    for key, (timestamp, driver, lap, segment, lap_percent) in transition_events.items():
        sector_percent: float | None = None
        sector_index = key[2]
        window = window_map.get((driver, lap))
        if window is not None:
            try:
                sector_number = int(sector_index)
            except ValueError:
                continue
            start = window.start if sector_number == 0 else sector_ends.get(
                (driver, lap, sector_number - 1)
            )
            end = sector_ends.get((driver, lap, sector_number))
            if start is None or end is None or end <= start:
                continue
            sector_percent = (timestamp - start) / (end - start) * 100.0
            if not 0 <= sector_percent <= 100:
                continue
        if normalized and sector_percent is None:
            # Once a valid Live Timing lap is available, a sector transition
            # without sector-local coordinates must not fall back to the
            # whole-lap percentage.
            continue
        distance = _lookup_distance(
            distance_lookup,
            driver,
            lap,
            timestamp,
            segment,
            lap_percent=lap_percent,
            sector_index=sector_index,
            sector_percent=sector_percent,
        )
        if distance is not None:
            transitions[key] = (distance, driver, lap, segment)

    if diagnostics is not None:
        diagnostics.update(lap_diagnostics)
        diagnostics["normalized_laps"] = len(live_windows)
        diagnostics["invalid_segment_sequence"] = len(invalid_laps)
        diagnostics["explicit_sector_completions"] = len(explicit_sector_ends)
        diagnostics["fallback_sector_completions"] = len(fallback_sector_ends)
        diagnostics["boundary_samples"] = len(transitions)

    values: list[float] = []
    for pair in order:
        samples = [entry for (driver, lap, sector, segment), entry in transitions.items() if (sector, segment) == pair]
        if len(samples) < min_samples:
            continue
        if len({entry[1] for entry in samples}) < min_samples and len({(entry[1], entry[2]) for entry in samples}) < min_samples:
            continue
        median = float(np.median([entry[0] for entry in samples]))
        if not math.isfinite(median) or median <= 0 or (track_length is not None and median >= track_length):
            continue
        if values and median <= values[-1] + 0.1:
            # Duplicate boundaries and reverse ordering are not useful for
            # segment tables.  Keep the first valid stream-order boundary.
            continue
        distance = round(median, 1)
        values.append(distance)
        if structured_boundaries is not None:
            try:
                structured_boundaries.append(
                    SeparatorBoundary(distance, int(pair[0]), int(pair[1]))
                )
            except (TypeError, ValueError):
                # Non-numeric archive keys remain usable through the legacy
                # distance output, but cannot be persisted as structured IDs.
                pass
    if len(values) == 0:
        raise SeparatorEstimationError("not enough valid sector/segment samples")
    return values


def estimate_separator_boundaries(
    timing_records: Sequence[Any],
    distance_lookup: Any = None,
    *,
    track_length: float | None = None,
    min_samples: int = 3,
    affected_intervals: Iterable[tuple[float, float]] = (),
    diagnostics: dict[str, int] | None = None,
) -> list[SeparatorBoundary]:
    """Estimate boundaries while retaining their sector/segment identity."""
    boundaries: list[SeparatorBoundary] = []
    estimate_separator_distances(
        timing_records,
        distance_lookup,
        track_length=track_length,
        min_samples=min_samples,
        affected_intervals=affected_intervals,
        diagnostics=diagnostics,
        structured_boundaries=boundaries,
    )
    return boundaries


def _valid_lap(lap: Any) -> bool:
    def get(name: str, default: Any = None) -> Any:
        if isinstance(lap, Mapping):
            return lap.get(name, default)
        return getattr(lap, name, default)

    if get("IsAccurate", True) is False or get("Deleted", False) is True:
        return False
    for key in ("PitInTime", "PitOutTime"):
        value = get(key)
        if value is not None and not pd.isna(value):
            return False
    return True


def _lap_value(lap: Any, name: str) -> Any:
    if isinstance(lap, Mapping):
        return lap.get(name)
    return getattr(lap, name, None)


def build_distance_lookup(session: Any) -> tuple[dict[tuple[str, int], dict[str, list[float]]], float | None]:
    """Build an interpolating lookup from FastF1 laps without guessing gaps."""
    laps = getattr(session, "laps", None)
    if laps is None:
        return {}, None
    lookup: dict[tuple[str, int], dict[str, list[float]]] = {}
    max_distance = 0.0
    try:
        count = len(laps)
    except TypeError:
        return {}, None
    for index in range(count):
        try:
            lap = laps.iloc[index]
        except (AttributeError, IndexError, KeyError):
            continue
        if not _valid_lap(lap):
            continue
        driver = str(_lap_value(lap, "DriverNumber") or _lap_value(lap, "Driver") or "")
        lap_number = _lap_value(lap, "LapNumber")
        try:
            lap_number = int(lap_number)
        except (TypeError, ValueError):
            continue
        try:
            telemetry = lap.get_telemetry().add_distance()
        except Exception:
            continue
        if telemetry is None or "Distance" not in telemetry:
            continue
        if "SessionTime" in telemetry:
            times = [_time_seconds(value) for value in telemetry["SessionTime"]]
        elif "Time" in telemetry:
            end = _time_seconds(_lap_value(lap, "Time"))
            duration = _time_seconds(_lap_value(lap, "LapTime"))
            start = (end - duration) if end is not None and duration is not None else None
            if start is None:
                continue
            relative_times = [_time_seconds(value) for value in telemetry["Time"]]
            if any(value is None for value in relative_times):
                continue
            times = [start + value for value in relative_times]
        else:
            continue
        distances = [float(value) if pd.notna(value) else math.nan for value in telemetry["Distance"]]
        pairs = [(time, distance) for time, distance in zip(times, distances) if time is not None and math.isfinite(distance)]
        if len(pairs) < 2:
            continue
        pairs.sort()
        if any(current[0] <= previous[0] for previous, current in zip(pairs, pairs[1:])):
            continue
        if any(current[1] < previous[1] for previous, current in zip(pairs, pairs[1:])):
            continue
        span = pairs[-1][0] - pairs[0][0]
        if span <= 0:
            continue
        lookup[(driver, lap_number)] = {
            "SessionTime": [pair[0] for pair in pairs],
            "LapTimePercent": [
                (pair[0] - pairs[0][0]) / span * 100.0 for pair in pairs
            ],
            "Distance": [pair[1] for pair in pairs],
        }
        sector_times = [
            _time_seconds(_lap_value(lap, name))
            for name in ("Sector1Time", "Sector2Time", "Sector3Time")
        ]
        sector_total = sum(value for value in sector_times if value is not None)
        lap_duration = _time_seconds(_lap_value(lap, "LapTime"))
        duration_tolerance = max(2.0, span * 0.05)
        sector_times_consistent = (
            all(value is not None and math.isfinite(value) and value > 0 for value in sector_times)
            and abs(sector_total - span) <= duration_tolerance
            and (lap_duration is None or abs(lap_duration - sector_total) <= duration_tolerance)
        )
        if sector_times_consistent:
            elapsed = [pair[0] - pairs[0][0] for pair in pairs]
            starts = [0.0, sector_times[0], sector_times[0] + sector_times[1]]
            ends = [start + duration for start, duration in zip(starts, sector_times)]
            if not any(start < 0 or end > span for start, end in zip(starts, ends)):
                lookup[(driver, lap_number)]["SectorTimePercent"] = {
                    str(index): [
                        (value - starts[index]) / sector_times[index] * 100.0
                        for value in elapsed
                    ]
                    for index in range(3)
                }
                lookup[(driver, lap_number)]["SectorDistanceRange"] = {
                    str(index): [
                        float(np.interp(starts[index], elapsed, [pair[1] for pair in pairs])),
                        float(np.interp(ends[index], elapsed, [pair[1] for pair in pairs])),
                    ]
                    for index in range(3)
                }
        max_distance = max(max_distance, pairs[-1][1])
    return lookup, max_distance or None


def affected_intervals_from_session(session: Any) -> list[tuple[float, float]]:
    """Return non-green track-status intervals as session-time ranges."""
    try:
        status_data = getattr(session, "track_status", None)
    except Exception:
        status_data = None
    if status_data is None:
        return []
    try:
        rows = status_data.sort_values("Time")
    except (AttributeError, KeyError):
        rows = status_data
    active: float | None = None
    intervals: list[tuple[float, float]] = []
    try:
        iterator = rows.iterrows()
    except AttributeError:
        return intervals
    for _, row in iterator:
        if isinstance(row, Mapping):
            time_value = row.get("Time", row.get("SessionTime"))
            status = row.get("Status")
        else:
            time_value = getattr(row, "Time", getattr(row, "SessionTime", None))
            status = getattr(row, "Status", None)
        timestamp = _time_seconds(time_value)
        if timestamp is None:
            continue
        clear = str(status).strip().casefold() in {"1", "green", "allclear", "all clear"}
        if not clear and active is None:
            active = timestamp
        elif clear and active is not None:
            if timestamp > active:
                intervals.append((active, timestamp))
            active = None
    if active is not None:
        intervals.append((active, float("inf")))
    return intervals


def _separator_maps(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    maps = []
    for key in (
        "separators", "Separators", "auto_separators", "AutoSeparators",
        # Accept a scoped object under the singular legacy spelling too.
        "separator", "Separator",
    ):
        value = config.get(key)
        if isinstance(value, Mapping):
            maps.append(value)
    return maps


def _scoped_separator_value(config: Mapping[str, Any], year: int, location: str) -> Any:
    locations = (location, location.casefold())
    for separator_map in _separator_maps(config):
        year_map = separator_map.get(str(year), separator_map.get(year))
        if not isinstance(year_map, Mapping):
            continue
        for key in locations:
            if key in year_map:
                return year_map[key]
        for key, value in year_map.items():
            if str(key).casefold() == location.casefold():
                return value
    return None


def _coerce_separator_boundary(value: Any) -> SeparatorBoundary | None:
    if isinstance(value, SeparatorBoundary):
        candidate = value
    elif isinstance(value, Mapping):
        distance = value.get("distance", value.get("Distance"))
        sector = value.get("sector", value.get("sector_index", value.get("Sector")))
        segment = value.get("segment", value.get("segment_index", value.get("Segment")))
        try:
            candidate = SeparatorBoundary(float(distance), int(sector), int(segment))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if not math.isfinite(candidate.distance) or candidate.distance <= 0:
        return None
    return candidate


def _structured_separator_boundaries(value: Any) -> list[SeparatorBoundary]:
    if isinstance(value, Mapping):
        value = value.get("boundaries", value.get("Boundaries", []))
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result = []
    for item in value:
        boundary = _coerce_separator_boundary(item)
        if boundary is not None:
            result.append(boundary)
    return result


def _scoped_boundaries(config: Mapping[str, Any], year: int, location: str) -> list[SeparatorBoundary]:
    return _structured_separator_boundaries(_scoped_separator_value(config, year, location))


def _scoped_separator(config: Mapping[str, Any], year: int, location: str) -> list[float] | None:
    value = _scoped_separator_value(config, year, location)
    structured = _structured_separator_boundaries(value)
    if structured:
        return [boundary.distance for boundary in structured]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            return None
    return None


def _legacy_separator(config: Mapping[str, Any]) -> list[float]:
    value = config.get("separator", config.get("Separator", []))
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return []


def save_scoped_separator(
    config_path: str | Path,
    year: int,
    location: str,
    separators: Sequence[Any],
    boundaries: Sequence[SeparatorBoundary] | None = None,
) -> None:
    """Atomically add a year/location separator map while retaining settings."""
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    maps = config.get("separators")
    if not isinstance(maps, dict):
        maps = {}
        config["separators"] = maps
    year_map = maps.setdefault(str(int(year)), {})
    if not isinstance(year_map, dict):
        year_map = {}
        maps[str(int(year))] = year_map
    structured = []
    for item in (boundaries or _structured_separator_boundaries(separators)):
        boundary = _coerce_separator_boundary(item)
        if boundary is not None:
            structured.append(boundary)
    if structured:
        year_map[str(location)] = {
            "schema_version": SEPARATOR_SCHEMA_VERSION,
            "boundaries": [boundary.to_dict() for boundary in structured],
        }
    else:
        year_map[str(location)] = [round(float(value), 1) for value in separators]
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump(config, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            import os

            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def resolve_separators(
    session: Any,
    config_path: str | Path,
    *,
    refresh: bool = False,
    client: StaticArchiveClient | None = None,
    log: Any = None,
) -> SeparatorResolution:
    """Select saved boundaries, estimate new ones, or safely fall back."""
    path = Path(config_path)
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        config = {}
    year, location = _year(session), _location(session)
    saved = _scoped_separator(config, year, location)
    saved_boundaries = _scoped_boundaries(config, year, location)
    legacy = _legacy_separator(config)
    if saved and not refresh:
        return SeparatorResolution(saved, "saved_auto", boundaries=saved_boundaries)

    try:
        archive = client or StaticArchiveClient(cache_dir=Path("cache") / "livetiming")
        timing = archive.timing_data(session)
        distance_lookup, track_length = build_distance_lookup(session)
        validation: dict[str, int] = {}
        boundaries = estimate_separator_boundaries(
            timing,
            distance_lookup,
            track_length=track_length,
            affected_intervals=affected_intervals_from_session(session),
            diagnostics=validation,
        )
        separators = [boundary.distance for boundary in boundaries]
        if log is not None:
            try:
                log.info("live timing mini-segment validation", **validation)
            except TypeError:
                log.info(f"live timing mini-segment validation: {validation}")
    except Exception as error:  # archive is optional; reports must remain usable
        if log is not None:
            try:
                log.warning("automatic separator estimation failed; using fallback", error=str(error))
            except TypeError:
                log.warning(f"automatic separator estimation failed; using fallback: {error}")
        if saved:
            return SeparatorResolution(saved, "saved_auto", boundaries=saved_boundaries)
        return SeparatorResolution(legacy, "fallback_corners" if not legacy else "configured_fallback")

    return SeparatorResolution(separators, "estimated", pending_save=True, boundaries=boundaries)


def persist_resolution(
    resolution: SeparatorResolution,
    config_path: str | Path,
    session: Any,
    *,
    refresh: bool = False,
) -> None:
    if not resolution.pending_save:
        return
    save_scoped_separator(
        config_path,
        _year(session),
        _location(session),
        resolution.separators,
        resolution.boundaries,
    )
