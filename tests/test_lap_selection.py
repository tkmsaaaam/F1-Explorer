"""Personal fastest-lap selection retains FastF1's selection contract."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastf1.core import Lap, Laps
import pandas as pd
import pytest

from f1_explorer.visualizations.lap_selection import fastest_laps_by_driver


def test_all_drivers_are_selected_by_personal_fastest_time_without_quicklap_cutoff():
    laps = Laps({
        'DriverNumber': ['3', '2', '10', '1', '4', '5'],
        'Driver': ['D3', 'D2', 'D10', 'D1', 'D4', 'D5'],
        'LapTime': pd.to_timedelta([180, 100, 100, 90, 80, None], unit='s'),
        'IsPersonalBest': [True, True, True, True, False, True],
    })
    original = laps.copy(deep=True)
    session = SimpleNamespace(drivers=['3', 2, '10', '1', '4', '5', '6'], laps=laps)
    assert '3' not in set(laps.pick_quicklaps().DriverNumber)
    with patch.object(Laps, 'pick_quicklaps', side_effect=AssertionError('must not filter')):
        selected = fastest_laps_by_driver(session)
    assert list(selected) == ['1', '10', '2', '3']
    assert all(isinstance(lap, Lap) for lap in selected.values())
    assert selected['3'].LapTime == pd.Timedelta(180, unit='s')
    pd.testing.assert_frame_equal(laps, original)


def test_fastf1_personal_best_rules_are_preserved_without_extra_accuracy_filter():
    laps = Laps({
        'DriverNumber': ['1', '1', '1', '2'],
        'Driver': ['D1', 'D1', 'D1', 'D2'],
        'LapNumber': [1, 2, 3, 1],
        'LapTime': pd.to_timedelta([60, 90, 95, 100], unit='s'),
        'IsPersonalBest': [False, True, True, False],
        'Deleted': [True, False, False, False],
        'IsAccurate': [True, False, True, True],
    })
    selected = fastest_laps_by_driver(SimpleNamespace(drivers=['2', '1'], laps=laps))
    assert list(selected) == ['1']
    assert selected['1'].LapNumber == 2
    assert selected['1'].LapTime == pd.Timedelta(90, unit='s')


@pytest.mark.parametrize('lap', [
    None,
    Lap(),
    Lap({'DriverNumber': '1', 'LapTime': pd.NaT}),
    Lap({'DriverNumber': '1', 'LapTime': pd.Timedelta(0, unit='s')}),
    Lap({'DriverNumber': '1', 'LapTime': pd.Timedelta(-1, unit='s')}),
    Lap({'DriverNumber': '1', 'LapTime': None}),
    SimpleNamespace(empty=False, LapTime=SimpleNamespace(total_seconds=lambda: float('inf'))),
    SimpleNamespace(empty=False, LapTime=SimpleNamespace(total_seconds=lambda: float('nan'))),
    SimpleNamespace(empty=False),
])
def test_unavailable_fastest_laps_are_excluded(lap):
    selection = Mock()
    selection.pick_fastest.return_value = lap
    session = SimpleNamespace(drivers=['1'], laps=SimpleNamespace(pick_drivers=Mock(return_value=selection)))
    assert fastest_laps_by_driver(session) == {}
    selection.pick_fastest.assert_called_once_with()


def test_selected_lap_is_returned_without_copy_or_telemetry_access():
    lap = Lap({'DriverNumber': '1', 'LapTime': pd.Timedelta(90, unit='s')})
    selection = Mock()
    selection.pick_fastest.return_value = lap
    session = SimpleNamespace(drivers=['1'], laps=SimpleNamespace(pick_drivers=Mock(return_value=selection)))
    selected = fastest_laps_by_driver(session)
    assert selected['1'] is lap


def test_one_unavailable_driver_does_not_hide_others():
    lap = Lap({'DriverNumber': '2', 'LapTime': pd.Timedelta(90, unit='s')})
    selection = Mock()
    selection.pick_fastest.side_effect = [ValueError('missing'), lap]
    session = SimpleNamespace(drivers=['1', '2'], laps=SimpleNamespace(pick_drivers=Mock(return_value=selection)))
    assert fastest_laps_by_driver(session) == {'2': lap}


def test_empty_session_has_no_personal_fastest_laps():
    assert fastest_laps_by_driver(SimpleNamespace(drivers=[], laps=Laps())) == {}
