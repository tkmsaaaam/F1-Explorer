from unittest.mock import MagicMock

import pandas as pd
import pytest

import analyze_practice
import analyze_qualifying


@pytest.mark.parametrize("loader", [analyze_practice._circuit_info_or_none, analyze_qualifying._circuit_info_or_none])
def test_circuit_info_failure_is_non_fatal(loader):
    session = MagicMock()
    session.get_circuit_info.side_effect = AttributeError("add_marker_distance")
    log = MagicMock()

    assert loader(session, log) is None
    log.warning.assert_called_once()


@pytest.mark.parametrize("error", [ConnectionError("offline"), RuntimeError("invalid map")])
def test_circuit_dependent_charts_skip_when_metadata_fails(error):
    from f1_explorer.visualizations import race, short_runs

    session = MagicMock()
    session.get_circuit_info.side_effect = error
    log = MagicMock()
    race.speed_until_turn1(log, "unused.png", session)
    short_runs.plot_speed_distance(session, log)
    assert log.warning.call_count >= 2


def test_optional_circuit_metadata_preserves_telemetry_figure():
    from f1_explorer.visualizations.qualifying_telemetry import make_telemetry_comparison

    session = MagicMock()
    session.laps.pick_quicklaps.return_value.empty = True
    session.get_circuit_info.side_effect = ConnectionError("offline")
    figure = make_telemetry_comparison(session)
    assert figure.layout.xaxis.title.text == "Distance [m]"
    session.get_circuit_info.assert_called_once()


@pytest.mark.parametrize("entrypoint", [analyze_practice, analyze_qualifying])
@pytest.mark.parametrize("telemetry", [
    None,
    pd.DataFrame(),
    pd.DataFrame({"Time": [0, 1]}),
    pd.DataFrame({"Distance": [float("nan"), float("inf")]}),
    pd.DataFrame({"Distance": [0, 0]}),
])
def test_entrypoint_skips_fastest_lap_circuit_plots_without_valid_distance(entrypoint, telemetry):
    log = MagicMock()

    assert entrypoint._fastest_distance_or_none(telemetry, log) is None
    log.warning.assert_called_once()


@pytest.mark.parametrize("entrypoint", [analyze_practice, analyze_qualifying])
def test_entrypoint_uses_last_finite_positive_distance(entrypoint):
    telemetry = pd.DataFrame({"Distance": [0, 500, float("nan"), 1234]})

    assert entrypoint._fastest_distance_or_none(telemetry, MagicMock()) == 1234
