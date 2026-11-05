from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from f1_explorer.visualizations.qualifying_telemetry import make_telemetry_comparison


def make_session():
    frames = []
    laps = []
    for number in (1, 2):
        frame = pd.DataFrame({
            "Distance": [0., 10., 10., 20., np.nan],
            "Time": pd.to_timedelta([0, number, number, 2 * number, 3], unit="s"),
            "Speed": [100., np.nan, 120., 130., 140.],
            "Throttle": [100., 90., 80., 70., 60.],
            "Brake": [False, False, True, False, False],
            "nGear": [3., 4., 4., 5., 6.],
        })
        data = Mock()
        data.add_distance.return_value = frame
        lap = SimpleNamespace(
            Driver=f"D{number}", Team="Team", LapTime=timedelta(seconds=number * 2), empty=False,
            get_car_data=Mock(return_value=data),
        )
        frames.append(frame)
        laps.append(lap)
    session = SimpleNamespace(
        event=SimpleNamespace(year=2026),
        drivers=["2", "1"],
        laps=SimpleNamespace(pick_drivers=lambda number: SimpleNamespace(
            pick_fastest=lambda: laps[int(number) - 1])),
    )
    return session, laps, frames


def build(session):
    with patch("fastf1.plotting.get_team_color", return_value="gray"):
        return make_telemetry_comparison(session)


def test_reuses_car_data_preserving_values_and_input():
    session, laps, frames = make_session()
    originals = [frame.copy(deep=True) for frame in frames]
    figure = build(session)
    assert len(figure.data) == 10
    np.testing.assert_allclose(figure.data[0].x, [0, 5, 10, 15])
    np.testing.assert_allclose(figure.data[0].y, [0, 0, 0, 0])
    np.testing.assert_allclose(figure.data[5].y, [0, .5, 1, 1.5])
    for offset in (0, 5):
        np.testing.assert_allclose(figure.data[offset + 1].x, [0, 10, 20])
        np.testing.assert_allclose(figure.data[offset + 1].y, [100, 120, 130])
        np.testing.assert_allclose(figure.data[offset + 2].y, [100, 90, 80, 70])
        np.testing.assert_allclose(figure.data[offset + 3].y, [0, 0, 1, 0])
        np.testing.assert_allclose(figure.data[offset + 4].y, [3, 4, 4, 5])
        assert figure.data[offset + 4].line.shape == "hv"
    for lap, frame, original in zip(laps, frames, originals):
        lap.get_car_data.assert_called_once_with()
        lap.get_car_data.return_value.add_distance.assert_called_once_with()
        pd.testing.assert_frame_equal(frame, original)
    build(session)
    assert all(lap.get_car_data.call_count == 2 for lap in laps)


@pytest.mark.parametrize("missing", ["Time", "Speed", "Throttle", "Brake", "nGear"])
def test_missing_channel_only_omits_its_tab(missing):
    session, _, frames = make_session()
    frames[1].drop(columns=missing, inplace=True)
    figure = build(session)
    assert len(figure.data) == 9
    buttons = figure.layout.updatemenus[0].buttons
    missing_index = ["Time", "Speed", "Throttle", "Brake", "nGear"].index(missing)
    assert [sum(button.args[0]["visible"]) for button in buttons] == [
        1 if i == missing_index else 2 for i in range(5)
    ]


@pytest.mark.parametrize("failure", ["error", "empty"])
def test_unavailable_telemetry_is_not_retried(failure):
    session, laps, frames = make_session()
    if failure == "error":
        laps[1].get_car_data.side_effect = ValueError("unavailable")
    else:
        frames[1].drop(index=frames[1].index, inplace=True)
    assert len(build(session).data) == 5
    laps[1].get_car_data.assert_called_once_with()


def test_circuit_fetch_failure_keeps_telemetry_series():
    session, _, _ = make_session()
    session.get_circuit_info = Mock(side_effect=ConnectionError("map unavailable"))
    figure = build(session)
    assert len(figure.data) == 10
    assert len(figure.layout.annotations or ()) == 0
    session.get_circuit_info.assert_called_once_with()


def test_telemetry_includes_slow_personal_fastest_lap_in_every_available_tab():
    session, laps, _ = make_session()
    laps[0].LapTime = timedelta(seconds=90)
    laps[1].LapTime = timedelta(seconds=180)
    figure = build(session)
    for tab_index in range(5):
        assert [trace.name for trace in tab_traces(figure, tab_index)] == ['D1', 'D2']


@pytest.mark.parametrize('invalid_time', [pd.NaT, pd.Timedelta(0, unit='s'), pd.Timedelta(-1, unit='s')])
def test_telemetry_excludes_driver_without_valid_personal_fastest(invalid_time):
    session, laps, _ = make_session()
    laps[1].LapTime = invalid_time
    figure = build(session)
    for tab_index in range(5):
        assert [trace.name for trace in tab_traces(figure, tab_index)] == ['D1']
    laps[1].get_car_data.assert_not_called()


def test_missing_reference_car_data_does_not_promote_a_slower_driver():
    session, laps, _ = make_session()
    laps[0].get_car_data.side_effect = ValueError('unavailable')
    figure = build(session)
    assert tab_traces(figure, 0) == []
    for tab_index in range(1, 5):
        assert [trace.name for trace in tab_traces(figure, tab_index)] == ['D2']


def replace_car_data(lap, distances, seconds):
    frame = pd.DataFrame({
        "Distance": distances,
        "Time": pd.to_timedelta(seconds, unit="s"),
        "Speed": 100., "Throttle": 80., "Brake": False, "nGear": 4.,
    })
    lap.get_car_data.return_value.add_distance.return_value = frame
    return frame


def tab_traces(figure, tab_index):
    visible = figure.layout.updatemenus[0].buttons[tab_index].args[0]["visible"]
    return [trace for trace, selected in zip(figure.data, visible) if selected]


@pytest.mark.parametrize(("reference_distances", "comparison_distances"), [
    ([0., 100.], [20., 80.]),
    ([20., 80.], [0., 100.]),
    ([10., 90.], [20., 80.]),
    ([20., 100.], [0., 80.]),
])
def test_delta_only_uses_shared_measured_range(reference_distances, comparison_distances):
    session, laps, _ = make_session()
    replace_car_data(laps[0], reference_distances, np.asarray(reference_distances) / 10 + .25)
    replace_car_data(laps[1], comparison_distances, np.asarray(comparison_distances) / 5 + 1.5)
    figure = build(session)
    reference, comparison = tab_traces(figure, 0)
    grid = np.arange(0., max(reference_distances), 5.)
    np.testing.assert_array_equal(comparison.x, grid)
    low = max(min(reference_distances), min(comparison_distances))
    high = min(max(reference_distances), max(comparison_distances))
    for distance, value in zip(grid, comparison.y):
        if low <= distance <= high:
            # Keep measured time origins; do not force the lap endpoints to agree.
            assert value == pytest.approx(distance / 10 + 1.25)
        else:
            assert value is None
    for distance, value in zip(grid, reference.y):
        assert value == (0. if min(reference_distances) <= distance <= max(reference_distances) else None)
    assert comparison.connectgaps is False
    assert len(tab_traces(figure, 1)) == 2
    serialized = json.loads(figure.to_json())
    assert serialized["data"][5]["y"] == list(comparison.y)


def test_delta_duplicate_distance_keeps_first_sample_before_checking_progress():
    session, laps, _ = make_session()
    replace_car_data(laps[0], [0., 100.], [0., 10.])
    frame = replace_car_data(laps[1], [0., 50., 50., 100.], [1., 11., 200., 21.])
    original = frame.copy(deep=True)
    reference, comparison = tab_traces(build(session), 0)
    np.testing.assert_allclose(reference.y, np.zeros(20))
    np.testing.assert_allclose(comparison.y, np.arange(0., 100., 5.) / 10 + 1)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("invalid_driver", [0, 1])
@pytest.mark.parametrize(("distances", "seconds"), [
    ([0., 60., 40., 100.], [0., 6., 7., 10.]),
    ([100., 50., 0.], [0., 5., 10.]),
    ([0., 50., 100.], [0., 10., 5.]),
])
def test_backward_progress_only_omits_delta(invalid_driver, distances, seconds):
    session, laps, _ = make_session()
    replace_car_data(laps[0], [0., 100.], [0., 10.])
    replace_car_data(laps[1], [0., 100.], [0., 20.])
    frame = replace_car_data(laps[invalid_driver], distances, seconds)
    original = frame.copy(deep=True)
    figure = build(session)
    deltas = tab_traces(figure, 0)
    # An invalid reference never falls back to a slower driver's telemetry.
    assert [trace.name for trace in deltas] == ([] if invalid_driver == 0 else ["D1"])
    for tab_index in range(1, 5):
        assert [trace.name for trace in tab_traces(figure, tab_index)] == ["D1", "D2"]
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.filterwarnings("error::RuntimeWarning")
def test_delta_filters_nonfinite_distance_and_time_samples():
    session, laps, _ = make_session()
    replace_car_data(laps[0], [0., 100.], [0., 10.])
    frame = replace_car_data(
        laps[1], [0., np.nan, 20., 40., 60., 80., 100., np.inf, -np.inf],
        [1., 3., np.nan, 9., 13., 17., 21., 23., 25.],
    )
    original = frame.copy(deep=True)
    _, comparison = tab_traces(build(session), 0)
    np.testing.assert_allclose(comparison.y, np.arange(0., 100., 5.) / 10 + 1)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize(("distances", "seconds"), [
    ([21., 24.], [0., 1.]),  # No common grid points.
    ([20., 24.], [0., 1.]),  # One common grid point.
    ([100., 120.], [0., 1.]),  # Beyond the reference grid.
    ([0., 0.], [0., 1.]),  # One unique distance.
    ([0., 100.], [np.nan, np.nan]),
    ([0., 100.], [np.nan, 1.]),
    ([np.nan, np.inf], [0., 1.]),
])
def test_insufficient_comparable_points_only_omit_delta(distances, seconds):
    session, laps, _ = make_session()
    replace_car_data(laps[0], [0., 100.], [0., 10.])
    replace_car_data(laps[1], distances, seconds)
    figure = build(session)
    assert [trace.name for trace in tab_traces(figure, 0)] == ["D1"]
    for tab_index in range(1, 5):
        expected = ["D1"] if not np.isfinite(distances).any() else ["D1", "D2"]
        assert [trace.name for trace in tab_traces(figure, tab_index)] == expected


def test_equal_time_samples_are_not_backward_progress():
    session, laps, _ = make_session()
    replace_car_data(laps[0], [0., 100.], [0., 10.])
    replace_car_data(laps[1], [0., 50., 100.], [0., 0., 10.])
    _, comparison = tab_traces(build(session), 0)
    assert comparison.y[10] == -5.


def test_missing_reference_time_does_not_change_reference_driver():
    session, _, frames = make_session()
    frames[0].drop(columns="Time", inplace=True)
    figure = build(session)
    assert tab_traces(figure, 0) == []
    for tab_index in range(1, 5):
        assert len(tab_traces(figure, tab_index)) == 2


def test_no_delta_series_falls_back_to_first_available_tab():
    session, laps, _ = make_session()
    replace_car_data(laps[0], [100., 50., 0.], [0., 5., 10.])  # Backward reference.
    replace_car_data(laps[1], [0., 100.], [0., 20.])
    figure = build(session)
    assert figure.layout.title.text == "速度"
    assert figure.layout.yaxis.title.text == "Speed [km/h]"
    assert [trace.name for trace in figure.data if trace.visible] == ["D1", "D2"]


def build_track_map(frames=None):
    from f1_explorer.visualizations.qualifying_telemetry import make_track_map_comparison

    session, laps, default_frames = make_session()
    if frames is None:
        frames = default_frames
    for frame in frames:
        if "X" not in frame:
            frame["X"] = [0., 1., 2., 3., np.nan][:len(frame)]
        if "Y" not in frame:
            frame["Y"] = [0., 2., 1., 0., 1.][:len(frame)]
    with patch("f1_explorer.visualizations.qualifying_telemetry.lap_telemetry_without_driver_ahead",
                  side_effect=lambda lap: frames[laps.index(lap)]), \
            patch("fastf1.plotting.get_team_color", return_value="gray"):
        return make_track_map_comparison(session)


def test_track_map_initially_shows_only_first_speed_driver():
    figure = build_track_map()
    assert len(figure.data) == 4
    assert [trace.meta for trace in figure.data if trace.visible] == [
        {"driverNumber": "1", "metric": "Speed"}]
    assert figure.layout.title.text == "速度 — D1"
    assert figure.layout.meta["selectedDriver"] == "1"
    for menu in figure.layout.updatemenus:
        assert all(button.execute is False for button in menu.buttons)
    speed = figure.data[0]
    np.testing.assert_allclose(speed.x, [0, 2, 3])
    np.testing.assert_allclose(speed.customdata, [100, 120, 130])
    assert figure.data[1].marker.colorbar.tickvals == tuple(range(1, 9))


@pytest.mark.filterwarnings("error::RuntimeWarning")
@pytest.mark.parametrize("missing", ["Speed", "nGear", "all", "coordinates", "empty"])
def test_track_map_missing_channels_are_independent(missing):
    _, _, frames = make_session()
    if missing in ("Speed", "nGear"):
        frames[0].drop(columns=missing, inplace=True)
        frames[1][missing] = np.nan
    elif missing == "all":
        for frame in frames:
            frame[["Speed", "nGear"]] = np.nan
    elif missing == "coordinates":
        for frame in frames:
            frame["X"] = np.inf
    elif missing == "empty":
        for frame in frames:
            frame.drop(index=frame.index, inplace=True)
    figure = build_track_map(frames)
    if missing == "nGear":
        assert [trace.meta["metric"] for trace in figure.data] == ["Speed", "Speed"]
        assert sum(bool(trace.visible) for trace in figure.data) == 1
    else:
        assert not any(trace.visible for trace in figure.data)
        assert figure.layout.title.text == "速度 — 有効なデータなし"
        assert len(figure.layout.updatemenus[1].buttons) == 0
        assert len(figure.data) == (2 if missing == "Speed" else 0)


def test_track_map_initial_driver_skips_missing_speed():
    _, _, frames = make_session()
    frames[0]["Speed"] = np.nan
    figure = build_track_map(frames)
    assert [trace.meta for trace in figure.data if trace.visible] == [
        {"driverNumber": "2", "metric": "Speed"}]
    assert figure.layout.title.text == "速度 — D2"


def test_track_map_includes_slow_driver_and_uses_fastest_lap_order():
    from f1_explorer.visualizations.qualifying_telemetry import make_track_map_comparison

    session, laps, frames = make_session()
    laps[0].LapTime = timedelta(seconds=90)
    laps[1].LapTime = timedelta(seconds=180)
    for frame in frames:
        frame['X'] = frame['Distance']
        frame['Y'] = 0.
    with patch('fastf1.plotting.get_team_color', return_value='gray'), \
            patch('f1_explorer.visualizations.qualifying_telemetry.lap_telemetry_without_driver_ahead',
                  side_effect=lambda lap: frames[laps.index(lap)]):
        figure = make_track_map_comparison(session)
    assert figure.layout.meta['drivers'] == [
        {'number': '1', 'label': 'D1'}, {'number': '2', 'label': 'D2'}]
    assert [trace.meta for trace in figure.data] == [
        {'driverNumber': number, 'metric': metric}
        for number in ['1', '2'] for metric in ['Speed', 'nGear']]


def test_track_map_excludes_driver_without_a_fastest_lap():
    from f1_explorer.visualizations.qualifying_telemetry import make_track_map_comparison

    session, laps, frames = make_session()
    laps[1].empty = True
    frames[0]['X'] = frames[0]['Distance']
    frames[0]['Y'] = 0.
    with patch('fastf1.plotting.get_team_color', return_value='gray'), \
            patch('f1_explorer.visualizations.qualifying_telemetry.lap_telemetry_without_driver_ahead',
                  return_value=frames[0]) as get_telemetry:
        figure = make_track_map_comparison(session)
    get_telemetry.assert_called_once_with(laps[0])
    assert figure.layout.meta['drivers'] == [{'number': '1', 'label': 'D1'}]
