"""Telemetry helpers that preserve FastF1's merge behavior."""

from __future__ import annotations

from typing import Any, Callable

from fastf1.core import Telemetry

from opentelemetry import trace

tracer = trace.get_tracer(__name__)


def _record_row_count(telemetry: Any) -> None:
    try:
        trace.get_current_span().set_attribute("f1.telemetry.rows", len(telemetry))
    except (TypeError, AttributeError):
        pass


@tracer.start_as_current_span("lap_telemetry_without_driver_ahead")
def lap_telemetry_without_driver_ahead(lap: Any, *, add_distance: bool = False) -> Any:
    """Build normal merged lap telemetry without FastF1's traffic scan.

    The timestamp-only merge preserves the time base used by FastF1's normal
    ``get_telemetry`` implementation. Distance is opt-in because some callers
    rely on FastF1's raw merged distance origin.
    """
    span = trace.get_current_span()
    span.set_attribute("f1.telemetry.add_distance", add_distance)
    for name in ("DriverNumber", "LapNumber"):
        value = getattr(lap, name, None)
        if value is not None:
            span.set_attribute(f"f1.lap.{name.lower()}", str(value))

    get_car_data: Callable[..., Telemetry] | None = getattr(lap, "get_car_data", None)
    get_pos_data: Callable[..., Telemetry] | None = getattr(lap, "get_pos_data", None)
    if get_car_data is None or get_pos_data is None or not callable(get_car_data) or not callable(get_pos_data):
        get_telemetry: Callable[[], Telemetry] | None = getattr(lap, "get_telemetry", None)
        span.set_attribute("f1.telemetry.fallback", True)
        telemetry = get_telemetry() if get_telemetry is not None and callable(get_telemetry) else lap.telemetry
        if add_distance:
            telemetry = telemetry.add_distance()
        _record_row_count(telemetry)
        return telemetry

    pos_data = get_pos_data(pad=1, pad_side="both")
    car_data = get_car_data(pad=1, pad_side="both")
    timestamps = car_data.iloc[1:-1].loc[:, ("Date", "Time", "SessionTime")]
    car_data = car_data.add_distance().add_relative_distance()
    car_data = car_data.merge_channels(timestamps)
    telemetry = pos_data.merge_channels(car_data).slice_by_lap(lap, interpolate_edges=True)
    if add_distance:
        telemetry = telemetry.add_distance()
    _record_row_count(telemetry)
    return telemetry
