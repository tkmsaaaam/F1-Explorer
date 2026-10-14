"""Session lap and qualifying-attack estimates for the season report."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from html import escape
from typing import Any

import pandas


ATTACK_LAP_RATIO = 1.02
PRACTICE_LONG_RUN_RATIO = 1.07
PRACTICE_LONG_RUN_LAPS = 4
SESSION_ROWS = ("FP1", "FP2", "FP3", "SQ", "S", "Q", "R")
ATTACK_ROWS = ("FP1", "FP2", "FP3", "SQ1", "SQ2", "SQ3", "Q1", "Q2", "Q3")


@dataclass(slots=True)
class Driver:
    key: str
    name: str
    abbreviation: str
    number: str
    team: str = ""


@dataclass(slots=True)
class Metric:
    value: int | None = None
    status: str = "not-held"
    details: list[str] = field(default_factory=list)
    provisional: bool = False
    incomplete: bool = False


@dataclass(slots=True)
class DriverMetrics:
    laps: dict[str, Metric] = field(default_factory=dict)
    attacks: dict[str, Metric] = field(default_factory=dict)


@dataclass(slots=True)
class WeekendMetrics:
    name: str
    round_number: int
    drivers: dict[str, DriverMetrics] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)


def session_code(name: str) -> str | None:
    normalized = name.strip().lower()
    if "practice 1" in normalized or normalized == "fp1":
        return "FP1"
    if "practice 2" in normalized or normalized == "fp2":
        return "FP2"
    if "practice 3" in normalized or normalized == "fp3":
        return "FP3"
    if "shootout" in normalized or "sprint qualifying" in normalized:
        return "SQ"
    if normalized == "sprint":
        return "S"
    if normalized == "qualifying":
        return "Q"
    if normalized == "race":
        return "R"
    return None


def _is_true(value: Any) -> bool:
    return False if value is None or pandas.isna(value) else bool(value)


def _seconds(value: Any) -> float | None:
    if value is None or pandas.isna(value):
        return None
    if hasattr(value, "total_seconds"):
        value = value.total_seconds()
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def count_completed_laps(laps: pandas.DataFrame) -> tuple[int, list[str]]:
    """Count unique lap numbers with a recorded end, excluding generated rows."""
    if laps.empty or "LapNumber" not in laps or "Time" not in laps:
        return 0, []
    ended = laps[laps["Time"].notna()].copy()
    if "FastF1Generated" in ended:
        ended = ended[~ended["FastF1Generated"].fillna(False).astype(bool)]
    numbers = sorted({int(value) for value in ended["LapNumber"].dropna() if float(value).is_integer()})
    missing = [str(number) for number in range(numbers[0], numbers[-1] + 1)
               if number not in numbers] if numbers else []
    return len(numbers), missing


def _identity_text(value: Any) -> str | None:
    if value is None or pandas.isna(value):
        return None
    normalized = " ".join(str(value).strip().casefold().split())
    if normalized in {"", "none", "nan", "null", "<na>", "unknown"}:
        return None
    if any(part in {"none", "nan", "null", "<na>"} for part in normalized.split()):
        return None
    return normalized


def _full_name(driver: Driver) -> str | None:
    name = _identity_text(driver.name)
    if name in {_identity_text(driver.abbreviation), driver.number.casefold()}:
        return None
    return name


def _same_driver(first: Driver, second: Driver) -> bool:
    """Match by complete name when available, otherwise by a real abbreviation."""
    first_name = _full_name(first)
    second_name = _full_name(second)
    if first_name and second_name:
        return first_name == second_name
    first_abbreviation = _identity_text(first.abbreviation)
    second_abbreviation = _identity_text(second.abbreviation)
    return bool(first_abbreviation and second_abbreviation
                and first_abbreviation != first.number.casefold()
                and second_abbreviation != second.number.casefold()
                and first_abbreviation == second_abbreviation)


def _valid_reference(row: Any) -> bool:
    if _is_true(getattr(row, "FastF1Generated", False)):
        return False
    if _is_true(getattr(row, "Deleted", False)):
        # Deleted timed laps are still eligible as reference values only when
        # the timing data says their lap and sectors are accurate.
        pass
    if getattr(row, "IsAccurate", False) is not True and not _is_true(getattr(row, "IsAccurate", False)):
        return False
    if pandas.notna(getattr(row, "PitInTime", pandas.NaT)) or pandas.notna(getattr(row, "PitOutTime", pandas.NaT)):
        return False
    if str(getattr(row, "TrackStatus", "1")) not in {"1", "1.0"}:
        return False
    return all(_seconds(getattr(row, column, None)) is not None
               for column in ("LapTime", "Sector1Time", "Sector2Time", "Sector3Time"))


def _attack_metrics(laps: pandas.DataFrame, code: str, qualifying: bool) -> dict[str, Metric]:
    output: dict[str, Metric] = {}
    if laps.empty:
        return output

    sections: list[tuple[str, pandas.DataFrame]]
    if qualifying:
        try:
            split = laps.attrs.get("session")
            if split is None:
                raise ValueError("session metadata unavailable")
            split_laps = split.laps.split_qualifying_sessions()
            sections = [(f"{code}{index}", part) for index, part in enumerate(split_laps, 1)]
            if len(split_laps) < 3:
                raise ValueError("qualifying split is incomplete")
        except (ValueError, AttributeError, KeyError):
            for index in range(1, 4):
                output[f"{code}{index}"] = Metric(None, "unknown", ["区分データなし"])
            return output
    else:
        sections = [(code, laps)]

    for section_code, section in sections:
        if section is None:
            output[str(section_code)] = Metric(None, "not-held")
            continue
        driver_metrics: dict[str, list[Metric]] = defaultdict(list)
        group_columns = ["DriverNumber"] + (["Compound"] if "Compound" in section else [])
        for group_key, driver_laps in section.groupby(group_columns, dropna=False, sort=False):
            group_key = group_key if isinstance(group_key, tuple) else (group_key,)
            driver_number = str(group_key[0])
            compound = group_key[1] if len(group_key) > 1 else None
            if compound is None or pandas.isna(compound) or not str(compound).strip():
                driver_metrics[driver_number].append(Metric(None, "unknown", ["コンパウンド不明"]))
                continue
            rows = list(driver_laps.sort_values("LapNumber", na_position="last").itertuples(index=False))
            reference_rows = [row for row in rows if _valid_reference(row)]
            if not reference_rows:
                driver_metrics[driver_number].append(Metric(None, "unknown", ["比較基準なし"]))
                continue
            best_lap = min(_seconds(row.LapTime) for row in reference_rows)
            best_s1 = min(_seconds(row.Sector1Time) for row in reference_rows)
            candidates: list[tuple[int, Any, str]] = []
            for row_index, row in enumerate(rows):
                if pandas.notna(getattr(row, "PitOutTime", pandas.NaT)):
                    continue
                lap_time = _seconds(getattr(row, "LapTime", None))
                sector1 = _seconds(getattr(row, "Sector1Time", None))
                if lap_time is not None and lap_time <= best_lap * ATTACK_LAP_RATIO:
                    candidates.append((row_index, row, "ラップ"))
                elif sector1 is not None and sector1 <= best_s1 * ATTACK_LAP_RATIO:
                    candidates.append((row_index, row, "S1"))

            excluded: set[int] = set()
            unknown_laps: list[int] = []
            if not qualifying:
                run: list[int] = []
                previous_number: int | None = None
                for index, row in enumerate(rows):
                    number = getattr(row, "LapNumber", None)
                    number = None if pandas.isna(number) else int(number)
                    lap_time = _seconds(getattr(row, "LapTime", None))
                    in_run = (number is not None and lap_time is not None
                              and lap_time <= best_lap * PRACTICE_LONG_RUN_RATIO
                              and not pandas.notna(getattr(row, "PitInTime", pandas.NaT))
                              and not pandas.notna(getattr(row, "PitOutTime", pandas.NaT))
                              and (previous_number is None or number == previous_number + 1))
                    if in_run:
                        run.append(index)
                    else:
                        if len(run) >= PRACTICE_LONG_RUN_LAPS:
                            excluded.update(run)
                        run = []
                    previous_number = number if in_run else None
                if len(run) >= PRACTICE_LONG_RUN_LAPS:
                    excluded.update(run)

            counted = [(row, reason) for index, row, reason in candidates if index not in excluded]
            unknown_laps = [int(row.LapNumber) for index, row, _ in candidates
                            if index in excluded
                            and not pandas.isna(getattr(row, "LapNumber", pandas.NA))]
            details = [f"Lap {int(row.LapNumber)} ({reason})" for row, reason in counted
                       if not pandas.isna(getattr(row, "LapNumber", pandas.NA))]
            if unknown_laps:
                details.append("FP用途判定不明: " + ", ".join(map(str, unknown_laps)))
            driver_metrics[driver_number].append(Metric(
                len(counted), "available", details, incomplete=bool(unknown_laps)))
        for driver_number, compound_metrics in driver_metrics.items():
            available = [metric for metric in compound_metrics if metric.value is not None]
            incomplete = any(metric.status == "unknown" or metric.incomplete for metric in compound_metrics)
            details = [f"コンパウンド単位: {detail}" for metric in compound_metrics for detail in metric.details]
            output[f"{section_code}:{driver_number}"] = Metric(
                sum(metric.value or 0 for metric in available) if available else None,
                "available" if available else "unknown", details,
                incomplete=incomplete)
    return output


def analyze_session(
    session: Any,
    code: str,
    *,
    provisional: bool = False,
    identity_by_number: dict[str, Driver] | None = None,
    identity_history_by_number: dict[str, list[Driver]] | None = None,
    identity_aliases: dict[str, str] | None = None,
) -> tuple[dict[str, Driver], dict[str, DriverMetrics]]:
    """Build per-driver session counts; caller handles data retrieval failures."""
    laps = session.laps.copy()
    if laps.empty or "DriverNumber" not in laps:
        return {}, {}
    drivers: dict[str, Driver] = {}
    metrics: dict[str, DriverMetrics] = {}
    for number, driver_laps in laps.groupby("DriverNumber", dropna=True, sort=False):
        number = str(number)
        try:
            info = session.get_driver(number)
        except (KeyError, ValueError, TypeError):
            info = {}
        driver_id = info.get("DriverId") if hasattr(info, "get") else None
        abbreviation = str(info.get("Abbreviation", number)) if hasattr(info, "get") else number
        name = str(info.get("FullName", abbreviation)) if hasattr(info, "get") else abbreviation
        team = str(info.get("TeamName", "")) if hasattr(info, "get") else ""
        has_driver_id = driver_id is not None and not pandas.isna(driver_id) and bool(str(driver_id).strip())
        key = str(driver_id) if has_driver_id else f"number:{number}"
        driver = Driver(key, name, abbreviation, number, team)
        history = identity_history_by_number.setdefault(number, []) if identity_history_by_number is not None else []
        previous = next((candidate for candidate in reversed(history) if _same_driver(candidate, driver)), None)
        if previous is None and identity_by_number is not None:
            candidate = identity_by_number.get(number)
            if candidate is not None and _same_driver(candidate, driver):
                previous = candidate
        if previous is not None:
            if has_driver_id:
                matching_history = [candidate for candidate in history if _same_driver(candidate, driver)]
                aliases = matching_history + ([previous] if previous not in matching_history else [])
                if identity_aliases is not None:
                    for candidate in aliases:
                        if candidate.key != key and candidate.key.startswith("number:"):
                            identity_aliases[candidate.key] = key
            else:
                key = previous.key
                driver.key = key
            if _full_name(driver) is None and _full_name(previous):
                driver.name = previous.name
            if (not _identity_text(driver.abbreviation)
                    or driver.abbreviation.casefold() == number.casefold()) and _identity_text(previous.abbreviation):
                driver.abbreviation = previous.abbreviation
        elif not has_driver_id and (history or (identity_by_number is not None and number in identity_by_number)):
            identity_suffix = "|".join((abbreviation, name)).casefold()
            key = f"number:{number}:{identity_suffix}"
            driver.key = key
        drivers[key] = driver
        if identity_by_number is not None:
            identity_by_number[number] = driver
        if identity_history_by_number is not None:
            matching_index = next((index for index, candidate in enumerate(history)
                                   if _same_driver(candidate, driver)), None)
            if matching_index is None:
                history.append(driver)
            else:
                history[matching_index] = driver
        completed, missing = count_completed_laps(driver_laps)
        metrics[key] = DriverMetrics(
            laps={code: Metric(completed, "available", [f"欠番: {', '.join(missing)}"] if missing else [], provisional)},
        )

    if code in {"FP1", "FP2", "FP3", "Q", "SQ"}:
        laps.attrs["session"] = session
        qualifying = code in {"Q", "SQ"}
        attack_values = _attack_metrics(laps, code, qualifying)
        for compound_key, metric in attack_values.items():
            if ":" not in compound_key:
                section = compound_key
                for driver in metrics.values():
                    if section in {"Q1", "Q2", "Q3", "SQ1", "SQ2", "SQ3"}:
                        driver.attacks[section] = metric
                continue
            section, number = compound_key.split(":", 1)
            driver = next((key for key, value in drivers.items() if value.number == number), None)
            if driver is None:
                continue
            if qualifying:
                metrics[driver].attacks[section] = metric
            else:
                metrics[driver].attacks[code] = metric
            metric.provisional = provisional
        if qualifying:
            for driver in metrics.values():
                for index in range(1, 4):
                    section_code = f"{code}{index}"
                    if section_code in attack_values:
                        driver.attacks[section_code] = attack_values[section_code]
                    else:
                        driver.attacks.setdefault(section_code, Metric(None, "not-participant"))
    return drivers, metrics


def apply_driver_aliases(
    drivers: dict[str, Driver],
    weekends: list[WeekendMetrics],
    aliases: dict[str, str],
) -> None:
    """Move fallback-key history to a newly discovered DriverId."""
    for old_key, new_key in aliases.items():
        if old_key == new_key:
            continue
        old_driver = drivers.pop(old_key, None)
        if old_driver is not None:
            old_driver.key = new_key
            drivers.setdefault(new_key, old_driver)
        for weekend in weekends:
            old_metrics = weekend.drivers.pop(old_key, None)
            if old_metrics is None:
                continue
            target = weekend.drivers.setdefault(new_key, DriverMetrics())
            target.laps.update(old_metrics.laps)
            target.attacks.update(old_metrics.attacks)


def _metric_text(metric: Metric | None) -> str:
    if metric is None:
        return "—"
    value = "取得失敗" if metric.status == "failed" else "判定不能" if metric.status == "unknown" else (
        "未実施" if metric.status == "not-held" else "未参加" if metric.status == "not-participant" else
        "—" if metric.value is None else str(metric.value))
    if metric.value is not None and metric.incomplete and metric.status == "available":
        value += "*"
    if metric.provisional and metric.value is not None:
        value += "†"
    if metric.details:
        value += f" <details><summary>詳細</summary>{escape('; '.join(metric.details))}</details>"
    return value


def _table(title: str, rows: tuple[str, ...], drivers: list[Driver], metrics: dict[str, DriverMetrics], kind: str) -> str:
    headings = "".join(f"<th>{escape(driver.abbreviation)}</th>" for driver in drivers)
    body = []
    for row in rows:
        cells = []
        for driver in drivers:
            driver_metrics = metrics.get(driver.key)
            source = {} if driver_metrics is None else (driver_metrics.laps if kind == "laps" else driver_metrics.attacks)
            cells.append(f"<td>{_metric_text(source.get(row))}</td>")
        body.append(f"<tr><th>{escape(row)}</th>{''.join(cells)}</tr>")
    return (f"<h3>{escape(title)}</h3><div class='table-scroll'><table><thead><tr><th>項目</th>{headings}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


def render_report_section(drivers: dict[str, Driver], weekends: list[WeekendMetrics],
                          *, driver_order: list[str] | None = None) -> str:
    """Render self-contained season totals and GP-selectable detail tables."""
    ranks = {key: index for index, key in enumerate(driver_order or [])}
    ordered = sorted(drivers.values(), key=lambda driver: (ranks.get(driver.key, len(ranks)),
                                                         driver.abbreviation, driver.key))
    totals = {key: DriverMetrics(laps={}, attacks={}) for key in drivers}
    for kind, rows in (("laps", SESSION_ROWS), ("attacks", ATTACK_ROWS)):
        target_name = kind
        for key in drivers:
            for row in rows:
                records = []
                for weekend in weekends:
                    metric = getattr(weekend.drivers.get(key, DriverMetrics()), target_name).get(row)
                    if metric is None:
                        lookup = row if row in SESSION_ROWS or row in ATTACK_ROWS else row[:2]
                        state = weekend.sessions.get(lookup, "not-held")
                        if state in {"available", "provisional"}:
                            state = "not-participant"
                        elif state == "planned":
                            state = "not-held"
                        metric = Metric(None, state)
                    records.append((weekend.name, metric))
                getattr(totals[key], target_name)[row] = _aggregate_metrics(records)
        total_row = "合計"
        for key in drivers:
            records = []
            for row in rows:
                records.append((row, getattr(totals[key], target_name)[row]))
            getattr(totals[key], target_name)[total_row] = _aggregate_metrics(records, row_total=True)

    total_laps = _table("終了周回数（記録ベース）— シーズン取得分合計", SESSION_ROWS + ("合計",), ordered, totals, "laps")
    total_attacks = _table("推定アタック試行数 — シーズン取得分合計", ATTACK_ROWS + ("合計",), ordered, totals, "attacks")
    detail_sections = []
    options = []
    for index, weekend in enumerate(weekends):
        options.append(f"<option value='{index}'>{escape(weekend.name)}</option>")
        lap_rows: dict[str, DriverMetrics] = {}
        for driver in ordered:
            source = weekend.drivers.get(driver.key, DriverMetrics())
            target = DriverMetrics(dict(source.laps), dict(source.attacks))
            for code in SESSION_ROWS:
                state = weekend.sessions.get(code, "not-held")
                if state in {"available", "provisional"}:
                    state = "not-participant"
                elif state == "planned":
                    state = "not-held"
                target.laps.setdefault(code, Metric(None, state))
            for code in ATTACK_ROWS:
                session_code_value = code[:2] if code.startswith(("Q", "SQ")) else code
                state = weekend.sessions.get(code, weekend.sessions.get(session_code_value, "not-held"))
                if state in {"available", "provisional"}:
                    state = "not-participant"
                elif state == "planned":
                    state = "not-held"
                target.attacks.setdefault(code, Metric(None, state))
            for target_name, rows in (("laps", SESSION_ROWS), ("attacks", ATTACK_ROWS)):
                records = [(row, getattr(target, target_name)[row]) for row in rows]
                getattr(target, target_name)["合計"] = _aggregate_metrics(records, row_total=True)
            lap_rows[driver.key] = target
        detail_sections.append(
            f"<div class='gp-tables' data-gp='{index}' {'hidden' if index else ''}>"
            + _table("終了周回数（記録ベース）", SESSION_ROWS + ("合計",), ordered, lap_rows, "laps")
            + _table("推定アタック試行数", ATTACK_ROWS + ("合計",), ordered, lap_rows, "attacks") + "</div>")
    selector = ("<label>GPを選択 <select id='mileage-gp'>" + "".join(options) + "</select></label>"
                if options else "<p>対象GPがありません。</p>")
    script = "<script>document.getElementById('mileage-gp')?.addEventListener('change',e=>{document.querySelectorAll('.gp-tables').forEach(x=>x.hidden=x.dataset.gp!==e.target.value)});</script>"
    return ("<section id='season-mileage'><h2>走行周回数・予選想定アタック</h2>"
            "<p>終了周回数は計時上の周回終了記録です。コース1周分の距離を保証しません。"
            "アタックはタイム基準による推定です。5*は一部の項目が未取得または判定不能、†は暫定値を示します。"
            "詳細から根拠を確認できます。</p>" + total_laps + total_attacks + selector
            + "".join(detail_sections) + script + "</section>")


def _aggregate_metrics(records: list[tuple[str, Metric]], *, row_total: bool = False) -> Metric:
    values = [metric.value for _, metric in records if metric.value is not None]
    incomplete = any(metric.status in {"failed", "unknown"} or metric.incomplete for _, metric in records)
    provisional = any(metric.provisional for _, metric in records)
    details = []
    for label, metric in records:
        if metric.details and (metric.incomplete or metric.status in {"failed", "unknown"}):
            details.extend(f"{label}: {detail}" for detail in metric.details)
    if incomplete and not details:
        details.append("一部項目に未取得・判定不能あり")
    if values:
        status = "available"
    elif incomplete:
        status = "unknown"
    elif records and all(metric.status == "not-participant" for _, metric in records):
        status = "not-participant"
    else:
        status = "not-held"
    return Metric(sum(values) if values else None, status, details,
                  provisional, incomplete)

