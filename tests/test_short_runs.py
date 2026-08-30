"""Tests for short-run track visualizations."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import pandas as pd

from visualizations.short_runs import plot_speed_on_track


def test_speed_on_track_uses_colored_line_collection_and_vertical_colorbar() -> None:
    telemetry = pd.DataFrame(
        {
            "X": [0.0, 10.0, 20.0],
            "Y": [0.0, 5.0, 0.0],
            "Speed": [100.0, 150.0, 120.0],
        }
    )
    lap = SimpleNamespace(
        Driver="VER",
        get_telemetry=lambda: telemetry,
    )
    selection = MagicMock()
    selection.pick_fastest.return_value = lap
    laps = MagicMock()
    laps.pick_drivers.return_value = selection
    session = SimpleNamespace(
        drivers=["1"],
        laps=laps,
        event=SimpleNamespace(year=2026, RoundNumber=1, Location="Test"),
        name="Qualifying",
    )

    with patch("visualizations.short_runs.save_matplotlib") as save:
        plot_speed_on_track(session, MagicMock(), output_dir=Path("plots"))

    figure = save.call_args.args[0]
    try:
        assert any(isinstance(collection, LineCollection) for collection in figure.axes[0].collections)
        assert len(figure.axes) == 2
        assert figure.axes[1].get_ylabel() == "Speed"
    finally:
        plt.close(figure)
