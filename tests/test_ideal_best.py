"""Characterize the selected laps and NaT behavior of both ideal-best figures."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastf1.core import Laps

from f1_explorer.visualizations import short_runs


def _laps():
    return Laps(pd.DataFrame({
        'DriverNumber': ['1', '1', '1', '2'],
        'Driver': ['AAA', 'AAA', 'AAA', 'BBB'],
        'Team': ['Team A', 'Team A', 'Team A', 'Team B'],
        'LapNumber': [1, 2, 3, 1],
        'IsAccurate': [True, True, False, True],
        'IsPersonalBest': [True, True, True, True],
        'LapTime': pd.to_timedelta([90, 90, 60, 95], unit='s'),
        'Sector1Time': pd.to_timedelta([29, 31, 20, 30], unit='s'),
        'Sector2Time': pd.to_timedelta([30, 28, 20, 32], unit='s'),
        'Sector3Time': pd.to_timedelta([33, 31, 20, 33], unit='s'),
    }))


def _figures(laps):
    session = SimpleNamespace(laps=laps, drivers=['2', '1'])
    result = []
    with patch.object(short_runs, 'save_plotly', side_effect=lambda figure, *args, **kwargs:
                      result.append(json.loads(figure.to_json()))), \
         patch.object(short_runs.fastf1.plotting, 'get_team_color', return_value='blue'):
        short_runs.plot_ideal_best(session, MagicMock(), output_dir='unused')
        short_runs.plot_ideal_best_diff(session, MagicMock(), output_dir='unused')
    return result


def test_sector_minima_can_come_from_different_laps_and_preserve_driver_order():
    figures = _figures(_laps())
    assert [trace['name'] for trace in figures[0]['data']] == ['BBB', 'AAA']
    assert [(trace['x'], trace['y']) for trace in figures[0]['data']] == [([95.0], [95.0]), ([90.0], [88.0])]
    assert [(trace['x'], trace['y']) for trace in figures[1]['data']] == [([0.0], [95.0]), ([-2.0], [88.0])]


@pytest.mark.parametrize('row, expected_ideal, expected_delta', [(0, None, None), (1, 88.0, -2.0)])
def test_nat_sector_keeps_python_min_order_behavior(row, expected_ideal, expected_delta):
    laps = _laps()
    laps.loc[row, 'Sector1Time'] = pd.NaT
    figures = _figures(laps)
    assert figures[0]['data'][1]['y'] == [expected_ideal]
    assert figures[1]['data'][1]['y'] == [expected_ideal]
    assert figures[1]['data'][1]['x'] == [expected_delta]


@pytest.mark.parametrize('condition', ['empty', 'no_fastest', 'inaccurate'])
def test_unavailable_driver_points_stay_absent(condition):
    laps = _laps()
    if condition == 'empty':
        laps = laps.iloc[0:0]
    elif condition == 'no_fastest':
        laps['IsPersonalBest'] = False
    else:
        laps['IsAccurate'] = False
    figures = _figures(laps)
    assert [figure['data'] for figure in figures] == [[], []]
