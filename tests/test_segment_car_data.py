"""Shared raw-car samples keep the two boundary tables numerically identical."""
import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from f1_explorer.visualizations import short_runs


def _session(*, no_reference=False):
    samples = pd.DataFrame({
        # Duplicate distance and an exactly matching boundary test strict <.
        'Distance': [0.0, 50.0, 50.0, 100.0, 150.0, float('nan')],
        'Time': pd.to_timedelta([0, 1, 2, 3, 4, None], unit='s'),
    })
    empty = samples.iloc[0:0].copy()
    laps = {}
    for number, data in [('2', samples), ('1', samples.copy()), ('3', empty)]:
        lap = MagicMock()
        lap.empty = False
        lap.DriverNumber = number
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
    quick = MagicMock()
    quick.sort_values.return_value = quick
    quick.DriverNumber = pd.Series(['1', '2', '3'])
    session.laps.pick_quicklaps.return_value = quick
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
    with patch.object(short_runs, 'save_plotly_batch', side_effect=save):
        for name, boundaries in [('corners', [0.0, 50.0, 100.0, 200.0]),
                                 ('mini_segments', [0.0, 25.0, 75.0, 125.0, 200.0])]:
            short_runs.compute_and_save_segment_tables_plotly(
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
    samples = short_runs.prepare_segment_car_data(session)
    originals = {number: data.copy(deep=True) for number, data in samples.items()}
    assert list(samples) == ['2', '1', '3']
    assert samples['3'].empty  # A valid lap with empty telemetry remains present.
    shared = _tables(session, car_data_by_driver=samples)
    assert shared == unshared
    assert len(shared) == (4 if no_reference else 6)
    assert [laps[number].get_car_data.call_count for number in ['2', '1', '3']] == [1, 1, 1]
    assert laps['5'].get_car_data.call_count == 0
    for number, original in originals.items():
        pd.testing.assert_frame_equal(samples[number], original)
    duration = shared[0][1]['data'][0]['cells']['values']
    # Column order comes from quick laps, independent of mapping insertion order.
    assert shared[0][1]['data'][0]['header']['values'][3:] == ['D1', 'D2', 'D3']
    assert duration[3] == [None, 2.0, 2.0]
    assert duration[5] == [None, None, None]
    ranks = shared[1][1]['data'][0]['cells']['values']
    assert ranks[2] == ranks[3] == [None, 1, 1]


def test_empty_mapping_does_not_fetch_missing_drivers():
    session, laps = _session(no_reference=True)
    _tables(session, car_data_by_driver={})
    for lap in laps.values():
        if lap is not None:
            lap.get_car_data.assert_not_called()
