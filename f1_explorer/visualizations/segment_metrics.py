"""Pure calculations used by the short-run segment tables.

The plotting code deals in cumulative timestamps (one value at each segment
boundary), while a segment table needs one duration per pair of boundaries.
The functions in this module intentionally know nothing about FastF1,
pandas, or Plotly so they can be used and tested with ordinary mappings and
sequences; numpy is the one allowed array helper.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from typing import TypeVar, overload

import numpy as np


Driver = TypeVar("Driver", bound=Hashable)
Numeric = float | int
MaybeNumeric = Numeric | None

__all__ = [
    "segment_durations",
    "rank_segment_durations",
    "deltas_to_reference",
    "interpolate_boundary_times",
    "derive_segment_durations",
    "compute_segment_durations",
    "delta_to_reference",
]


def _is_missing(value: MaybeNumeric) -> bool:
    """Return whether *value* should be treated as an unavailable time.

    ``None`` is the public missing-value representation.  NaN is treated as
    missing as well because it cannot be ordered reliably for ranking and is
    the common numeric representation of a missing sample.
    """

    if value is None:
        return True
    try:
        return math.isnan(value)
    except (TypeError, ValueError):
        return False


def _durations_for_boundaries(
    boundaries: Sequence[MaybeNumeric],
) -> list[MaybeNumeric]:
    """Convert one cumulative-boundary sequence to adjacent durations."""

    return [
        None if start is None or end is None or _is_missing(start) or _is_missing(end) else end - start
        for start, end in zip(boundaries, boundaries[1:])
    ]


@overload
def segment_durations(
    boundary_times: Mapping[Driver, Sequence[MaybeNumeric]],
) -> dict[Driver, list[MaybeNumeric]]:
    ...


@overload
def segment_durations(
    boundary_times: Sequence[MaybeNumeric],
) -> list[MaybeNumeric] | dict[Hashable, list[MaybeNumeric]]:
    ...


def segment_durations(
    boundary_times: Mapping[Driver, Sequence[MaybeNumeric]]
    | Sequence[MaybeNumeric],
) -> dict[Driver, list[MaybeNumeric]] | list[MaybeNumeric]:
    """Derive segment durations from cumulative boundary times.

    For a driver with boundaries ``[b0, b1, b2]`` the result is
    ``[b1 - b0, b2 - b1]``.  A segment is ``None`` whenever either boundary is
    missing; missing values are never converted to zero.  A sequence can be
    passed directly for the one-driver case, or a mapping can be passed to
    calculate all drivers while preserving its key order.
    """

    # Mapping takes precedence even for objects also implementing Sequence.
    # The Sequence overload includes that possible mapping return type.
    if isinstance(boundary_times, Mapping):
        return {
            driver: _durations_for_boundaries(boundaries)
            for driver, boundaries in boundary_times.items()
        }
    return _durations_for_boundaries(boundary_times)


def rank_segment_durations(
    durations_by_driver: Mapping[Driver, Sequence[MaybeNumeric]],
) -> dict[Driver, list[int | None]]:
    """Rank each segment's available durations, fastest first.

    Ranking is one-based competition ranking: values ``[1.0, 1.0, 2.0]``
    receive ranks ``[1, 1, 3]``.  Thus equal values always receive the same
    rank, missing values receive ``None``, and missing values do not consume a
    rank.  Drivers may have sequences of different lengths; absent trailing
    segments simply do not appear for that driver.
    """

    if not durations_by_driver:
        return {}

    max_segments = max(
        (len(durations) for durations in durations_by_driver.values()),
        default=0,
    )
    ranks: dict[Driver, list[int | None]] = {
        driver: [None] * len(durations)
        for driver, durations in durations_by_driver.items()
    }

    for segment_index in range(max_segments):
        valid = [
            durations[segment_index]
            for durations in durations_by_driver.values()
            if segment_index < len(durations)
            and durations[segment_index] is not None
            and not _is_missing(durations[segment_index])
        ]
        for driver, durations in durations_by_driver.items():
            if segment_index >= len(durations):
                continue
            value = durations[segment_index]
            if value is None or _is_missing(value):
                continue
            # Number of strictly faster values + one is competition rank and
            # naturally gives equal values the same rank.
            ranks[driver][segment_index] = 1 + sum(
                other < value for other in valid if other is not None
            )

    return ranks


def deltas_to_reference(
    durations_by_driver: Mapping[Driver, Sequence[MaybeNumeric]],
    reference_driver: Driver,
) -> dict[Driver, list[MaybeNumeric]]:
    """Return each driver's per-segment delta from ``reference_driver``.

    A delta is ``driver_duration - reference_duration``: positive means the
    driver is slower than the reference, and negative means faster.  If the
    reference driver or either duration is missing, the corresponding delta
    is ``None``.  The output retains each driver's sequence length and mapping
    order, including the reference driver's all-zero deltas where available.
    """

    if not durations_by_driver:
        return {}

    reference = durations_by_driver.get(reference_driver)
    return {
        driver: [
            (
                None
                if reference is None
                or index >= len(reference)
                or duration is None
                or reference[index] is None
                or _is_missing(duration)
                or _is_missing(reference[index])
                else duration - reference[index]
            )
            for index, duration in enumerate(durations)
        ]
        for driver, durations in durations_by_driver.items()
    }


# Descriptive aliases make the implementation easy to discover without
# creating a second calculation path.
derive_segment_durations = segment_durations
compute_segment_durations = segment_durations
delta_to_reference = deltas_to_reference


def interpolate_boundary_times(
    distances: Sequence[float],
    times: Sequence[float],
    boundaries: Sequence[float],
) -> list[float | None]:
    """Interpolate elapsed seconds at boundaries inside ordered observations.

    Reject the whole series on missing/nonfinite data, duplicate or
    decreasing distance, or decreasing time. Do not sort, drop samples, or
    extrapolate: boundaries outside ``[distances[0], distances[-1]]`` are
    ``None``. At least two samples are needed, including for exact endpoint
    matches. Equal times are allowed; equal distances are not.
    """
    missing = [None] * len(boundaries)
    if len(distances) < 2 or len(distances) != len(times):
        return missing
    sample_distances = np.array(distances, dtype=float)
    sample_times = np.array(times, dtype=float)
    if (not np.all(np.isfinite(sample_distances)) or not np.all(np.isfinite(sample_times))
            or np.any(np.diff(sample_distances) <= 0) or np.any(np.diff(sample_times) < 0)):
        return missing
    return [
        float(np.interp(distance, sample_distances, sample_times))
        if math.isfinite(distance) and sample_distances[0] <= distance <= sample_distances[-1]
        else None
        for distance in boundaries
    ]
