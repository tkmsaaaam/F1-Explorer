"""Shared raw-car samples keep the two boundary tables numerically identical."""
import json
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from f1_explorer.visualizations import segment_analysis
from f1_explorer.visualizations.segment_metrics import (
    interpolate_boundary_times,
    rank_segment_durations,
    segment_durations,
)


def _session(*, no_reference=False):
    samples = pd.DataFrame({
        # Ordered raw observations include exact matches and out-of-range boundaries.
        'Distance': [0.0, 50.0, 100.0, 150.0],
        'Time': pd.to_timedelta([0, 1, 2, 3], unit='s'),
    })
    empty = samples.iloc[0:0].copy()
    laps = {}
    for number, data in [('2', samples), ('1', samples.copy()), ('3', empty)]:
        lap = MagicMock()
        lap.empty = False
        lap.DriverNumber = number
        lap.LapTime = pd.Timedelta({'1': 90, '2': 100, '3': 180}[number], unit='s')
        lap.get_car_data.return_value.add_distance.return_value = data
        laps[number] = lap
    absent = MagicMock()
    absent.empty = True
    laps['4'] = None
    laps['5'] = absent
    session = MagicMock()
    session.drivers = ['2', '1', '3', '4', '5']
    session.laps.pick_drivers.side_effect = lambda number: MagicMock(
        pick_fastest=MagicMock(return_value=laps[number]))
    session.laps.pick_quicklaps.side_effect = AssertionError('No session-wide cutoff for segment tables')
    session.laps.pick_fastest.return_value = None if no_reference else laps['1']
    session.get_circuit_info.return_value.corners = pd.DataFrame({
        'Distance': [50.0, 100.0], 'Number': [1, 2],
    })
    session.get_driver.side_effect = lambda number: MagicMock(Abbreviation=f'D{number}')
    return session, laps


def _tables(session, **kwargs):
    captured = []
    def save(figures, paths, *args, **settings):
        captured.extend((path, json.loads(figure.to_json())) for figure, path in zip(figures, paths))
    with patch.object(segment_analysis, 'save_plotly_batch', side_effect=save):
        for name, boundaries in [('corners', [0.0, 50.0, 100.0, 200.0]),
                                 ('mini_segments', [0.0, 25.0, 75.0, 125.0, 200.0])]:
            segment_analysis.compute_and_save_segment_tables_plotly(
                session, name, boundaries, MagicMock(), **kwargs)
    return captured


@pytest.mark.parametrize('no_reference', [False, True])
def test_shared_samples_match_standalone_tables_and_reduce_reads(no_reference):
    session, laps = _session(no_reference=no_reference)
    unshared = _tables(session)
    assert [laps[number].get_car_data.call_count for number in ['2', '1', '3']] == [2, 2, 2]
    for lap in laps.values():
        if lap is not None:
            lap.get_car_data.reset_mock()
    samples = segment_analysis.prepare_segment_car_data(session)
    originals = {number: data.copy(deep=True) for number, data in samples.items()}
    assert list(samples) == ['1', '2', '3']
    assert samples['3'].empty  # A valid lap with empty telemetry remains present.
    shared = _tables(session, car_data_by_driver=dict(reversed(list(samples.items()))))
    assert shared == unshared
    assert len(shared) == (4 if no_reference else 6)
    assert [laps[number].get_car_data.call_count for number in ['2', '1', '3']] == [1, 1, 1]
    assert laps['5'].get_car_data.call_count == 0
    for number, original in originals.items():
        pd.testing.assert_frame_equal(samples[number], original)
    duration = shared[0][1]['data'][0]['cells']['values']
    # Column order comes from personal fastest laps, independent of mapping insertion order.
    assert shared[0][1]['data'][0]['header']['values'][3:] == ['D1', 'D2', 'D3']
    assert duration[3] == [1.0, 1.0, None]
    assert duration[5] == [None, None, None]
    ranks = shared[1][1]['data'][0]['cells']['values']
    assert ranks[2] == ranks[3] == [1, 1, None]


def test_empty_mapping_does_not_fetch_missing_drivers():
    session, laps = _session(no_reference=True)
    _tables(session, car_data_by_driver={})
    for lap in laps.values():
        if lap is not None:
            lap.get_car_data.assert_not_called()


def test_slow_driver_remains_in_all_three_tables_with_measured_values():
    session, laps = _session()
    slow_data = laps['1'].get_car_data.return_value.add_distance.return_value.copy(deep=True)
    slow_data['Time'] *= 2
    laps['3'].get_car_data.return_value.add_distance.return_value = slow_data
    tables = _tables(session)
    for path, figure in tables:
        table = figure['data'][0]
        assert table['header']['values'][-3:] == ['D1', 'D2', 'D3']
        if path == 'corners_durations.png':
            assert table['cells']['values'][-1] == [2., 2., None]
        elif path == 'corners_ranks.png':
            assert table['cells']['values'][-1] == [3, 3, None]
        elif path == 'corners_gaps_to_best.png':
            assert table['cells']['values'][-1] == [1., 1., None]


def test_table_columns_break_equal_lap_time_ties_by_driver_number_text():
    session, laps = _session()
    laps['10'] = laps.pop('3')
    laps['10'].DriverNumber = '10'
    laps['10'].LapTime = laps['2'].LapTime
    session.drivers = ['2', '10', '1', '4', '5']
    for _, figure in _tables(session):
        assert figure['data'][0]['header']['values'][-3:] == ['D1', 'D10', 'D2']


@pytest.mark.parametrize('failure', ['error', 'none', 'missing_columns'])
@pytest.mark.parametrize('driver', ['1', '2'])
def test_unavailable_car_samples_keep_driver_column_missing(failure, driver):
    session, laps = _session()
    if failure == 'error':
        laps[driver].get_car_data.side_effect = ValueError('unavailable')
    else:
        laps[driver].get_car_data.return_value.add_distance.return_value = (
            None if failure == 'none' else pd.DataFrame({'Speed': [100.]}))
    tables = _tables(session, color_by_corner_speed=(driver == '1'))
    for path, figure in tables:
        table = figure['data'][0]
        assert table['header']['values'][-3:] == ['D1', 'D2', 'D3']
        column = table['header']['values'].index('D' + driver)
        assert all(value is None for value in table['cells']['values'][column])
        if driver == '1':
            assert 'gaps_to_best' not in path


def test_no_valid_fastest_laps_produce_no_driver_columns():
    session, _ = _session(no_reference=True)
    session.laps.pick_drivers.side_effect = None
    session.laps.pick_drivers.return_value.pick_fastest.return_value = None
    for _, figure in _tables(session):
        headers = figure['data'][0]['header']['values']
        assert headers in (['segment', 'distance', 'corners'], ['segment', 'distance'])


def test_interpolation_recovers_known_speed_and_ranking():
    durations = {}
    for driver, speed, start, step in [('A', 50, 0, 60), ('B', 49.5, 3, 20)]:
        distance = np.arange(start, 304, step, dtype=float)
        data = pd.DataFrame({'Distance': distance, 'Time': pd.to_timedelta(distance / speed, unit='s')})
        durations[driver] = segment_durations(segment_analysis.segment_boundary_times(data, [0, 100, 200, 300]))
    assert durations['A'] == pytest.approx([2, 2, 2])
    assert durations['B'][0] is None
    assert durations['B'][1:] == pytest.approx([100 / 49.5] * 2)
    assert rank_segment_durations(durations)['A'][1] == 1


@pytest.mark.parametrize('model', ['constant', 'accelerating', 'decelerating'])
@pytest.mark.parametrize('step', [5, 20, 60])
@pytest.mark.parametrize('offset', [0, 3])
def test_interpolation_matches_aud12_analytic_fixtures(model, step, offset):
    functions = {
        'constant': lambda x: x / 50,
        'accelerating': lambda x: (np.sqrt(100 + 4 * x) - 10) / 2,
        'decelerating': lambda x: 10 - np.sqrt(100 - x / 4),
    }
    distance = np.arange(offset, 301, step, dtype=float)
    times = functions[model](distance)
    boundaries = np.array([0, 100, 200, 300], dtype=float)
    data = pd.DataFrame({'Distance': distance, 'Time': pd.to_timedelta(times, unit='s')})
    original = data.copy(deep=True)
    actual = segment_analysis.segment_boundary_times(data, boundaries)
    # The analytic truth values are the only oracle; the interpolation
    # residual grows with sample spacing, so the tolerance scales with it.
    truth = functions[model](boundaries)
    # The interpolation residual grows with sample spacing (measured AUD-12
    # worst case: ~0.082 at the coarsest grid); the tolerance scales with it.
    tolerance = 0.1 * 60 / step
    for i, boundary in enumerate(boundaries):
        if distance[0] <= boundary <= distance[-1]:
            assert actual[i] == pytest.approx(truth[i], abs=tolerance)
        else:
            assert actual[i] is None
    if offset == 0:
        assert actual[0] == 0
    pd.testing.assert_frame_equal(data, original)


@pytest.mark.parametrize('distance,times', [
    ([], []), ([0], [0]), ([0, 20, 10], [0, 1, 2]),
    ([0, 20, 20], [0, 1, 2]), ([0, float('nan'), 20], [0, 1, 2]),
    ([0, float('inf'), 20], [0, 1, 2]), ([0, 10, 20], [0, None, 2]),
    ([0, 10, 20], [0, 2, 1]),
])
def test_invalid_series_is_missing_without_repair(distance, times):
    data = pd.DataFrame({'Distance': distance, 'Time': pd.to_timedelta(times, unit='s')})
    assert segment_analysis.segment_boundary_times(data, [0, 10, 20]) == [None] * 3
    session, _ = _session()
    for _, figure in _tables(session, car_data_by_driver={'1': data}):
        assert all(v is None for v in figure['data'][0]['cells']['values'][
            figure['data'][0]['header']['values'].index('D1')])


def test_endpoint_matches_and_outside_boundaries_do_not_extrapolate():
    data = pd.DataFrame({'Distance': [10, 20], 'Time': pd.to_timedelta([1, 2], unit='s')})
    assert segment_analysis.segment_boundary_times(data, [0, 10, 15, 20, 30, float('nan')]) == [
        None, 1, 1.5, 2, None, None]
    # Equal timestamps are allowed; time must not decrease.
    data['Time'] = pd.to_timedelta([1, 1], unit='s')
    assert segment_analysis.segment_boundary_times(data, [10, 15, 20]) == [1, 1, 1]


def test_table_ranks_and_deltas_use_unrounded_durations_and_include_note():
    session, _ = _session()
    samples = {number: pd.DataFrame({'Distance': [0, 50, 100, 200],
                                   'Time': pd.to_timedelta([0, seconds, 2 * seconds, 4 * seconds], unit='s')})
               for number, seconds in [('1', 1.0004), ('2', 1.0001)]}
    tables = dict(_tables(session, car_data_by_driver=samples))
    for figure in tables.values():
        assert 'ミリ秒精度を保証しません' in figure['layout']['meta']['segmentTimingNote']
    assert tables['corners_durations.png']['data'][0]['cells']['values'][3][:2] == [1, 1]
    assert tables['corners_ranks.png']['data'][0]['cells']['values'][2][:2] == [2, 2]
    assert tables['corners_ranks.png']['data'][0]['cells']['values'][3][:2] == [1, 1]
    # Round after subtracting: round(1.0006 - 1.0004, 3) differs from subtracting rounded values.
    samples['2']['Time'] = pd.to_timedelta([0, 1.0006, 2.0012, 4.0024], unit='s')
    gaps = dict(_tables(session, car_data_by_driver=samples))['corners_gaps_to_best.png']
    assert gaps['data'][0]['cells']['values'][4][0] == 0.0


def test_interpolate_boundary_times_policy_holds_without_pandas():
    assert interpolate_boundary_times([0, 10], [0, 2], [5, 10, 20, float('nan')]) == [1, 2, None, None]
    assert interpolate_boundary_times([0, 10, 10], [0, 1, 2], [5]) == [None]  # duplicate distance
    assert interpolate_boundary_times([0, 10], [2, 0], [5]) == [None]  # decreasing time
    assert interpolate_boundary_times([0, 10], [0, 2], [5]) == [1]  # equal times stay valid
    assert interpolate_boundary_times([0], [0], [5]) == [None]  # single sample
    assert interpolate_boundary_times([0, 10], [0], [5]) == [None]  # mismatched lengths
